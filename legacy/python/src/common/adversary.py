"""Threat model -- AR-EAURP advancement, docx step 1.

Three adversary behaviours, composable through the role bit flags in
``node.py``:

``blackhole``
    Answers every route request claiming an excellent route, then drops 100% of
    the data it is asked to relay. It keeps relaying *control* traffic so that
    it stays inside the topology and keeps attracting routes.

``grayhole`` (selective forwarding)
    Relays control traffic and small packets, and drops large data packets with
    probability ``GRAYHOLE_LARGE_DROP_P``. This is the attack the advancement
    doc is built around: with a 512-1024 byte size distribution and a 700-byte
    boundary, the observed Packet Forwarding Ratio lands near 0.8 -- comfortably
    above the 0.6 revocation threshold of base.pdf 3.7. A protocol that watches
    only a scalar PFR cannot see it at all.

``trust_poisoning``
    A gray-hole that also slanders: in its PT_GID reports it vouches for its
    fellow attackers (trust 1.0) and accuses the most trusted honest nodes
    (trust 0.15), attacking the consensus mechanism rather than the data plane.

Placement is drawn from the dedicated adversary stream, so the same nodes are
malicious no matter which protocol is under test.
"""

import numpy as np

from . import config
from .node import FLAG_BLACKHOLE, FLAG_GRAYHOLE, FLAG_SLANDERER, ROLE_HONEST

ATTACK_ROLES = {
    "none": ROLE_HONEST,
    "blackhole": FLAG_BLACKHOLE,
    "grayhole": FLAG_GRAYHOLE,
    "trust_poisoning": FLAG_GRAYHOLE | FLAG_SLANDERER,
}


def assign_roles(nodes, attack, malicious_fraction, rng_adversary):
    """Mark a fraction of the nodes as adversarial and return their indices."""
    nodes.role[:] = ROLE_HONEST
    key = str(attack).lower()
    if key not in ATTACK_ROLES:
        raise ValueError(
            "unknown attack {0!r}; choose from {1}".format(attack, sorted(ATTACK_ROLES))
        )

    role = ATTACK_ROLES[key]
    fraction = float(malicious_fraction)
    if role == ROLE_HONEST or fraction <= 0.0:
        return np.zeros(0, dtype=np.int64)

    count = int(round(fraction * nodes.n))
    count = max(0, min(count, nodes.n - 2))  # always leave an honest pair
    if count == 0:
        return np.zeros(0, dtype=np.int64)

    chosen = rng_adversary.choice(nodes.n, size=count, replace=False)
    nodes.role[chosen] = role
    return np.sort(chosen)


def forwards_data(nodes, node_id, packet, rng_adversary):
    """Does ``node_id`` actually relay this data packet?

    Returns True for honest nodes. This is the single place where adversarial
    packet-level behaviour is decided.
    """
    role = int(nodes.role[node_id])
    if role == ROLE_HONEST:
        return True

    if role & FLAG_BLACKHOLE:
        return False

    if role & FLAG_GRAYHOLE:
        if not packet.is_large:
            return True  # small packets pass, keeping the observed PFR high
        return bool(rng_adversary.random() >= config.GRAYHOLE_LARGE_DROP_P)

    # A pure slanderer attacks the control plane only; its data plane is honest.
    return True


def forwards_control(nodes, node_id):
    """Adversaries relay control traffic to stay reachable and attract routes."""
    return True


def advertises_false_route(nodes, node_id):
    """Black-holes claim a perfect route to everything (base.pdf threat model)."""
    return bool(int(nodes.role[node_id]) & FLAG_BLACKHOLE)


def reported_trust(nodes, observer, subject, honest_value):
    """Trust value ``observer`` publishes about ``subject`` in its PT_GID report.

    Honest nodes report what they measured. Slanderers invert the signal: they
    vouch for colluders and accuse whichever honest nodes are most trusted,
    which is precisely what makes the majority vote of base.pdf 3.7 exploitable.
    """
    if not (int(nodes.role[observer]) & FLAG_SLANDERER):
        return float(honest_value)

    if int(nodes.role[subject]) != ROLE_HONEST:
        return config.SLANDER_HIGH
    return config.SLANDER_LOW


def slander_targets(nodes, observer, k=None):
    """The honest neighbours a slanderer will accuse: the most trusted ones."""
    neighbours = nodes.neighbours[observer]
    if neighbours.size == 0:
        return np.zeros(0, dtype=np.int64)

    honest = neighbours[nodes.role[neighbours] == ROLE_HONEST]
    if honest.size == 0:
        return honest

    order = np.argsort(-nodes.trust[observer, honest])
    if k is None:
        k = max(1, honest.size // 2)
    return honest[order[: int(k)]]


def describe(attack, malicious_fraction):
    """Label used in CSV output and plot legends."""
    if str(attack).lower() == "none" or malicious_fraction <= 0.0:
        return "clean"
    return "{0}@{1:.0f}%".format(attack, 100.0 * float(malicious_fraction))
