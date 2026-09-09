"""Implementation B -- senior_code.ipynb, logic copied verbatim.

TRANSCRIPTION POLICY
--------------------
Every function body below is character-for-character the senior's, in the order
the notebook executes them. ``random.seed(42)`` is set once, in the same place
(notebook cell 3), because their published numbers only reproduce when the
notebook is run top to bottom.

The only additions are: this docstring, a ``main()`` guard, an ``Agg``
matplotlib backend, CSV/PNG output, and the ``PROVENANCE`` table below. No
constant, formula or random draw has been altered.

WHAT THIS CODE ACTUALLY IS -- read before interpreting any of its numbers
------------------------------------------------------------------------
This is not a network simulator. It is a metric generator. ``src`` and ``dst``
are drawn at random each round and are never connected by a path; delivery is
one coin flip against a *global average*:

    success_prob = 0.45 + 0.25*avg_trust + 0.2*avg_energy + 0.1*avg_mobility
    success = random.random() < success_prob

Consequences, all verifiable in the code below:

1. No route exists, so trust never selects a path.
2. ``nodes[src].forwarded += 1`` and ``nodes[dst].received += 1`` accumulate the
   Packet Forwarding Ratio across *unrelated* nodes, so ``node.trust`` is a
   drift, not a measurement.
3. ``node.malicious`` is assigned by ``adaptive_trust_update`` and then never
   read by anything.
4. The Q-learning is degenerate: action 0 always adds +0.08 and action 1 always
   +0.02 regardless of state, so Q converges to "always exploit" almost
   immediately and ``get_state`` has no influence on behaviour.
5. The "Existing" baseline is EAURP's own output multiplied by constants
   (Lekha.pdf Eq. 14-18), not a protocol.
6. The network-lifetime difference between the base and proposed models comes
   entirely from the drain constants -- U(0.05,0.15) versus U(0.04,0.12).

None of that is a defect in the transcription; it is what the delivered code
does. It is reported here so the comparison in the report can be honest.
"""

import csv
import math
import os
import random
from collections import defaultdict

import numpy as np

# Which reported numbers are computed and which are literals. Quoted in the
# report so nobody has to take the distinction on trust.
PROVENANCE = {
    "cells_2_11": "simulated (coin-flip model, no routing)",
    "cell_12": "HARDCODED -- random.randint/uniform printed as packet trace",
    "cell_13": "HARDCODED -- random.uniform printed as measured metrics "
               "(PDR 89.04, delay 498.64 ms, throughput 17.46 kbps, "
               "lifetime 99.28%); these appear in Lekha.pdf Sec. IV-A-6 as "
               "'observed behaviour'",
    "existing_baseline": "DERIVED -- EAURP output x {1.2, 1.5, 0.7, 0.85, 0.98} "
                         "(Lekha.pdf Eq. 14-18), not a simulated protocol",
}

# ==========================================================================
# Cell 4 -- configuration (verbatim)
# ==========================================================================

# Network settings
AREA_SIZE = 1000
COMM_RANGE = 150

# Node settings
INITIAL_ENERGY = 100
ENERGY_TX = 0.5
ENERGY_RX = 0.2

# Trust parameters
TRUST_THRESHOLD = 0.6

# Speed range used in paper graphs
MIN_SPEED = 10000
MAX_SPEED = 40000

# Node counts used in graphs
NODE_COUNTS = [60, 80, 100, 120, 150, 200]

# Simulation rounds
SIM_ROUNDS = 2000


# ==========================================================================
# Cell 5 -- Node (verbatim)
# ==========================================================================

class Node:

    def __init__(self, node_id):

        self.id = node_id

        # Position
        self.x = random.uniform(0, AREA_SIZE)
        self.y = random.uniform(0, AREA_SIZE)

        # Mobility
        self.speed = random.uniform(MIN_SPEED, MAX_SPEED)

        # Destination for movement
        self.dest_x = random.uniform(0, AREA_SIZE)
        self.dest_y = random.uniform(0, AREA_SIZE)

        # Energy model
        self.energy = INITIAL_ENERGY

        # Trust model
        self.forwarded = 0
        self.received = 0
        self.trust = 1.0

        # Node status
        self.malicious = False

        # Neighbors
        self.neighbors = []

        # Routing table
        self.routes = {}


# ==========================================================================
# Cells 6-8 -- network construction and mobility (verbatim)
# ==========================================================================

def create_network(n):

    nodes = []

    for i in range(n):
        nodes.append(Node(i))

    return nodes


def update_neighbors(nodes):

    for node in nodes:
        node.neighbors = []

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):

            n1 = nodes[i]
            n2 = nodes[j]

            dist = math.sqrt((n1.x - n2.x) ** 2 + (n1.y - n2.y) ** 2)

            if dist <= COMM_RANGE:

                n1.neighbors.append(n2.id)
                n2.neighbors.append(n1.id)


def move_network(nodes):

    for node in nodes:

        dx = node.dest_x - node.x
        dy = node.dest_y - node.y

        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 1:
            node.dest_x = random.uniform(0, AREA_SIZE)
            node.dest_y = random.uniform(0, AREA_SIZE)
            continue

        node.x += (dx / dist) * node.speed * 0.001
        node.y += (dy / dist) * node.speed * 0.001


# ==========================================================================
# Cell 9 -- EAURP base model (verbatim)
# ==========================================================================

def run_simulation(num_nodes, speed):

    nodes = create_network(num_nodes)

    for n in nodes:
        n.speed = speed

    update_neighbors(nodes)

    packets_sent = 0
    packets_received = 0
    packet_loss_bytes = 0
    total_delay = 0
    total_data = 0

    first_dead_round = None

    for r in range(SIM_ROUNDS):

        move_network(nodes)
        update_neighbors(nodes)

        src = random.randint(0, num_nodes - 1)
        dst = random.randint(0, num_nodes - 1)

        if src == dst:
            continue

        packets_sent += 1

        packet_size = random.randint(512, 1024)  # bytes

        hops = random.randint(3, 10)

        # success probability decreases with speed
        success_prob = max(0.4, 0.9 - (speed / 100000))

        success = random.random() < success_prob

        if success:

            packets_received += 1

            # realistic delay model (milliseconds)
            base_delay = random.uniform(20, 60)
            hop_delay = hops * random.uniform(5, 15)

            delay = base_delay + hop_delay

            total_delay += delay

            total_data += packet_size

        else:

            packet_loss_bytes += packet_size

        # energy consumption
        for n in nodes:

            n.energy -= random.uniform(0.05, 0.15)

            if n.energy <= 0 and first_dead_round is None:
                first_dead_round = r

        dead = sum(1 for n in nodes if n.energy <= 0)

        if dead >= num_nodes * 0.8:
            break

    avg_delay = total_delay / packets_received if packets_received > 0 else 0

    simulation_time = max(r, 1)

    throughput = (total_data * 8) / (simulation_time * 1000)

    pdr = packets_received / packets_sent if packets_sent > 0 else 0

    lifetime = first_dead_round if first_dead_round else simulation_time

    return avg_delay, packet_loss_bytes, throughput, pdr, lifetime


# ==========================================================================
# Cell 17 -- ATEAURP (verbatim)
# ==========================================================================

def adaptive_trust_update(node):

    if node.received == 0:
        return

    pfr = node.forwarded / node.received

    # moving average trust update
    node.trust = 0.7 * node.trust + 0.3 * pfr

    if node.trust < TRUST_THRESHOLD and node.received > 5:
        node.malicious = True


def mobility_score(node):

    # mobility stability factor
    return 1 / (1 + node.speed / MAX_SPEED)


def run_proposed_simulation(num_nodes, speed):

    nodes = create_network(num_nodes)

    for n in nodes:
        n.speed = speed

    update_neighbors(nodes)

    packets_sent = 0
    packets_received = 0
    packet_loss_bytes = 0
    total_delay = 0
    total_data = 0

    first_dead_round = None

    for r in range(SIM_ROUNDS):

        move_network(nodes)
        update_neighbors(nodes)

        src = random.randint(0, num_nodes - 1)
        dst = random.randint(0, num_nodes - 1)

        if src == dst:
            continue

        packets_sent += 1

        packet_size = random.randint(512, 1024)

        hops = random.randint(3, 10)

        # cross layer metrics
        avg_trust = np.mean([n.trust for n in nodes])
        avg_energy = np.mean([n.energy for n in nodes]) / INITIAL_ENERGY
        avg_mobility = np.mean([mobility_score(n) for n in nodes])

        success_prob = 0.4 + 0.3 * avg_trust + 0.2 * avg_energy + 0.1 * avg_mobility
        success_prob = min(success_prob, 0.95)

        success = random.random() < success_prob

        if success:

            packets_received += 1

            base_delay = random.uniform(20, 60)
            hop_delay = hops * random.uniform(4, 12)

            delay = base_delay + hop_delay

            total_delay += delay

            total_data += packet_size

        else:

            packet_loss_bytes += packet_size

        # trust updates
        nodes[src].forwarded += 1
        nodes[dst].received += 1

        adaptive_trust_update(nodes[src])
        adaptive_trust_update(nodes[dst])

        # energy consumption
        for n in nodes:

            n.energy -= random.uniform(0.04, 0.12)

            if n.energy <= 0 and first_dead_round is None:
                first_dead_round = r

        dead = sum(1 for n in nodes if n.energy <= 0)

        if dead >= num_nodes * 0.8:
            break

    avg_delay = total_delay / packets_received if packets_received > 0 else 0

    simulation_time = max(r, 1)

    throughput = (total_data * 8) / (simulation_time * 1000)

    pdr = packets_received / packets_sent if packets_sent > 0 else 0

    lifetime = first_dead_round if first_dead_round else simulation_time

    return avg_delay, packet_loss_bytes, throughput, pdr, lifetime


# ==========================================================================
# Cells 22-25 -- PSE-EAURP (verbatim)
# ==========================================================================

def init_trust_history(nodes):
    for n in nodes:
        n.trust_history = [1.0, 1.0, 1.0]  # initial trust history


def predict_trust(node):

    t = node.trust_history

    # weighted prediction
    pred = 0.5 * t[-1] + 0.3 * t[-2] + 0.2 * t[-3]

    return pred


def update_trust_history(node):

    node.trust_history.append(node.trust)

    if len(node.trust_history) > 3:
        node.trust_history.pop(0)


def run_predictive_simulation(num_nodes, speed):

    nodes = create_network(num_nodes)

    init_trust_history(nodes)

    for n in nodes:
        n.speed = speed

    update_neighbors(nodes)

    packets_sent = 0
    packets_received = 0
    packet_loss_bytes = 0
    total_delay = 0
    total_data = 0

    first_dead_round = None

    for r in range(SIM_ROUNDS):

        move_network(nodes)
        update_neighbors(nodes)

        src = random.randint(0, num_nodes - 1)
        dst = random.randint(0, num_nodes - 1)

        if src == dst:
            continue

        packets_sent += 1

        packet_size = random.randint(512, 1024)
        hops = random.randint(3, 10)

        # NEW: predictive trust
        avg_pred_trust = np.mean([predict_trust(n) for n in nodes])
        avg_energy = np.mean([n.energy for n in nodes]) / INITIAL_ENERGY
        avg_mobility = np.mean([1 / (1 + n.speed / MAX_SPEED) for n in nodes])

        success_prob = 0.4 + 0.35 * avg_pred_trust + 0.15 * avg_energy + 0.1 * avg_mobility
        success_prob = min(success_prob, 0.97)

        success = random.random() < success_prob

        if success:

            packets_received += 1

            delay = random.uniform(20, 50) + hops * random.uniform(4, 10)

            total_delay += delay
            total_data += packet_size

        else:
            packet_loss_bytes += packet_size

        # trust update
        nodes[src].forwarded += 1
        nodes[dst].received += 1

        adaptive_trust_update(nodes[src])
        adaptive_trust_update(nodes[dst])

        update_trust_history(nodes[src])
        update_trust_history(nodes[dst])

        # energy
        for n in nodes:
            n.energy -= random.uniform(0.04, 0.12)

            if n.energy <= 0 and first_dead_round is None:
                first_dead_round = r

        dead = sum(1 for n in nodes if n.energy <= 0)

        if dead >= num_nodes * 0.8:
            break

    avg_delay = total_delay / packets_received if packets_received > 0 else 0

    simulation_time = max(r, 1)

    throughput = (total_data * 8) / (simulation_time * 1000)

    pdr = packets_received / packets_sent if packets_sent > 0 else 0

    lifetime = first_dead_round if first_dead_round else simulation_time

    return avg_delay, packet_loss_bytes, throughput, pdr, lifetime


# ==========================================================================
# Cell 31 -- DRL-EAURP (verbatim)
# ==========================================================================

# Q-learning parameters
Q_table = defaultdict(lambda: [0, 0])

alpha = 0.1
gamma = 0.9
epsilon = 0.1


def get_state(nodes):

    avg_trust = np.mean([n.trust for n in nodes])
    avg_energy = np.mean([n.energy for n in nodes]) / INITIAL_ENERGY
    avg_mobility = np.mean([1 / (1 + n.speed / MAX_SPEED) for n in nodes])

    state = (
        round(avg_trust, 1),
        round(avg_energy, 1),
        round(avg_mobility, 1)
    )

    return state


def choose_action(state):

    if random.random() < epsilon:
        return random.randint(0, 1)

    return np.argmax(Q_table[state])


def update_Q(state, action, reward, next_state):

    best_next = max(Q_table[next_state])

    Q_table[state][action] = Q_table[state][action] + alpha * (
        reward + gamma * best_next - Q_table[state][action]
    )


def run_drl_simulation(num_nodes, speed):

    nodes = create_network(num_nodes)

    for n in nodes:
        n.speed = speed

    update_neighbors(nodes)

    packets_sent = 0
    packets_received = 0
    packet_loss_bytes = 0
    total_delay = 0
    total_data = 0

    first_dead_round = None

    for r in range(SIM_ROUNDS):

        move_network(nodes)
        update_neighbors(nodes)

        src = random.randint(0, num_nodes - 1)
        dst = random.randint(0, num_nodes - 1)

        if src == dst:
            continue

        packets_sent += 1

        packet_size = random.randint(512, 1024)
        hops = random.randint(3, 10)

        # RL state
        state = get_state(nodes)

        action = choose_action(state)

        # Cross-layer routing metrics
        avg_trust = np.mean([n.trust for n in nodes])
        avg_energy = np.mean([n.energy for n in nodes]) / INITIAL_ENERGY
        avg_mobility = np.mean([1 / (1 + n.speed / MAX_SPEED) for n in nodes])

        # Base EAURP routing probability
        base_success_prob = 0.45 + 0.25 * avg_trust + 0.2 * avg_energy + 0.1 * avg_mobility

        # DRL routing adjustment
        if action == 0:
            success_prob = base_success_prob + 0.08   # trusted path
        else:
            success_prob = base_success_prob + 0.02   # exploration path

        success_prob = min(max(success_prob, 0.4), 0.98)

        success = random.random() < success_prob

        if success:

            packets_received += 1

            delay = random.uniform(20, 50) + hops * random.uniform(4, 10)

            total_delay += delay
            total_data += packet_size

            reward = 1

        else:

            packet_loss_bytes += packet_size

            reward = -1

        # Trust updates (EAURP logic)
        nodes[src].forwarded += 1
        nodes[dst].received += 1

        adaptive_trust_update(nodes[src])
        adaptive_trust_update(nodes[dst])

        # Next state for Q-learning
        next_state = get_state(nodes)

        update_Q(state, action, reward, next_state)

        # Energy consumption
        for n in nodes:

            n.energy -= random.uniform(0.04, 0.12)

            if n.energy <= 0 and first_dead_round is None:
                first_dead_round = r

        dead = sum(1 for n in nodes if n.energy <= 0)

        if dead >= num_nodes * 0.8:
            break

    avg_delay = total_delay / packets_received if packets_received > 0 else 0

    simulation_time = max(r, 1)

    throughput = (total_data * 8) / (simulation_time * 1000)

    pdr = packets_received / packets_sent if packets_sent > 0 else 0

    lifetime = first_dead_round if first_dead_round else simulation_time

    return avg_delay, packet_loss_bytes, throughput, pdr, lifetime


# ==========================================================================
# Cell 13 -- the hardcoded "metrics" block, reproduced so the report can show
# exactly what it does. NOT a measurement of anything.
# ==========================================================================

def hardcoded_metrics_block():
    """Cell 13 of the notebook, verbatim. Every value is ``random.uniform``."""
    send_packets = random.randint(225, 230)

    recv_packets = int(send_packets * random.uniform(0.86, 0.90))

    packet_loss_metric = send_packets - recv_packets

    local_pdr_metric = (recv_packets / send_packets) * 100

    routing_overhead = random.uniform(9.5, 10.5)

    local_avg_delay_metric = random.uniform(490, 520)

    local_throughput_metric = random.uniform(16.5, 18)

    local_network_lifetime_metric = random.uniform(99.1, 99.3)

    total_energy = random.uniform(92, 93)

    return {
        "send": send_packets,
        "recv": recv_packets,
        "PacketDeliveryRatio": local_pdr_metric,
        "Routingoverheads": routing_overhead,
        "AverageDelaynsec": local_avg_delay_metric,
        "Packetloss": packet_loss_metric,
        "Throughput_kbps": local_throughput_metric,
        "NetworkLifetime_percentage": local_network_lifetime_metric,
        "TotalEnergyConsumed": total_energy,
        "_provenance": "ALL VALUES ARE random.uniform LITERALS -- NOT MEASURED",
    }


# ==========================================================================
# Driver -- runs the notebook's experiment sequence and writes CSVs
# ==========================================================================

SPEED_RANGE = [10000, 15000, 20000, 25000, 30000, 35000, 40000]
RUNS = 5


def run_all(runs=RUNS, speed_range=None, node_counts=None, seed=42):
    """Reproduce every model in the notebook, in notebook order.

    ``random.seed`` is set once here, exactly as notebook cell 3 does, because
    the senior's published numbers depend on top-to-bottom execution order.
    """
    speed_range = SPEED_RANGE if speed_range is None else speed_range
    node_counts = NODE_COUNTS if node_counts is None else node_counts

    random.seed(seed)

    results = {"speed_range": list(speed_range), "node_counts": list(node_counts)}

    # ---- EAURP base, averaged over RUNS (notebook cell 10) ----
    delay_vs_speed, packetloss_vs_speed = [], []
    throughput_vs_speed, pdr_vs_speed, network_lifetime = [], [], []

    for speed in speed_range:
        delay_avg = loss_avg = thr_avg = pdr_avg = life_avg = 0
        for _ in range(runs):
            d, loss, thr, pdr, life = run_simulation(100, speed)
            delay_avg += d
            loss_avg += loss
            thr_avg += thr
            pdr_avg += pdr
            life_avg += life
        delay_vs_speed.append(delay_avg / runs)
        packetloss_vs_speed.append(loss_avg / runs)
        throughput_vs_speed.append(thr_avg / runs)
        pdr_vs_speed.append(pdr_avg / runs)
        network_lifetime.append(life_avg / runs)

    results["EAURP"] = {
        "delay": delay_vs_speed, "loss": packetloss_vs_speed,
        "throughput": throughput_vs_speed, "pdr": pdr_vs_speed,
        "lifetime": network_lifetime,
    }

    # ---- "Existing": EAURP scaled by constants (Lekha Eq. 14-18) ----
    existing = {"delay": [], "loss": [], "throughput": [], "pdr": [], "lifetime": []}
    for speed in speed_range:
        d, loss, thr, pdr, life = run_simulation(100, speed)
        existing["delay"].append(d * 1.2)
        existing["loss"].append(loss * 1.5)
        existing["throughput"].append(thr * 0.7)
        existing["pdr"].append(pdr * 0.85)
        existing["lifetime"].append(life * 0.98)
    existing["_provenance"] = PROVENANCE["existing_baseline"]
    results["Existing"] = existing

    # ---- node-count sweep (notebook cell 10) ----
    delay_vs_nodes, packetloss_vs_nodes, data_reliability = [], [], []
    for nodes_count in node_counts:
        delay_avg = loss_avg = pdr_avg = 0
        for _ in range(runs):
            d, loss, thr, pdr, life = run_simulation(nodes_count, 20000)
            delay_avg += d
            loss_avg += loss
            pdr_avg += pdr
        delay_vs_nodes.append(delay_avg / runs)
        packetloss_vs_nodes.append(loss_avg / runs)
        data_reliability.append(pdr_avg / runs)
    results["EAURP_vs_nodes"] = {
        "delay": delay_vs_nodes, "loss": packetloss_vs_nodes,
        "reliability": data_reliability,
    }

    # ---- ATEAURP / PSE-EAURP / DRL-EAURP (single run each, as in notebook) ----
    for label, runner in (
        ("ATEAURP", run_proposed_simulation),
        ("PSE-EAURP", run_predictive_simulation),
        ("DRL-EAURP", run_drl_simulation),
    ):
        bucket = {"delay": [], "loss": [], "throughput": [], "pdr": [], "lifetime": []}
        for speed in speed_range:
            d, loss, thr, pdr, life = runner(100, speed)
            bucket["delay"].append(d)
            bucket["loss"].append(loss)
            bucket["throughput"].append(thr)
            bucket["pdr"].append(pdr)
            bucket["lifetime"].append(life)
        results[label] = bucket

    results["hardcoded_cell_13"] = hardcoded_metrics_block()
    results["provenance"] = PROVENANCE
    return results


def to_rows(results):
    """Flatten :func:`run_all` output into CSV rows."""
    rows = []
    speeds = results["speed_range"]
    for model in ("Existing", "EAURP", "ATEAURP", "PSE-EAURP", "DRL-EAURP"):
        block = results.get(model)
        if not block:
            continue
        for index, speed in enumerate(speeds):
            rows.append({
                "track": "track1_as_is",
                "implementation": "B_senior_code",
                "model": model,
                "speed": speed,
                "avg_delay_ms": block["delay"][index],
                "packet_loss_bytes": block["loss"][index],
                "throughput": block["throughput"][index],
                "pdr": block["pdr"][index],
                "network_lifetime": block["lifetime"][index],
            })
    return rows


def write_csv(rows, path):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def main(out_dir="results/csv", runs=RUNS):
    results = run_all(runs=runs)
    rows = to_rows(results)
    path = write_csv(rows, os.path.join(out_dir, "b_senior_as_is.csv"))
    print("B (senior's code, as-is) ->", path)
    for model in ("Existing", "EAURP", "ATEAURP", "PSE-EAURP", "DRL-EAURP"):
        block = results[model]
        print("  {0:11s} PDR {1:.3f}-{2:.3f}  delay {3:.1f}-{4:.1f} ms  "
              "lifetime {5:.0f}".format(
                  model, min(block["pdr"]), max(block["pdr"]),
                  min(block["delay"]), max(block["delay"]),
                  np.mean(block["lifetime"])))
    return results


if __name__ == "__main__":
    main()
