"""Traffic generation.

Two modes:

``flows``   (default for Track 2)
    A fixed set of persistent CBR source/destination pairs. Realistic, and it
    lets the routing layer cache routes instead of rediscovering a path for
    every packet -- which is what keeps the sweep inside the Colab time budget.

``random``  (paper-faithful)
    A fresh (src, dst) pair drawn uniformly every packet, reproducing the
    senior's ``src = random.randint(...)`` behaviour.
"""

from dataclasses import dataclass

import numpy as np

from . import config


@dataclass
class Packet:
    """One data packet in flight."""

    pid: int
    src: int
    dst: int
    size: int
    created_round: int

    @property
    def is_large(self):
        """Gray-hole selective forwarding keys off this boundary."""
        return self.size >= config.LARGE_PACKET_THRESHOLD


class TrafficGenerator(object):
    """Produces the packets offered to the routing layer each round."""

    def __init__(self, nodes, rng_traffic, mode="flows", n_flows=None,
                 packets_per_round=None):
        self.nodes = nodes
        self.rng = rng_traffic
        self.mode = str(mode).lower()
        if self.mode not in ("flows", "random"):
            raise ValueError("traffic mode must be 'flows' or 'random'")

        self.n_flows = config.N_FLOWS if n_flows is None else int(n_flows)
        self.packets_per_round = (
            config.PACKETS_PER_ROUND if packets_per_round is None
            else int(packets_per_round)
        )
        self._next_pid = 0
        self.flows = self._make_flows() if self.mode == "flows" else []

    def _reachable_pool(self):
        """Node ids in the largest connected component of the initial topology.

        Real CBR flows are set up between hosts that can currently reach each
        other, so we draw endpoints from the giant component rather than
        uniformly. Without this, at the papers' own parameters roughly one flow
        in ten would sit permanently across a network partition and contribute
        nothing but "no route" losses for the whole run -- which adds variance
        without telling us anything about the protocol. Genuine route breaks
        still happen constantly once the nodes start moving.
        """
        adjacency = self.nodes.adjacency
        if adjacency is None or not adjacency.any():
            return np.arange(self.nodes.n)

        unseen = set(range(self.nodes.n))
        best = []
        while unseen:
            root = unseen.pop()
            component = [root]
            frontier = [root]
            while frontier:
                current = frontier.pop()
                for neighbour in np.flatnonzero(adjacency[current]):
                    neighbour = int(neighbour)
                    if neighbour in unseen:
                        unseen.discard(neighbour)
                        component.append(neighbour)
                        frontier.append(neighbour)
            if len(component) > len(best):
                best = component
        return np.asarray(sorted(best)) if len(best) >= 2 else np.arange(self.nodes.n)

    def _make_flows(self):
        """Pick persistent source/destination pairs, avoiding self-loops."""
        flows = []
        pool = self._reachable_pool()
        if pool.size < 2:
            return flows

        wanted = min(self.n_flows, max(1, int(pool.size) // 2))
        attempts = 0
        while len(flows) < wanted and attempts < 50 * wanted:
            attempts += 1
            src = int(self.rng.choice(pool))
            dst = int(self.rng.choice(pool))
            if src != dst and (src, dst) not in flows:
                flows.append((src, dst))
        return flows

    def _new_pid(self):
        self._next_pid += 1
        return self._next_pid

    def _size(self):
        return int(
            self.rng.integers(config.PACKET_SIZE_MIN, config.PACKET_SIZE_MAX + 1)
        )

    def generate(self, round_idx):
        """Return the packets offered this round.

        Flows whose endpoints are dead or revoked are skipped rather than
        rerouted, so losing an endpoint shows up as reduced offered load rather
        than as a spurious delivery failure.
        """
        packets = []
        usable = self.nodes.eligible_mask()

        if self.mode == "flows":
            if not self.flows:
                return packets
            picks = self.rng.integers(0, len(self.flows), self.packets_per_round)
            for index in picks:
                src, dst = self.flows[int(index)]
                if not (usable[src] and usable[dst]):
                    continue
                packets.append(
                    Packet(self._new_pid(), src, dst, self._size(), int(round_idx))
                )
            return packets

        eligible = np.flatnonzero(usable)
        if eligible.size < 2:
            return packets
        for _ in range(self.packets_per_round):
            src, dst = self.rng.choice(eligible, size=2, replace=False)
            packets.append(
                Packet(self._new_pid(), int(src), int(dst), self._size(), int(round_idx))
            )
        return packets
