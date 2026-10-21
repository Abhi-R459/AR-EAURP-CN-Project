"""Destination-driven mobility -- Lekha.pdf Eq. (5)-(6).

Each node walks toward a randomly assigned destination; on arrival a fresh
destination is drawn. Displacement per round is ``speed * MOVE_SCALE``, which
reproduces the senior's ``node.x += (dx/dist) * node.speed * 0.001``.
"""

import numpy as np

from . import config

ARRIVAL_RADIUS = 1.0


def assign_speeds(nodes, speed, rng_mobility=None, jitter=0.0):
    """Set every node's speed, optionally with multiplicative jitter."""
    base = np.full(nodes.n, float(speed))
    if jitter > 0.0 and rng_mobility is not None:
        base = base * rng_mobility.uniform(1.0 - jitter, 1.0 + jitter, nodes.n)
    nodes.speed = np.clip(base, 0.0, None)
    return nodes.speed


def step(nodes, rng_mobility):
    """Advance every node one round toward its destination (Eq. 5-6)."""
    dx = nodes.dest_x - nodes.x
    dy = nodes.dest_y - nodes.y
    dist = np.sqrt(dx * dx + dy * dy)

    # Nodes that have arrived pick a new destination and stay put this round,
    # matching the senior's `continue` branch.
    arrived = dist < ARRIVAL_RADIUS
    n_arrived = int(arrived.sum())
    if n_arrived:
        nodes.dest_x[arrived] = rng_mobility.uniform(0.0, config.AREA_SIZE, n_arrived)
        nodes.dest_y[arrived] = rng_mobility.uniform(0.0, config.AREA_SIZE, n_arrived)

    moving = ~arrived
    if moving.any():
        safe = np.where(dist > 0.0, dist, 1.0)
        stride = nodes.speed * config.MOVE_SCALE
        nodes.x[moving] += (dx[moving] / safe[moving]) * stride[moving]
        nodes.y[moving] += (dy[moving] / safe[moving]) * stride[moving]

    # Keep the swarm inside the deployment square. The senior's code lets nodes
    # drift out of the 1000x1000 area at high speed; clamping keeps the node
    # density (and therefore the connectivity) consistent across speeds, which
    # is what makes the speed sweep interpretable.
    np.clip(nodes.x, 0.0, config.AREA_SIZE, out=nodes.x)
    np.clip(nodes.y, 0.0, config.AREA_SIZE, out=nodes.y)
