"""EAURP and plain-AODV routing policies -- base.pdf.

``AodvPolicy``
    The reference baseline both papers compare against: shortest hop count, no
    trust, no energy gate, no encryption. This replaces the senior's "Existing"
    curve, which is not a protocol at all but EAURP's own output multiplied by
    fixed constants (Lekha.pdf Eq. 14-18).

``EaurpPolicy``
    base.pdf as specified: routes scored by ``R_Score = a*T + b*E``, relays gated
    on the 20%-of-initial-energy threshold and the revocation list, trust from
    watchdog-observed packet forwarding ratios, majority-vote revocation over
    PT_GID, and ECC payload protection.

Both are ordinary :class:`~src.common.simulator.RoutingPolicy` implementations,
so they run on exactly the same world as A, B and C.
"""

import numpy as np

from ..common import config
from ..common.simulator import RoutingPolicy
from . import aodv


class AodvPolicy(RoutingPolicy):
    """Plain AODV: minimum hop count, security- and energy-blind."""

    name = "AODV"

    def select_route(self, sim, packet):
        return sim.discover(packet.src, packet.dst, mode=aodv.MODE_AODV)

    def detected_mask(self, sim):
        # Plain AODV has no detection mechanism at all, so it never accuses
        # anyone. Reporting an all-false mask keeps its TPR/FPR honest (0/0)
        # rather than inheriting the trust layer's verdicts.
        return np.zeros(sim.nodes.n, dtype=bool)


class EaurpPolicy(RoutingPolicy):
    """base.pdf EAURP: trust- and energy-aware route selection with revocation."""

    name = "EAURP"

    def __init__(self, rescore_period=10):
        self.rescore_period = int(rescore_period)

    def reset(self, sim):
        sim.refresh_scores()

    def on_round_start(self, sim, round_idx):
        # Route scores drift as energy drains and trust is updated; recomputing
        # every round would dominate the runtime for no measurable benefit.
        if round_idx % self.rescore_period == 0:
            sim.refresh_scores()

    def select_route(self, sim, packet):
        return sim.discover(packet.src, packet.dst, mode=aodv.MODE_EAURP)

    def detected_mask(self, sim):
        return sim.nodes.revoked.copy()

    def extra_metrics(self, sim):
        a, b = aodv.score_coefficients(sim.nodes)
        return {
            "score_weight_trust_a": a,
            "score_weight_energy_b": b,
            "mean_route_score": float(sim.scores.mean()),
        }
