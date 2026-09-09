"""Run the whole Review-2 evaluation.

    python experiments/run_all.py --profile quick
    python experiments/run_all.py --profile full
    python experiments/run_all.py --only e3 --profile full

Track 1 (each implementation in its native form) and Track 2 (all three on one
mechanistic harness) are both produced. Sweeps checkpoint to CSV as they finish
and are skipped on a re-run unless ``--fresh`` is given, so a dropped Colab
session resumes instead of restarting.
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from experiments import sweeps  # noqa: E402
from experiments.harness import csv_path, pretrained_c, write_rows  # noqa: E402
from src.common import config  # noqa: E402


def run_track1(profile, out_dir=None, skip_b=False, verbose=True):
    """A from the paper's equations, B from the delivered code."""
    print("=" * 78)
    print("TRACK 1 -- each implementation in its native form")
    print("=" * 78)

    from src.a_drl_eaurp import run_track1 as a_track1

    rounds = 2000 if profile.name == "full" else 600
    runs = 3 if profile.name == "full" else 2

    print("\nA: DRL-EAURP re-implemented from Lekha.pdf Eq. (1)-(38)")
    speed_results, policy_notes = a_track1.run_speed_sweep(rounds=rounds, runs=runs)
    density_results = a_track1.run_density_sweep(rounds=rounds, runs=runs,
                                                 verbose=False)
    rows = a_track1.to_rows(speed_results, density_results)
    a_track1.write_csv(rows, csv_path("a_paper_track1.csv", out_dir=out_dir))

    print("\nA: drain-band ablation -- isolating Eq. (8) from the delivered code")
    ablation = a_track1.drain_band_ablation(rounds=1400, runs=runs)
    print("   Eq. (8) band [0.05,0.15]: lifetime {0:7.1f}  PDR {1:.4f}".format(
        ablation["paper_Eq8_0.05-0.15"]["network_lifetime"],
        ablation["paper_Eq8_0.05-0.15"]["pdr"]))
    print("   code band  [0.04,0.12]: lifetime {0:7.1f}  PDR {1:.4f}".format(
        ablation["code_0.04-0.12"]["network_lifetime"],
        ablation["code_0.04-0.12"]["pdr"]))
    print("   => {0:+.1f} rounds of 'lifetime improvement' from the constant "
          "alone".format(ablation["lifetime_delta"]))
    write_rows(
        [
            dict(band=key, **value)
            for key, value in ablation.items()
            if isinstance(value, dict)
        ],
        csv_path("a_drain_band_ablation.csv", out_dir=out_dir),
    )

    if not skip_b:
        print("\nB: senior_code.ipynb, logic verbatim")
        from src.b_senior import senior_asis

        senior_results = senior_asis.run_all(runs=5 if profile.name == "full" else 2)
        senior_asis.write_csv(
            senior_asis.to_rows(senior_results),
            csv_path("b_senior_as_is.csv", out_dir=out_dir),
        )
        for model in ("Existing", "EAURP", "ATEAURP", "PSE-EAURP", "DRL-EAURP"):
            block = senior_results[model]
            print("   B/{0:11s} PDR {1:.3f}-{2:.3f}".format(
                model, min(block["pdr"]), max(block["pdr"])))
    return True


def run_track2(profile, only=None, out_dir=None, fresh=False, verbose=True):
    """All policies on the shared mechanistic harness."""
    print()
    print("=" * 78)
    print("TRACK 2 -- A, B and C as routing policies on one harness")
    print("=" * 78)

    print("\nPre-training C (clean commissioning run, no adversaries present)")
    shared_c, pretrain_summary = pretrained_c(profile, verbose=verbose)
    write_rows([pretrain_summary], csv_path("c_pretrain.csv", out_dir=out_dir))

    wanted = list(sweeps.EXPERIMENTS) if not only else [key.lower() for key in only]
    kwargs = dict(out_dir=out_dir, resume=not fresh, verbose=verbose)

    for key in wanted:
        runner = sweeps.EXPERIMENTS.get(key)
        if runner is None:
            print("  [warn] unknown experiment {0!r}".format(key))
            continue
        print()
        if key == "e5":
            runner(profile, **kwargs)
        else:
            runner(profile, shared_c=shared_c, **kwargs)
    return shared_c


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="quick", choices=("quick", "full"))
    parser.add_argument("--only", nargs="*", default=None,
                        help="subset of e1..e6 to run")
    parser.add_argument("--out-dir", default=None,
                        help="results root (use a Drive path on Colab)")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore existing CSVs and recompute everything")
    parser.add_argument("--skip-track1", action="store_true")
    parser.add_argument("--skip-track2", action="store_true")
    parser.add_argument("--skip-b", action="store_true",
                        help="skip B's slow verbatim run (it takes ~200 s)")
    args = parser.parse_args(argv)

    profile = config.get_profile(args.profile)
    started = time.perf_counter()

    print("AR-EAURP Review 2 -- profile={0} rounds={1} runs={2}".format(
        profile.name, profile.rounds, profile.runs))

    if not args.skip_track1:
        run_track1(profile, out_dir=args.out_dir, skip_b=args.skip_b)
    if not args.skip_track2:
        run_track2(profile, only=args.only, out_dir=args.out_dir, fresh=args.fresh)

    print()
    print("=" * 78)
    print("done in {0:.1f} s".format(time.perf_counter() - started))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
