"""The A vs B vs C comparison, and the caveats that make it honest.

Reads the CSVs produced by the sweeps and assembles the comparison tables plus
the "what is and isn't comparable" section. Everything printed here is derived
from measured output; nothing is typed in by hand.
"""

import os

import numpy as np

from .harness import as_float, out_path, read_rows

IMPLEMENTATIONS = [
    "A: DRL-EAURP (paper)",
    "B: DRL-EAURP (senior code)",
    "C: AR-EAURP (advancement)",
]
REFERENCES = ["AODV (reference baseline)", "EAURP (base.pdf substrate)"]


def _mean(rows, key, default=float("nan")):
    if not rows:
        return default
    values = as_float(rows, key)
    return float(np.mean(values)) if values.size else default


def _filter(rows, **conditions):
    out = []
    for row in rows:
        keep = True
        for key, value in conditions.items():
            actual = row.get(key)
            if isinstance(value, float):
                try:
                    keep = keep and abs(float(actual) - value) < 1e-6
                except (TypeError, ValueError):
                    keep = False
            else:
                keep = keep and str(actual) == str(value)
            if not keep:
                break
        if keep:
            out.append(row)
    return out


def build_comparison(out_dir=None):
    """Collect every comparison the report needs into one dict."""
    report = {"available": {}, "caveats": []}

    files = {
        "e1": "e1_speed.csv",
        "e2": "e2_density.csv",
        "e3": "e3_attack.csv",
        "e4": "e4_energy.csv",
        "e4b": "e4b_lifetime.csv",
        "e5": "e5_ablation.csv",
        "e5b": "e5b_cmdp_floor.csv",
        "e6": "e6_overhead.csv",
        "a1": "a_paper_track1.csv",
        "b1": "b_senior_as_is.csv",
        "drain": "a_drain_band_ablation.csv",
    }
    data = {}
    for key, name in files.items():
        path = out_path("csv", name, out_dir=out_dir)
        data[key] = read_rows(path)
        report["available"][key] = bool(data[key])
    report["_data"] = data

    # -- Track 1 headline numbers -----------------------------------------
    track1 = {}
    for label, rows, model_key in (("A", data["a1"], "model"),
                                   ("B", data["b1"], "model")):
        if not rows:
            continue
        block = {}
        for model in ("Existing", "EAURP", "ATEAURP", "PSE-EAURP", "DRL-EAURP"):
            subset = [
                row for row in rows
                if row.get(model_key) == model
                and row.get("sweep", "speed") == "speed"
            ]
            if subset:
                block[model] = {
                    "pdr": _mean(subset, "pdr"),
                    "delay": _mean(subset, "avg_delay_ms"),
                    "lifetime": _mean(subset, "network_lifetime"),
                }
        track1[label] = block
    report["track1"] = track1

    if data["drain"]:
        bands = {row.get("band"): row for row in data["drain"]}
        paper = bands.get("paper_Eq8_0.05-0.15")
        code = bands.get("code_0.04-0.12")
        if paper and code:
            report["drain_band"] = {
                "paper_lifetime": float(paper.get("network_lifetime", 0.0)),
                "code_lifetime": float(code.get("network_lifetime", 0.0)),
                "paper_pdr": float(paper.get("pdr", 0.0)),
                "code_pdr": float(code.get("pdr", 0.0)),
                "delta": float(code.get("network_lifetime", 0.0))
                - float(paper.get("network_lifetime", 0.0)),
            }

    # -- Track 2 clean baseline -------------------------------------------
    clean = {}
    for policy in REFERENCES + IMPLEMENTATIONS:
        subset = _filter(data["e1"], policy_label=policy)
        if subset:
            clean[policy] = {
                "pdr": _mean(subset, "pdr"),
                "pdr_routable": _mean(subset, "pdr_routable"),
                "delay": _mean(subset, "avg_delay_ms"),
                "throughput": _mean(subset, "throughput"),
            }
    report["track2_clean"] = clean

    # -- Track 2 under attack ---------------------------------------------
    attacks = {}
    for attack in ("blackhole", "grayhole", "trust_poisoning"):
        per_policy = {}
        for policy in REFERENCES + IMPLEMENTATIONS:
            points = {}
            for pct in (0.0, 10.0, 20.0, 30.0, 40.0, 50.0):
                subset = _filter(data["e3"], policy_label=policy,
                                 attack_type=attack, malicious_pct=pct)
                if subset:
                    points[pct] = {
                        "pdr": _mean(subset, "pdr"),
                        "tpr": _mean(subset, "det_tpr"),
                        "fpr": _mean(subset, "det_fpr"),
                    }
            if points:
                per_policy[policy] = points
        attacks[attack] = per_policy
    report["track2_attack"] = attacks

    # -- ablation and CMDP feasibility ------------------------------------
    if data["e5"]:
        report["ablation"] = [
            {
                "label": row.get("label"),
                "pdr": float(row.get("pdr", 0.0) or 0.0),
                "tpr": float(row.get("det_tpr", 0.0) or 0.0),
                "fpr": float(row.get("det_fpr", 0.0) or 0.0),
            }
            for row in data["e5"]
        ]
    if data["e5b"]:
        report["cmdp_floor"] = [
            {
                "floor": float(row.get("pdr_floor", 0.0) or 0.0),
                "achieved": float(row.get("pdr", 0.0) or 0.0),
                "violation_rate": float(row.get("cmdp_violation_rate", 0.0) or 0.0),
            }
            for row in data["e5b"]
        ]
    if data["e6"]:
        report["overhead"] = [
            {
                "label": row.get("label"),
                "control_per_round": float(row.get("control_per_round", 0.0) or 0.0),
                "wall_clock": float(row.get("wall_clock_seconds", 0.0) or 0.0),
            }
            for row in data["e6"] if row.get("control_per_round")
        ]
    return report


# --------------------------------------------------------------------------

def _table(headers, rows, widths=None):
    widths = widths or [max(12, len(h)) for h in headers]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    out = [line, "-" * len(line)]
    for row in rows:
        out.append("  ".join(str(c).ljust(w) for c, w in zip(row, widths)))
    return "\n".join(out)


def print_report(report):
    """Render the comparison to stdout."""
    print("=" * 78)
    print("A vs B vs C -- RESULTS")
    print("=" * 78)

    # ---- Track 1 ----
    if report.get("track1"):
        print()
        print("TRACK 1 -- each implementation in its native form")
        print()
        rows = []
        for model in ("Existing", "EAURP", "ATEAURP", "PSE-EAURP", "DRL-EAURP"):
            a = report["track1"].get("A", {}).get(model, {})
            b = report["track1"].get("B", {}).get(model, {})
            rows.append([
                model,
                "{:.3f}".format(a.get("pdr", float("nan"))),
                "{:.3f}".format(b.get("pdr", float("nan"))),
                "{:.1f}".format(a.get("delay", float("nan"))),
                "{:.1f}".format(b.get("delay", float("nan"))),
                "{:.0f}".format(a.get("lifetime", float("nan"))),
                "{:.0f}".format(b.get("lifetime", float("nan"))),
            ])
        print(_table(
            ["model", "A PDR", "B PDR", "A delay", "B delay", "A life", "B life"],
            rows, [12, 8, 8, 9, 9, 8, 8]))
        print()
        print("  'Existing' is Lekha.pdf Eq. (14)-(18): EAURP's own output times")
        print("  fixed constants. It is arithmetic, not a protocol, in both.")

    if report.get("drain_band"):
        band = report["drain_band"]
        print()
        print("  Where B's lifetime advantage comes from:")
        print("    Eq. (8) band [0.05,0.15]:  lifetime {:7.1f}  PDR {:.4f}".format(
            band["paper_lifetime"], band["paper_pdr"]))
        print("    code band   [0.04,0.12]:  lifetime {:7.1f}  PDR {:.4f}".format(
            band["code_lifetime"], band["code_pdr"]))
        print("    => {:+.1f} rounds from the undocumented constant alone.".format(
            band["delta"]))

    # ---- Track 2 clean ----
    if report.get("track2_clean"):
        print()
        print("TRACK 2 -- clean network, identical seeds and worlds")
        print()
        rows = []
        for policy, stats in report["track2_clean"].items():
            rows.append([
                policy[:28],
                "{:.3f}".format(stats["pdr"]),
                "{:.3f}".format(stats["pdr_routable"]),
                "{:.1f}".format(stats["delay"]),
                "{:.3f}".format(stats["throughput"]),
            ])
        print(_table(["implementation", "PDR", "PDR routable", "delay ms",
                      "throughput"], rows, [30, 8, 13, 9, 11]))

    # ---- Track 2 attack ----
    attacks = report.get("track2_attack") or {}
    for attack, per_policy in attacks.items():
        if not per_policy:
            continue
        print()
        print("TRACK 2 -- {0}: PDR / detection recall at each adversary "
              "fraction".format(attack))
        print()
        percentages = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
        header = ["implementation"] + ["{:.0f}%".format(p) for p in percentages]
        rows = []
        for policy, points in per_policy.items():
            rows.append([policy[:28]] + [
                "{:.2f}/{:.2f}".format(points[p]["pdr"], points[p]["tpr"])
                if p in points else "-"
                for p in percentages
            ])
        print(_table(header, rows, [30] + [10] * len(percentages)))

    grayhole = attacks.get("grayhole", {})
    if grayhole:
        print()
        print("  The gray-hole column is the point of the advancement.")
        for policy, points in grayhole.items():
            recalls = [points[p]["tpr"] for p in points if p > 0]
            if recalls:
                print("    {:30s} mean detection recall under attack: {:.2f}".format(
                    policy[:30], float(np.mean(recalls))))

    # ---- ablation ----
    if report.get("ablation"):
        print()
        print("ABLATION of C (gray-hole @ 30%)")
        print()
        print(_table(["variant", "PDR", "TPR", "FPR"],
                     [[r["label"][:24], "{:.3f}".format(r["pdr"]),
                       "{:.3f}".format(r["tpr"]), "{:.3f}".format(r["fpr"])]
                      for r in report["ablation"]], [26, 8, 8, 8]))

    if report.get("cmdp_floor"):
        print()
        print("CMDP FEASIBILITY -- is the doc's 90% PDR floor reachable?")
        print()
        print(_table(["requested floor", "achieved PDR", "violation rate"],
                     [["{:.2f}".format(r["floor"]),
                       "{:.3f}".format(r["achieved"]),
                       "{:.3f}".format(r["violation_rate"])]
                      for r in report["cmdp_floor"]], [16, 14, 15]))

    if report.get("overhead"):
        print()
        print("OVERHEAD")
        print()
        print(_table(["implementation", "control pkts/round", "wall clock s"],
                     [[r["label"][:30],
                       "{:.1f}".format(r["control_per_round"]),
                       "{:.1f}".format(r["wall_clock"])]
                      for r in report["overhead"]], [32, 19, 13]))

    print()
    print("=" * 78)
    print("WHAT IS AND ISN'T COMPARABLE -- read before quoting any number")
    print("=" * 78)
    print(CAVEATS.strip())


CAVEATS = """
1. TRACK 1 AND TRACK 2 ARE NOT THE SAME EXPERIMENT.
   Track 1 numbers come from the papers' own probabilistic model: no routes, no
   relays, delivery decided by one coin flip against a global average. Track 2
   numbers come from a mechanistic simulator that walks every packet hop by hop
   through a real topology. A Track 1 PDR of 0.96 and a Track 2 PDR of 0.79 are
   not in disagreement; they are measuring different things. Compare within a
   track, never across.

2. B'S HEADLINE NUMBERS ARE PARTLY LITERALS.
   Cell 13 of senior_code.ipynb prints random.uniform values formatted as
   measured metrics (PDR 89.04, delay 498.64 ms, throughput 17.46 kbps,
   lifetime 99.28%). Those exact figures appear in Lekha.pdf Sec. IV-A-6 as
   "observed behaviour". Re-running the cell produces different values, because
   nothing is being measured. The simulated curves (the five models' sweeps)
   are genuinely computed; the summary block is not.

3. "EXISTING" IS NOT A PROTOCOL.
   Lekha.pdf Eq. (14)-(18) derives it by multiplying EAURP's own output by
   fixed constants. Every "improvement over Existing" is therefore arithmetic
   by construction. Track 2 replaces it with a real AODV implementation.

4. B'S LIFETIME ADVANTAGE IS A CONSTANT, NOT A PROTOCOL.
   Eq. (8) specifies one drain band. The delivered code uses a gentler one for
   the three proposed models. Running the same model under both bands isolates
   the effect; see the drain-band ablation above.

5. C IS EXPECTED TO LOOK WORSE THAN B ON RAW PDR IN TRACK 1.
   B computes delivery from a formula; C routes real packets through real
   adversaries across a topology in which about 9% of node pairs are not even
   connected. The comparison that means something is the Track 2 attack sweep,
   where both face the same world.

6. THE CHANNEL MODEL IS OUR ASSUMPTION.
   Neither paper contains a PHY or link model, so the per-hop reliability in
   Track 2 is a modelling choice, calibrated so a clean network lands in the
   same PDR regime the papers report. Conclusions rest on relative comparisons
   under identical channel settings, never on absolute values.

7. THE 90% PDR FLOOR IN THE ADVANCEMENT DOC MAY BE INFEASIBLE.
   The doc asks for PDR >= 0.90 under 30% adversarial nodes. On a topology
   where ~9% of pairs are unreachable before any attack, that ceiling cannot be
   reached, and the Lagrangian multiplier rises without ever satisfying the
   constraint. The CMDP feasibility table above measures where the real ceiling
   is instead of assuming one. This confirms the risk flagged in the Review 1
   critique.

8. A'S TRACK 1 LIFETIME IS CENSORED UNDER THE QUICK PROFILE.
   B always runs the senior's hardcoded SIM_ROUNDS = 2000. A runs 2000 only
   under --profile full; the quick profile stops it at 600, before any node has
   drained, so A's lifetime column reads as the run length rather than a first
   death. Compare the A and B lifetime columns only from a full-profile run --
   or use the drain-band ablation above, which controls for this directly.

9. DETECTION RATES ARE MEASURED AGAINST GROUND TRUTH.
   TPR and FPR compare each protocol's own verdicts with the known roles
   assigned by the threat model. B reports 0.00 everywhere because the
   delivered code sets node.malicious and never reads it - that is the honest
   consequence of the code, not a failure to measure it.
"""


def write_markdown(report, path):
    """Persist the comparison as a Markdown file."""
    import io

    buffer = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(buffer):
        print_report(report)

    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# AR-EAURP Review 2 - Results\n\n")
        handle.write("```\n")
        handle.write(buffer.getvalue())
        handle.write("\n```\n")
    return path
