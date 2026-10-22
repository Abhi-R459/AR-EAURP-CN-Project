#!/usr/bin/env python3
"""Aggregate whatever verified E2 density checkpoints are currently available."""
from __future__ import annotations
import csv
import importlib.util
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("e2runner", HERE / "run_e2_parallel.py")
e2 = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(e2)
protocol_labels = {
    "aodv": "AODV (reference baseline)", "eaurp": "EAURP (base substrate)",
    "drl-paper": "A: DRL-EAURP (paper)", "drl-senior": "B: DRL-EAURP (senior)",
    "ar-eaurp": "C: AR-EAURP (advancement)",
}
records = []
for nodes in e2.NODE_COUNTS:
    for protocol in e2.PROTOCOLS:
        samples = []
        for run in range(1, 6):
            params = e2.params(protocol, nodes, run)
            sig = e2.signature(params)
            path = e2.OUT / "raw" / f"{sig}.csv"
            if not e2.valid_checkpoint(path, sig):
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            samples.append({key: float(value) for key, value in (line.split(",", 1) for line in lines[3:])})
        if not samples:
            continue
        keys = sorted(samples[0])
        vals = {}
        for key in keys:
            series = [sample[key] for sample in samples]
            mean = sum(series) / len(series)
            sd = math.sqrt(sum((x - mean) ** 2 for x in series) / (len(series) - 1)) if len(series) > 1 else 0.0
            vals[key] = mean
            vals[key + "_std"] = sd
        vals["runs"] = float(len(samples))
        records.append({
            "label": f"{protocol_labels[protocol]} @ N={nodes}",
            "policy_label": protocol_labels[protocol], "protocol": protocol, "attack": "none",
            "engine": "ns-3", "ns3_version": "3.45", "source_sha256": e2.IDENTITY,
            "profile": "review", "node_count": str(nodes), **{k: format(v, ".17g") for k, v in vals.items()},
        })
out = HERE / "csv" / "e2_density.csv"
out.parent.mkdir(parents=True, exist_ok=True)
columns = list(dict.fromkeys(key for row in records for key in row))
with out.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(records)
print(f"Wrote {len(records)} E2 configurations from {sum(int(float(r['runs'])) for r in records)} verified run checkpoints: {out}")
