"""Figures for the Review-2 report.

Reads the CSVs written by ``sweeps`` and renders the figures. Kept separate
from the experiments so plots can be regenerated without re-running anything,
and so the sweeps stay importable on a machine without matplotlib.
"""

import os

import numpy as np

from src.common import config

from .harness import as_float, out_path, read_rows

try:  # pragma: no cover - depends on the runtime environment
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except Exception:  # pragma: no cover
    MATPLOTLIB_AVAILABLE = False

# One colour per implementation, used consistently across every figure.
COLOURS = {
    "AODV (reference baseline)": "#8c8c8c",
    "EAURP (base.pdf substrate)": "#6a9fb5",
    "A: DRL-EAURP (paper)": "#2f6f9f",
    "B: DRL-EAURP (senior code)": "#e08a1e",
    "C: AR-EAURP (advancement)": "#c0392b",
}
MARKERS = {
    "AODV (reference baseline)": "o",
    "EAURP (base.pdf substrate)": "s",
    "A: DRL-EAURP (paper)": "^",
    "B: DRL-EAURP (senior code)": "D",
    "C: AR-EAURP (advancement)": "v",
}
ORDER = list(COLOURS)

# Short forms for cramped bar-chart axes, so labels are never truncated
# mid-word into things like "EAURP (base.pd".
SHORT_NAMES = {
    "AODV (reference baseline)": "AODV",
    "EAURP (base.pdf substrate)": "EAURP",
    "A: DRL-EAURP (paper)": "A (paper)",
    "B: DRL-EAURP (senior code)": "B (senior)",
    "C: AR-EAURP (advancement)": "C (AR-EAURP)",
}


def _require():
    if not MATPLOTLIB_AVAILABLE:
        raise RuntimeError(
            "matplotlib is not available; figures cannot be rendered here"
        )


def _style(ax, title, xlabel, ylabel):
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(alpha=0.25, linewidth=0.6)
    ax.tick_params(labelsize=8)


def _series(rows, policy, x_key, y_key):
    subset = [row for row in rows if row.get("policy_label") == policy]
    if not subset:
        return None, None
    x = as_float(subset, x_key)
    y = as_float(subset, y_key)
    order = np.argsort(x)
    return x[order], y[order]


def _save(fig, name, out_dir=None):
    path = out_path("figures", name, out_dir=out_dir)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("  figure ->", path)
    return path


# --------------------------------------------------------------------------

def plot_speed(out_dir=None):
    """E1: the five metrics both papers report, against node speed."""
    _require()
    rows = read_rows(out_path("csv", "e1_speed.csv", out_dir=out_dir))
    if not rows:
        return None

    # Note the absence of a network-lifetime panel. Over a performance-sweep
    # run no node has drained yet, so "lifetime" would read as the run length
    # for every policy -- a flat line that looks like a result and is not one.
    # Lifetime gets its own long-horizon experiment; see plot_lifetime (E4b).
    panels = [
        ("pdr", "Packet Delivery Ratio", "PDR"),
        ("pdr_routable", "PDR among routable packets", "PDR (routable)"),
        ("avg_delay_ms", "Average end-to-end delay", "delay (ms)"),
        ("packet_loss_bytes", "Packet loss", "bytes lost"),
        ("throughput", "Throughput", "bits/round / 1000"),
        ("loss_no_route", "Packets with no route at all", "packets"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for ax, (key, title, ylabel) in zip(axes.ravel(), panels):
        for policy in ORDER:
            x, y = _series(rows, policy, "speed_value", key)
            if x is None:
                continue
            ax.plot(x, y, marker=MARKERS[policy], color=COLOURS[policy],
                    label=policy, linewidth=1.6, markersize=5)
        _style(ax, title, "node speed", ylabel)
    axes[0, 0].legend(fontsize=7, loc="best")
    fig.suptitle("E1 - Track 2: all implementations on one harness, identical "
                 "seeds.\nNetwork lifetime is measured separately over a long "
                 "horizon (E4b) - within this window no node has drained.",
                 fontsize=12)
    fig.tight_layout()
    return _save(fig, "e1_speed.png", out_dir=out_dir)


def plot_density(out_dir=None):
    """E2: performance against node count."""
    _require()
    rows = read_rows(out_path("csv", "e2_density.csv", out_dir=out_dir))
    if not rows:
        return None

    panels = [
        ("pdr", "Packet Delivery Ratio", "PDR"),
        ("loss_no_route", "Packets with no route at all", "packets"),
        ("avg_delay_ms", "Average delay", "delay (ms)"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))
    for ax, (key, title, ylabel) in zip(axes, panels):
        for policy in ORDER:
            x, y = _series(rows, policy, "node_count", key)
            if x is None:
                continue
            ax.plot(x, y, marker=MARKERS[policy], color=COLOURS[policy],
                    label=policy, linewidth=1.6, markersize=5)
        _style(ax, title, "number of nodes", ylabel)
    axes[0].legend(fontsize=7)
    fig.suptitle("E2 - node density. The 'no route' panel is topology, not "
                 "protocol: at N=60 only ~39% of node pairs are connected at all.",
                 fontsize=11)
    fig.tight_layout()
    return _save(fig, "e2_density.png", out_dir=out_dir)


def plot_lifetime(out_dir=None):
    """E4b: network lifetime, over a horizon long enough for deaths to happen.

    Kept apart from E1 deliberately. Both papers quote a ~1230-round lifetime
    alongside a 0.96 delivery ratio, which is only possible because their energy
    model charges an idle drain and never charges transmission. Once per-hop
    TX/RX cost is modelled the two quantities need different time horizons, and
    reporting them from one sweep hides that.
    """
    _require()
    rows = read_rows(out_path("csv", "e4b_lifetime.csv", out_dir=out_dir))
    if not rows:
        return None

    modes = ["linear", "solar"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, (key, title, ylabel) in zip(axes, [
        ("network_lifetime", "Round of first node death", "rounds"),
        ("eighty_pct_dead_round", "Round at which 80% of nodes are dead",
         "rounds"),
    ]):
        width = 0.35
        positions = np.arange(len(ORDER))
        for offset, mode in enumerate(modes):
            values = []
            for policy in ORDER:
                subset = [
                    row for row in rows
                    if row.get("policy_label") == policy
                    and row.get("energy_mode") == mode
                ]
                values.append(
                    float(np.mean(as_float(subset, key))) if subset else 0.0
                )
            ax.bar(positions + offset * width, values, width,
                   label="{0} energy".format(mode),
                   color="#6a9fb5" if mode == "linear" else "#c0392b",
                   alpha=0.9)
        ax.set_xticks(positions + width / 2.0)
        ax.set_xticklabels([SHORT_NAMES.get(p, p) for p in ORDER],
                           rotation=15, ha="right", fontsize=8)
        _style(ax, title, "", ylabel)
        ax.legend(fontsize=8)
        # Bars that sit exactly on the horizon are censored, not measured.
        if values and max(values) >= config.LIFETIME_ROUNDS - 1:
            ax.axhline(config.LIFETIME_ROUNDS, color="#666666",
                       linestyle=":", linewidth=1.0)
            ax.annotate("bars touching the dotted line are censored:\n"
                        "the run ended before 80% of nodes had died",
                        xy=(0.03, 0.055), xycoords="axes fraction",
                        ha="left", fontsize=7.5, color="#333333",
                        bbox=dict(boxstyle="round,pad=0.35", fc="#ffffff",
                                  ec="#888888", lw=0.6, alpha=0.92))
    fig.suptitle("E4b - network lifetime over a long horizon. Solar harvesting "
                 "is the advancement's replacement for Eq. (8).", fontsize=11)
    fig.tight_layout()
    return _save(fig, "e4b_lifetime.png", out_dir=out_dir)


def plot_attack(out_dir=None):
    """E3: the headline figure -- PDR and detection against adversary strength."""
    _require()
    rows = read_rows(out_path("csv", "e3_attack.csv", out_dir=out_dir))
    if not rows:
        return None

    attacks = ["blackhole", "grayhole", "trust_poisoning"]
    titles = {
        "blackhole": "Black-hole (drops 100%)",
        "grayhole": "Gray-hole (drops ~15%, PFR stays 0.84)",
        "trust_poisoning": "Trust poisoning (gray-hole + slander)",
    }

    fig, axes = plt.subplots(3, 3, figsize=(16, 12))
    for column, attack in enumerate(attacks):
        subset = [row for row in rows if row.get("attack_type") == attack]
        for row_index, (key, ylabel) in enumerate([
            ("pdr", "PDR"),
            ("det_tpr", "detection recall (TPR)"),
            ("det_fpr", "false-positive rate (FPR)"),
        ]):
            ax = axes[row_index, column]
            for policy in ORDER:
                x, y = _series(subset, policy, "malicious_pct", key)
                if x is None:
                    continue
                ax.plot(x, y, marker=MARKERS[policy], color=COLOURS[policy],
                        label=policy, linewidth=1.8, markersize=5)
            title = titles[attack] if row_index == 0 else ""
            _style(ax, title, "malicious nodes (%)", ylabel)
            if key in ("det_tpr", "det_fpr", "pdr"):
                ax.set_ylim(-0.03, 1.03)
    axes[0, 0].legend(fontsize=7, loc="best")

    fig.suptitle(
        "E3 - ATTACK SWEEP. Middle row is the point of the advancement: under "
        "gray-hole,\nevery prior implementation detects nothing at any attack "
        "level (TPR = 0).",
        fontsize=12,
    )
    fig.tight_layout()
    return _save(fig, "e3_attack.png", out_dir=out_dir)


def plot_ablation(out_dir=None):
    """E5: which component of C is doing the work."""
    _require()
    rows = read_rows(out_path("csv", "e5_ablation.csv", out_dir=out_dir))
    if not rows:
        return None

    labels = [row.get("label", "") for row in rows]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    for ax, (key, title, ylabel) in zip(axes, [
        ("pdr", "Packet Delivery Ratio", "PDR"),
        ("det_tpr", "Detection recall", "TPR"),
        ("det_fpr", "False-positive rate", "FPR"),
    ]):
        values = as_float(rows, key)
        positions = np.arange(len(labels))
        bars = ax.bar(positions, values, color="#c0392b", alpha=0.85)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
        # An all-zero column must read as a measured zero, not as a broken
        # axis: with no floor, matplotlib auto-ranges to +/-0.05 and draws
        # nothing at all, which looks like a rendering failure.
        top = max(0.05, float(values.max()) * 1.25) if values.size else 1.0
        ax.set_ylim(0.0, top)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2.0,
                    bar.get_height() + top * 0.02,
                    "{0:.3f}".format(value), ha="center", fontsize=7)
        _style(ax, title, "", ylabel)
    fig.suptitle("E5 - ablation of C under gray-hole @ 30%", fontsize=12)
    fig.tight_layout()
    figure = _save(fig, "e5_ablation.png", out_dir=out_dir)

    floors = read_rows(out_path("csv", "e5b_cmdp_floor.csv", out_dir=out_dir))
    if floors:
        fig, ax = plt.subplots(figsize=(7, 4.4))
        x = as_float(floors, "pdr_floor")
        achieved = as_float(floors, "pdr")
        violations = as_float(floors, "cmdp_violation_rate")
        order = np.argsort(x)
        ax.plot(x[order], achieved[order], marker="o", color="#c0392b",
                label="achieved PDR")
        ax.plot(x[order], x[order], linestyle="--", color="#666666",
                label="requested floor")
        ax.plot(x[order], violations[order], marker="s", color="#e08a1e",
                label="constraint violation rate")
        _style(ax, "E5b - is the CMDP floor reachable?", "requested PDR floor",
               "value")
        ax.legend(fontsize=8)
        fig.tight_layout()
        _save(fig, "e5b_cmdp_floor.png", out_dir=out_dir)
    return figure


def plot_track1_comparison(out_dir=None):
    """Track 1: A (from the paper) beside B (the delivered code)."""
    _require()
    a_rows = read_rows(out_path("csv", "a_paper_track1.csv", out_dir=out_dir))
    b_rows = read_rows(out_path("csv", "b_senior_as_is.csv", out_dir=out_dir))
    if not a_rows and not b_rows:
        return None

    models = ["Existing", "EAURP", "ATEAURP", "PSE-EAURP", "DRL-EAURP"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))

    for ax, (key, ylabel) in zip(axes, [
        ("pdr", "PDR"),
        ("avg_delay_ms", "delay (ms)"),
        ("network_lifetime", "lifetime (rounds)"),
    ]):
        for source, rows, style in (
            ("A (from paper)", a_rows, "-"),
            ("B (senior code)", b_rows, "--"),
        ):
            if not rows:
                continue
            values = []
            for model in models:
                subset = [
                    row for row in rows
                    if row.get("model") == model
                    and row.get("sweep", "speed") == "speed"
                ]
                values.append(float(np.mean(as_float(subset, key))) if subset else np.nan)
            ax.plot(models, values, style, marker="o",
                    label=source, linewidth=1.8, markersize=5)
            # A's lifetime is censored whenever it comes out flat at the run
            # length: under the quick profile A stops at 600 rounds, before
            # anything has drained, while B always runs the senior's hardcoded
            # 2000. Saying so on the figure stops it being read as a result.
            if key == "network_lifetime" and source.startswith("A"):
                finite = [v for v in values if np.isfinite(v)]
                if finite and (max(finite) - min(finite)) < 0.05 * max(finite):
                    ax.annotate(
                        "A censored: no node died within\n"
                        "the run (use --profile full)",
                        xy=(0.5, 0.12), xycoords="axes fraction",
                        ha="center", fontsize=7.5, color="#2f6f9f",
                        bbox=dict(boxstyle="round,pad=0.3", fc="#eef4fa",
                                  ec="#2f6f9f", lw=0.6))
        _style(ax, {"pdr": "Packet Delivery Ratio",
                    "avg_delay_ms": "Average delay",
                    "network_lifetime": "Network lifetime"}.get(key, key),
               "", ylabel)
        ax.tick_params(axis="x", rotation=20)
    axes[0].legend(fontsize=8)
    fig.suptitle("Track 1 - A (Lekha.pdf equations) vs B (delivered code). "
                 "'Existing' is derived arithmetic in both (Eq. 14-18), "
                 "not a protocol.", fontsize=11)
    fig.tight_layout()
    return _save(fig, "track1_a_vs_b.png", out_dir=out_dir)


def plot_gan_training(detector, out_dir=None):
    """GAN training curves, straight from a fitted detector."""
    _require()
    history = getattr(detector, "history", None)
    if not history or not history.get("d_loss"):
        print("  (no GAN training history -- detector used its fallback)")
        return None
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(history["d_loss"], label="discriminator", color="#2f6f9f", linewidth=1.2)
    ax.plot(history["g_loss"], label="generator", color="#c0392b", linewidth=1.2)
    _style(ax, "GAN training (honest behaviour only)", "epoch", "loss")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, "c_gan_training.png", out_dir=out_dir)


def plot_lstm_accuracy(predictor, out_dir=None):
    """LSTM forecast error beside both naive baselines."""
    _require()
    evaluation = getattr(predictor, "evaluation", None)
    if not evaluation:
        return None
    fallback = bool(getattr(predictor, "using_fallback", False))
    names = ["LSTM (fallback:\npersistence)" if fallback else "LSTM",
             "persistence", "seasonal naive"]
    values = [
        evaluation.get("lstm_mae", 0.0),
        evaluation.get("persistence_mae", 0.0),
        evaluation.get("seasonal_naive_mae", 0.0),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    bars = axes[0].bar(names, values, color=["#c0392b", "#8c8c8c", "#6a9fb5"])
    top = max(values) * 1.25 if max(values) > 0 else 1.0
    axes[0].set_ylim(0.0, top)
    for bar, value in zip(bars, values):
        axes[0].text(bar.get_x() + bar.get_width() / 2.0,
                     bar.get_height() + top * 0.02,
                     "{0:.5f}".format(value), ha="center", fontsize=7.5)
    title = "Harvest forecast error (lower is better)"
    if fallback:
        # Without torch the "model" *is* persistence, so the first two bars are
        # the same number. Say so, or the figure reads as a trained LSTM that
        # merely tied with a naive baseline.
        title += "\nno torch: the first bar IS persistence, not a trained LSTM"
    _style(axes[0], title, "", "MAE")

    history = getattr(predictor, "history", None)
    if history:
        axes[1].plot(history, color="#c0392b", linewidth=1.3)
        _style(axes[1], "LSTM training loss", "epoch", "MSE")
    else:
        axes[1].text(0.5, 0.5, "no training history\n(fallback in use)",
                     ha="center", va="center", fontsize=10)
        axes[1].axis("off")
    fig.tight_layout()
    return _save(fig, "c_lstm_accuracy.png", out_dir=out_dir)


def plot_all(out_dir=None):
    """Render every figure whose CSV exists."""
    _require()
    made = []
    for renderer in (plot_speed, plot_density, plot_attack, plot_lifetime,
                     plot_ablation, plot_track1_comparison):
        try:
            path = renderer(out_dir=out_dir)
            if path:
                made.append(path)
        except Exception as error:  # keep going; a missing sweep is not fatal
            print("  [warn] {0} failed: {1}".format(renderer.__name__, error))
    return made
