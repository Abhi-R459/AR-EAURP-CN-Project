"""Paired ns-3 runs, measurement aggregation and atomic result checkpoints."""
import csv
from dataclasses import asdict, replace
import hashlib
import json
import math
import os
from pathlib import Path
from .ns3 import valid_result
import statistics

import numpy as np

DEFAULT_OUT = os.environ.get("AR_EAURP_RESULTS", "results/ns3")
BASE_SEED = 20260909
POLICIES = (
    ("AODV (reference baseline)", "aodv"),
    ("EAURP (base.pdf substrate)", "eaurp"),
    ("A: DRL-EAURP (paper)", "drl-paper"),
    ("B: DRL-EAURP (senior code)", "drl-senior"),
    ("C: AR-EAURP (advancement)", "ar-eaurp"),
)


def out_path(*parts, out_dir=None):
    path = Path(out_dir or DEFAULT_OUT).joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def csv_path(name, out_dir=None):
    return out_path("csv", name, out_dir=out_dir)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def aggregate(rows):
    if not rows:
        raise ValueError("cannot aggregate no runs")
    out = {}
    for key in dict.fromkeys(k for row in rows for k in row):
        values = [row[key] for row in rows if key in row]
        if all(isinstance(v, (int, float)) for v in values):
            out[key] = statistics.mean(values)
            out[key + "_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        elif all(v == values[0] for v in values):
            out[key] = values[0]
    out["runs"] = len(rows)
    return out


def run_config(runner, scenario, runs, out_dir=None, resume=True, base_seed=BASE_SEED):
    if not isinstance(runs, int) or runs < 1:
        raise ValueError("runs must be a positive integer")
    rows = []
    fingerprint = runner.fingerprint()
    for index in range(runs):
        current = replace(scenario, seed=base_seed, run=index + 1)
        signature = {"schema": 1, "engine": "ns-3", "source_sha256": fingerprint,
                     "scenario": asdict(current)}
        key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        path = Path(out_path("raw", key + ".json", out_dir=out_dir))
        row = None
        if resume and path.is_file():
            try:
                saved = json.loads(path.read_text())
                candidate = saved["result"]
                if saved["signature"] == signature and valid_result(candidate, current):
                    row = candidate
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if row is None:
            row = runner.run(current)
            atomic_json(path, {"signature": signature, "result": row})
        rows.append(row)
    result = aggregate(rows)
    result["source_sha256"] = fingerprint
    return result


def sweep(name, configs, runs, *, runner, out_dir=None, resume=True, verbose=True,
          base_seed=BASE_SEED, profile_name="custom"):
    rows = []
    for index, (label, scenario, extra) in enumerate(configs, start=1):
        row = run_config(runner, scenario, runs, out_dir=out_dir, resume=resume,
                         base_seed=base_seed)
        row.update(extra or {})
        row["profile"] = profile_name
        row["label"] = label
        row["policy_label"] = (extra or {}).get("policy_label", label)
        rows.append(row)
        # The per-run JSON is authoritative; this CSV is a rebuildable view.
        write_rows(rows, csv_path(name + ".csv", out_dir))
        if verbose:
            print(f"  [{index}/{len(configs)}] {label}: PDR={row['pdr']:.3f} "
                  f"delay={row['mean_delay_s'] * 1000:.1f} ms", flush=True)
    return rows, csv_path(name + ".csv", out_dir)


def write_rows(rows, path):
    if not rows:
        return path
    keys = list(dict.fromkeys(key for row in rows for key in row))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)
    return str(path)


def read_rows(path):
    if not Path(path).is_file():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if any(row.get("engine") != "ns-3" or not row.get("source_sha256") for row in rows):
        raise ValueError(f"{path} has no ns-3 provenance; rerun the migrated experiments")
    return rows


def as_float(rows, key, default=float("nan")):
    values = []
    for row in rows:
        try:
            values.append(float(row.get(key, default)))
        except (TypeError, ValueError):
            values.append(default)
    return np.asarray(values)
