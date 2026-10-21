"""Metric accumulation for one simulation run.

Beyond the five metrics both papers report (delay, packet loss, throughput,
PDR, network lifetime) we also track:

* **why** each packet was lost -- no route, link failure, a dead relay, or an
  adversary dropping it. Without this breakdown "PDR went down" says nothing
  about whether the protocol or the attacker caused it.
* **detection quality** -- true/false positive rates against the known ground
  truth of which nodes are actually malicious. This is how the advancement (C)
  earns its keep, and neither paper measures it.
* **control overhead** -- PT_NID / PT_GID / PT_CREV and route-discovery traffic,
  so the cost of the trust machinery is visible rather than assumed free.
"""

import numpy as np

# Reasons a packet failed to arrive.
LOSS_NO_ROUTE = "no_route"
LOSS_LINK = "link_failure"
LOSS_DEAD_NODE = "dead_relay"
LOSS_MALICIOUS = "malicious_drop"
LOSS_REASONS = (LOSS_NO_ROUTE, LOSS_LINK, LOSS_DEAD_NODE, LOSS_MALICIOUS)


class RunMetrics(object):
    """Accumulates every statistic for a single run."""

    def __init__(self, n_nodes):
        self.n_nodes = int(n_nodes)

        self.packets_sent = 0
        self.packets_received = 0
        self.bytes_delivered = 0
        self.bytes_lost = 0
        self.total_delay = 0.0
        self.total_hops = 0

        self.losses = dict((reason, 0) for reason in LOSS_REASONS)

        self.control_packets = 0
        self.route_discoveries = 0
        self.route_failures = 0

        self.rounds_completed = 0
        self.first_death_round = None
        self.eighty_percent_dead_round = None

        self.energy_spent = 0.0
        self.energy_harvested = 0.0

        # CMDP bookkeeping (advancement, docx step 4).
        self.cmdp_checks = 0
        self.cmdp_violations = 0

        # Rolling window used by the CMDP constraint and by the DRL state.
        self._window = []
        self._window_size = 100

        self.detection = {
            "tp": 0, "fp": 0, "fn": 0, "tn": 0,
            "tpr": 0.0, "fpr": 0.0, "precision": 0.0, "f1": 0.0,
        }
        self.extra = {}

    # -- packet accounting -------------------------------------------------

    def record_sent(self, packet):
        self.packets_sent += 1

    def record_delivered(self, packet, delay_ms, hops):
        self.packets_received += 1
        self.bytes_delivered += int(packet.size)
        self.total_delay += float(delay_ms)
        self.total_hops += int(hops)
        self._push_window(1.0)

    def record_lost(self, packet, reason):
        if reason not in self.losses:
            self.losses[reason] = 0
        self.losses[reason] += 1
        self.bytes_lost += int(packet.size)
        self._push_window(0.0)

    def _push_window(self, outcome):
        self._window.append(float(outcome))
        if len(self._window) > self._window_size:
            self._window.pop(0)

    def window_pdr(self, default=1.0):
        """Delivery ratio over the recent window, used by the CMDP constraint."""
        if not self._window:
            return float(default)
        return float(sum(self._window) / len(self._window))

    def record_cmdp_check(self, satisfied):
        self.cmdp_checks += 1
        if not satisfied:
            self.cmdp_violations += 1

    # -- network accounting ------------------------------------------------

    def record_control(self, count=1):
        self.control_packets += int(count)

    def record_discovery(self, found):
        self.route_discoveries += 1
        if not found:
            self.route_failures += 1

    def record_round(self, round_idx, nodes):
        self.rounds_completed = int(round_idx) + 1
        dead = int((~nodes.alive).sum())
        if dead > 0 and self.first_death_round is None:
            self.first_death_round = int(round_idx)
        if (
            self.eighty_percent_dead_round is None
            and dead >= 0.8 * self.n_nodes
        ):
            self.eighty_percent_dead_round = int(round_idx)

    # -- detection ---------------------------------------------------------

    def score_detection(self, nodes, detected_mask=None):
        """Compare the protocol's verdicts with the ground-truth roles."""
        truth = nodes.malicious_mask()
        if detected_mask is None:
            detected_mask = nodes.revoked | nodes.contested
        detected = np.asarray(detected_mask, dtype=bool)

        tp = int((detected & truth).sum())
        fp = int((detected & ~truth).sum())
        fn = int((~detected & truth).sum())
        tn = int((~detected & ~truth).sum())

        tpr = tp / float(tp + fn) if (tp + fn) else 0.0
        fpr = fp / float(fp + tn) if (fp + tn) else 0.0
        precision = tp / float(tp + fp) if (tp + fp) else 0.0
        f1 = (
            2.0 * precision * tpr / (precision + tpr)
            if (precision + tpr) > 0.0
            else 0.0
        )

        self.detection = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "tpr": tpr, "fpr": fpr, "precision": precision, "f1": f1,
        }
        return self.detection

    # -- results -----------------------------------------------------------

    def finalise(self, nodes=None):
        """Collapse the accumulators into a flat dict ready for a CSV row."""
        rounds = max(1, self.rounds_completed)
        received = self.packets_received

        avg_delay = self.total_delay / received if received else 0.0
        pdr = received / float(self.packets_sent) if self.packets_sent else 0.0
        avg_hops = self.total_hops / float(received) if received else 0.0

        # Throughput uses the senior's convention -- delivered bits divided by
        # rounds, scaled by 1000 -- so our numbers sit on the same axis as the
        # published ones. It is bits per round / 1000, not true kbps; the
        # report says so explicitly.
        throughput = (self.bytes_delivered * 8.0) / (rounds * 1000.0)

        lifetime = (
            self.first_death_round if self.first_death_round is not None else rounds
        )

        # PDR restricted to packets for which a route existed at all. This
        # separates protocol quality from raw topology: at the papers' own
        # parameters ~9% of node pairs are not even connected, and no routing
        # protocol can deliver across a partition.
        routable = self.packets_sent - self.losses.get(LOSS_NO_ROUTE, 0)
        pdr_routable = received / float(routable) if routable > 0 else 0.0

        row = {
            "packets_sent": self.packets_sent,
            "packets_received": received,
            "packets_lost": self.packets_sent - received,
            "pdr": pdr,
            "pdr_routable": pdr_routable,
            "avg_delay_ms": avg_delay,
            "avg_hops": avg_hops,
            "throughput": throughput,
            "bytes_delivered": self.bytes_delivered,
            "packet_loss_bytes": self.bytes_lost,
            "network_lifetime": lifetime,
            "rounds_completed": rounds,
            "eighty_pct_dead_round": (
                self.eighty_percent_dead_round
                if self.eighty_percent_dead_round is not None
                else rounds
            ),
            "control_packets": self.control_packets,
            "route_discoveries": self.route_discoveries,
            "route_failures": self.route_failures,
            "energy_spent": self.energy_spent,
            "energy_harvested": self.energy_harvested,
            "cmdp_checks": self.cmdp_checks,
            "cmdp_violations": self.cmdp_violations,
            "cmdp_violation_rate": (
                self.cmdp_violations / float(self.cmdp_checks)
                if self.cmdp_checks else 0.0
            ),
        }

        for reason in LOSS_REASONS:
            row["loss_" + reason] = self.losses.get(reason, 0)

        for key, value in self.detection.items():
            row["det_" + key] = value

        if nodes is not None:
            alive = nodes.alive
            row["nodes_alive"] = int(alive.sum())
            row["nodes_revoked"] = int(nodes.revoked.sum())
            row["nodes_contested"] = int(nodes.contested.sum())
            row["mean_residual_energy"] = (
                float(nodes.energy[alive].mean()) if alive.any() else 0.0
            )
            row["total_energy_consumed"] = float(
                (nodes.initial_energy - nodes.energy).sum()
            )

        row.update(self.extra)
        return row


def aggregate(rows):
    """Average a list of per-run result dicts, adding ``*_std`` columns."""
    if not rows:
        return {}

    keys = sorted(rows[0].keys())
    out = {}
    for key in keys:
        values = [row.get(key) for row in rows]
        numeric = [v for v in values if isinstance(v, (int, float, np.integer, np.floating))]
        if len(numeric) == len(values) and numeric:
            array = np.asarray(numeric, dtype=float)
            out[key] = float(array.mean())
            out[key + "_std"] = float(array.std())
        else:
            out[key] = values[0]
    out["n_runs"] = len(rows)
    return out
