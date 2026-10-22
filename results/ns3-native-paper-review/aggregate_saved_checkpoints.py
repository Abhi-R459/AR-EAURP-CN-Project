#!/usr/bin/env python3
"""Quickly aggregate saved, checksummed ns-3 run checkpoints for E1/E3-E6."""
from __future__ import annotations
import csv
import math
import importlib.util
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paper", ROOT / "generate_paper_report.py")
paper = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(paper)
POLICIES = dict(paper.PROTOCOLS)
configs: dict[str, list[tuple[str, str, str, dict[str, str], dict[str, str]]]] = defaultdict(list)

def add(exp, policy, protocol, label, flags=None, meta=None):
    p = paper.base_parameters(protocol, 1)
    p.update(flags or {})
    configs[exp].append((policy, protocol, label, p, meta or {}))

for policy, proto in paper.PROTOCOLS:
    for speed in [1, 5, 10, 15, 20]:
        add("e1_speed", policy, proto, f"{policy} @ {speed} m/s", {"maxSpeed": str(speed)}, {"speed_value": str(speed)})
    for attack in paper.ATTACKS:
        for pct in paper.PCTS:
            add("e3_attack", policy, proto, f"{policy} | {attack} @ {pct}%",
                {"attack": attack, "malicious": f"{pct/100:.6f}"},
                {"attack_type": attack, "malicious_pct": str(pct)})
    for mode in ["battery", "solar"]:
        add("e4_energy", policy, proto, f"{policy} | {mode}", {"harvest": "1" if mode == "solar" else "0"}, {"energy_mode": mode})
        add("e4b_lifetime", policy, proto, f"{policy} | {mode}",
            {"harvest": "1" if mode == "solar" else "0", "time": "900", "energy": "350"}, {"energy_mode": mode})
    add("e6_overhead", policy, proto, policy, {"attack": "grayhole", "malicious": "0.3"})

variants = ["C full", "C without GAN", "C without LSTM", "C without CMDP", "C bare", "C without energy excuse"]
for label in variants:
    flags = {"attack": "grayhole", "malicious": "0.3"}
    if label in {"C without GAN", "C bare"}: flags["gan"] = "0"
    if label in {"C without LSTM", "C bare"}: flags["lstm"] = "0"
    if label in {"C without CMDP", "C bare"}: flags["cmdp"] = "0"
    if label == "C without energy excuse": flags["energyExcuse"] = "0"
    add("e5_ablation", label, "ar-eaurp", label, flags)
for floor in ["0.70", "0.80", "0.90", "0.95"]:
    add("e5b_cmdp_floor", "C: AR-EAURP (advancement)", "ar-eaurp", f"C floor={floor}",
        {"attack": "grayhole", "malicious": "0.3", "pdrFloor": floor}, {"pdr_floor": floor})
add("e6_overhead", "C without ECC", "ar-eaurp", "C without ECC",
    {"attack": "grayhole", "malicious": "0.3", "ecc": "0"})

for exp, entries in configs.items():
    records = []
    for policy, protocol, label, p1, meta in entries:
        samples = []
        for run in range(1, 6):
            p = dict(p1, run=str(run))
            material = "ns-3.45 native batch v1\n" + paper.IDENTITY + "\n"
            material += "".join(f"{key}={p[key]}\n" for key in sorted(p))
            signature = __import__("hashlib").sha256(material.encode()).hexdigest()
            if not (ROOT / "raw" / f"{signature}.csv").is_file():
                continue
            samples.append(paper.run_checkpoint(p))
        if not samples:
            continue
        record = {"label": label, "policy_label": policy, "protocol": protocol,
                  "attack": p1["attack"], "engine": "ns-3", "ns3_version": "3.45",
                  "source_sha256": paper.IDENTITY, "profile": "review", **meta}
        keys = sorted(set.intersection(*(set(s) for s in samples)))
        for key in keys:
            values = [sample[key] for sample in samples]
            mean = sum(values) / len(values)
            sd = math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1)) if len(values) > 1 else 0.0
            record[key] = mean
            record[key + "_std"] = sd
        record["runs"] = len(samples)
        records.append(record)
    path = ROOT / "csv" / f"{exp}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(key for row in records for key in row))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    print(f"{exp}: aggregated {len(records)} conditions from saved checkpoints", flush=True)
