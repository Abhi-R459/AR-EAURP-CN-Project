#!/usr/bin/env python3
"""Run the E3 protocol × attack × hostile-fraction matrix concurrently.

Results are saved as native JSON and also encoded as the batch runner's normal
checksummed per-run checkpoints, so the standard report generator can reuse
them without rerunning the simulations.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "parts" / "e3"
PROJECT = ROOT.parents[1]
NS3_HOME = Path(os.environ.get("NS3_HOME", "/home/abhi/.cache/ar-eaurp/ns-3.45"))
NATIVE = NS3_HOME / "build/scratch/ns3.45-ar-eaurp-sim-optimized"
PROTOCOLS = ["aodv", "eaurp", "drl-paper", "drl-senior", "ar-eaurp"]
ATTACKS = ["blackhole", "grayhole", "trust_poisoning"]
PCTS = [0, 10, 20, 30, 40, 50]
IDENTITY = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["source_sha256"]


def checkpoint_parameters(protocol: str, attack: str, pct: int, run: int) -> dict[str, str]:
    return {
        "area": "420", "attack": attack, "commission": "240", "flows": "6",
        "ganEpochs": "120", "lstmEpochs": "30", "malicious": f"{pct/100:.6f}",
        "nodes": "24", "protocol": protocol, "run": str(run),
        "seed": "20260909", "time": "120", "warmup": "20",
    }


def signature(params: dict[str, str]) -> str:
    material = "ns-3.45 native batch v1\n" + IDENTITY + "\n"
    material += "".join(f"{key}={params[key]}\n" for key in sorted(params))
    return hashlib.sha256(material.encode()).hexdigest()


def to_checkpoint(values: dict, params: dict[str, str]) -> Path:
    metrics = {key: float(value) for key, value in values.items()
               if isinstance(value, (int, float)) and not isinstance(value, bool)}
    payload = "".join(f"{key},{metrics[key]:.17g}\n" for key in sorted(metrics))
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    path = OUT / "raw" / f"{signature(params)}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("AR-EAURP native checkpoint 1\n" + IDENTITY + "\n" + checksum + "\n" + payload,
                    encoding="utf-8", newline="\n")
    return path


def valid_checkpoint(path: Path, params: dict[str, str]) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        payload = "\n".join(lines[3:]) + "\n"
        return (lines[0] == "AR-EAURP native checkpoint 1" and lines[1] == IDENTITY and
                lines[2] == hashlib.sha256(payload.encode()).hexdigest() and
                path.stem == signature(params))
    except (OSError, IndexError):
        return False


def run_one(item: tuple[str, int, str, int], check_only: bool) -> tuple[str, str]:
    protocol, pct, attack, run = item
    params = checkpoint_parameters(protocol, attack, pct, run)
    cache = OUT / "raw" / f"{signature(params)}.csv"
    if check_only:
        return (str(item), "checkpoint exists" if cache.is_file() else "checkpoint missing")
    if valid_checkpoint(cache, params):
        return (str(item), "cached")
    stem = f"{attack}-p{pct:02d}-{protocol}-r{run}"
    raw_json = OUT / "raw_json" / f"{stem}.json"
    log = OUT / "raw_json" / f"{stem}.log"
    raw_json.parent.mkdir(parents=True, exist_ok=True)
    command = [str(NATIVE)] + [f"--{key}={value}" for key, value in params.items()]
    command.append(f"--json={raw_json}")
    env = os.environ.copy()
    env["AR_EAURP_PROJECT"] = str(PROJECT)
    env["NS3_HOME"] = str(NS3_HOME)
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(command, cwd=PROJECT, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0 or not raw_json.is_file():
        raise RuntimeError(f"Simulation failed: {stem}; inspect {log}")
    values = json.loads(raw_json.read_text(encoding="utf-8"))
    to_checkpoint(values, params)
    return (stem, "done")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.check_only and not NATIVE.is_file():
        raise SystemExit(f"Native simulator not found: {NATIVE}")
    tasks = [(proto, pct, attack, run)
             for attack in ATTACKS for pct in PCTS for proto in PROTOCOLS for run in range(1, 6)]
    if args.check_only:
        for task in tasks[:5]:
            print(*run_one(task, True))
        return
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(run_one, task, False): task for task in tasks}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            task = futures[future]
            try:
                stem, status = future.result()
                done += 1
                print(f"[{done}/{len(tasks)}] {stem}: {status}", flush=True)
            except Exception as error:
                failures.append((task, str(error)))
                print(f"FAILED {task}: {error}", file=sys.stderr, flush=True)
    if failures:
        raise SystemExit(f"{len(failures)} E3 simulation(s) failed; rerun to resume from existing checkpoints")
    print("All 450 E3 native simulations completed and checkpointed.")


if __name__ == "__main__":
    main()
