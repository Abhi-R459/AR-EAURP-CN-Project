"""Build and run E1–E6 using the native ns-3.45 simulation engine."""
import argparse
from dataclasses import asdict
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import config, sweeps
from experiments.harness import DEFAULT_OUT, atomic_json
from experiments.ns3 import Ns3Runner


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=config.PROFILES, default="quick")
    parser.add_argument("--only", nargs="+", choices=sweeps.EXPERIMENTS)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    parser.add_argument("--ns3-home", help="ns-3.45 source/build directory (or NS3_HOME)")
    parser.add_argument("--no-build", action="store_true", help="use an already configured build")
    parser.add_argument("--fresh", action="store_true", help="rerun matching checkpoints")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    runner = Ns3Runner(args.ns3_home)
    if not args.no_build:
        runner.build()
    profile = config.get_profile(args.profile)
    wanted = args.only or list(sweeps.EXPERIMENTS)
    root = Path(args.out_dir)
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / "manifest.json", {"engine": "ns-3", "ns3_version": "3.45",
                "source_sha256": runner.fingerprint(), "profile": asdict(profile),
                "experiments": wanted})
    started = time.perf_counter()
    print(f"ns-3.45 / {profile.name}: {profile.duration:g} s, {profile.runs} run(s)", flush=True)
    for name in wanted:
        print(f"{name.upper()} using native C++ scenarios", flush=True)
        rows, path = sweeps.EXPERIMENTS[name](profile, runner=runner, out_dir=root,
                                             resume=not args.fresh, verbose=not args.quiet, profile_name=profile.name)
        print(f"  {len(rows)} configurations -> {path}", flush=True)
    print(f"Completed in {time.perf_counter() - started:.1f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
