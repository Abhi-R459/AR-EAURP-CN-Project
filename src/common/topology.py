"""Neighbour discovery -- Lekha.pdf Eq. (4).

A link exists between i and j iff the Euclidean distance between them is at
most ``COMM_RANGE``. Distances are computed as one vectorised N x N operation;
for N <= 200 this is a few hundred microseconds, versus tens of milliseconds
for the nested Python loop the senior's notebook uses.
"""

import numpy as np

from . import config


def pairwise_distances(nodes):
    """Full N x N Euclidean distance matrix."""
    points = np.stack((nodes.x, nodes.y), axis=1)
    diff = points[:, None, :] - points[None, :, :]
    return np.sqrt((diff * diff).sum(axis=-1))


def rebuild(nodes, comm_range=None):
    """Recompute adjacency and per-node neighbour lists.

    Dead and revoked nodes are removed from the topology: a flat battery cannot
    relay, and a revoked node is excluded from all network activity
    (base.pdf 3.7).
    """
    radius = config.COMM_RANGE if comm_range is None else float(comm_range)
    distances = pairwise_distances(nodes)

    adjacency = distances <= radius
    np.fill_diagonal(adjacency, False)

    usable = nodes.alive & (~nodes.revoked)
    adjacency &= usable[:, None]
    adjacency &= usable[None, :]

    nodes.adjacency = adjacency
    nodes.neighbours = [np.flatnonzero(row) for row in adjacency]
    return distances


def link_exists(nodes, i, j):
    """True when i and j are currently one hop apart."""
    return bool(nodes.adjacency[i, j])


def path_is_valid(nodes, path):
    """True when every hop of ``path`` still exists and every node is usable."""
    if not path or len(path) < 2:
        return False
    for node_id in path:
        if not nodes.alive[node_id] or nodes.revoked[node_id]:
            return False
    for a, b in zip(path[:-1], path[1:]):
        if not nodes.adjacency[a, b]:
            return False
    return True


def connected_pairs(nodes, rng, count):
    """Draw ``count`` (src, dst) pairs that are distinct and currently usable.

    Falls back to any two distinct eligible nodes; reachability is left to the
    routing layer so that "no route found" remains a real, measurable outcome.
    """
    eligible = np.flatnonzero(nodes.eligible_mask())
    if eligible.size < 2:
        return []
    pairs = []
    for _ in range(int(count)):
        src, dst = rng.choice(eligible, size=2, replace=False)
        pairs.append((int(src), int(dst)))
    return pairs
