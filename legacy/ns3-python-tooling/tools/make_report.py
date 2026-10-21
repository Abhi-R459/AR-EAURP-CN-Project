"""Generate an ns-3 report from measured CSVs; never reuse historical numbers."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from experiments.harness import DEFAULT_OUT
from experiments.report import build_comparison
from experiments.plots import render_all


def number(row, key, scale=1):
    return f"{float(row.get(key, 0)) * scale:.4g}"


def table(lines, rows, columns):
    lines += ["| Configuration | " + " | ".join(title for title, _, _ in columns) + " |",
              "|---|" + "---:|" * len(columns)]
    for row in rows:
        values = [number(row, key, scale) for _, key, scale in columns]
        lines.append("| " + row["label"].replace("|", " / ") + " | " + " | ".join(values) + " |")
    lines.append("")


def make_report(out_dir=None, destination=None):
    data = build_comparison(out_dir)
    figures = render_all(out_dir)  # regenerate from the same verified CSVs
    manifest = data["manifest"]
    profile = manifest.get("profile", {}).get("name", "unrecorded")
    lines = ["# AR-EAURP — ns-3 evaluation", "", f"Engine: ns-3.45 C++; profile: **{profile}**.", "",
             f"Source/build fingerprint: `{manifest.get('source_sha256', 'unrecorded')}`.", ""]
    if profile == "smoke":
        lines += ["These short single-seed runs validate the migration. They do not support performance or detection-accuracy claims.", ""]
    for name, rows in data["experiments"].items():
        if not rows:
            continue
        lines += ["## " + name.replace("_", " ").upper(), "",
                  "| Configuration | Runs | PDR ± seed SD | Delay (ms) | Throughput (kbit/s) | GAN trained | LSTM trained |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for row in rows:
            label = row["label"].replace("|", " / ")
            lines.append(f"| {label} | {row['runs']} | {number(row, 'pdr')} ± {number(row, 'pdr_std')} | "
                         f"{number(row, 'mean_delay_s', 1000)} | {number(row, 'throughput_bps', .001)} | "
                         f"{number(row, 'gan_trained')} | {number(row, 'lstm_trained')} |")
        lines.append("")
        if name == "e3_attack":
            lines += ["C's detector flags require two honest witnesses; revocations require one. Counts are node-level; zero malicious nodes has TPR zero by convention.", ""]
            table(lines, rows, (("Contested TPR", "detect_tpr", 1), ("Contested FPR", "detect_fpr", 1),
                                ("Revocation TPR", "revoke_tpr", 1), ("Revocation FPR", "revoke_fpr", 1),
                                ("Scored windows", "detector_windows", 1)))
        if name == "e4_energy":
            table(lines, rows, (("Residual energy (J)", "residual_energy_j", 1),
                                ("Harvested energy (J)", "harvested_j", 1),
                                ("Residual fraction", "mean_residual_fraction", 1)))
            lines += ["Forecast errors below use disjoint commissioning holdouts in watts. A zero error with an untrained flag is a placeholder, not a perfect forecast.", ""]
            table(lines, rows, (("LSTM trained", "lstm_trained", 1),
                                ("Training sequences", "lstm_train_sequences", 1),
                                ("Validation sequences", "lstm_validation_sequences", 1),
                                ("LSTM MAE (W)", "lstm_mae_w", 1),
                                ("Persistence MAE (W)", "lstm_persistence_mae_w", 1),
                                ("Window mean MAE (W)", "lstm_window_mean_mae_w", 1)))
        if name in ("e5_ablation", "e5b_cmdp_floor"):
            lines += ["Multiplier, violations and actions count policy activity across the evaluation run, including warmup and feedback during cooldown. Achieved PDR uses the measurement cohort.", ""]
            table(lines, rows, (("Target PDR", "cfg_pdr_floor", 1), ("Achieved PDR", "pdr", 1),
                                ("Final multiplier", "cmdp_lambda", 1), ("Peak multiplier", "cmdp_lambda_peak", 1),
                                ("Violations", "cmdp_violations", 1), ("Decisions", "cmdp_decisions", 1)))
            table(lines, rows, (("Trust actions", "cmdp_action_trust", 1),
                                ("Energy actions", "cmdp_action_energy_surplus", 1),
                                ("Balanced actions", "cmdp_action_balanced", 1),
                                ("Diversified actions", "cmdp_action_diversified", 1)))
        if name == "e6_overhead":
            lines += ["Wall time includes commissioning and crypto computation. Crypto counts cover messages transmitted during the measurement window, including ACKs. Wall time is host runtime, not simulated processing delay.", ""]
            table(lines, rows, (("Generated control messages", "control_packets", 1),
                                ("Wall time (s)", "wall_clock_seconds", 1),
                                ("Crypto messages", "crypto_packets", 1),
                                ("Crypto overhead (bytes)", "crypto_overhead_bytes", 1),
                                ("Authentication failures", "crypto_auth_failures", 1)))
        if name == "e4b_lifetime":
            lines += ["| Configuration | First death | 80% deaths | Horizon (s) |", "|---|---:|---:|---:|"]
            for row in rows:
                def lifetime(time_key, flag_key):
                    flag = float(row[flag_key])
                    return number(row, time_key) + " s" if flag == 1 else ("censored" if flag == 0 else "mixed observed/censored seeds")
                lines.append(f"| {row['label'].replace('|', ' / ')} | {lifetime('first_death_s', 'first_death_observed')} | "
                             f"{lifetime('eighty_pct_dead_s', 'eighty_pct_death_observed')} | {number(row, 'lifetime_horizon_s')} |")
            lines.append("")
    lines += ["## Interpretation and modelling limits", "", *["- " + caveat for caveat in data["caveats"]], ""]
    for figure in figures:
        figure = Path(figure)
        # Absolute paths make the report preview usable inside the app.
        lines += [f"![{figure.stem}]({figure.resolve()})", ""]
    path = Path(destination or ROOT / "report/REVIEW2_REPORT.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    return str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    parser.add_argument("--output")
    args = parser.parse_args()
    print(make_report(args.out_dir, args.output))


if __name__ == "__main__":
    main()
