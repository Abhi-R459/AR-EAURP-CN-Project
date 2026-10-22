"""Implementation A on the mechanistic harness (Track 2).

The agent is the paper's: tabular Q-learning over the state <T, E, M> of
Eq. (29)-(32), rounded to one decimal, an epsilon-greedy policy (Eq. 34), two
actions (Eq. 33), the +/-1 reward of Eq. (37) and the update of Eq. (3).

THE ONE NECESSARY TRANSLATION. Eq. (36) expresses an action as an additive
bonus to a global success probability -- ``+0.08`` for exploit, ``+0.02`` for
explore. That is only meaningful when there is no route. Here routes exist, so
the two actions map to what they are *named* after:

    A = 0  exploit  -> take the highest-trust route
    A = 1  explore  -> take a diversified (node-disjoint) route

This is the smallest change that lets the paper's agent act at all, and it is
strictly favourable to the paper: an agent choosing between real routes has
more to work with than one adding a constant to a coin flip.

TRUST ATTRIBUTION follows Eq. (19) as written -- a node's forwarding ratio is
what *it* relayed out of what *it* received, measured by the watchdog. This is
the point where A and B diverge on Track 2: the delivered code credits the
randomly chosen source and destination instead, which is reproduced faithfully
in ``src/b_senior/policy_common.py``.
"""

import numpy as np

from ..common import config
from ..common.simulator import RoutingPolicy
from ..routing import aodv

ACTION_EXPLOIT = 0
ACTION_EXPLORE = 1


class TabularDrlPolicy(RoutingPolicy):
    """Lekha.pdf's Q-learning agent driving real route selection."""

    name = "A:DRL-EAURP"
    trust_source = "watchdog_pfr"   # Eq. (19) as written

    def __init__(self, alpha=None, gamma=None, epsilon=None, rescore_period=10):
        self.alpha = config.RL_ALPHA if alpha is None else float(alpha)
        self.gamma = config.RL_GAMMA if gamma is None else float(gamma)
        self.epsilon = config.RL_EPSILON if epsilon is None else float(epsilon)
        self.rescore_period = int(rescore_period)

        self.q_table = {}
        self.action_counts = [0, 0]
        self.updates = 0
        self.total_reward = 0.0
        self._pending = None

    # -- state and policy --------------------------------------------------

    def _q(self, state):
        if state not in self.q_table:
            self.q_table[state] = [0.0, 0.0]
        return self.q_table[state]

    def state_of(self, sim):
        """Eq. (29)-(32), discretised to one decimal."""
        nodes = sim.nodes
        alive = nodes.alive
        if not alive.any():
            return (0.0, 0.0, 0.0)
        trust = float(nodes.network_trust()[alive].mean())
        energy = float(nodes.normalised_energy()[alive].mean())
        mobility = float(nodes.mobility_factor()[alive].mean())
        return (round(trust, 1), round(energy, 1), round(mobility, 1))

    def choose_action(self, sim, state):
        """Eq. (34): epsilon-greedy."""
        if sim.seeds.policy.random() < self.epsilon:
            return int(sim.seeds.policy.integers(0, 2))
        values = self._q(state)
        return ACTION_EXPLOIT if values[0] >= values[1] else ACTION_EXPLORE

    # -- harness hooks -----------------------------------------------------

    def reset(self, sim):
        self.q_table = {}
        self.action_counts = [0, 0]
        self.updates = 0
        self.total_reward = 0.0
        self._pending = None
        sim.refresh_scores(trust=self.trust_vector(sim))

    def trust_vector(self, sim):
        """Per-node trust the policy feeds into route scoring."""
        return sim.nodes.network_trust()

    def on_round_start(self, sim, round_idx):
        if round_idx % self.rescore_period == 0:
            sim.refresh_scores(trust=self.trust_vector(sim))

    def select_route(self, sim, packet):
        state = self.state_of(sim)
        action = self.choose_action(sim, state)
        self.action_counts[action] += 1

        if action == ACTION_EXPLOIT:
            path = sim.discover(packet.src, packet.dst, mode=aodv.MODE_TRUST)
        else:
            primary = sim.discover(packet.src, packet.dst, mode=aodv.MODE_EAURP)
            path = aodv.find_diverse_route(
                sim.nodes, packet.src, packet.dst, sim.scores, primary=primary
            )

        self._pending = (state, action)
        return path

    def on_result(self, sim, packet, delivered, path, hops, reason):
        """Eq. (37) reward, Eq. (3) update."""
        if self._pending is None:
            return
        state, action = self._pending
        reward = config.REWARD_SUCCESS if delivered else config.REWARD_FAILURE
        self.total_reward += reward

        next_state = self.state_of(sim)
        best_next = max(self._q(next_state))
        values = self._q(state)
        values[action] += self.alpha * (
            reward + self.gamma * best_next - values[action]
        )
        self.updates += 1
        self._pending = None

    def detected_mask(self, sim):
        return sim.nodes.revoked.copy()

    def extra_metrics(self, sim):
        total = sum(self.action_counts) or 1
        greedy_zero = sum(
            1 for values in self.q_table.values() if values[0] >= values[1]
        )
        return {
            "q_states": len(self.q_table),
            "q_updates": self.updates,
            "action0_share": self.action_counts[0] / float(total),
            "states_preferring_action0": greedy_zero,
            "mean_reward": self.total_reward / float(max(1, self.updates)),
            "trust_source": self.trust_source,
        }
