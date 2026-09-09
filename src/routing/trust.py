"""Trust evaluation, consensus and revocation -- base.pdf 3.6 to 3.8.

The chain specified by the paper is:

1. **Watchdog.** Node i hands a packet to neighbour j and listens for j to
   relay it. That gives the Packet Forwarding Ratio ``PFR = PF / PR``.
2. **PT_NID.** Neighbours periodically exchange those ratios.
3. **Trust update.** ``T <- 0.7*T + 0.3*PFR`` (Lekha Eq. 20; base.pdf uses the
   raw ratio, the moving average is the senior's refinement).
4. **PT_GID consensus.** "If many nodes complain about the misbehaviour of a
   single node, that node will be considered malicious."
5. **Energy excuse.** Before blaming a node, check its battery -- a node too
   flat to relay is not malicious. base.pdf 3.7 is explicit about this.
6. **PT_CREV.** Broadcast the revocation; every node drops routes through it.

Step 4 is precisely what the slander adversary attacks: the vote is only as
honest as the nodes casting it.
"""

import numpy as np

from ..common import adversary, config
from . import packets


def reset_observations(nodes):
    """Clear the watchdog tables (used between runs)."""
    for name in (
        "sent_to", "fwd_seen", "sent_large", "fwd_seen_large",
        "sent_small", "fwd_seen_small", "lat_sum", "lat_sq", "lat_n",
    ):
        getattr(nodes, name).fill(0.0)
    nodes.trust.fill(config.INITIAL_TRUST)
    nodes.trust_history.fill(config.INITIAL_TRUST)
    nodes.accusations.fill(0)


def observe_forward(nodes, observer, subject, packet, forwarded, latency=0.0):
    """Record that ``observer`` watched ``subject`` either relay or drop a packet."""
    observer = int(observer)
    subject = int(subject)

    nodes.sent_to[observer, subject] += 1.0
    if packet.is_large:
        nodes.sent_large[observer, subject] += 1.0
    else:
        nodes.sent_small[observer, subject] += 1.0

    if forwarded:
        nodes.fwd_seen[observer, subject] += 1.0
        if packet.is_large:
            nodes.fwd_seen_large[observer, subject] += 1.0
        else:
            nodes.fwd_seen_small[observer, subject] += 1.0
        nodes.lat_sum[observer, subject] += float(latency)
        nodes.lat_sq[observer, subject] += float(latency) * float(latency)
        nodes.lat_n[observer, subject] += 1.0


def refresh_trust(nodes, smoothing=None):
    """Moving-average trust update over every observed pair (Lekha Eq. 20)."""
    weight = config.TRUST_SMOOTHING if smoothing is None else float(smoothing)
    pfr = nodes.observed_pfr()
    observed = nodes.sent_to > 0.0
    updated = weight * nodes.trust + (1.0 - weight) * pfr
    nodes.trust = np.where(observed, updated, nodes.trust)
    np.clip(nodes.trust, 0.0, 1.0, out=nodes.trust)
    return nodes.trust


def push_trust_history(nodes):
    """Slide the trust history window (Lekha Eq. 27)."""
    nodes.trust_history[:-1] = nodes.trust_history[1:]
    nodes.trust_history[-1] = nodes.trust


def predicted_trust(nodes, weights=None):
    """Weighted trust forecast over the history window (Lekha Eq. 26)."""
    w = config.PREDICTIVE_WEIGHTS if weights is None else weights
    history = nodes.trust_history
    depth = min(len(w), history.shape[0])
    prediction = np.zeros_like(nodes.trust)
    # w[0] is the weight on the most recent value.
    for offset in range(depth):
        prediction += w[offset] * history[history.shape[0] - 1 - offset]
    return np.clip(prediction, 0.0, 1.0)


def pt_nid_round(nodes, run_metrics=None):
    """Periodic PT_NID exchange. Counts one control packet per active node."""
    active = int(nodes.eligible_mask().sum())
    if run_metrics is not None:
        run_metrics.record_control(active)
    return active


def _observer_counts(nodes):
    """How many nodes have actually watched each subject."""
    return (nodes.sent_to >= config.MIN_OBSERVATIONS).sum(axis=0)


def build_accusations(nodes, enable_slander=True):
    """Each observer decides whether to report each watched neighbour.

    Honest observers report what they measured. Slanderers publish inverted
    values, which is how the consensus of base.pdf 3.7 gets poisoned.
    """
    nodes.accusations.fill(0)
    watched = nodes.sent_to >= config.MIN_OBSERVATIONS
    observers = np.flatnonzero(nodes.alive & (~nodes.revoked))

    for observer in observers:
        subjects = np.flatnonzero(watched[observer])
        for subject in subjects:
            if subject == observer:
                continue
            measured = float(nodes.trust[observer, subject])
            if enable_slander:
                reported = adversary.reported_trust(
                    nodes, int(observer), int(subject), measured
                )
            else:
                reported = measured
            if reported < config.TRUST_THRESHOLD:
                nodes.accusations[observer, subject] = 1
    return nodes.accusations


def pt_gid_round(nodes, run_metrics=None, enable_slander=True,
                 enable_energy_excuse=True, route_cache=None, round_idx=0):
    """PT_GID consensus followed by PT_CREV revocation (base.pdf 3.6-3.7).

    Returns the list of node ids revoked during this round.
    """
    build_accusations(nodes, enable_slander=enable_slander)

    accusers = nodes.accusations.sum(axis=0)
    observers = _observer_counts(nodes)
    threshold = np.maximum(
        config.GID_MIN_ACCUSERS,
        np.ceil(config.GID_CONSENSUS_FRACTION * observers),
    )

    condemned = (accusers >= threshold) & (observers >= config.GID_MIN_ACCUSERS)
    condemned &= ~nodes.revoked
    condemned &= nodes.alive

    if enable_energy_excuse:
        # base.pdf 3.7 -- "before labeling it malicious, the energy level will
        # be checked. This helps prevent punishing an exemplary node just
        # because of its lower power."
        flat_battery = nodes.energy <= nodes.energy_threshold()
        condemned &= ~flat_battery

    revoked_now = np.flatnonzero(condemned)
    for node_id in revoked_now:
        nodes.revoked[node_id] = True
        nodes.revocation_round[node_id] = int(round_idx)
        if route_cache is not None:
            route_cache.drop_node(int(node_id))

    if run_metrics is not None:
        active = int(nodes.eligible_mask().sum())
        # One PT_GID beacon per active node, plus one PT_CREV broadcast per
        # revocation reaching every active node.
        run_metrics.record_control(active + active * len(revoked_now))

    return [int(node_id) for node_id in revoked_now]


def crev_packets(nodes, revoked_ids, round_idx):
    """Materialise the PT_CREV broadcasts, for logging and inspection."""
    return [
        packets.CrevPacket(
            sender=-1,
            timestamp=int(round_idx),
            revoked=int(node_id),
            evidence=float(nodes.accusations[:, node_id].sum()),
        )
        for node_id in revoked_ids
    ]
