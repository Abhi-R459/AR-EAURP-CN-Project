"""Unit tests for the mechanistic harness.

These run with numpy alone -- no torch, no matplotlib -- so they can be
executed on any machine before the notebook is ever opened in Colab.

Run with:  python -m pytest tests/ -q
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common import (  # noqa: E402
    adversary, config, energy, metrics, mobility, node as node_mod, seeding,
    topology, traffic,
)
from src.common.simulator import SimParams, Simulation  # noqa: E402
from src.routing import aodv, ecc, trust  # noqa: E402
from src.routing.eaurp import AodvPolicy, EaurpPolicy  # noqa: E402


def build_nodes(n=100, seed=11, speed=20000):
    bundle = seeding.make_seed_bundle(seed)
    nodes = node_mod.NodeState(n, bundle.topology)
    mobility.assign_speeds(nodes, speed)
    topology.rebuild(nodes)
    return nodes, bundle


# --------------------------------------------------------------------------
# Topology and mobility
# --------------------------------------------------------------------------

def test_adjacency_is_symmetric_and_loopless():
    nodes, _ = build_nodes()
    assert (nodes.adjacency == nodes.adjacency.T).all()
    assert not np.diagonal(nodes.adjacency).any()


def test_links_respect_communication_range():
    nodes, _ = build_nodes()
    distances = topology.pairwise_distances(nodes)
    linked = nodes.adjacency
    assert distances[linked].max() <= config.COMM_RANGE + 1e-9
    unlinked = (~linked) & ~np.eye(nodes.n, dtype=bool)
    assert distances[unlinked].min() > config.COMM_RANGE - 1e-9


def test_mobility_keeps_nodes_inside_the_area():
    nodes, bundle = build_nodes()
    for _ in range(50):
        mobility.step(nodes, bundle.mobility)
    assert nodes.x.min() >= 0.0 and nodes.x.max() <= config.AREA_SIZE
    assert nodes.y.min() >= 0.0 and nodes.y.max() <= config.AREA_SIZE


def test_dead_nodes_leave_the_topology():
    nodes, _ = build_nodes()
    nodes.alive[5] = False
    nodes.revoked[6] = True
    topology.rebuild(nodes)
    assert not nodes.adjacency[5].any() and not nodes.adjacency[:, 5].any()
    assert not nodes.adjacency[6].any() and not nodes.adjacency[:, 6].any()


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------

def test_routes_are_loop_free_and_valid():
    nodes, _ = build_nodes()
    scores = aodv.route_scores(nodes)
    rng = np.random.default_rng(3)
    found = 0
    for _ in range(150):
        src, dst = (int(v) for v in rng.integers(0, nodes.n, 2))
        if src == dst:
            continue
        path = aodv.find_route(nodes, src, dst, scores)
        if path is None:
            continue
        found += 1
        assert len(set(path)) == len(path), "route contains a loop"
        assert topology.path_is_valid(nodes, path)
        assert path[0] == src and path[-1] == dst
    assert found > 20, "expected to find routes in a connected network"


def test_energy_threshold_excludes_relays():
    """base.pdf 3.5 -- nodes below 20% of initial energy must not be relays."""
    nodes, _ = build_nodes()
    scores = aodv.route_scores(nodes)
    drained = 7
    nodes.energy[drained] = 0.05 * config.INITIAL_ENERGY
    rng = np.random.default_rng(5)
    for _ in range(200):
        src, dst = (int(v) for v in rng.integers(0, nodes.n, 2))
        if src == dst or drained in (src, dst):
            continue
        path = aodv.find_route(nodes, src, dst, scores)
        if path:
            assert drained not in path[1:-1]


def test_revoked_nodes_are_never_relays():
    nodes, _ = build_nodes()
    nodes.revoked[9] = True
    topology.rebuild(nodes)
    scores = aodv.route_scores(nodes)
    rng = np.random.default_rng(7)
    for _ in range(200):
        src, dst = (int(v) for v in rng.integers(0, nodes.n, 2))
        if src == dst:
            continue
        path = aodv.find_route(nodes, src, dst, scores)
        if path:
            assert 9 not in path


def test_score_coefficients_sum_to_one():
    """base.pdf 3.3 -- a = 1 - avg/max, b = avg/max."""
    nodes, _ = build_nodes()
    a, b = aodv.score_coefficients(nodes)
    assert abs((a + b) - 1.0) < 1e-9
    assert 0.0 <= a <= 1.0 and 0.0 <= b <= 1.0


def test_route_cache_invalidates_on_broken_link():
    nodes, _ = build_nodes()
    scores = aodv.route_scores(nodes)
    cache = aodv.RouteCache()
    path = None
    rng = np.random.default_rng(13)
    while path is None or len(path) < 3:
        src, dst = (int(v) for v in rng.integers(0, nodes.n, 2))
        if src == dst:
            continue
        path = aodv.find_route(nodes, src, dst, scores)
    cache.put(path[0], path[-1], path)
    assert cache.get(nodes, path[0], path[-1]) == path
    nodes.alive[path[1]] = False
    assert cache.get(nodes, path[0], path[-1]) is None


# --------------------------------------------------------------------------
# Trust and the threat model
# --------------------------------------------------------------------------

def test_pfr_arithmetic():
    nodes, _ = build_nodes(n=10)

    class Pkt(object):
        size = 800

        @property
        def is_large(self):
            return True

    for index in range(10):
        trust.observe_forward(nodes, 0, 1, Pkt(), index < 6)
    assert abs(nodes.observed_pfr()[0, 1] - 0.6) < 1e-9
    # Unobserved pairs stay fully trusted (base.pdf only penalises what it saw).
    assert nodes.observed_pfr()[0, 2] == 1.0


def test_grayhole_evades_the_trust_threshold():
    """The core premise of the advancement.

    A gray-hole that drops only large packets must keep its *observed* Packet
    Forwarding Ratio comfortably above base.pdf's 0.6 revocation threshold --
    otherwise there would be nothing for the GAN detector to add.
    """
    nodes, bundle = build_nodes(n=20)
    nodes.role[3] = node_mod.FLAG_GRAYHOLE

    class Pkt(object):
        def __init__(self, size):
            self.size = size

        @property
        def is_large(self):
            return self.size >= config.LARGE_PACKET_THRESHOLD

    rng = np.random.default_rng(21)
    for _ in range(4000):
        size = int(rng.integers(config.PACKET_SIZE_MIN, config.PACKET_SIZE_MAX + 1))
        packet = Pkt(size)
        relayed = adversary.forwards_data(nodes, 3, packet, bundle.adversary)
        trust.observe_forward(nodes, 0, 3, packet, relayed)

    pfr = nodes.observed_pfr()[0, 3]
    assert 0.75 < pfr < 0.92, "observed PFR was {0:.3f}".format(pfr)
    assert pfr > config.TRUST_THRESHOLD, "gray-hole must evade the 0.6 threshold"

    # ... yet the size-conditioned view separates cleanly, which is exactly the
    # signal the GAN detector is given.
    large_pfr = nodes.fwd_seen_large[0, 3] / nodes.sent_large[0, 3]
    small_pfr = nodes.fwd_seen_small[0, 3] / nodes.sent_small[0, 3]
    assert small_pfr == 1.0
    assert large_pfr < 0.85
    assert (small_pfr - large_pfr) > 0.15


def test_blackhole_drops_everything():
    nodes, bundle = build_nodes(n=10)
    nodes.role[4] = node_mod.FLAG_BLACKHOLE

    class Pkt(object):
        size = 600
        is_large = False

    assert not any(
        adversary.forwards_data(nodes, 4, Pkt(), bundle.adversary) for _ in range(100)
    )


def test_slanderer_inverts_its_reports():
    nodes, _ = build_nodes(n=10)
    nodes.role[1] = node_mod.FLAG_SLANDERER
    nodes.role[2] = node_mod.FLAG_GRAYHOLE
    # Vouches for a fellow attacker...
    assert adversary.reported_trust(nodes, 1, 2, 0.1) == config.SLANDER_HIGH
    # ...and accuses an honest node.
    assert adversary.reported_trust(nodes, 1, 3, 0.99) == config.SLANDER_LOW
    # An honest observer reports what it measured.
    assert adversary.reported_trust(nodes, 0, 3, 0.77) == 0.77


def test_energy_excuse_protects_a_flat_battery():
    """base.pdf 3.7 -- do not brand a node malicious for being out of power."""
    nodes, _ = build_nodes(n=12)
    victim = 5
    nodes.energy[victim] = 0.05 * config.INITIAL_ENERGY
    nodes.sent_to[:, victim] = 20.0
    nodes.fwd_seen[:, victim] = 0.0
    trust.refresh_trust(nodes)
    nodes.trust[:, victim] = 0.1

    trust.pt_gid_round(nodes, enable_energy_excuse=True, round_idx=30)
    assert not nodes.revoked[victim]

    trust.pt_gid_round(nodes, enable_energy_excuse=False, round_idx=60)
    assert nodes.revoked[victim]


def test_malicious_fraction_is_respected():
    nodes, bundle = build_nodes(n=100)
    for fraction in (0.1, 0.3, 0.5):
        ids = adversary.assign_roles(nodes, "grayhole", fraction, bundle.adversary)
        assert ids.size == int(round(fraction * 100))
        assert int(nodes.malicious_mask().sum()) == ids.size


# --------------------------------------------------------------------------
# Energy
# --------------------------------------------------------------------------

def test_linear_depletion_is_monotone():
    nodes, bundle = build_nodes(n=30)
    model = energy.LinearDepletion()
    model.reset(nodes, bundle.channel)
    previous = nodes.energy.copy()
    for round_idx in range(30):
        model.step(nodes, round_idx, bundle.channel)
        assert (nodes.energy <= previous + 1e-9).all()
        previous = nodes.energy.copy()


def test_solar_harvesting_can_recharge_and_respects_the_cap():
    nodes, bundle = build_nodes(n=30)
    model = energy.SolarHarvesting()
    model.reset(nodes, bundle.channel)
    nodes.energy[:] = 50.0
    recharged = False
    for round_idx in range(300):
        before = nodes.energy.copy()
        model.step(nodes, round_idx, bundle.channel)
        if (nodes.energy > before + 1e-9).any():
            recharged = True
        assert nodes.energy.max() <= config.MAX_ENERGY_CAP + 1e-9
    assert recharged, "a solar model that never recharges anything is not a solar model"


def test_nodes_die_exactly_once():
    nodes, bundle = build_nodes(n=20)
    model = energy.LinearDepletion()
    # Below the minimum drain of 0.04, so a single step is certain to kill.
    nodes.energy[:] = 0.03
    model.step(nodes, 5, bundle.channel)
    assert (~nodes.alive).all()
    assert (nodes.death_round == 5).all()
    model.step(nodes, 6, bundle.channel)
    assert (nodes.death_round == 5).all(), "death round must not be overwritten"


# --------------------------------------------------------------------------
# Determinism -- the property the whole comparison rests on
# --------------------------------------------------------------------------

def test_same_seed_gives_identical_worlds():
    first, _ = build_nodes(seed=99)
    second, _ = build_nodes(seed=99)
    assert np.array_equal(first.x, second.x)
    assert np.array_equal(first.adjacency, second.adjacency)


def test_policy_randomness_cannot_shift_the_world():
    """A policy that burns extra randomness must not change the environment."""

    class GreedyPolicy(EaurpPolicy):
        name = "greedy"

        def on_round_start(self, sim, round_idx):
            super(GreedyPolicy, self).on_round_start(sim, round_idx)
            sim.seeds.policy.random(25)  # consume policy randomness

    params = dict(n_nodes=60, speed=20000, rounds=40, seed=7)
    plain = Simulation(EaurpPolicy(), SimParams(**params))
    plain.run()
    greedy = Simulation(GreedyPolicy(), SimParams(**params))
    greedy.run()
    assert np.allclose(plain.nodes.x, greedy.nodes.x)
    assert np.array_equal(plain.nodes.role, greedy.nodes.role)


def test_identical_runs_reproduce_exactly():
    params = SimParams(n_nodes=60, speed=20000, rounds=60, seed=4242)
    first = Simulation(EaurpPolicy(), params).run()
    second = Simulation(EaurpPolicy(), params).run()
    for key in ("pdr", "avg_delay_ms", "packets_sent", "packet_loss_bytes"):
        assert first[key] == second[key], "run is not reproducible on {0}".format(key)


# --------------------------------------------------------------------------
# ECC
# --------------------------------------------------------------------------

def test_ecc_roundtrip():
    assert ecc.verify_roundtrip()


def test_ecc_actually_changes_the_payload():
    keyring = ecc.ECCKeyring(4, enabled=True)
    message = b"A" * 128
    blob = keyring.encrypt(0, 1, message)
    assert blob[8:] != message


# --------------------------------------------------------------------------
# End-to-end
# --------------------------------------------------------------------------

def test_simulation_produces_a_complete_result_row():
    params = SimParams(n_nodes=60, speed=20000, rounds=80, seed=1)
    row = Simulation(EaurpPolicy(), params).run()
    for key in ("pdr", "pdr_routable", "avg_delay_ms", "throughput",
                "network_lifetime", "det_tpr", "det_fpr", "policy"):
        assert key in row
    assert 0.0 <= row["pdr"] <= 1.0
    assert row["packets_sent"] > 0


def test_loss_reasons_account_for_every_lost_packet():
    params = SimParams(n_nodes=80, speed=25000, rounds=100, seed=2,
                       attack="blackhole", malicious_fraction=0.3)
    row = Simulation(EaurpPolicy(), params).run()
    accounted = sum(row["loss_" + reason] for reason in metrics.LOSS_REASONS)
    assert accounted == row["packets_lost"]


def test_blackhole_hurts_delivery():
    clean = Simulation(
        EaurpPolicy(), SimParams(n_nodes=100, rounds=150, seed=3)
    ).run()
    attacked = Simulation(
        EaurpPolicy(),
        SimParams(n_nodes=100, rounds=150, seed=3, attack="blackhole",
                  malicious_fraction=0.3),
    ).run()
    assert attacked["pdr"] < clean["pdr"]
    assert attacked["loss_malicious_drop"] > 0
