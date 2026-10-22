"""Behaviour features for anomaly detection -- AR-EAURP step 1/2.

The adversary behaviours themselves live in ``common.adversary`` (they have to,
because the harness applies them during forwarding). What lives here is the
observation side: turning the watchdog counters into the feature vectors the
GAN discriminator sees.

THE TWO FEATURES THAT MATTER -- these are the technical core of C.

``drop_rate_large`` vs ``drop_rate_small``
    A single scalar Packet Forwarding Ratio cannot tell "drops 15% of
    everything" apart from "drops 25% of the big packets and nothing else". The
    gray-hole of the threat model is the second thing, and measured on this
    harness its scalar PFR sits at 0.84 -- comfortably above the 0.6 revocation
    threshold of base.pdf, hence invisible. Split the same observations by
    packet size and the gap is 0.25, which is enormous. Selective forwarding is
    only stealthy if you refuse to look at what is being selected.

``report_disagreement``
    How far one observer's published opinion of a node sits from the median
    opinion of every other observer. An honest node reports what it measured, so
    its disagreement is small. A slanderer publishes 1.0 for its colluders and
    0.15 for the most trusted honest nodes, so its disagreement is large -- and
    it is large *whichever* direction it lies in, which is what makes the
    feature catch both vouching and accusing.

Everything is computed as a delta against the previous detection pass, so the
features describe recent behaviour rather than an ever-flattening lifetime
average.
"""

import numpy as np

from ..common import adversary, config

FEATURE_NAMES = (
    "pfr_short",
    "pfr_long",
    "pfr_delta",
    "drop_rate_large",
    "drop_rate_small",
    "fwd_latency_mean",
    "fwd_latency_std",
    "report_disagreement",
)
assert len(FEATURE_NAMES) == config.GAN_FEATURE_DIM


def _safe_ratio(numerator, denominator, default=1.0):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denominator > 0.0, numerator / np.maximum(denominator, 1e-9),
                        default)


class BehaviourFeatureExtractor(object):
    """Turns watchdog counters into per-(observer, subject) feature vectors."""

    def __init__(self, n_nodes, min_observations=None):
        self.n = int(n_nodes)
        self.min_observations = (
            config.MIN_OBSERVATIONS if min_observations is None
            else int(min_observations)
        )
        shape = (self.n, self.n)
        self._prev_sent = np.zeros(shape)
        self._prev_fwd = np.zeros(shape)
        self._prev_sent_large = np.zeros(shape)
        self._prev_fwd_large = np.zeros(shape)
        self._prev_sent_small = np.zeros(shape)
        self._prev_fwd_small = np.zeros(shape)

    def snapshot(self, nodes):
        """Record the current counters as the baseline for the next window."""
        self._prev_sent = nodes.sent_to.copy()
        self._prev_fwd = nodes.fwd_seen.copy()
        self._prev_sent_large = nodes.sent_large.copy()
        self._prev_fwd_large = nodes.fwd_seen_large.copy()
        self._prev_sent_small = nodes.sent_small.copy()
        self._prev_fwd_small = nodes.fwd_seen_small.copy()

    def report_disagreement(self, nodes):
        """|this observer's opinion - median opinion of the others|, per pair."""
        observed = nodes.sent_to >= self.min_observations
        reported = np.array(nodes.trust, dtype=float)

        # Apply each observer's *published* value, which for a slanderer is a lie.
        slanderers = np.flatnonzero(
            (nodes.role & 4) != 0  # FLAG_SLANDERER
        )
        for observer in slanderers:
            for subject in np.flatnonzero(observed[observer]):
                reported[observer, subject] = adversary.reported_trust(
                    nodes, int(observer), int(subject),
                    float(nodes.trust[observer, subject]),
                )

        disagreement = np.zeros_like(reported)
        for subject in range(self.n):
            observers = np.flatnonzero(observed[:, subject])
            if observers.size < 2:
                continue
            opinions = reported[observers, subject]
            median = float(np.median(opinions))
            disagreement[observers, subject] = np.abs(opinions - median)
        return disagreement

    def extract(self, nodes, update_snapshot=True):
        """Return ``(features, observer_ids, subject_ids)`` for watched pairs.

        ``features`` has shape ``(n_pairs, GAN_FEATURE_DIM)``.
        """
        d_sent = nodes.sent_to - self._prev_sent
        d_fwd = nodes.fwd_seen - self._prev_fwd
        d_sent_large = nodes.sent_large - self._prev_sent_large
        d_fwd_large = nodes.fwd_seen_large - self._prev_fwd_large
        d_sent_small = nodes.sent_small - self._prev_sent_small
        d_fwd_small = nodes.fwd_seen_small - self._prev_fwd_small

        pfr_short = _safe_ratio(d_fwd, d_sent, default=1.0)
        pfr_long = _safe_ratio(nodes.fwd_seen, nodes.sent_to, default=1.0)
        drop_large = 1.0 - _safe_ratio(d_fwd_large, d_sent_large, default=1.0)
        drop_small = 1.0 - _safe_ratio(d_fwd_small, d_sent_small, default=1.0)

        latency_mean = _safe_ratio(nodes.lat_sum, nodes.lat_n, default=0.0)
        second_moment = _safe_ratio(nodes.lat_sq, nodes.lat_n, default=0.0)
        latency_var = np.clip(second_moment - latency_mean ** 2, 0.0, None)
        latency_std = np.sqrt(latency_var)

        disagreement = self.report_disagreement(nodes)

        # A pair qualifies once it has enough total observations and has been
        # seen at least once in the current window.
        eligible = (nodes.sent_to >= self.min_observations) & (d_sent > 0.0)
        observers, subjects = np.nonzero(eligible)

        if observers.size == 0:
            if update_snapshot:
                self.snapshot(nodes)
            return (
                np.zeros((0, config.GAN_FEATURE_DIM)),
                observers.astype(np.int64),
                subjects.astype(np.int64),
            )

        features = np.column_stack([
            pfr_short[observers, subjects],
            pfr_long[observers, subjects],
            pfr_short[observers, subjects] - pfr_long[observers, subjects],
            drop_large[observers, subjects],
            drop_small[observers, subjects],
            # Latency is scaled into roughly [0, 1] so no single feature
            # dominates the discriminator's input purely by magnitude.
            latency_mean[observers, subjects] / max(1.0, config.HOP_DELAY_MAX),
            latency_std[observers, subjects] / max(1.0, config.HOP_DELAY_MAX),
            disagreement[observers, subjects],
        ]).astype(np.float64)

        features = np.nan_to_num(features, nan=0.0, posinf=1.0, neginf=0.0)
        features = np.clip(features, -1.0, 2.0)

        if update_snapshot:
            self.snapshot(nodes)
        return features, observers.astype(np.int64), subjects.astype(np.int64)


def aggregate_by_subject(scores, subjects, n_nodes, reduce="mean"):
    """Collapse per-pair anomaly scores into one score per node.

    Mean rather than max: a single hostile observer should not be able to get an
    honest node flagged on its own, which is precisely the slander attack.
    """
    totals = np.zeros(n_nodes)
    counts = np.zeros(n_nodes)
    np.add.at(totals, subjects, scores)
    np.add.at(counts, subjects, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        if reduce == "max":
            out = np.zeros(n_nodes)
            np.maximum.at(out, subjects, scores)
            return out
        return np.where(counts > 0, totals / np.maximum(counts, 1.0), 0.0)


def scenario_description(attack, malicious_fraction):
    """Human-readable label for a threat configuration."""
    return {
        "attack": attack,
        "malicious_fraction": float(malicious_fraction),
        "label": adversary.describe(attack, malicious_fraction),
        "behaviour": {
            "blackhole": "advertises a perfect route, drops 100% of data",
            "grayhole": "relays control and small packets, drops {0:.0%} of "
                        "packets >= {1} bytes".format(
                            config.GRAYHOLE_LARGE_DROP_P,
                            config.LARGE_PACKET_THRESHOLD),
            "trust_poisoning": "gray-hole that also publishes false PT_GID "
                               "reports (1.0 for colluders, 0.15 for the most "
                               "trusted honest nodes)",
            "none": "no adversary",
        }.get(str(attack).lower(), "unknown"),
    }
