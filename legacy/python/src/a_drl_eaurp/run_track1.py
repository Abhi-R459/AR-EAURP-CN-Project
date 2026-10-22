"""Track-1 driver for implementation A.

Reproduces the paper's speed and node-count sweeps for all five models, using
the paper's own equations and -- crucially -- the single energy drain band that
Eq. (8) actually specifies, for every variant. See assumption A2 in
``paper_model``: the delivered code quietly uses a gentler band for the three
proposed models, which is where their entire lifetime advantage comes from.
"""

import csv
import os

import numpy as np

from . import paper_model as pm
from .variants import DrlEaurpModel, ExistingModel, make_variant

SPEED_RANGE = [10000, 15000, 20000, 25000, 30000, 35000, 40000]
NODE_COUNTS = [60, 80, 100, 120, 150, 200]
MODEL_ORDER = ["EAURP", "ATEAURP", "PSE-EAURP", "DRL-EAURP"]


def run_speed_sweep(rounds=pm.SIM_ROUNDS, runs=3, speeds=None, n_nodes=100,
                    base_seed=42, drain_min=None, drain_max=None, verbose=True):
    """Every model across the speed range, averaged over ``runs`` seeds."""
    speeds = SPEED_RANGE if speeds is None else speeds
    drain_min = pm.PAPER_DRAIN_MIN if drain_min is None else drain_min
    drain_max = pm.PAPER_DRAIN_MAX if drain_max is None else drain_max

    results = {}
    policy_notes = {}

    for model_name in MODEL_ORDER:
        per_speed = []
        for speed in speeds:
            runs_out = []
            variant = make_variant(model_name)
            for run_index in range(int(runs)):
                out = pm.run_paper_simulation(
                    variant, n_nodes, speed, rounds=rounds,
                    seed=base_seed + 1000 * run_index,
                    drain_min=drain_min, drain_max=drain_max,
                )
                runs_out.append(out)
            averaged = {
                key: float(np.mean([row[key] for row in runs_out]))
                for key in runs_out[0]
            }
            averaged["speed"] = speed
            per_speed.append(averaged)
            if isinstance(variant, DrlEaurpModel):
                policy_notes[speed] = variant.policy_summary()
        results[model_name] = per_speed
        if verbose:
            pdrs = [row["pdr"] for row in per_speed]
            delays = [row["avg_delay_ms"] for row in per_speed]
            lifetimes = [row["network_lifetime"] for row in per_speed]
            print("  A/{0:11s} PDR {1:.3f}-{2:.3f}  delay {3:.1f}-{4:.1f} ms  "
                  "lifetime {5:.0f}".format(
                      model_name, min(pdrs), max(pdrs),
                      min(delays), max(delays), float(np.mean(lifetimes))))

    # Eq. (14)-(18): derive "Existing" from the EAURP curve.
    results["Existing"] = [ExistingModel.derive(row) for row in results["EAURP"]]
    if verbose:
        pdrs = [row["pdr"] for row in results["Existing"]]
        print("  A/{0:11s} PDR {1:.3f}-{2:.3f}   [DERIVED, Eq. 14-18]".format(
            "Existing", min(pdrs), max(pdrs)))

    return results, policy_notes


def run_density_sweep(rounds=pm.SIM_ROUNDS, runs=3, node_counts=None, speed=20000,
                      base_seed=42, verbose=True):
    """Delay, loss and reliability against node count (paper Figs. 4 and 6)."""
    node_counts = NODE_COUNTS if node_counts is None else node_counts
    results = {}
    for model_name in MODEL_ORDER:
        per_count = []
        for count in node_counts:
            variant = make_variant(model_name)
            runs_out = [
                pm.run_paper_simulation(
                    variant, count, speed, rounds=rounds,
                    seed=base_seed + 1000 * run_index,
                )
                for run_index in range(int(runs))
            ]
            averaged = {
                key: float(np.mean([row[key] for row in runs_out]))
                for key in runs_out[0]
            }
            averaged["n_nodes"] = count
            per_count.append(averaged)
        results[model_name] = per_count
        if verbose:
            print("  A/{0:11s} density sweep done".format(model_name))
    results["Existing"] = [ExistingModel.derive(row) for row in results["EAURP"]]
    return results


def drain_band_ablation(rounds=pm.SIM_ROUNDS, runs=3, speed=20000, n_nodes=100,
                        base_seed=42):
    """Isolate the effect of the undocumented drain-band change.

    Runs DRL-EAURP twice: once with the band Eq. (8) specifies, once with the
    band the delivered code actually uses. If the lifetime gap the paper
    attributes to its protocol is really just this constant, this shows it.
    """
    out = {}
    for label, (low, high) in (
        ("paper_Eq8_0.05-0.15", (0.05, 0.15)),
        ("code_0.04-0.12", (0.04, 0.12)),
    ):
        rows = [
            pm.run_paper_simulation(
                make_variant("DRL-EAURP"), n_nodes, speed, rounds=rounds,
                seed=base_seed + 1000 * index, drain_min=low, drain_max=high,
            )
            for index in range(int(runs))
        ]
        out[label] = {
            key: float(np.mean([row[key] for row in rows])) for key in rows[0]
        }
    lifetimes = [out[key]["network_lifetime"] for key in out]
    out["lifetime_delta"] = float(lifetimes[1] - lifetimes[0])
    return out


def to_rows(speed_results, density_results=None):
    """Flatten into CSV rows."""
    rows = []
    for model_name, entries in speed_results.items():
        for entry in entries:
            row = {
                "track": "track1_as_is",
                "implementation": "A_paper_reimplementation",
                "model": model_name,
                "sweep": "speed",
                "speed": entry.get("speed"),
                "n_nodes": 100,
            }
            for key in ("pdr", "avg_delay_ms", "throughput", "packet_loss_bytes",
                        "network_lifetime", "packets_sent", "packets_received",
                        "nodes_flagged_malicious"):
                row[key] = entry.get(key)
            row["derived"] = bool(model_name == "Existing")
            rows.append(row)

    if density_results:
        for model_name, entries in density_results.items():
            for entry in entries:
                row = {
                    "track": "track1_as_is",
                    "implementation": "A_paper_reimplementation",
                    "model": model_name,
                    "sweep": "density",
                    "speed": 20000,
                    "n_nodes": entry.get("n_nodes"),
                }
                for key in ("pdr", "avg_delay_ms", "throughput",
                            "packet_loss_bytes", "network_lifetime",
                            "packets_sent", "packets_received",
                            "nodes_flagged_malicious"):
                    row[key] = entry.get(key)
                row["derived"] = bool(model_name == "Existing")
                rows.append(row)
    return rows


def write_csv(rows, path):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main(out_dir="results/csv", rounds=pm.SIM_ROUNDS, runs=3, density=True):
    print("A (DRL-EAURP re-implemented from Lekha.pdf equations)")
    speed_results, policy_notes = run_speed_sweep(rounds=rounds, runs=runs)
    density_results = (
        run_density_sweep(rounds=rounds, runs=runs) if density else None
    )
    rows = to_rows(speed_results, density_results)
    path = write_csv(rows, os.path.join(out_dir, "a_paper_track1.csv"))
    print("  ->", path)

    if policy_notes:
        sample = policy_notes[sorted(policy_notes)[0]]
        print("  DRL policy check: {0} states visited, action-0 share "
              "{1:.3f}, {2}/{3} states prefer action 0".format(
                  sample["q_states_visited"], sample["action0_share"],
                  sample["states_preferring_action0"], sample["states_total"]))
    return speed_results, density_results, policy_notes


if __name__ == "__main__":
    main()
