"""Track-1 scaffolding for DRL-EAURP, built from Lekha.pdf's equations.

Everything here traces to a numbered equation in the paper:

    Eq. (4)      link exists iff d_ij <= R
    Eq. (5)-(6)  destination-driven mobility
    Eq. (8)      energy depletion, dE in [0.05, 0.15]
    Eq. (9)-(13) PDR, throughput, average delay, per-packet delay, packet loss
    Eq. (19)     PFR_i = F_i / R_i
    Eq. (20)     T_i(t+1) = 0.7 T_i(t) + 0.3 PFR_i
    Eq. (21)     malicious iff T_i < 0.6 and R_i > 5
    Eq. (22)     M_i = 1 / (1 + v_i / v_max)
    Eq. (23)     E_norm = E_i / E_init

DOCUMENTED ASSUMPTIONS -- the paper does not specify these, so a choice had to
be made. Each is flagged here and repeated in the report, because they are
exactly the places where an independent reading can diverge from the delivered
code.

A1. **Who accrues forwarding credit.** Eq. (19) defines ``PFR = F_i / R_i`` but
    the paper never says which nodes increment F and R. It does model a packet
    as traversing ``H_k`` hops (Eq. 12), so we attribute the forward/receive
    counters to the ``H_k`` relay nodes actually carrying the packet. That makes
    trust a property of relaying behaviour, which is what Eq. (19) is clearly
    for. The delivered code instead credits the randomly chosen source and
    destination, which are not relays at all.

A2. **Energy drain band.** Eq. (8) gives one band, ``dE in [0.05, 0.15]``, and
    Sec. IV-D-6 says depletion is "continuously modeled as in" that equation for
    the DRL model too. A therefore uses [0.05, 0.15] for *every* variant. The
    delivered code silently uses [0.04, 0.12] for ATEAURP/PSE/DRL, which is
    where their entire network-lifetime advantage comes from.

A3. **Hop count.** Eq. (12) uses ``H_k`` without defining its distribution. We
    draw ``H ~ U{3..10}``, the only hop range consistent with the paper's
    reported delays.
"""

import math
import random

# Paper parameters -- Lekha.pdf Sec. IV-A
AREA_SIZE = 1000.0
COMM_RANGE = 150.0
INITIAL_ENERGY = 100.0
MIN_SPEED = 10000.0
MAX_SPEED = 40000.0
TRUST_THRESHOLD = 0.6          # Eq. (21)
MIN_RECEIVED_FOR_VERDICT = 5   # Eq. (21)

# Eq. (8): the single drain band the paper specifies. See assumption A2.
PAPER_DRAIN_MIN = 0.05
PAPER_DRAIN_MAX = 0.15

HOP_MIN, HOP_MAX = 3, 10       # assumption A3
PACKET_MIN, PACKET_MAX = 512, 1024
SIM_ROUNDS = 2000
DEAD_FRACTION = 0.8

# Deviations between the published paper and the delivered code, found by
# implementing A from the equations first and diffing afterwards.
DEVIATIONS = [
    {
        "topic": "Energy drain band",
        "paper": "Eq. (8): dE in [0.05, 0.15] for the energy model; Sec. IV-D-6 "
                 "states DRL-EAURP depletes energy the same way.",
        "code": "run_simulation uses U(0.05, 0.15) but run_proposed_simulation, "
                "run_predictive_simulation and run_drl_simulation all use "
                "U(0.04, 0.12).",
        "impact": "The reported ~1230-round lifetime of the proposed models "
                  "versus ~1000 for the base is produced entirely by this "
                  "undocumented constant change, not by any protocol behaviour.",
    },
    {
        "topic": "Trust counter attribution",
        "paper": "Eq. (19) PFR_i = F_i / R_i, i.e. what node i forwarded out of "
                 "what it received.",
        "code": "nodes[src].forwarded += 1 and nodes[dst].received += 1 -- the "
                "numerator and denominator are accumulated on two different, "
                "randomly chosen nodes that are not relays.",
        "impact": "PFR is not a forwarding ratio of anything. node.trust becomes "
                  "an unanchored drift, and node.malicious is never read.",
    },
    {
        "topic": "Existing baseline",
        "paper": "Eq. (14)-(18) openly define 'Existing' as EAURP output scaled "
                 "by fixed constants.",
        "code": "Same -- delay x1.2, loss x1.5, throughput x0.7, PDR x0.85, "
                "lifetime x0.98.",
        "impact": "Faithfully implemented, but it is a derived curve, not a "
                  "competing protocol. Every 'improvement over Existing' is "
                  "arithmetic, not a measurement.",
    },
    {
        "topic": "DRL action effect",
        "paper": "Eq. (36): P = P_base + 0.08 if A=0 else P_base + 0.02.",
        "code": "Same.",
        "impact": "Action 0 dominates action 1 unconditionally and independently "
                  "of state, so the optimal policy is constant. The Q-table "
                  "converges within a handful of updates and the state "
                  "<T,E,M> has no influence on the outcome.",
    },
    {
        "topic": "Trust threshold effect",
        "paper": "Eq. (21) classifies a node malicious when T_i < 0.6 and R_i > 5.",
        "code": "Sets node.malicious, but no routing, scoring or delivery "
                "decision ever reads that flag.",
        "impact": "The security mechanism has no effect on any reported metric.",
    },
]


class PaperNode(object):
    """A node exactly as the paper describes one."""

    def __init__(self, node_id, rng):
        self.id = node_id
        self.x = rng.uniform(0.0, AREA_SIZE)
        self.y = rng.uniform(0.0, AREA_SIZE)
        self.dest_x = rng.uniform(0.0, AREA_SIZE)
        self.dest_y = rng.uniform(0.0, AREA_SIZE)
        self.speed = rng.uniform(MIN_SPEED, MAX_SPEED)
        self.energy = INITIAL_ENERGY

        # Eq. (19)-(21)
        self.forwarded = 0
        self.received = 0
        self.trust = 1.0
        self.malicious = False

        # Eq. (25): trust history for the predictive model
        self.trust_history = [1.0, 1.0, 1.0]
        self.neighbors = []

    def mobility_factor(self):
        """Eq. (22)."""
        return 1.0 / (1.0 + self.speed / MAX_SPEED)

    def normalised_energy(self):
        """Eq. (23)."""
        return max(0.0, self.energy) / INITIAL_ENERGY


def create_network(n, rng):
    return [PaperNode(index, rng) for index in range(int(n))]


def update_neighbors(nodes):
    """Eq. (4): a link exists iff the Euclidean distance is at most R."""
    for node in nodes:
        node.neighbors = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            first, second = nodes[i], nodes[j]
            dx = first.x - second.x
            dy = first.y - second.y
            if math.sqrt(dx * dx + dy * dy) <= COMM_RANGE:
                first.neighbors.append(second.id)
                second.neighbors.append(first.id)


def move_network(nodes, rng):
    """Eq. (5)-(6): move each node toward its destination."""
    for node in nodes:
        dx = node.dest_x - node.x
        dy = node.dest_y - node.y
        distance = math.sqrt(dx * dx + dy * dy)
        if distance < 1.0:
            node.dest_x = rng.uniform(0.0, AREA_SIZE)
            node.dest_y = rng.uniform(0.0, AREA_SIZE)
            continue
        node.x += (dx / distance) * node.speed * 0.001
        node.y += (dy / distance) * node.speed * 0.001


def deplete_energy(nodes, rng, drain_min=PAPER_DRAIN_MIN, drain_max=PAPER_DRAIN_MAX):
    """Eq. (8). Returns the ids of nodes whose battery ran out this round."""
    newly_dead = []
    for node in nodes:
        if node.energy <= 0.0:
            continue
        node.energy -= rng.uniform(drain_min, drain_max)
        if node.energy <= 0.0:
            newly_dead.append(node.id)
    return newly_dead


def relay_nodes(nodes, source, destination, hops, rng):
    """Assumption A1 -- the ``H_k`` relays that actually carry a packet.

    The paper models a packet as crossing ``H_k`` hops but never names the
    intermediate nodes, so we sample them. This is what lets Eq. (19)'s
    forwarding ratio describe forwarding.
    """
    candidates = [node.id for node in nodes
                  if node.id not in (source, destination) and node.energy > 0.0]
    if not candidates:
        return []
    count = min(int(hops), len(candidates))
    return rng.sample(candidates, count)


def update_trust(node):
    """Eq. (19)-(21)."""
    if node.received == 0:
        return
    pfr = node.forwarded / float(node.received)
    node.trust = 0.7 * node.trust + 0.3 * pfr
    if node.trust < TRUST_THRESHOLD and node.received > MIN_RECEIVED_FOR_VERDICT:
        node.malicious = True


def push_trust_history(node):
    """Eq. (27): slide the three-deep trust history."""
    node.trust_history.append(node.trust)
    if len(node.trust_history) > 3:
        node.trust_history.pop(0)


def predict_trust(node):
    """Eq. (26): T_pred = 0.5 T_t + 0.3 T_{t-1} + 0.2 T_{t-2}."""
    history = node.trust_history
    return 0.5 * history[-1] + 0.3 * history[-2] + 0.2 * history[-3]


def network_state(nodes):
    """Eq. (30)-(32): the mean trust, energy and mobility of the network."""
    live = [node for node in nodes if node.energy > 0.0] or nodes
    count = float(len(live))
    trust = sum(node.trust for node in live) / count
    energy = sum(node.normalised_energy() for node in live) / count
    mobility = sum(node.mobility_factor() for node in live) / count
    return trust, energy, mobility


def run_paper_simulation(variant, num_nodes, speed, rounds=SIM_ROUNDS, seed=42,
                         drain_min=PAPER_DRAIN_MIN, drain_max=PAPER_DRAIN_MAX):
    """Run one variant of the paper's model.

    ``variant`` supplies the success probability (Eq. 7 / 24 / 28 / 35-36) and
    optionally reacts to the outcome (the DRL Q-update, Eq. 3 / 37).
    """
    rng = random.Random(seed)
    nodes = create_network(num_nodes, rng)
    for node in nodes:
        node.speed = float(speed)
    update_neighbors(nodes)

    variant.reset(nodes, rng)

    packets_sent = 0
    packets_received = 0
    packet_loss_bytes = 0
    total_delay = 0.0
    total_data = 0
    first_dead_round = None
    last_round = 0

    for round_idx in range(int(rounds)):
        last_round = round_idx
        move_network(nodes, rng)
        update_neighbors(nodes)

        source = rng.randrange(num_nodes)
        destination = rng.randrange(num_nodes)
        if source == destination:
            continue

        packets_sent += 1
        packet_size = rng.randint(PACKET_MIN, PACKET_MAX)
        hops = rng.randint(HOP_MIN, HOP_MAX)

        state = variant.observe(nodes, rng)
        probability = variant.success_probability(nodes, state, rng)
        success = rng.random() < probability

        if success:
            packets_received += 1
            # Eq. (12): D_k = D_base + H_k * D_hop
            delay = variant.delay(hops, rng)
            total_delay += delay
            total_data += packet_size
        else:
            packet_loss_bytes += packet_size

        # Assumption A1: credit the relays that carried the packet.
        relays = relay_nodes(nodes, source, destination, hops, rng)
        for relay_id in relays:
            node = nodes[relay_id]
            node.received += 1
            if success:
                node.forwarded += 1
            variant.update_node_trust(node)

        variant.feedback(nodes, state, success, rng)

        newly_dead = deplete_energy(nodes, rng, drain_min, drain_max)
        if newly_dead and first_dead_round is None:
            first_dead_round = round_idx

        dead = sum(1 for node in nodes if node.energy <= 0.0)
        if dead >= num_nodes * DEAD_FRACTION:
            break

    # Eq. (9)-(13)
    avg_delay = total_delay / packets_received if packets_received else 0.0
    simulation_time = max(last_round, 1)
    throughput = (total_data * 8.0) / (simulation_time * 1000.0)
    pdr = packets_received / float(packets_sent) if packets_sent else 0.0
    lifetime = first_dead_round if first_dead_round is not None else simulation_time

    flagged = sum(1 for node in nodes if node.malicious)
    return {
        "avg_delay_ms": avg_delay,
        "packet_loss_bytes": packet_loss_bytes,
        "throughput": throughput,
        "pdr": pdr,
        "network_lifetime": lifetime,
        "packets_sent": packets_sent,
        "packets_received": packets_received,
        "rounds_completed": simulation_time,
        "nodes_flagged_malicious": flagged,
    }


class PaperVariant(object):
    """Interface each of the paper's five models implements."""

    name = "variant"
    equations = ""

    def reset(self, nodes, rng):
        return None

    def observe(self, nodes, rng):
        """State handed to :meth:`success_probability` (Eq. 29 for the DRL model)."""
        return None

    def success_probability(self, nodes, state, rng):
        raise NotImplementedError

    def delay(self, hops, rng):
        """Eq. (12). The paper gives different bands per model."""
        return rng.uniform(20.0, 60.0) + hops * rng.uniform(5.0, 15.0)

    def update_node_trust(self, node):
        """Default: no trust model (the base EAURP model of Eq. 7)."""
        return None

    def feedback(self, nodes, state, success, rng):
        return None
