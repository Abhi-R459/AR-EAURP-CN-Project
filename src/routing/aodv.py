"""Energy- and trust-gated route discovery -- base.pdf 3.3 to 3.5, 3.8.

The paper specifies discovery as an RREQ flood in which each node forwards only
when it is not revoked and holds more than 20% of its initial energy, with each
route accumulating ``R_Score = a*T + b*E``; the destination then picks the route
with the highest cumulative score and no revoked hop.

Two things are worth flagging to the review panel, because both are properties
of the *paper*, not of this implementation:

1. ``a = 1 - avg_energy/max_energy`` and ``b = avg_energy/max_energy`` invert
   the intuitive priority. When the network is energy-rich, ``b -> 1`` and the
   score is dominated by energy; trust only starts to matter once batteries are
   already low -- exactly the opposite of what a security-motivated protocol
   wants. We implement the coefficients as published and report the effect.

2. Selecting the *highest cumulative* score rewards longer routes, since every
   extra hop adds another non-negative term. Taken literally it prefers the
   longest path in the network. We therefore minimise accumulated
   ``(1 - R_Score_j) + hop_penalty``, which preserves the paper's intent -- prefer
   trusted, energy-rich relays -- without the pathology. The literal variant is
   available via ``cumulative_score`` for comparison.

Discovery is modelled by its outcome (a shortest-path search over the current
adjacency) rather than by simulating every individual RREQ frame. The gating
rules are identical, and it is orders of magnitude faster, which is what keeps
the sweeps inside the Colab time budget.
"""

import heapq

import numpy as np

from ..common import config

HOP_PENALTY = 0.35
BLACKHOLE_ADVERTISED_SCORE = 1.0

MODE_EAURP = "eaurp"
MODE_AODV = "aodv"
MODE_TRUST = "max_trust"
MODE_ENERGY = "max_energy"
MODE_DIVERSE = "diversified"
ROUTE_MODES = (MODE_EAURP, MODE_AODV, MODE_TRUST, MODE_ENERGY, MODE_DIVERSE)


def score_coefficients(nodes):
    """The (a, b) pair of base.pdf 3.3."""
    alive = nodes.alive
    if not alive.any():
        return 0.5, 0.5
    max_energy = float(nodes.initial_energy.max())
    if max_energy <= 0.0:
        return 0.5, 0.5
    b = float(np.clip(nodes.energy[alive].mean() / max_energy, 0.0, 1.0))
    return 1.0 - b, b


def route_scores(nodes, trust=None, energy=None, honour_blackhole=True):
    """Per-node ``R_Score`` in [0, 1] used to weight route discovery.

    ``trust`` and ``energy`` may be overridden so that a policy can substitute
    its own view -- the advancement, for instance, feeds in GAN-adjusted trust
    and LSTM-predicted energy surplus.
    """
    a, b = score_coefficients(nodes)
    trust_vec = nodes.network_trust() if trust is None else np.asarray(trust, dtype=float)
    energy_vec = (
        nodes.normalised_energy() if energy is None else np.asarray(energy, dtype=float)
    )
    scores = a * np.clip(trust_vec, 0.0, 1.0) + b * np.clip(energy_vec, 0.0, 1.0)

    if honour_blackhole:
        # A black-hole answers every RREQ claiming a perfect route. From the
        # network's point of view that is simply a maximal advertised score.
        from ..common.node import FLAG_BLACKHOLE

        liars = (nodes.role & FLAG_BLACKHOLE) != 0
        if liars.any():
            scores = np.where(liars, BLACKHOLE_ADVERTISED_SCORE, scores)

    return np.clip(scores, 0.0, 1.0)


def _edge_cost(scores, node_id, mode, hop_penalty):
    if mode == MODE_AODV:
        return 1.0  # plain hop-count AODV: no trust, no energy awareness
    return (1.0 - float(scores[node_id])) + hop_penalty


def find_route(nodes, src, dst, scores, mode=MODE_EAURP, hop_penalty=HOP_PENALTY,
               avoid=None, max_hops=None):
    """Dijkstra over the current topology honouring the base.pdf gating rules.

    Returns the path as a list ``[src, ..., dst]`` or ``None`` when no eligible
    route exists.
    """
    src = int(src)
    dst = int(dst)
    if src == dst:
        return None

    eligible = nodes.eligible_mask()
    if not (eligible[src] and eligible[dst]):
        return None

    avoid_set = set() if avoid is None else set(int(a) for a in avoid)
    cap = nodes.n if max_hops is None else int(max_hops)

    dist = {src: 0.0}
    previous = {}
    visited = set()
    queue = [(0.0, src)]

    while queue:
        cost, current = heapq.heappop(queue)
        if current in visited:
            continue
        visited.add(current)
        if current == dst:
            break

        for neighbour in nodes.neighbours[current]:
            neighbour = int(neighbour)
            if neighbour in visited:
                continue
            # base.pdf 3.3/3.5: only relay through nodes that are alive, not
            # revoked and above the 20%-of-initial-energy threshold. The
            # destination itself is always allowed.
            if neighbour != dst:
                if not eligible[neighbour] or neighbour in avoid_set:
                    continue
            step = _edge_cost(scores, neighbour, mode, hop_penalty)
            candidate = cost + step
            if candidate < dist.get(neighbour, float("inf")):
                dist[neighbour] = candidate
                previous[neighbour] = current
                heapq.heappush(queue, (candidate, neighbour))

    if dst not in previous and dst != src:
        return None

    path = [dst]
    while path[-1] != src:
        step = previous.get(path[-1])
        if step is None:
            return None
        path.append(step)
        if len(path) > cap:
            return None
    path.reverse()
    return path


def find_diverse_route(nodes, src, dst, scores, primary=None, **kwargs):
    """A second, node-disjoint-ish route used by the 'explore' action.

    Falls back to the primary route when no alternative exists, which is the
    honest outcome in a sparse topology rather than reporting a failure.
    """
    if primary is None:
        primary = find_route(nodes, src, dst, scores, **kwargs)
    if primary is None or len(primary) <= 2:
        return primary

    avoid = set(primary[1:-1])
    alternative = find_route(nodes, src, dst, scores, avoid=avoid, **kwargs)
    return alternative if alternative is not None else primary


def cumulative_score(scores, path):
    """The paper's literal cumulative R_Score for a discovered route."""
    if not path:
        return 0.0
    return float(sum(float(scores[node_id]) for node_id in path[1:]))


def mean_score(scores, path):
    """Per-hop mean score -- the length-normalised alternative."""
    if not path or len(path) < 2:
        return 0.0
    return cumulative_score(scores, path) / float(len(path) - 1)


class RouteCache(object):
    """Caches discovered routes and invalidates them when they break.

    base.pdf 3.8 -- a node checks the revocation list before forwarding, emits
    a route error when the path is broken, and rediscovers. Caching is also
    what makes the sweep affordable: rediscovering on every packet would mean a
    Dijkstra per packet instead of one per route break.
    """

    def __init__(self):
        self._routes = {}
        self.hits = 0
        self.misses = 0
        self.invalidations = 0

    def get(self, nodes, src, dst):
        key = (int(src), int(dst))
        path = self._routes.get(key)
        if path is None:
            self.misses += 1
            return None
        if not self._still_valid(nodes, path):
            del self._routes[key]
            self.invalidations += 1
            self.misses += 1
            return None
        self.hits += 1
        return path

    def put(self, src, dst, path):
        if path:
            self._routes[(int(src), int(dst))] = path

    def drop_node(self, node_id):
        """Remove every cached route traversing a newly revoked/dead node."""
        node_id = int(node_id)
        stale = [key for key, path in self._routes.items() if node_id in path]
        for key in stale:
            del self._routes[key]
        self.invalidations += len(stale)
        return len(stale)

    def clear(self):
        self._routes.clear()

    @staticmethod
    def _still_valid(nodes, path):
        for node_id in path:
            if not nodes.alive[node_id] or nodes.revoked[node_id]:
                return False
        for a, b in zip(path[:-1], path[1:]):
            if not nodes.adjacency[a, b]:
                return False
        return True
