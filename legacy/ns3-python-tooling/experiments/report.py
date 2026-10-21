"""Read only ns-3 measurements and explain their limits."""
import json
from pathlib import Path

from .harness import DEFAULT_OUT, read_rows

CAVEATS = [
    "All network events, radio contention, mobility, energy, attacks and learning execute in ns-3.45 C++. Python only launches processes and analyses their measurements.",
    "A and B are adaptations to distributed packet routing. They use local neighbour estimates instead of the papers' global probability formulas. A uses watchdog trust; B advertises trust from its own source-send and destination-receive counters and never revokes nodes. B's destination counter increments on actual arrival; failed attempts are unavailable to a remote endpoint.",
    "The AODV attack baseline shares the custom routing substrate. The optional ns3-aodv mode uses the upstream implementation and supports clean runs only, because it has no adversarial-forwarding hook.",
    "Speed is measured in m/s, delay in seconds, battery charge in joules, forecast error in watts, and throughput in bits/s. Historical Python rounds and 10,000–40,000 speed labels are not comparable.",
    "Application PDR counts sends inside the measurement window and their arrivals through cooldown. Undelivered packets at the end of cooldown count as losses. Delivery rewards use returned ACKs, so a lost ACK can penalise a successfully delivered data packet.",
    "GAN and LSTM fit only clean commissioning observations. Training flags and sample counts are reported; an untrained component contributes no learned inference. LSTM validation uses disjoint chronological intervals for each node. Its second baseline is a window mean, not a seasonal-naive forecast.",
    "Detection counts nodes flagged by honest witnesses, using ground truth only for scoring. Contested TPR/FPR requires two witnesses; revocation TPR/FPR requires one. The no-score AUC placeholder is 0.5; inspect detector_windows before interpreting it.",
    "A first death or 80% death time is observed only when its event flag is set. Unobserved events are censored at the run horizon. Averaging times with censored runs is not a lifetime estimate.",
    "Solar and kinetic power are modelling assumptions. The diurnal cycle is compressed. Physical degree within 150 m is a diagnostic distance threshold, not a hard radio range; propagation and fading determine delivery.",
    "The native BasicEnergySource is an ideal reservoir without a capacity ceiling; harvested charge can exceed initial charge. A guard on the ns-3.45 radio model prevents nested callbacks from orphaning shutdown timers, and keeps current flowing when a predicted shutdown still has harvested charge. Depletion uses a 1e-9 charge fraction or an exhausted remainder of at most one nanosecond. Like the original Python model, first depletion permanently disables the node's PHY; later reservoir charging does not restart it.",
    "X25519/HKDF/AES-GCM encrypts and authenticates UDP messages, adding 28 bytes per message. Deterministic per-flow keys are provisioned before simulation; key exchange messages are not modelled. Crypto CPU time contributes to wall time but is not injected as simulated latency.",
    "CMDP reports achieved PDR, constraint violations and its multiplier. An unmet target does not prove the constraint is mathematically infeasible. Its reward uses a per-hop energy proxy; residual battery measurements come from the Wi-Fi radio energy model.",
    "IP/MAC/routing drop counters are diagnostic event counts and can count different layers of the same packet. They are not additive loss categories. PDR and offered-minus-delivered application packets are the end-to-end measures.",
    "Control-packet counts measure generated message attempts, including attempts after a depleted PHY switches off. They do not measure successful radio transmissions.",
    "A smoke profile validates execution only. Use the full multi-seed profile for numerical comparisons; successful execution does not establish that C outperforms A or B.",
]

FILES = ("e1_speed", "e2_density", "e3_attack", "e4_energy", "e4b_lifetime",
         "e5_ablation", "e5b_cmdp_floor", "e6_overhead")


def build_comparison(out_dir=None):
    root = Path(out_dir or DEFAULT_OUT)
    manifest = json.loads((root / "manifest.json").read_text()) if (root / "manifest.json").is_file() else {}
    data = {name: read_rows(root / "csv" / (name + ".csv")) for name in FILES}
    fingerprints = {row["source_sha256"] for rows in data.values() for row in rows}
    if len(fingerprints) > 1 or (fingerprints and manifest.get("source_sha256") not in fingerprints):
        raise ValueError("mixed ns-3 source versions in result CSVs; rerun all selected experiments")
    expected_profile = manifest.get("profile", {}).get("name")
    if any(row.get("profile") != expected_profile for rows in data.values() for row in rows):
        raise ValueError("mixed runtime profiles in result CSVs; use a separate output directory per profile")
    return {"manifest": manifest, "experiments": data, "caveats": CAVEATS}
