#!/usr/bin/env python3
"""Generate a transparent paper-style report from the native ns-3 E1-E6 batch."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
IDENTITY = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["source_sha256"]
T_CRIT_95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
             6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
             15: 2.131, 20: 2.086, 25: 2.060, 29: 2.045}
BOUNDED_RATE_METRICS = {"pdr", "detect_tpr", "detect_fpr", "detector_auc"}

PROTOCOLS = [
    ("AODV", "aodv"), ("EAURP", "eaurp"),
    ("DRL-EAURP (paper)", "drl-paper"),
    ("DRL-EAURP (senior)", "drl-senior"), ("AR-EAURP", "ar-eaurp"),
]
ATTACKS = ["blackhole", "grayhole", "trust_poisoning"]
PCTS = [0, 10, 20, 30, 40, 50]
SIMULATOR_DEFAULTS = {
    "cfg_min_speed_m_s": "1", "cfg_pause_max_s": "2",
    "cfg_min_packet_bytes": "512", "cfg_max_packet_bytes": "1024",
    "cfg_radio_tx_power_dbm": "16.0206", "cfg_radio_sensitivity_dbm": "-96",
    "cfg_path_loss_exponent": "3", "cfg_panel_fraction": "0.7",
    "cfg_harvest_day_length_s": "600", "cfg_cmdp_eps_start": "0.30",
    "cfg_cmdp_eps_end": "0.05", "cfg_flow_monitor": "0",
}


def ci95(mean: float, sd: float, n: int) -> tuple[float, float]:
    if n < 2:
        return mean, mean
    t = T_CRIT_95.get(n - 1, 1.96)
    half = t * sd / math.sqrt(n)
    return mean - half, mean + half


def fmt(mean: str | float, sd: str | float | None = None, pct=False) -> str:
    m = float(mean)
    s = float(sd or 0)
    scale = 100 if pct else 1
    return f"{m*scale:.2f} ± {s*scale:.2f}"


def load_rows(name: str) -> list[dict[str, str]]:
    path = ROOT / "csv" / f"{name}.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def metric_cell(row: dict[str, str], key: str, pct=False) -> str:
    return fmt(row[key], row.get(key + "_std", "0"), pct=pct)


def run_checkpoint(parameters: dict[str, str]) -> dict[str, float]:
    material = "ns-3.45 native batch v1\n" + IDENTITY + "\n"
    material += "".join(f"{key}={parameters[key]}\n" for key in sorted(parameters))
    signature = hashlib.sha256(material.encode()).hexdigest()
    path = ROOT / "raw" / f"{signature}.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    # E3's isolated runner stores the build identity in line 2; native C++
    # checkpoints store the parameter signature there. Both are bound to the
    # hashed filename and payload checksum.
    if len(lines) < 4 or lines[0] != "AR-EAURP native checkpoint 1" or lines[1] not in {IDENTITY, signature}:
        raise RuntimeError(f"Invalid or missing checkpoint: {path}")
    payload = "\n".join(lines[3:]) + "\n"
    if hashlib.sha256(payload.encode()).hexdigest() != lines[2]:
        raise RuntimeError(f"Checkpoint checksum mismatch: {path}")
    values = {}
    for line in lines[3:]:
        key, value = line.split(",", 1)
        values[key] = float(value)
    return values


def base_parameters(protocol: str, run: int) -> dict[str, str]:
    return {
        "area": "420", "attack": "none", "commission": "240",
        "flows": "6", "ganEpochs": "120", "lstmEpochs": "30",
        "malicious": "0", "nodes": "24", "protocol": protocol,
        "run": str(run), "seed": "20260909", "time": "120", "warmup": "20",
    }


def experiment_parameters(experiment: str, row: dict[str, str], run: int) -> dict[str, str]:
    """Reconstruct the exact native batch CLI parameter map for a table row."""
    p = base_parameters(row["protocol"], run)
    p["attack"] = row["attack"]
    if experiment == "e1_speed":
        p["maxSpeed"] = row["speed_value"]
    elif experiment == "e2_density":
        p["nodes"] = row["node_count"]
    elif experiment == "e3_attack":
        p["malicious"] = f"{int(float(row['malicious_pct'])) / 100:.6f}"
    elif experiment == "e4_energy":
        p["harvest"] = "1" if row["energy_mode"] == "solar" else "0"
    elif experiment == "e4b_lifetime":
        p.update({"harvest": "1" if row["energy_mode"] == "solar" else "0",
                  "time": "900", "energy": "350"})
    elif experiment == "e5_ablation":
        p.update({"attack": "grayhole", "malicious": "0.3"})
        variant = row["label"]
        if variant in {"C without GAN", "C bare"}: p["gan"] = "0"
        if variant in {"C without LSTM", "C bare"}: p["lstm"] = "0"
        if variant in {"C without CMDP", "C bare"}: p["cmdp"] = "0"
        if variant == "C without energy excuse": p["energyExcuse"] = "0"
    elif experiment == "e5b_cmdp_floor":
        p.update({"attack": "grayhole", "malicious": "0.3", "pdrFloor": row["pdr_floor"]})
    elif experiment == "e6_overhead":
        p.update({"attack": "grayhole", "malicious": "0.3"})
        if row["label"] == "C without ECC": p["ecc"] = "0"
    return p


def write_settings_ledgers() -> tuple[int, int]:
    """Write condition and per-run ledgers with full settings and checkpoint provenance."""
    experiments = ["e1_speed", "e2_density", "e3_attack", "e4_energy",
                   "e4b_lifetime", "e5_ablation", "e5b_cmdp_floor", "e6_overhead"]
    condition_rows: list[dict[str, str]] = []
    run_rows: list[dict[str, str]] = []
    metric_keys = ["pdr", "mean_delay_s", "throughput_bps", "detect_tpr", "detect_fpr",
                   "detector_auc", "residual_energy_j", "cmdp_lambda", "control_packets",
                   "crypto_overhead_bytes", "first_death_s", "first_death_observed"]
    setting_keys = ["cfg_nodes", "cfg_area", "cfg_max_speed", "cfg_flows", "cfg_rate",
                    "cfg_duration", "cfg_warmup", "cfg_cooldown", "cfg_commission",
                    "cfg_gan_epochs", "cfg_lstm_epochs", "cfg_train", "cfg_realtime",
                    "cfg_energy_j", "cfg_harvest", "cfg_gan", "cfg_lstm", "cfg_cmdp",
                    "cfg_energy_excuse", "cfg_ecc", "cfg_pdr_floor", "cfg_seed"]
    setting_keys += list(SIMULATOR_DEFAULTS)
    for experiment in experiments:
        path = ROOT / "csv" / f"{experiment}.csv"
        if not path.is_file():
            raise RuntimeError(f"Missing completed experiment table: {path}")
        for row in load_rows(experiment):
            parameters_for_run1 = experiment_parameters(experiment, row, 1)
            config = {
                "experiment": experiment, "label": row["label"], "protocol": row["protocol"],
                "attack": row["attack"], "hostile_fraction_percent": row.get("malicious_pct", "0"),
                "run_numbers": "", "replicate_count": "0", "seed": "20260909",
                "parameters_json": json.dumps(parameters_for_run1, sort_keys=True),
                "source_sha256": IDENTITY,
            }
            for key in setting_keys:
                config[key] = row.get(key, SIMULATOR_DEFAULTS.get(key, ""))
            for key in metric_keys:
                config[f"mean_{key}"] = row.get(key, "")
                config[f"sd_{key}"] = row.get(key + "_std", "")
            replicate_metrics = []
            for run in range(1, 6):
                params = experiment_parameters(experiment, row, run)
                material = "ns-3.45 native batch v1\n" + IDENTITY + "\n"
                material += "".join(f"{key}={params[key]}\n" for key in sorted(params))
                checkpoint = ROOT / "raw" / (hashlib.sha256(material.encode()).hexdigest() + ".csv")
                if not checkpoint.is_file():
                    continue
                metrics = run_checkpoint(params)
                replicate_metrics.append(metrics)
                record = {
                    "experiment": experiment, "label": row["label"], "protocol": row["protocol"],
                    "attack": row["attack"], "hostile_fraction_percent": row.get("malicious_pct", "0"),
                    "seed": str(metrics.get("cfg_seed", 20260909)), "run": str(run),
                    "parameters_json": json.dumps(params, sort_keys=True),
                    "checkpoint": checkpoint.relative_to(ROOT).as_posix(),
                    "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                    "source_sha256": IDENTITY,
                }
                for key in setting_keys:
                    record[key] = str(metrics.get(key, SIMULATOR_DEFAULTS.get(key, "")))
                for key in metric_keys:
                    record[key] = str(metrics.get(key, ""))
                run_rows.append(record)
            if not replicate_metrics:
                raise RuntimeError(f"No verified run checkpoints for {experiment}: {row['label']}")
            config["run_numbers"] = ";".join(str(i) for i in range(1, 6)
                if (ROOT / "raw" / (hashlib.sha256(("ns-3.45 native batch v1\n" + IDENTITY + "\n" +
                    "".join(f"{key}={value}\n" for key, value in sorted(experiment_parameters(
                        experiment, row, i).items()))).encode()).hexdigest() + ".csv")).is_file())
            config["replicate_count"] = str(len(replicate_metrics))
            for key in metric_keys:
                values = [m[key] for m in replicate_metrics if key in m]
                if len(values) >= 2 and key not in {"first_death_s", "first_death_observed"}:
                    mean = sum(values) / len(values)
                    sd = math.sqrt(sum((v-mean)**2 for v in values)/(len(values)-1))
                    lo, hi = ci95(mean, sd, len(values))
                    if key in BOUNDED_RATE_METRICS:
                        lo, hi = max(0.0, lo), min(1.0, hi)
                    config[f"ci95_low_{key}"] = str(lo)
                    config[f"ci95_high_{key}"] = str(hi)
            condition_rows.append(config)
    def write_csv(name: str, records: list[dict[str, str]]) -> None:
        columns = list(dict.fromkeys(key for record in records for key in record))
        with (ROOT / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
    write_csv("configuration_settings.csv", condition_rows)
    write_csv("run_settings.csv", run_rows)
    return len(condition_rows), len(run_rows)


def write_all_pairwise_e3() -> int:
    """Create matched-run PDR contrasts for every protocol pair and E3 condition."""
    samples = matched_e3()
    records = []
    for attack in ATTACKS:
        for pct in PCTS:
            for (label_a, proto_a), (label_b, proto_b) in combinations(PROTOCOLS, 2):
                a_runs = samples[(attack, pct, proto_a)]
                b_runs = samples[(attack, pct, proto_b)]
                deltas = [100 * (a["pdr"] - b["pdr"]) for a, b in zip(a_runs, b_runs)]
                n = len(deltas)
                mean = sum(deltas) / n
                sd = math.sqrt(sum((d-mean)**2 for d in deltas) / (n-1))
                lo, hi = ci95(mean, sd, n)
                records.append({
                    "attack": attack, "malicious_pct": pct,
                    "protocol_a": proto_a, "protocol_a_label": label_a,
                    "protocol_b": proto_b, "protocol_b_label": label_b,
                    "delta_definition": "PDR(protocol_a) - PDR(protocol_b), percentage points",
                    "n_paired_runs": n, "seed": 20260909, "run_numbers": "1;2;3;4;5",
                    "mean_delta_pp": mean, "paired_sd_pp": sd,
                    "ci95_low_pp": lo, "ci95_high_pp": hi,
                    "wins_a": sum(d > 0 for d in deltas),
                    "ties": sum(d == 0 for d in deltas),
                    "wins_b": sum(d < 0 for d in deltas),
                    "run_deltas_pp": json.dumps(deltas),
                })
    path = ROOT / "pairwise_e3_comparisons.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
    return len(records)


def render_figures() -> list[str]:
    """Create publication-style SVG and PNG plots from the aggregate tables."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    colors = ["#3366AA", "#109648", "#DC6B19", "#8E63B5", "#C33C54"]
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 13, "axes.labelsize": 11,
                         "figure.dpi": 150, "savefig.dpi": 300,
                         "axes.spines.top": False, "axes.spines.right": False})
    made: list[str] = []

    def finish(fig, name: str) -> None:
        fig.tight_layout()
        fig.savefig(out / f"{name}.svg", bbox_inches="tight")
        fig.savefig(out / f"{name}.png", bbox_inches="tight")
        plt.close(fig)
        made.append(name)

    for attack in ATTACKS:
        rows = [r for r in load_rows("e3_attack") if r["attack"] == attack]
        fig, ax = plt.subplots(figsize=(8.4, 4.8))
        for color, (label, protocol) in zip(colors, PROTOCOLS):
            group = sorted((r for r in rows if r["protocol"] == protocol), key=lambda r: int(float(r["malicious_pct"])))
            x = [float(r["malicious_pct"]) for r in group]
            y = [100 * float(r["pdr"]) for r in group]
            err = [100 * float(r.get("pdr_std", 0)) for r in group]
            ax.errorbar(x, y, yerr=err, marker="o", linewidth=1.8, capsize=3, color=color, label=label)
        ax.set(title=f"Packet delivery under {attack.replace('_', ' ')} attack",
               xlabel="Hostile nodes (%)", ylabel="Packet delivery ratio (%)")
        ax.set_xticks(PCTS); ax.set_ylim(0, 103); ax.grid(axis="y", alpha=.25); ax.legend(frameon=False, ncol=2)
        finish(fig, f"paper_e3_{attack}_pdr")

    for experiment, xfield, xlabel, title, name in [
        ("e1_speed", "speed_value", "Maximum node speed (m/s)", "Mobility sensitivity", "paper_e1_mobility"),
        ("e2_density", "node_count", "Number of nodes", "Network density sensitivity", "paper_e2_density"),
    ]:
        rows = load_rows(experiment)
        fig, ax = plt.subplots(figsize=(8.4, 4.8))
        for color, (label, protocol) in zip(colors, PROTOCOLS):
            group = sorted((r for r in rows if r["protocol"] == protocol), key=lambda r: int(float(r[xfield])))
            if experiment == "e2_density":
                replicated = [r for r in group if int(float(r.get("runs", "1"))) >= 2]
                single = [r for r in group if int(float(r.get("runs", "1"))) < 2]
                if replicated:
                    ax.errorbar([float(r[xfield]) for r in replicated], [100*float(r["pdr"]) for r in replicated],
                                yerr=[100*float(r.get("pdr_std",0)) for r in replicated], marker="o", capsize=3,
                                linewidth=1.8, color=color, label=label)
                else:
                    ax.plot([], [], marker="o", linewidth=1.8, color=color, label=label)
                if single:
                    ax.scatter([float(r[xfield]) for r in single], [100*float(r["pdr"]) for r in single],
                               marker="o", facecolors="none", edgecolors=color, linewidths=1.8, zorder=4)
            else:
                ax.errorbar([float(r[xfield]) for r in group], [100*float(r["pdr"]) for r in group],
                            yerr=[100*float(r.get("pdr_std",0)) for r in group], marker="o", capsize=3,
                            linewidth=1.8, color=color, label=label)
        ax.set(title=title, xlabel=xlabel, ylabel="Packet delivery ratio (%)")
        ax.set_ylim(0,103); ax.grid(axis="y",alpha=.25)
        if experiment == "e2_density":
            from matplotlib.lines import Line2D
            handles, labels = ax.get_legend_handles_labels()
            handles.append(Line2D([], [], marker="o", linestyle="None", markerfacecolor="none",
                                  markeredgecolor="#333333"))
            ax.legend(handles, labels + ["Single run (n=1; descriptive)"], frameon=False, ncol=2)
        else:
            ax.legend(frameon=False,ncol=2)
        finish(fig,name)

    rows = load_rows("e4_energy")
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    x = range(len(rows)); labels = [r["label"].replace(" (base substrate)", "") for r in rows]
    ax.bar(x, [float(r["residual_energy_j"]) for r in rows], color=["#3366AA" if r["energy_mode"]=="battery" else "#36A270" for r in rows])
    ax.set(title="Residual network energy by protocol and energy mode", ylabel="Residual energy (J)")
    ax.set_xticks(list(x), labels, rotation=55, ha="right"); ax.grid(axis="y",alpha=.25)
    finish(fig,"paper_e4_residual_energy")

    rows = load_rows("e5_ablation")
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.bar(range(len(rows)), [100*float(r["pdr"]) for r in rows], color="#4777B8")
    ax.set(title="AR-EAURP component ablation", ylabel="Packet delivery ratio (%)")
    ax.set_xticks(range(len(rows)), [r["label"] for r in rows], rotation=35, ha="right"); ax.set_ylim(0,103); ax.grid(axis="y",alpha=.25)
    finish(fig,"paper_e5_ablation")
    return made


def matched_e3() -> dict[tuple[str, int, str], list[dict[str, float]]]:
    result = {}
    for attack in ATTACKS:
        for pct in PCTS:
            for label, protocol in PROTOCOLS:
                replicates = []
                for run in range(1, 6):
                    p = base_parameters(protocol, run)
                    p["attack"] = attack
                    p["malicious"] = f"{pct/100:.6f}"
                    replicates.append(run_checkpoint(p))
                result[(attack, pct, protocol)] = replicates
    return result


def t_markdown(rows: list[dict[str, str]], columns: list[tuple[str, str, bool]]) -> str:
    if not rows:
        return "(No rows.)\n"
    out = ["| " + " | ".join(title for _, title, _ in columns) + " |",
           "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        cells = []
        for key, _, pct in columns:
            if key == "label":
                cells.append(row[key])
            elif key in {"first_death_s", "eighty_pct_dead_s"}:
                flag = "first_death_observed" if key == "first_death_s" else "eighty_pct_death_observed"
                state = float(row.get(flag, "0"))
                cells.append(metric_cell(row, key) if state == 1 else "censored / mixed")
            elif key == "runs":
                cells.append(str(int(float(row[key]))))
            elif float(row.get("runs", "2") or "2") < 2:
                scale = 100 if pct else 1
                cells.append(f"{float(row[key]) * scale:.2f} (n=1)")
            else:
                cells.append(metric_cell(row, key, pct))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def settings() -> dict:
    return {
        "study": "Native ns-3 protocol and robustness comparison",
        "engine": "ns-3.45 native C++",
        "profile": "review",
        "build_source_sha256": IDENTITY,
        "reproduction_command_from_project_root": "bash ns3/scripts/run.sh --profile=review --only=e1,e2,e3,e4,e5,e6 --out=results/ns3-native-paper-review --render=0",
        "base_configuration": {
            "nodes": 24, "flows": 6, "area_side_m": 420,
            "measurement_duration_s": 120, "warmup_s": 20,
            "commissioning_duration_s_for_AR_s": 240,
            "gan_epochs": 120, "lstm_epochs": 30,
            "seed": 20260909, "run_numbers": [1, 2, 3, 4, 5],
            "replicates_per_condition": 5,
            "min_speed_m_s": 1, "default_max_speed_m_s": 20,
            "waypoint_pause_max_s": 2, "initial_energy_J_per_node": 350,
            "cooldown_s": 10,
            "default_application_rate_packets_per_second_per_flow": 1,
            "default_packet_size_bytes": "uniform 512–1024",
            "default_radio_tx_power_dbm": 16.0206, "default_radio_sensitivity_dbm": -96,
            "default_path_loss_exponent": 3.0,
            "default_cmdp_pdr_floor": 0.90,
            "default_harvest": True, "default_gan_lstm_cmdp_ecc": True,
            "default_realtime_pacing": False,
            "default_cmdp_epsilon_start": 0.30,
            "default_cmdp_epsilon_end": 0.05,
            "radio": {"transmit_power_dbm": 16.0206, "receiver_sensitivity_dbm": -96,
                      "path_loss_exponent": 3.0},
            "traffic": {"rate_packets_per_second_per_flow": 1.0,
                        "packet_size_bytes_min": 512, "packet_size_bytes_max": 1024},
            "mobility": {"minimum_speed_m_s": 1, "maximum_speed_factor_default_m_s": 20,
                         "waypoint_pause_max_s": 2},
            "harvesting": {"panel_fraction": 0.7, "compressed_day_length_s": 600},
        },
        "protocols": [{"label": label, "id": proto} for label, proto in PROTOCOLS],
        "variations": {
            "E1_mobility_max_speed_m_s": [1, 5, 10, 15, 20],
            "E2_node_count": [60, 80, 100, 120, 150, 200],
            "E3_attacks": ATTACKS,
            "E3_malicious_fraction_percent": PCTS,
            "E4_energy_modes": ["battery (harvest disabled)", "solar/kinetic harvesting"],
            "E4b_lifetime_horizon_s": 900,
            "E5_AR_EAURP_ablations": ["full", "without GAN", "without LSTM", "without CMDP", "bare", "without energy excuse"],
            "E5b_CMDP_delivery_floors": [0.70, 0.80, 0.90, 0.95],
            "E6_security_overhead": ["all protocols with grayhole at 30%", "AR-EAURP without ECC"],
        },
        "statistics": {
            "summary": "arithmetic mean and sample standard deviation across available ns-3 run numbers; five planned",
            "interval": "two-sided 95% Student-t confidence interval using observed sample size; omitted for n<2; intervals for PDR, TPR, FPR, and AUC are bounded to [0,1]",
            "paired_comparisons": "AR-EAURP vs EAURP paired per-run PDR differences for E3 conditions (five matched runs)",
        },
        "planned_condition_count": 181,
        "planned_native_run_count": 905,
        "rng_configuration": {
            "master_seed": 20260909,
            "run_numbers": [1, 2, 3, 4, 5],
            "method": "Fixed ns-3 master seed with distinct RngRun numbers; run numbers are matched across protocol comparisons.",
            "event_level_common_random_numbers": False,
        },
        "settings_files": {
            "configuration_settings.csv": "One row per condition with canonical run-1 CLI settings, observed run numbers, means, sample SDs, and 95% bounded Student-t intervals for selected rate metrics.",
            "run_settings.csv": "One row per native replication, with exact CLI settings, measured cfg_* values, selected metrics, and checkpoint SHA-256.",
        },
        "execution_provenance": {
            "final_report_scope": "Composite E1-E6 report built from verified ns-3 per-run checkpoints.",
            "original_root_manifest_selection": "e3,e4,e5,e6",
            "note": "The root manifest selection records the original native C++ batch selection; the final report also aggregates E1 and partial E2 checkpoints. The exact run coverage and source identity are recorded in the ledgers.",
        },
    }


def main() -> None:
    protocol_text = ", ".join(label for label, _ in PROTOCOLS)
    md = [
        "# Native ns-3 comparative evaluation",
        "",
        "## Executive summary",
        "",
        "This report summarizes the native ns-3.45 review matrix within the available time. "
        "The planned budget is five run numbers per condition with a fixed ns-3 seed of 20260909; the completion table records actual coverage, and incomplete replications are not imputed. "
        "The E3 attack sweep includes a paired AR-EAURP versus EAURP PDR analysis from the checksummed per-run checkpoints.",
        "",
        "## Methods and reproducibility",
        "",
        "Reproduction command from the project root: `bash ns3/scripts/run.sh --profile=review --only=e1,e2,e3,e4,e5,e6 --out=results/ns3-native-paper-review --render=0`. The experiment runner resumes only checksummed runs whose full parameter map and source/build identity match. Run `python generate_paper_report.py` from the result directory to rebuild the expanded settings ledgers and charts.",
        "",
        "Execution provenance: this final E1–E6 report is assembled from verified native ns-3 run checkpoints. The root `manifest.json` selection field records the original C++ batch selection (`e3,e4,e5,e6`); E1 and the time-boxed E2 results were included from their verified checkpoint sets. The per-run ledger is the authoritative record of the 863 included runs.",
        "",
        "## Simulation settings",
        "",
        "Each row in `configuration_settings.csv` names the canonical run-1 CLI arguments and aggregate metrics for one condition, including the actual replicate count and run numbers. Each row in `run_settings.csv` records the exact CLI argument map for that completed run, simulator-reported cfg_* values, selected per-run metrics, and the SHA-256 of the checksummed raw checkpoint. Confidence intervals are omitted where fewer than two replications exist.",
        "",
        "| Experiment | Factors varied | Conditions | Native runs |",
        "|---|---|---:|---:|",
        "| E1 mobility | 5 protocols × max speed 1, 5, 10, 15, 20 m/s | 25 | 125 |",
        "| E2 density | 5 protocols × 60, 80, 100, 120, 150, 200 nodes | 30 | 150 |",
        "| E3 attacks | 5 protocols × 3 attacks × 0–50% hostile nodes (10-point steps) | 90 | 450 |",
        "| E4 energy | 5 protocols × battery/solar-kinetic harvesting | 10 | 50 |",
        "| E4b lifetime | 5 protocols × battery/solar-kinetic harvesting, 900 s horizon | 10 | 50 |",
        "| E5 ablation | 6 AR-EAURP component configurations | 6 | 30 |",
        "| E5b CMDP floor | 0.70, 0.80, 0.90, 0.95 PDR constraints | 4 | 20 |",
        "| E6 security overhead | 5 protocols plus AR-EAURP without ECC | 6 | 30 |",
        "",
        f"- Simulator: ns-3.45, native C++ source/build identity SHA-256 `{IDENTITY}`.",
        f"- Protocols: {protocol_text}.",
        "- Base review scenario: 24 nodes, six CBR flows, 420 m square area, 120 s evaluation, 20 s warm-up, 10 s cooldown.",
        "- AR-EAURP clean commissioning: 240 s; GAN 120 epochs; LSTM 30 epochs. The CMDP route selector also learns during clean commissioning before attack evaluation.",
        "- RNG: fixed seed 20260909 and run numbers 1–5 planned per condition. Run numbers are matched between protocol comparisons; results are stochastic replications, not repeated packets from one run.",
        "- Metrics are reported as mean ± sample SD when at least two replications are present. Per-condition 95% confidence intervals use a two-sided Student t interval with degrees of freedom based on the observed sample size; bounded rate intervals (PDR, TPR, FPR, and AUC) are constrained to [0, 1]. E3 primary paired differences compare AR-EAURP and EAURP using corresponding run numbers.",
        "- All ten pairwise protocol contrasts are retained for each E3 attack/prevalence condition in `pairwise_e3_comparisons.csv`; their intervals are unadjusted and should be interpreted as exploratory across this multiple-comparison family.",
        "- `configuration_settings.csv` records each condition’s canonical run-1 CLI parameter map, observed run numbers, aggregate metrics, and simulator-reported settings. `run_settings.csv` records the exact CLI map for every completed run, measured cfg_* values, seed/run number, and the checksum of its raw checkpoint. Aggregate tables in `csv/` retain cfg_* means and sample SDs.",
        "",
        "The review profile retains the Colab notebook’s E1–E6 factor levels but uses 120 s evaluation and the 24-node/six-flow review workload rather than the notebook full profile’s 400 s and larger default workload. The planned budget is five runs. Any time-boxed shortfall appears in the completion table; this is not a byte-for-byte rerun of the Colab full-profile configuration.",
        "",
        "## E1 — Mobility",
        "",
    ]
    rows = load_rows("e1_speed")
    md += [t_markdown(rows, [("label", "Configuration", False), ("pdr", "PDR", True), ("mean_delay_s", "Delay (s)", False), ("throughput_bps", "Throughput (bit/s)", False)]), ""]
    md += ["## E2 — Network density", "",
           "Run count is shown for each condition. A single run is descriptive only and is not a replicated estimate; the settings ledgers show exact coverage.", ""]
    rows = load_rows("e2_density")
    md += [t_markdown(rows, [("label", "Configuration", False), ("runs", "Runs", False), ("pdr", "PDR", True), ("mean_delay_s", "Delay (s)", False), ("throughput_bps", "Throughput (bit/s)", False)]), ""]

    md += ["## E3 — Attack prevalence by protocol", "", "PDR cells show mean ± sample SD across five run numbers; the table keeps attack types and hostile-node percentages separate.", ""]
    e3rows = load_rows("e3_attack")
    e3key = {(r["protocol"], r["attack"], int(float(r["malicious_pct"]))): r for r in e3rows}
    for attack in ATTACKS:
        md += [f"### {attack.replace('_', ' ').title()}", "",
               "| Hostile nodes | " + " | ".join(label for label, _ in PROTOCOLS) + " |",
               "|---:|" + "---:|" * len(PROTOCOLS)]
        for pct in PCTS:
            cells = [str(pct) + "%"]
            for label, protocol in PROTOCOLS:
                row = e3key[(protocol, attack, pct)]
                cells.append(metric_cell(row, "pdr", pct=True))
            md.append("| " + " | ".join(cells) + " |")
        md.append("")
    md += ["### E3 detection and paired delivery analysis", "",
           "EAURP and the two DRL-EAURP baselines do not use the AR GAN detector; their detector-specific fields are not comparable. AR detector values below are the project’s per-window metrics.", "",
           "| Attack | Hostile nodes | AR window TPR | AR window FPR | AR score AUC | AR−EAURP PDR (pp) | Paired 95% CI (pp) | AR wins |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    runs = matched_e3()
    paired_summary = []
    for attack in ATTACKS:
        for pct in PCTS:
            row = e3key[("ar-eaurp", attack, pct)]
            ar = runs[(attack, pct, "ar-eaurp")]
            base = runs[(attack, pct, "eaurp")]
            diffs = [100 * (a["pdr"] - b["pdr"]) for a, b in zip(ar, base)]
            n = len(diffs)
            mean = sum(diffs) / n
            sd = math.sqrt(sum((x - mean) ** 2 for x in diffs) / (n - 1))
            lo, hi = ci95(mean, sd, n)
            wins = sum(d > 0 for d in diffs)
            md.append("| {} | {}% | {} | {} | {} | {:.2f} | [{:.2f}, {:.2f}] | {}/{} |".format(
                attack.replace("_", " "), pct, fmt(row["detect_tpr"], row["detect_tpr_std"], True),
                fmt(row["detect_fpr"], row["detect_fpr_std"], True),
                fmt(row["detector_auc"], row["detector_auc_std"]), mean, lo, hi, wins, n))
            paired_summary.append({"attack": attack, "malicious_pct": pct, "paired_pdr_delta_pp": mean,
                                   "paired_delta_sd_pp": sd, "paired_ci95_low_pp": lo,
                                   "paired_ci95_high_pp": hi, "ar_wins": wins, "n": n})
    md += ["", "The paired interval is for AR-EAURP minus EAURP PDR within that attack/prevalence condition. A positive point estimate is not, by itself, evidence of superiority; inspect the interval and the five paired outcomes in the raw checkpoints.", ""]

    for section, csv_name, cols in [
        ("E4 — Energy mode", "e4_energy", [("label", "Configuration", False), ("pdr", "PDR", True), ("residual_energy_j", "Residual energy (J)", False), ("dead_nodes", "Dead nodes", False)]),
        ("E4b — Network lifetime", "e4b_lifetime", [("label", "Configuration", False), ("first_death_s", "First death (s)", False), ("eighty_pct_dead_s", "80% dead (s)", False), ("residual_energy_j", "Residual energy (J)", False)]),
        ("E5 — AR-EAURP component ablations", "e5_ablation", [("label", "Configuration", False), ("pdr", "PDR", True), ("detect_tpr", "Window TPR", True), ("detect_fpr", "Window FPR", True), ("detector_auc", "Score AUC", False)]),
        ("E5b — CMDP PDR floor", "e5b_cmdp_floor", [("label", "Configuration", False), ("pdr", "PDR", True), ("cmdp_lambda", "Final CMDP λ", False), ("cmdp_lambda_peak", "Peak CMDP λ", False)]),
        ("E6 — Security overhead", "e6_overhead", [("label", "Configuration", False), ("pdr", "PDR", True), ("crypto_overhead_bytes", "Crypto overhead (B)", False), ("control_bytes", "Control bytes", False), ("mean_delay_s", "Delay (s)", False)]),
    ]:
        md += [f"## {section}", ""]
        md += [t_markdown(load_rows(csv_name), cols), ""]
    md += [
        "## Interpretation and limits",
        "",
        "1. E3 is the direct attack-prevalence comparison. Read the protocol rows at each attack and prevalence rather than collapsing all hostile fractions into one score.",
        "2. PDR is application packets received divided by packets sent in the measured window, with arrivals through cooldown. Delay and throughput are also application-level metrics.",
        "3. The planned design uses five run numbers per condition. The completion-status table reports the actual number used for each experiment; single-run conditions have no empirical SD or confidence interval and support descriptive observations only. Multiple comparisons across many cells are exploratory and no family-wise error correction is applied.",
        "4. Pairing matches the configured ns-3 seed and run number across protocols. It does not force event-by-event identical random draws; protocol-specific event paths can consume random streams differently.",
        "5. AR’s TPR/FPR/AUC are detector measurements. Baseline protocols do not implement that detector, so a zero/default baseline detector value must not be interpreted as perfect classification or compared as a detector score.",
        "6. The lifetime experiment includes censored runs. Censored observations must not be treated as observed death times; the raw observed/censored flags are preserved in the CSV.",
        "7. These simulations support claims only for the stated ns-3 models and factor ranges. They do not establish real-world wireless performance without calibration and independent replication.",
        "",
        "## Files and provenance",
        "",
        "- `study_settings.json`: complete configuration and factor-level manifest.",
        "- `configuration_settings.csv`: full settings plus aggregate result for every condition.",
        "- `run_settings.csv`: settings and raw checkpoint provenance for each completed individual run.",
        "- `csv/`: aggregate condition-level results, including all `cfg_*` settings and sample SDs.",
        "- `raw/`: checksummed per-run metric checkpoints used for the paired E3 PDR analysis.",
        "- `report.md`, `report.html`, and `figures/`: native experiment-runner report and plots.",
        "- `paper_results.md`: this expanded paper-style summary.",
        "",
    ]
    condition_count, run_count = write_settings_ledgers()
    if not condition_count or not run_count or condition_count > 181 or run_count > 905:
        raise RuntimeError(f"Invalid completion counts: {condition_count} conditions and {run_count} runs")
    pairwise_count = write_all_pairwise_e3()
    if pairwise_count != 180:
        raise RuntimeError(f"Expected 180 paired E3 contrasts, got {pairwise_count}")
    planned_conditions = {"e1_speed": 25, "e2_density": 30, "e3_attack": 90, "e4_energy": 10,
                          "e4b_lifetime": 10, "e5_ablation": 6, "e5b_cmdp_floor": 4, "e6_overhead": 6}
    condition_counts = {name: len(load_rows(name)) for name in planned_conditions}
    run_counts = defaultdict(int)
    with (ROOT / "run_settings.csv").open(newline="", encoding="utf-8") as stream:
        for record in csv.DictReader(stream):
            run_counts[record["experiment"]] += 1
    status_lines = ["## Completion status", "",
                    f"Completed {condition_count} of 181 planned conditions and {run_count} of 905 planned native runs. The time-boxed E2 density sweep has missing replications; they are absent from the ledgers and are not imputed.", "",
                    "| Experiment | Completed conditions | Completed runs |", "|---|---:|---:|"]
    for name, planned in planned_conditions.items():
        status_lines.append(f"| {name} | {condition_counts[name]}/{planned} | {run_counts[name]}/{planned * 5} |")
    insert_at = md.index("## E1 — Mobility")
    md[insert_at:insert_at] = status_lines + [""]
    figure_names = render_figures()
    md[md.index("## Files and provenance"):] = [
        "## Visual comparisons", "",
        "Error bars show sample standard deviation. In the density figure, open circles mark single-run conditions (n=1), which are descriptive only.", "",
        *[f"![{name}](figures/{name}.svg)" for name in figure_names],
        "",
        "## Files and provenance", "",
        f"- Completed {condition_count} of 181 planned conditions and {run_count} of 905 planned ns-3 runs; per-experiment coverage is tabulated above.",
        "- `study_settings.json`: complete configuration and factor-level manifest.",
        "- `configuration_settings.csv`: full settings plus aggregate result for every condition.",
        "- `run_settings.csv`: settings and raw checkpoint provenance for each completed individual run.",
        "- `pairwise_e3_comparisons.csv`: all ten matched protocol-pair PDR contrasts across the 18 attack/prevalence conditions, with 95% intervals and per-run differences.",
        "- `csv/`: aggregate condition-level results, including simulator-reported cfg_* settings and sample SDs.",
        "- `raw/`: checksummed per-run metric checkpoints used for the paired E3 PDR analysis.",
        "- `report.md`, `report.html`, and `figures/`: native experiment-runner tables, plot scripts, and rendered SVG/PNG figures.",
        "- `paper_results.md`: this expanded paper-style summary.", "",
    ]
    study = settings()
    study["completion"] = {
        "status": "time-boxed partial matrix", "completed_conditions": condition_count,
        "planned_conditions": 181, "completed_native_runs": run_count,
        "planned_native_runs": 905, "condition_counts_by_experiment": condition_counts,
        "run_counts_by_experiment": dict(run_counts), "incomplete_runs_are_imputed": False,
    }
    (ROOT / "study_settings.json").write_text(json.dumps(study, indent=2) + "\n", encoding="utf-8")
    (ROOT / "paired_e3_summary.json").write_text(json.dumps(paired_summary, indent=2) + "\n", encoding="utf-8")
    markdown = "\n".join(md)
    (ROOT / "paper_results.md").write_text(markdown, encoding="utf-8")
    import mistune
    rendered = mistune.create_markdown(plugins=["table"])(markdown)
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Native ns-3 Comparative Evaluation</title>
<style>body{font:16px/1.6 system-ui,sans-serif;color:#182433;background:#f4f7fa;margin:0}main{max-width:1180px;margin:32px auto;padding:36px;background:#fff;border-radius:14px;box-shadow:0 6px 28px #20334a18}h1,h2,h3{line-height:1.25;color:#12334c}h2{margin-top:2.2em;border-bottom:1px solid #d8e2eb;padding-bottom:.35em}table{border-collapse:collapse;width:100%;display:block;overflow-x:auto;margin:1em 0}th,td{padding:8px 11px;border:1px solid #d8e2eb;text-align:left;white-space:nowrap}th{background:#eaf1f6}img{max-width:100%;height:auto}code{overflow-wrap:anywhere;background:#f1f4f7;padding:2px 4px;border-radius:4px}.downloads{position:sticky;top:0;background:#10334b;color:#fff;padding:12px 24px;display:flex;gap:20px;flex-wrap:wrap}.downloads a{color:#8de7fa}</style></head><body>
<nav class="downloads"><strong>Study files</strong><a href="study_settings.json">Settings JSON</a><a href="configuration_settings.csv">Condition settings &amp; results</a><a href="run_settings.csv">Per-run settings &amp; checksums</a><a href="pairwise_e3_comparisons.csv">All paired E3 contrasts</a><a href="paired_e3_summary.json">AR vs EAURP summary</a></nav>
<main>""" + rendered + "</main></body></html>"""
    (ROOT / "paper_results.html").write_text(html, encoding="utf-8")
    print(f"Wrote {ROOT / 'paper_results.md'}")
    print(f"Wrote {ROOT / 'paper_results.html'}")
    print(f"Wrote {ROOT / 'study_settings.json'}")
    print(f"Wrote {condition_count} conditions and {run_count} per-run settings records")


if __name__ == "__main__":
    main()
