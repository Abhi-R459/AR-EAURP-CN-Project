"""Implementation B on the mechanistic harness (Track 2).

Same Q-learning agent as A -- identical alpha, gamma, epsilon, identical
<T, E, M> state discretisation, identical two actions and +/-1 reward -- because
both come from the same equations.

The one difference is faithful to the delivered code, and it is the whole point
of running B on Track 2:

    A (paper, Eq. 19)  trust[i][j] = what j relayed out of what i gave it,
                       measured by the watchdog.

    B (delivered code) nodes[src].forwarded += 1
                       nodes[dst].received  += 1
                       ...where src and dst are drawn at random and are not
                       relays of anything.

On the coin-flip model that difference is invisible, because trust only feeds a
scalar in a probability formula. On a harness where trust actually selects
routes, it is the difference between routing on evidence and routing on noise.
Reproducing it here is what makes that visible.
"""

import numpy as np

from ..a_drl_eaurp.policy_common import TabularDrlPolicy


class SeniorDrlPolicy(TabularDrlPolicy):
    """The senior's DRL-EAURP, including its trust-attribution semantics."""

    name = "B:DRL-EAURP(senior)"
    trust_source = "endpoint_counters"   # nodes[src].forwarded / nodes[dst].received

    def __init__(self, **kwargs):
        super(SeniorDrlPolicy, self).__init__(**kwargs)
        # The code's own counters, kept separately from the harness watchdog so
        # that both views can be reported side by side.
        self._forwarded = None
        self._received = None
        self._trust = None

    def reset(self, sim):
        n = sim.nodes.n
        self._forwarded = np.zeros(n)
        self._received = np.zeros(n)
        self._trust = np.ones(n)
        super(SeniorDrlPolicy, self).reset(sim)

    def trust_vector(self, sim):
        """Trust as the delivered code computes it."""
        if self._trust is None:
            return np.ones(sim.nodes.n)
        return np.clip(self._trust, 0.0, 1.0)

    def state_of(self, sim):
        """Eq. (29)-(32) over the code's own trust values."""
        nodes = sim.nodes
        alive = nodes.alive
        if not alive.any() or self._trust is None:
            return (0.0, 0.0, 0.0)
        trust = float(np.clip(self._trust, 0.0, 1.0)[alive].mean())
        energy = float(nodes.normalised_energy()[alive].mean())
        mobility = float(nodes.mobility_factor()[alive].mean())
        return (round(trust, 1), round(energy, 1), round(mobility, 1))

    def on_result(self, sim, packet, delivered, path, hops, reason):
        # Verbatim from senior_code.ipynb:
        #     nodes[src].forwarded += 1
        #     nodes[dst].received  += 1
        #     adaptive_trust_update(nodes[src]); adaptive_trust_update(nodes[dst])
        self._forwarded[packet.src] += 1.0
        self._received[packet.dst] += 1.0
        for node_id in (packet.src, packet.dst):
            self._adaptive_trust_update(node_id)

        super(SeniorDrlPolicy, self).on_result(
            sim, packet, delivered, path, hops, reason
        )

    def _adaptive_trust_update(self, node_id):
        """``adaptive_trust_update`` from the notebook, unchanged."""
        received = self._received[node_id]
        if received == 0:
            return
        pfr = self._forwarded[node_id] / received
        self._trust[node_id] = 0.7 * self._trust[node_id] + 0.3 * pfr

    def detected_mask(self, sim):
        """The delivered code never acts on ``node.malicious``.

        ``adaptive_trust_update`` sets the flag and nothing reads it, so B
        detects nobody. Reporting an all-false mask states that honestly rather
        than borrowing the harness's revocation list.
        """
        return np.zeros(sim.nodes.n, dtype=bool)

    def extra_metrics(self, sim):
        row = super(SeniorDrlPolicy, self).extra_metrics(sim)
        if self._trust is not None:
            watchdog = sim.nodes.network_trust()
            row["code_trust_mean"] = float(np.clip(self._trust, 0.0, 1.0).mean())
            row["watchdog_trust_mean"] = float(watchdog.mean())
            # Correlation between the code's trust signal and a real
            # forwarding-behaviour measurement. Near zero means the signal
            # carries no information about who actually forwards.
            code = np.clip(self._trust, 0.0, 1.0)
            if code.std() > 1e-9 and watchdog.std() > 1e-9:
                row["trust_signal_correlation"] = float(
                    np.corrcoef(code, watchdog)[0, 1]
                )
            else:
                row["trust_signal_correlation"] = 0.0
        return row
