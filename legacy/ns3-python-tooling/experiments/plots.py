"""Render ns-3 figures with physical units and seed standard deviations."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .harness import DEFAULT_OUT, POLICIES, as_float, out_path
from .report import build_comparison

COLOURS = dict(zip((label for label, _ in POLICIES), ("#777777", "#6a9fb5", "#2f6f9f", "#e08a1e", "#c0392b")))


def _save(fig, name, out_dir):
    fig.tight_layout()
    path = out_path("figures", name + ".png", out_dir=out_dir)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _curves(rows, xkey, xlabel, name, out_dir):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    metrics = (("pdr", "PDR", 1), ("mean_delay_s", "Mean delay (ms)", 1000),
               ("loss_packets", "Application packet losses", 1), ("throughput_bps", "Throughput (kbit/s)", 0.001))
    for label, _ in POLICIES:
        values = sorted((row for row in rows if row.get("policy_label") == label), key=lambda row: float(row[xkey]))
        for ax, (metric, ylabel, scale) in zip(axes.flat, metrics):
            ax.errorbar(as_float(values, xkey), as_float(values, metric) * scale,
                        yerr=as_float(values, metric + "_std", 0) * scale,
                        label=label, color=COLOURS[label], marker="o", capsize=2)
            ax.set(xlabel=xlabel, ylabel=ylabel)
            ax.grid(alpha=0.25)
    axes.flat[0].legend(fontsize=7)
    return _save(fig, name, out_dir)


def render_all(out_dir=None):
    report = build_comparison(out_dir)
    data = report["experiments"]
    files = []
    for name, key, xlabel in (("e1_speed", "speed_value", "Maximum speed (m/s)"),
                              ("e2_density", "node_count", "Number of nodes")):
        if data[name]:
            files.append(_curves(data[name], key, xlabel, name, out_dir))
    attacks = data["e3_attack"]
    for attack in sorted({row["attack_type"] for row in attacks}):
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        for label, protocol in POLICIES:
            rows = sorted((row for row in attacks if row["attack_type"] == attack and row["policy_label"] == label),
                          key=lambda row: float(row["malicious_pct"]))
            for ax, metric, ylabel in zip(axes, ("pdr", "detect_tpr" if protocol == "ar-eaurp" else "revoke_tpr",
                                                 "detect_fpr" if protocol == "ar-eaurp" else "revoke_fpr"),
                                          ("PDR", "Node flag TPR", "Node flag FPR")):
                ax.plot(as_float(rows, "malicious_pct"), as_float(rows, metric), marker="o", color=COLOURS[label], label=label)
                ax.set(xlabel="Malicious nodes (%)", ylabel=ylabel, ylim=(-0.02, 1.02))
                ax.grid(alpha=0.25)
        axes[0].legend(fontsize=6)
        fig.suptitle(attack.replace("_", " ") + " — C contested flags; others revocations")
        files.append(_save(fig, "e3_" + attack, out_dir))
    energy = data["e4_energy"]
    if energy:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        positions = np.arange(len(energy))
        for offset, metric, label in ((-.2, "residual_energy_j", "Residual"), (.2, "harvested_j", "Harvested")):
            axes[0].bar(positions + offset, as_float(energy, metric), .4, label=label)
        axes[0].set_xticks(positions, [r["label"] for r in energy], rotation=55, ha="right", fontsize=6)
        axes[0].set_ylabel("Energy (J), at measurement end")
        axes[0].legend()
        trained = [r for r in energy if float(r["lstm_trained"]) == 1]
        for offset, metric, label in ((-.25, "lstm_mae_w", "LSTM"), (0, "lstm_persistence_mae_w", "Persistence"),
                                     (.25, "lstm_window_mean_mae_w", "Window mean")):
            axes[1].bar(np.arange(len(trained)) + offset, as_float(trained, metric), .25, label=label)
        axes[1].set_xticks(np.arange(len(trained)), [r["label"] for r in trained], rotation=55, ha="right", fontsize=6)
        axes[1].set_ylabel("Commissioning holdout MAE (W)")
        axes[1].legend()
        if not trained:
            axes[1].text(.5, .5, "No trained LSTM in these runs", ha="center", transform=axes[1].transAxes)
        files.append(_save(fig, "e4_energy", out_dir))
    floors = data["e5b_cmdp_floor"]
    if floors:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        x = as_float(floors, "pdr_floor")
        axes[0].errorbar(x, as_float(floors, "pdr"), yerr=as_float(floors, "pdr_std", 0), marker="o", label="Achieved")
        axes[0].plot(x, x, "--", label="Target")
        axes[0].set(xlabel="PDR constraint", ylabel="PDR", ylim=(0, 1.02))
        axes[0].legend()
        axes[1].plot(x, as_float(floors, "cmdp_lambda"), marker="o", label="Final")
        axes[1].plot(x, as_float(floors, "cmdp_lambda_peak"), marker="s", label="Peak")
        axes[1].set(xlabel="PDR constraint", ylabel="Constraint multiplier")
        axes[1].legend()
        files.append(_save(fig, "e5b_cmdp_floor", out_dir))
    overhead = data["e6_overhead"]
    if overhead:
        fig, axes = plt.subplots(1, 3, figsize=(13, 5))
        for ax, metric, ylabel in zip(axes, ("control_packets", "wall_clock_seconds", "crypto_overhead_bytes"),
                                     ("Generated control messages", "Wall time incl. commissioning (s)", "Crypto overhead (bytes)")):
            ax.bar(np.arange(len(overhead)), as_float(overhead, metric), color="#2f6f9f")
            ax.set_xticks(np.arange(len(overhead)), [r["label"] for r in overhead], rotation=55, ha="right", fontsize=6)
            ax.set_ylabel(ylabel)
            ax.grid(axis="y", alpha=.25)
        files.append(_save(fig, "e6_overhead", out_dir))
    for name, metric, ylabel in (("e4b_lifetime", "first_death_s", "First death (s); unavailable bars are censored"),
                                 ("e5_ablation", "pdr", "PDR")):
        rows = data[name]
        if not rows:
            continue
        fig, ax = plt.subplots(figsize=(10, 5))
        y = as_float(rows, metric)
        labels = [row["label"] for row in rows]
        if name == "e4b_lifetime":
            for i, row in enumerate(rows):
                if float(row["first_death_observed"]) != 1:
                    y[i] = np.nan
                    labels[i] += " (censored/mixed)"
        ax.bar(np.arange(len(rows)), y, color="#2f6f9f")
        ax.set_xticks(np.arange(len(rows)), labels, rotation=55, ha="right", fontsize=7)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        files.append(_save(fig, name, out_dir))
    return files
