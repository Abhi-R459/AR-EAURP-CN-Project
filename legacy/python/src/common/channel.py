"""Per-hop link model.

Neither source paper models a link: both compute one global success
probability per *packet* and flip a coin. Here reliability is a property of the
individual hop, degrading with the fraction of the communication range used
and with node speed. That is the minimum needed for a routing decision to have
consequences -- a longer path really is riskier than a short one.

Delay follows Lekha.pdf Eq. (12): ``D = D_base + H * D_hop``, accumulated hop
by hop rather than sampled once from a hop count drawn at random.
"""

import numpy as np

from . import config


def link_reliability(nodes, i, j, distance=None):
    """Probability that a single transmission from i to j is received."""
    if distance is None:
        dx = nodes.x[i] - nodes.x[j]
        dy = nodes.y[i] - nodes.y[j]
        distance = float(np.sqrt(dx * dx + dy * dy))

    range_use = min(1.0, distance / config.COMM_RANGE)
    speed_use = min(1.0, max(nodes.speed[i], nodes.speed[j]) / config.MAX_SPEED)

    reliability = (
        config.LINK_BASE_RELIABILITY
        - config.LINK_RANGE_PENALTY * range_use
        - config.LINK_MOBILITY_PENALTY * speed_use
    )
    return float(np.clip(reliability, config.LINK_MIN_RELIABILITY, 1.0))


def transmit(nodes, i, j, rng_channel, distance=None):
    """Attempt one hop. Returns True when the frame is received by j."""
    return bool(rng_channel.random() < link_reliability(nodes, i, j, distance))


def hop_delay(rng_channel):
    """Per-hop delay contribution in milliseconds (Lekha Eq. 12)."""
    return float(rng_channel.uniform(config.HOP_DELAY_MIN, config.HOP_DELAY_MAX))


def base_delay(rng_channel):
    """Fixed per-packet processing delay in milliseconds (Lekha Eq. 12)."""
    return float(rng_channel.uniform(config.BASE_DELAY_MIN, config.BASE_DELAY_MAX))


def spend_hop_energy(nodes, sender, receiver, size_bytes, energy_model):
    """Charge a transmission to the sender and a reception to the receiver."""
    tx_cost = energy_model.transmit_cost(size_bytes)
    rx_cost = energy_model.receive_cost(size_bytes)
    nodes.energy[sender] -= tx_cost
    nodes.energy[receiver] -= rx_cost
    return tx_cost + rx_cost
