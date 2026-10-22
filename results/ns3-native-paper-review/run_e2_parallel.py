#!/usr/bin/env python3
"""Run the node-density sweep as resumable, isolated native ns-3 processes."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "parts" / "e2"
PROJECT = ROOT.parents[1]
NS3_HOME = Path(os.environ.get("NS3_HOME", "/home/abhi/.cache/ar-eaurp/ns-3.45"))
NATIVE = NS3_HOME / "build/scratch/ns3.45-ar-eaurp-sim-optimized"
IDENTITY = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))["source_sha256"]
PROTOCOLS = ["aodv", "eaurp", "drl-paper", "drl-senior", "ar-eaurp"]
NODE_COUNTS = [60, 80, 100, 120, 150, 200]

def params(protocol: str, nodes: int, run: int) -> dict[str, str]:
    return {"area":"420", "attack":"none", "commission":"240", "flows":"6",
            "ganEpochs":"120", "lstmEpochs":"30", "malicious":"0", "nodes":str(nodes),
            "protocol":protocol, "run":str(run), "seed":"20260909", "time":"120", "warmup":"20"}

def signature(p: dict[str, str]) -> str:
    text = "ns-3.45 native batch v1\n" + IDENTITY + "\n"
    text += "".join(f"{k}={p[k]}\n" for k in sorted(p))
    return hashlib.sha256(text.encode()).hexdigest()

def valid_checkpoint(path: Path, sig: str) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return (lines[0] == "AR-EAURP native checkpoint 1" and lines[1] == sig and
                hashlib.sha256(("\n".join(lines[3:]) + "\n").encode()).hexdigest() == lines[2])
    except (OSError, IndexError):
        return False

def run_one(job: tuple[str, int, int]) -> tuple[str, str]:
    protocol, nodes, run = job
    p = params(protocol, nodes, run)
    sig = signature(p)
    cache = OUT / "raw" / f"{sig}.csv"
    if valid_checkpoint(cache, sig): return (f"{protocol}-n{nodes}-r{run}", "cached")
    stem = f"n{nodes:03d}-{protocol}-r{run}"
    raw_json, log = OUT / "raw_json" / f"{stem}.json", OUT / "raw_json" / f"{stem}.log"
    raw_json.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy(); env["AR_EAURP_PROJECT"] = str(PROJECT); env["NS3_HOME"] = str(NS3_HOME)
    command = [str(NATIVE)] + [f"--{k}={v}" for k,v in p.items()] + [f"--json={raw_json}"]
    with log.open("w", encoding="utf-8") as stream:
        done = subprocess.run(command, cwd=PROJECT, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, check=False)
    if done.returncode or not raw_json.is_file(): raise RuntimeError(f"Failed {stem}; see {log}")
    metrics = {k:float(v) for k,v in json.loads(raw_json.read_text(encoding="utf-8")).items()
               if isinstance(v,(int,float)) and not isinstance(v,bool)}
    payload = "".join(f"{k},{metrics[k]:.17g}\n" for k in sorted(metrics))
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(f"AR-EAURP native checkpoint 1\n{sig}\n{checksum}\n{payload}",
                     encoding="utf-8", newline="\n")
    return (stem, "done")

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--workers",type=int,default=4)
    ap.add_argument("--min-nodes",type=int,default=60); ap.add_argument("--exclude-ar",action="store_true")
    ap.add_argument("--max-run",type=int,default=5,
                    help="highest run number to include (default: 5); report must disclose reduced repetitions")
    ap.add_argument("--protocols",default=",".join(PROTOCOLS),
                    help="comma-separated protocol subset; use disjoint subsets for safe parallel batches")
    a=ap.parse_args()
    requested=[p.strip() for p in a.protocols.split(",") if p.strip()]
    unknown=set(requested)-set(PROTOCOLS)
    if unknown: ap.error(f"unknown protocols: {', '.join(sorted(unknown))}")
    protocols=[p for p in requested if not (a.exclude_ar and p=="ar-eaurp")]
    if not protocols: ap.error("no protocols selected")
    if not 1 <= a.max_run <= 5: ap.error("--max-run must be between 1 and 5")
    jobs=[(p,n,r) for n in NODE_COUNTS if n>=a.min_nodes for p in protocols for r in range(1,a.max_run+1)]
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,a.workers)) as pool:
        futures={pool.submit(run_one,j):j for j in jobs}
        for i,future in enumerate(concurrent.futures.as_completed(futures),1):
            try:
                name,status=future.result(); print(f"[{i}/{len(jobs)}] {name}: {status}",flush=True)
            except Exception as e:
                failures.append((futures[future],str(e))); print(f"FAILED {futures[future]}: {e}",file=sys.stderr,flush=True)
    if failures: raise SystemExit(f"{len(failures)} density runs failed; rerun to resume")
    print("All 150 E2 native runs are checkpointed.")

if __name__ == "__main__": main()
