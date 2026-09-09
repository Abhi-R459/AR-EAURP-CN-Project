"""Node state for the mechanistic MANET harness.

Design note (performance): rather than one Python object per node, all node
state is held as parallel ``numpy`` arrays inside :class:`NodeState`. Mobility,
energy drain, neighbour discovery and trust decay are then single vectorised
operations instead of N-iteration Python loops. The per-hop forwarding loop is
inherently sequential and still uses plain indexing, but everything around it
is bulk. On a 2-vCPU Colab box this is the difference between a sweep that
finishes in minutes and one that does not finish at all.

The per-observer watchdog tables are N x N arrays: ``sent_to[i, j]`` is how
many packets node i handed to node j for forwarding, and ``fwd_seen[i, j]`` is
how many of those i observed j actually relay. The Packet Forwarding Ratio of
base.pdf 3.7 is then ``fwd_seen[i, j] / sent_to[i, j]``.

The large/small split of those counters is what makes selective forwarding
(gray-hole) visible at all -- a single scalar PFR cannot distinguish "drops 15%
of everything" from "drops 60% of the big packets and nothing else".
"""

import numpy as np

from . import config

# Role flags. Deliberately bit flags so behaviours compose: the docx's
# "trust poisoning" adversary is a gray-hole that also slanders.
ROLE_HONEST = 0
FLAG_BLACKHOLE = 1
FLAG_GRAYHOLE = 2
FLAG_SLANDERER = 4

ROLE_LABELS = {
    ROLE_HONEST: "honest",
    FLAG_BLACKHOLE: "blackhole",
    FLAG_GRAYHOLE: "grayhole",
    FLAG_SLANDERER: "slanderer",
    FLAG_GRAYHOLE | FLAG_SLANDERER: "grayhole+slanderer",
    FLAG_BLACKHOLE | FLAG_SLANDERER: "blackhole+slanderer",
}


def role_label(role):
    """Human-readable name for a role bitmask."""
    return ROLE_LABELS.get(int(role), "role<{0}>".format(int(role)))


class NodeState(object):
    """Vectorised state for every node in one simulation run."""

    def __init__(self, n_nodes, rng_topology, initial_energy=None):
        if n_nodes < 2:
            raise ValueError("need at least 2 nodes, got {0}".format(n_nodes))

        self.n = int(n_nodes)
        e0 = config.INITIAL_ENERGY if initial_energy is None else float(initial_energy)

        # --- position and mobility ---------------------------------------
        self.x = rng_topology.uniform(0.0, config.AREA_SIZE, self.n)
        self.y = rng_topology.uniform(0.0, config.AREA_SIZE, self.n)
        self.dest_x = rng_topology.uniform(0.0, config.AREA_SIZE, self.n)
        self.dest_y = rng_topology.uniform(0.0, config.AREA_SIZE, self.n)
        self.speed = np.full(self.n, float(config.DEFAULT_SPEED))

        # --- energy -------------------------------------------------------
        self.initial_energy = np.full(self.n, e0)
        self.energy = np.full(self.n, e0)
        self.alive = np.ones(self.n, dtype=bool)
        self.death_round = np.full(self.n, -1, dtype=np.int64)

        # Energy harvesting (only used by the AR-EAURP solar model).
        self.panel_gain = np.zeros(self.n)
        self.cloud = np.ones(self.n)
        self.harvest_last = np.zeros(self.n)

        # --- roles --------------------------------------------------------
        self.role = np.zeros(self.n, dtype=np.int64)

        # --- watchdog observation tables (observer i, subject j) ----------
        shape = (self.n, self.n)
        self.sent_to = np.zeros(shape)
        self.fwd_seen = np.zeros(shape)
        self.sent_large = np.zeros(shape)
        self.fwd_seen_large = np.zeros(shape)
        self.sent_small = np.zeros(shape)
        self.fwd_seen_small = np.zeros(shape)
        self.lat_sum = np.zeros(shape)
        self.lat_sq = np.zeros(shape)
        self.lat_n = np.zeros(shape)

        # i's trust in j (base.pdf 3.7, Lekha Eq. 20).
        self.trust = np.full(shape, config.INITIAL_TRUST)
        # Sliding trust history for the predictive model (Lekha Eq. 25-27).
        self.trust_history = np.full(
            (config.TRUST_HISTORY_LEN, self.n, self.n), config.INITIAL_TRUST
        )

        # --- control plane state (base.pdf 3.6-3.7) -----------------------
        # accusations[i, j] == 1 -> i has reported j as suspicious via PT_GID
        self.accusations = np.zeros(shape, dtype=np.int8)
        self.revoked = np.zeros(self.n, dtype=bool)
        self.revocation_round = np.full(self.n, -1, dtype=np.int64)

        # --- AR-EAURP anomaly state ---------------------------------------
        self.contested = np.zeros(self.n, dtype=bool)
        self.contested_until = np.zeros(self.n, dtype=np.int64)
        self.anomaly_score = np.zeros(self.n)

        # --- neighbour adjacency, filled by topology.rebuild --------------
        self.adjacency = np.zeros(shape, dtype=bool)
        self.neighbours = [np.zeros(0, dtype=np.int64) for _ in range(self.n)]

    # -- role helpers ------------------------------------------------------

    def is_blackhole(self, i):
        return bool(self.role[i] & FLAG_BLACKHOLE)

    def is_grayhole(self, i):
        return bool(self.role[i] & FLAG_GRAYHOLE)

    def is_slanderer(self, i):
        return bool(self.role[i] & FLAG_SLANDERER)

    def malicious_mask(self):
        """Boolean mask of nodes with any adversarial flag set."""
        return self.role != ROLE_HONEST

    # -- energy helpers ----------------------------------------------------

    def energy_threshold(self):
        """base.pdf 3.5 -- per-node 20%-of-initial forwarding threshold."""
        return config.ENERGY_THRESHOLD_FRAC * self.initial_energy

    def eligible_mask(self):
        """Nodes that may carry traffic: alive, not revoked, above threshold."""
        return self.alive & (~self.revoked) & (self.energy > self.energy_threshold())

    def normalised_energy(self):
        """E_i / E_init, clipped to [0, 1] (Lekha Eq. 23/31)."""
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(
                self.initial_energy > 0.0, self.energy / self.initial_energy, 0.0
            )
        return np.clip(ratio, 0.0, 1.0)

    def mobility_factor(self):
        """M_i = 1 / (1 + v_i / v_max)  (Lekha Eq. 22/32)."""
        return 1.0 / (1.0 + self.speed / config.MAX_SPEED)

    # -- trust helpers -----------------------------------------------------

    def observed_pfr(self):
        """PFR[i, j] = fwd_seen[i, j] / sent_to[i, j], 1.0 where unobserved.

        Unobserved pairs default to 1.0 (fully trusted) to match base.pdf,
        which only ever penalises a node once it has actually been watched.
        """
        with np.errstate(divide="ignore", invalid="ignore"):
            pfr = np.where(self.sent_to > 0.0, self.fwd_seen / self.sent_to, 1.0)
        return np.clip(pfr, 0.0, 1.0)

    def network_trust(self):
        """Per-node trust as seen by the network: mean over active observers."""
        observed = self.sent_to > 0.0
        counts = observed.sum(axis=0)
        totals = np.where(observed, self.trust, 0.0).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            mean_trust = np.where(counts > 0, totals / np.maximum(counts, 1), config.INITIAL_TRUST)
        return np.clip(mean_trust, 0.0, 1.0)

    def summary(self):
        """Compact dict used for logging and sanity checks."""
        return {
            "n": self.n,
            "alive": int(self.alive.sum()),
            "revoked": int(self.revoked.sum()),
            "contested": int(self.contested.sum()),
            "malicious": int(self.malicious_mask().sum()),
            "mean_energy": float(self.energy[self.alive].mean()) if self.alive.any() else 0.0,
        }
