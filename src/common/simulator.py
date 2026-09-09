"""The mechanistic simulation loop shared by A, B and C (Track 2).

This is the piece the source material does not have. In the senior's notebook a
"transmission" is one coin flip against a global average, so there is no path,
no relay, and nothing for a routing policy to decide. Here every packet is
walked hop by hop: each relay can be dead, out of range, out of energy, or
adversarial, and the predecessor watches whether it actually forwarded. That is
what makes trust measurable, gray-hole attacks expressible, and a routing
decision consequential.

A protocol plugs in by subclassing :class:`RoutingPolicy`. The loop guarantees
that every policy sees byte-identical topology, mobility, traffic, channel and
adversary streams for a given seed, so any difference in the results is
attributable to the policy alone.

One round is:

    move -> rebuild topology -> harvest/drain energy -> offer packets
    -> (policy picks a route) -> walk the route hop by hop -> watchdog
    -> policy feedback -> periodic PT_NID / PT_GID / PT_CREV control plane
"""

from dataclasses import dataclass, field

import numpy as np

from . import adversary, channel, config, energy as energy_mod, metrics as metrics_mod
from . import mobility, node as node_mod, seeding, topology, traffic
from ..routing import aodv, ecc, trust as trust_mod


@dataclass
class SimParams:
    """Every knob for one simulation run."""

    n_nodes: int = config.DEFAULT_NODES
    speed: float = config.DEFAULT_SPEED
    rounds: int = 400
    seed: int = 12345
    attack: str = "none"
    malicious_fraction: float = 0.0
    energy_model: str = "linear"
    traffic_mode: str = "flows"
    packets_per_round: int = config.PACKETS_PER_ROUND
    use_ecc: bool = True
    enable_control_plane: bool = True
    enable_slander: bool = True
    enable_energy_excuse: bool = True
    stop_when_dead: bool = True
    extra: dict = field(default_factory=dict)


class Simulation(object):
    """Owns the world; a :class:`RoutingPolicy` decides how packets move."""

    def __init__(self, policy, params):
        self.policy = policy
        self.params = params

        self.seeds = seeding.make_seed_bundle(params.seed)
        self.nodes = node_mod.NodeState(params.n_nodes, self.seeds.topology)
        mobility.assign_speeds(self.nodes, params.speed)

        self.energy_model = energy_mod.make_energy_model(params.energy_model)
        self.energy_model.reset(self.nodes, self.seeds.channel)

        self.malicious_ids = adversary.assign_roles(
            self.nodes, params.attack, params.malicious_fraction, self.seeds.adversary
        )

        self.keyring = ecc.ECCKeyring(params.n_nodes, enabled=params.use_ecc)
        self.route_cache = aodv.RouteCache()
        self.metrics = metrics_mod.RunMetrics(params.n_nodes)
        self.metrics._window_size = config.CMDP_WINDOW

        self.traffic = traffic.TrafficGenerator(
            self.nodes,
            self.seeds.traffic,
            mode=params.traffic_mode,
            packets_per_round=params.packets_per_round,
        )

        topology.rebuild(self.nodes)
        self.scores = aodv.route_scores(self.nodes)
        self.round_idx = 0

    # -- helpers exposed to policies ---------------------------------------

    def refresh_scores(self, trust=None, energy=None):
        """Recompute per-node route scores, optionally from a policy's view."""
        self.scores = aodv.route_scores(self.nodes, trust=trust, energy=energy)
        return self.scores

    def discover(self, src, dst, mode=aodv.MODE_EAURP, use_cache=True):
        """Route discovery with caching and RERR-style invalidation."""
        if use_cache:
            cached = self.route_cache.get(self.nodes, src, dst)
            if cached is not None:
                return cached

        path = aodv.find_route(self.nodes, src, dst, self.scores, mode=mode)
        self.metrics.record_discovery(path is not None)
        if path is not None and use_cache:
            self.route_cache.put(src, dst, path)
        return path

    # -- the per-packet forwarding walk ------------------------------------

    def forward(self, packet, path):
        """Walk ``path`` hop by hop.

        Returns ``(delivered, delay_ms, hops_completed, reason)``. ``reason`` is
        ``None`` on success, otherwise one of the ``metrics.LOSS_*`` constants.
        """
        nodes = self.nodes
        rng_channel = self.seeds.channel
        rng_adv = self.seeds.adversary

        if self.params.use_ecc:
            # Payload confidentiality is end-to-end (base.pdf 3.9), so it is
            # applied once at the source, not at every hop.
            self.keyring.encrypt(packet.src, packet.dst, b"\x00" * min(packet.size, 256))

        delay = channel.base_delay(rng_channel)
        hops_done = 0

        for index in range(len(path) - 1):
            sender = int(path[index])
            receiver = int(path[index + 1])

            if not nodes.alive[receiver] or nodes.revoked[receiver]:
                return False, delay, hops_done, metrics_mod.LOSS_DEAD_NODE
            if not nodes.adjacency[sender, receiver]:
                return False, delay, hops_done, metrics_mod.LOSS_LINK

            spent = channel.spend_hop_energy(
                nodes, sender, receiver, packet.size, self.energy_model
            )
            self.metrics.energy_spent += spent

            if not channel.transmit(nodes, sender, receiver, rng_channel):
                return False, delay, hops_done, metrics_mod.LOSS_LINK

            hop_ms = channel.hop_delay(rng_channel)
            delay += hop_ms
            hops_done += 1

            if receiver == int(packet.dst):
                return True, delay, hops_done, None

            # The relay now decides whether to forward, and the node that just
            # handed it the packet watches (base.pdf 3.6 promiscuous monitoring).
            relays = adversary.forwards_data(nodes, receiver, packet, rng_adv)
            trust_mod.observe_forward(nodes, sender, receiver, packet, relays, hop_ms)
            if not relays:
                return False, delay, hops_done, metrics_mod.LOSS_MALICIOUS

        return False, delay, hops_done, metrics_mod.LOSS_LINK

    # -- the round loop ----------------------------------------------------

    def run(self):
        params = self.params
        nodes = self.nodes

        self.policy.reset(self)

        for round_idx in range(int(params.rounds)):
            self.round_idx = round_idx

            mobility.step(nodes, self.seeds.mobility)
            topology.rebuild(nodes)

            self.energy_model.step(nodes, round_idx, self.seeds.channel)
            # harvest_last is rewritten every step, so this is the per-round total.
            self.metrics.energy_harvested += float(nodes.harvest_last.sum())

            self.policy.on_round_start(self, round_idx)

            for packet in self.traffic.generate(round_idx):
                self.metrics.record_sent(packet)
                path = self.policy.select_route(self, packet)

                if not path or len(path) < 2:
                    self.metrics.record_lost(packet, metrics_mod.LOSS_NO_ROUTE)
                    self.policy.on_result(self, packet, False, path, 0,
                                          metrics_mod.LOSS_NO_ROUTE)
                    continue

                delivered, delay, hops, reason = self.forward(packet, path)
                if delivered:
                    self.metrics.record_delivered(packet, delay, hops)
                else:
                    self.metrics.record_lost(packet, reason)
                    # base.pdf 3.8 -- a broken path triggers a route error and
                    # rediscovery, so drop the stale cache entry.
                    self.route_cache.drop_node(int(path[min(hops + 1, len(path) - 1)]))
                self.policy.on_result(self, packet, delivered, path, hops, reason)

            if params.enable_control_plane:
                self._control_plane(round_idx)

            self.policy.on_round_end(self, round_idx)
            self.metrics.record_round(round_idx, nodes)

            if params.stop_when_dead:
                dead = int((~nodes.alive).sum())
                if dead >= config.DEAD_FRACTION_STOP * nodes.n:
                    break

        detected = self.policy.detected_mask(self)
        self.metrics.score_detection(nodes, detected)

        row = self.metrics.finalise(nodes)
        row.update(self.keyring.cost_summary())
        row.update(self.policy.extra_metrics(self))
        row.update(
            {
                "policy": self.policy.name,
                "n_nodes": params.n_nodes,
                "speed": params.speed,
                "attack": params.attack,
                "malicious_fraction": params.malicious_fraction,
                "energy_model": params.energy_model,
                "seed": params.seed,
                "malicious_nodes": int(self.malicious_ids.size),
                "route_cache_hits": self.route_cache.hits,
                "route_cache_misses": self.route_cache.misses,
            }
        )
        return row

    def _control_plane(self, round_idx):
        """PT_NID / PT_GID / PT_CREV, on the periods given in base.pdf 3.6."""
        if round_idx % config.PT_NID_PERIOD == 0:
            trust_mod.pt_nid_round(self.nodes, self.metrics)
            trust_mod.refresh_trust(self.nodes)
            trust_mod.push_trust_history(self.nodes)

        if round_idx % config.PT_GID_PERIOD == 0 and round_idx > 0:
            trust_mod.pt_gid_round(
                self.nodes,
                run_metrics=self.metrics,
                enable_slander=self.params.enable_slander,
                enable_energy_excuse=self.params.enable_energy_excuse,
                route_cache=self.route_cache,
                round_idx=round_idx,
            )


class RoutingPolicy(object):
    """Interface every protocol implements to plug into :class:`Simulation`."""

    name = "policy"

    def reset(self, sim):
        """Called once before the first round."""
        return None

    def on_round_start(self, sim, round_idx):
        """Called after the world has advanced, before traffic is offered."""
        return None

    def select_route(self, sim, packet):
        """Return the path this policy chooses, or ``None`` for no route."""
        return sim.discover(packet.src, packet.dst)

    def on_result(self, sim, packet, delivered, path, hops, reason):
        """Feedback hook -- where reinforcement learning updates happen."""
        return None

    def on_round_end(self, sim, round_idx):
        return None

    def detected_mask(self, sim):
        """Nodes this policy believes are malicious; ``None`` uses the default."""
        return None

    def extra_metrics(self, sim):
        """Policy-specific columns appended to the result row."""
        return {}


def run_simulation(policy, params):
    """Convenience wrapper: build a :class:`Simulation` and run it."""
    return Simulation(policy, params).run()
