"""The five models of Lekha.pdf, each written from its own equations.

    ExistingModel   Eq. (14)-(18)
    EaurpBaseModel  Eq. (7)
    AteaurpModel    Eq. (19)-(24)
    PseEaurpModel   Eq. (25)-(28)
    DrlEaurpModel   Eq. (3), (29)-(38)

Every variant is a :class:`~src.a_drl_eaurp.paper_model.PaperVariant`, so they
all run through the same loop and differ only where the paper says they differ.
"""

import random

import numpy as np

from . import paper_model as pm

# Eq. (14)-(18): the constants the paper uses to derive its "Existing" curve.
EXISTING_SCALING = {
    "avg_delay_ms": 1.2,
    "packet_loss_bytes": 1.5,
    "throughput": 0.7,
    "pdr": 0.85,
    "network_lifetime": 0.98,
}


class EaurpBaseModel(pm.PaperVariant):
    """Eq. (7): P_success = max(0.4, 0.9 - v / 100000).

    Mobility is the only input. There is no trust term and no energy term, so
    this variant is the paper's own statement that its baseline ignores both.
    """

    name = "EAURP"
    equations = "Eq. (4)-(13)"

    def success_probability(self, nodes, state, rng):
        speed = nodes[0].speed if nodes else 0.0
        return max(0.4, 0.9 - (speed / 100000.0))

    def delay(self, hops, rng):
        return rng.uniform(20.0, 60.0) + hops * rng.uniform(5.0, 15.0)


class AteaurpModel(pm.PaperVariant):
    """Eq. (24): P = min(0.4 + 0.3 T + 0.2 E + 0.1 M, 0.95).

    Adds the adaptive trust update of Eq. (20) and the classification rule of
    Eq. (21).
    """

    name = "ATEAURP"
    equations = "Eq. (19)-(24)"

    def observe(self, nodes, rng):
        return pm.network_state(nodes)

    def success_probability(self, nodes, state, rng):
        trust, energy, mobility = state
        return min(0.4 + 0.3 * trust + 0.2 * energy + 0.1 * mobility, 0.95)

    def delay(self, hops, rng):
        return rng.uniform(20.0, 60.0) + hops * rng.uniform(4.0, 12.0)

    def update_node_trust(self, node):
        pm.update_trust(node)


class PseEaurpModel(AteaurpModel):
    """Eq. (28): P = min(0.4 + 0.35 T_pred + 0.15 E + 0.1 M, 0.97).

    Trust is replaced by the three-tap forecast of Eq. (26).
    """

    name = "PSE-EAURP"
    equations = "Eq. (25)-(28)"

    def observe(self, nodes, rng):
        live = [node for node in nodes if node.energy > 0.0] or nodes
        count = float(len(live))
        predicted = sum(pm.predict_trust(node) for node in live) / count
        _, energy, mobility = pm.network_state(nodes)
        return predicted, energy, mobility

    def success_probability(self, nodes, state, rng):
        predicted, energy, mobility = state
        return min(0.4 + 0.35 * predicted + 0.15 * energy + 0.1 * mobility, 0.97)

    def delay(self, hops, rng):
        return rng.uniform(20.0, 50.0) + hops * rng.uniform(4.0, 10.0)

    def update_node_trust(self, node):
        pm.update_trust(node)
        pm.push_trust_history(node)


class DrlEaurpModel(pm.PaperVariant):
    """Eq. (29)-(38): tabular Q-learning over the state <T, E, M>.

    Eq. (35): P_base = 0.45 + 0.25 T + 0.20 E + 0.10 M
    Eq. (36): P = P_base + 0.08 if A = 0 else P_base + 0.02, clipped to [0.4, 0.98]
    Eq. (37): r = +1 delivered, -1 lost
    Eq. (3):  Q(s,a) <- Q(s,a) + alpha [r + gamma max_a' Q(s',a') - Q(s,a)]
    Eq. (34): epsilon-greedy policy

    NOTE FOR THE REVIEW. Eq. (36) makes action 0 strictly better than action 1
    for every state, so the optimal policy is the constant "always exploit".
    The agent learns it within a few dozen updates, after which the state has no
    influence on anything. :meth:`policy_summary` reports how often the greedy
    action was 0, which makes that degeneracy measurable rather than asserted.
    """

    name = "DRL-EAURP"
    equations = "Eq. (3), (29)-(38)"

    def __init__(self, alpha=0.1, gamma=0.9, epsilon=0.1):
        self.alpha = float(alpha)
        self.gamma = float(gamma)
        self.epsilon = float(epsilon)
        self.q_table = {}
        self.action_counts = [0, 0]
        self.updates = 0
        self._last = None

    # -- Q-table helpers ---------------------------------------------------

    def _q(self, state):
        if state not in self.q_table:
            self.q_table[state] = [0.0, 0.0]
        return self.q_table[state]

    def reset(self, nodes, rng):
        self.q_table = {}
        self.action_counts = [0, 0]
        self.updates = 0
        self._last = None

    def observe(self, nodes, rng):
        """Eq. (29)-(32), discretised to one decimal as the paper's code does."""
        trust, energy, mobility = pm.network_state(nodes)
        key = (round(trust, 1), round(energy, 1), round(mobility, 1))
        return key, trust, energy, mobility

    def success_probability(self, nodes, state, rng):
        key, trust, energy, mobility = state

        # Eq. (34): epsilon-greedy
        if rng.random() < self.epsilon:
            action = rng.randint(0, 1)
        else:
            values = self._q(key)
            action = 0 if values[0] >= values[1] else 1

        self.action_counts[action] += 1
        self._last = (key, action)

        # Eq. (35)-(36)
        base = 0.45 + 0.25 * trust + 0.20 * energy + 0.10 * mobility
        probability = base + (0.08 if action == 0 else 0.02)
        return min(max(probability, 0.4), 0.98)

    def delay(self, hops, rng):
        return rng.uniform(20.0, 50.0) + hops * rng.uniform(4.0, 10.0)

    def update_node_trust(self, node):
        pm.update_trust(node)

    def feedback(self, nodes, state, success, rng):
        """Eq. (37) reward, Eq. (3) Q-update."""
        if self._last is None:
            return
        key, action = self._last
        reward = 1.0 if success else -1.0

        next_key = self.observe(nodes, rng)[0] if nodes else key
        best_next = max(self._q(next_key))

        values = self._q(key)
        values[action] += self.alpha * (
            reward + self.gamma * best_next - values[action]
        )
        self.updates += 1

    def policy_summary(self):
        """Evidence for the degeneracy noted in the class docstring."""
        total = sum(self.action_counts) or 1
        greedy_zero = sum(
            1 for values in self.q_table.values() if values[0] >= values[1]
        )
        return {
            "q_states_visited": len(self.q_table),
            "q_updates": self.updates,
            "action0_share": self.action_counts[0] / float(total),
            "states_preferring_action0": greedy_zero,
            "states_total": len(self.q_table),
        }


class ExistingModel(object):
    """Eq. (14)-(18) -- NOT a protocol.

    The paper derives its "Existing" curve by scaling EAURP's own output by
    fixed constants. Implemented faithfully, and labelled in every output so it
    is never mistaken for a measurement.
    """

    name = "Existing"
    equations = "Eq. (14)-(18)"
    is_derived = True

    @staticmethod
    def derive(eaurp_result):
        derived = dict(eaurp_result)
        for key, factor in EXISTING_SCALING.items():
            if key in derived:
                derived[key] = derived[key] * factor
        derived["provenance"] = (
            "DERIVED from EAURP output via Lekha.pdf Eq. (14)-(18); "
            "not a simulated protocol"
        )
        return derived


VARIANTS = {
    "EAURP": EaurpBaseModel,
    "ATEAURP": AteaurpModel,
    "PSE-EAURP": PseEaurpModel,
    "DRL-EAURP": DrlEaurpModel,
}


def make_variant(name):
    key = str(name).upper().replace("_", "-")
    for candidate, cls in VARIANTS.items():
        if candidate.upper() == key:
            return cls()
    raise ValueError(
        "unknown variant {0!r}; choose from {1}".format(name, sorted(VARIANTS))
    )
