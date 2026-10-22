"""The six Track-2 experiments (E1-E6).

Kept in one module rather than six near-identical files; each experiment is a
function so the notebook can run them individually and the CLI can run them all.

    E1  speed sweep            all policies, 10k-40k (plus a realistic annex)
    E2  density sweep          all policies, 60-200 nodes
    E3  ATTACK SWEEP           A / B / C under 0-50% malicious x 3 attacks
    E4  energy + lifetime      linear vs solar, LSTM accuracy, network lifetime
    E5  ablation               C without GAN / LSTM / CMDP, plus a floor sweep
    E6  overhead               control traffic, wall-clock, ECC cost

E3 is the headline: it is the only experiment in which the advancement's threat
model is actually exercised, and the only one the base papers cannot run at all.
"""

import time

import numpy as np

from src.c_ar_eaurp.protocol import ArEaurpPolicy
from src.common import config
from src.common.simulator import SimParams, Simulation
from src.routing import ecc

from .harness import (
    BASE_SEED, csv_path, make_policies, pretrained_c, run_config, sweep,
    write_rows,
)


def _params(profile, **kwargs):
    base = dict(
        n_nodes=config.DEFAULT_NODES,
        speed=config.DEFAULT_SPEED,
        rounds=profile.rounds,
        packets_per_round=profile.packets_per_round,
    )
    base.update(kwargs)
    return SimParams(**base)


# --------------------------------------------------------------------------
# E1 -- speed sweep
# --------------------------------------------------------------------------

def e1_speed(profile, shared_c=None, out_dir=None, realistic=True, **kw):
    print("E1  speed sweep (paper range 10k-40k)")
    configs = []
    for label, factory in make_policies(shared_c):
        for speed in config.SPEEDS_PAPER:
            configs.append((
                "{0} @ v={1}".format(label, speed),
                factory,
                _params(profile, speed=speed),
                {"policy_label": label, "sweep": "speed", "speed_value": speed},
            ))
    rows, path = sweep("e1_speed", configs, profile.runs, out_dir=out_dir, **kw)

    if realistic:
        print("E1b speed sweep (physically realistic 1-20 m/round annex)")
        annex = []
        for label, factory in make_policies(shared_c):
            for speed in config.SPEEDS_REALISTIC:
                annex.append((
                    "{0} @ v={1}".format(label, speed),
                    factory,
                    _params(profile, speed=speed),
                    {"policy_label": label, "sweep": "speed_realistic",
                     "speed_value": speed},
                ))
        sweep("e1b_speed_realistic", annex, profile.runs, out_dir=out_dir, **kw)
    return rows, path


# --------------------------------------------------------------------------
# E2 -- density sweep
# --------------------------------------------------------------------------

def e2_density(profile, shared_c=None, out_dir=None, **kw):
    print("E2  node-density sweep (60-200 nodes)")
    configs = []
    for label, factory in make_policies(shared_c):
        for count in config.NODE_COUNTS:
            configs.append((
                "{0} @ N={1}".format(label, count),
                factory,
                _params(profile, n_nodes=count),
                {"policy_label": label, "sweep": "density", "node_count": count},
            ))
    return sweep("e2_density", configs, profile.runs, out_dir=out_dir, **kw)


# --------------------------------------------------------------------------
# E3 -- attack sweep (the headline)
# --------------------------------------------------------------------------

def e3_attack(profile, shared_c=None, out_dir=None, **kw):
    print("E3  ATTACK SWEEP -- 0-50% malicious x {blackhole, grayhole, "
          "trust_poisoning}")
    configs = []
    for label, factory in make_policies(shared_c):
        for attack in config.ATTACKS:
            for fraction in config.MALICIOUS_FRACTIONS:
                configs.append((
                    "{0} | {1} @ {2:.0f}%".format(label, attack, 100 * fraction),
                    factory,
                    _params(profile, attack=attack, malicious_fraction=fraction),
                    {
                        "policy_label": label,
                        "sweep": "attack",
                        "attack_type": attack,
                        "malicious_pct": 100.0 * fraction,
                    },
                ))
    return sweep("e3_attack", configs, profile.runs, out_dir=out_dir, **kw)


# --------------------------------------------------------------------------
# E4 -- energy model, lifetime and forecast accuracy
# --------------------------------------------------------------------------

def e4_energy(profile, shared_c=None, out_dir=None, **kw):
    print("E4  energy model, network lifetime and LSTM forecast accuracy")

    configs = []
    for label, factory in make_policies(shared_c):
        for model in ("linear", "solar"):
            configs.append((
                "{0} | {1} energy".format(label, model),
                factory,
                _params(profile, energy_model=model),
                {"policy_label": label, "sweep": "energy", "energy_mode": model},
            ))
    rows, path = sweep("e4_energy", configs, profile.runs, out_dir=out_dir, **kw)

    # Network lifetime needs a much longer horizon than the performance sweeps:
    # under the papers' own drain the first death is around round 1250.
    print("E4b network lifetime (long horizon, {0} rounds)".format(
        config.LIFETIME_ROUNDS))
    lifetime_configs = []
    for label, factory in make_policies(shared_c):
        for model in ("linear", "solar"):
            lifetime_configs.append((
                "{0} | {1}".format(label, model),
                factory,
                _params(profile, rounds=config.LIFETIME_ROUNDS,
                        energy_model=model, stop_when_dead=True),
                {"policy_label": label, "sweep": "lifetime", "energy_mode": model},
            ))
    sweep("e4b_lifetime", lifetime_configs, max(2, profile.runs // 2),
          out_dir=out_dir, **kw)

    # Forecast quality, on its own, against both naive baselines.
    if shared_c is not None and shared_c.predictor is not None:
        evaluation = dict(shared_c.predictor.evaluation)
        evaluation.update(shared_c.predictor.summary())
        write_rows([evaluation], csv_path("e4c_lstm_accuracy.csv", out_dir=out_dir))
        print("  LSTM MAE {0:.5f} | persistence {1:.5f} | seasonal-naive "
              "{2:.5f} | beats both: {3}".format(
                  evaluation.get("lstm_mae", float("nan")),
                  evaluation.get("persistence_mae", float("nan")),
                  evaluation.get("seasonal_naive_mae", float("nan")),
                  bool(evaluation.get("beats_persistence"))
                  and bool(evaluation.get("beats_seasonal_naive"))))
    return rows, path


# --------------------------------------------------------------------------
# E5 -- ablation of C, and the CMDP feasibility sweep
# --------------------------------------------------------------------------

def e5_ablation(profile, out_dir=None, attack="grayhole", fraction=0.3, **kw):
    print("E5  ablation of C  (-GAN, -LSTM, -CMDP) under {0} @ {1:.0f}%".format(
        attack, 100 * fraction))

    variants = [
        ("C full", dict(use_gan=True, use_lstm=True, use_cmdp=True)),
        ("C without GAN", dict(use_gan=False, use_lstm=True, use_cmdp=True)),
        ("C without LSTM", dict(use_gan=True, use_lstm=False, use_cmdp=True)),
        ("C without CMDP", dict(use_gan=True, use_lstm=True, use_cmdp=False)),
        ("C bare (none)", dict(use_gan=False, use_lstm=False, use_cmdp=False)),
    ]

    configs = []
    for label, flags in variants:
        policy, _ = pretrained_c(profile, verbose=False, **flags)
        configs.append((
            label,
            (lambda captured=policy: captured),
            _params(profile, attack=attack, malicious_fraction=fraction),
            {"policy_label": label, "sweep": "ablation", "attack_type": attack,
             "malicious_pct": 100.0 * fraction},
        ))
    rows, path = sweep("e5_ablation", configs, profile.runs, out_dir=out_dir, **kw)

    # How high can the CMDP floor go before it stops being satisfiable?
    # The Review-1 critique predicts the doc's 0.90 is infeasible; this measures
    # where the real ceiling is instead of asserting one.
    print("E5b CMDP feasibility -- how high a PDR floor is actually reachable")
    from src.c_ar_eaurp.cmdp_agent import CmdpRoutingAgent

    # Train the detector and forecaster once and share them across every floor
    # setting: only the constraint changes, so retraining per floor would burn
    # minutes to produce identical models.
    reference, _ = pretrained_c(profile, verbose=False)

    floor_configs = []
    for floor in (0.5, 0.6, 0.7, 0.8, 0.9):
        policy = ArEaurpPolicy(
            detector=reference.detector,
            predictor=reference.predictor,
            agent=CmdpRoutingAgent(n_actions=4, pdr_floor=floor),
        )
        floor_configs.append((
            "CMDP floor {0:.2f}".format(floor),
            (lambda captured=policy: captured),
            _params(profile, attack=attack, malicious_fraction=fraction),
            {"policy_label": "C", "sweep": "cmdp_floor", "pdr_floor": floor},
        ))
    sweep("e5b_cmdp_floor", floor_configs, max(2, profile.runs // 2),
          out_dir=out_dir, **kw)
    return rows, path


# --------------------------------------------------------------------------
# E6 -- overhead
# --------------------------------------------------------------------------

def e6_overhead(profile, shared_c=None, out_dir=None, **kw):
    print("E6  overhead -- control traffic, wall-clock and ECC cost")
    rows = []
    for label, factory in make_policies(shared_c):
        params = _params(profile, attack="grayhole", malicious_fraction=0.3)
        started = time.perf_counter()
        row = run_config(factory, params, max(2, profile.runs // 2))
        elapsed = time.perf_counter() - started
        row["label"] = label
        row["policy_label"] = label
        row["wall_clock_seconds"] = elapsed
        row["wall_clock_per_round_ms"] = 1000.0 * elapsed / max(
            1.0, row.get("rounds_completed", profile.rounds)
        )
        row["control_per_round"] = row.get("control_packets", 0.0) / max(
            1.0, row.get("rounds_completed", 1.0)
        )
        rows.append(row)
        print("  {0:44s} control/round={1:7.1f}  wall={2:5.1f}s".format(
            label[:44], row["control_per_round"], elapsed))

    bench = ecc.benchmark()
    bench["label"] = "ECC benchmark (standalone)"
    bench["policy_label"] = "ECC"
    rows.append(bench)
    print("  ECC: {0} backend, {1:.1f} us/packet, {2:.1f} us/key-agreement".format(
        bench["ecc_backend"], 1e6 * bench["bench_seconds_per_packet"],
        1e6 * bench["ecc_seconds_per_agreement"]))

    path = csv_path("e6_overhead.csv", out_dir=out_dir)
    write_rows(rows, path)
    print("  ->", path)
    return rows, path


EXPERIMENTS = {
    "e1": e1_speed,
    "e2": e2_density,
    "e3": e3_attack,
    "e4": e4_energy,
    "e5": e5_ablation,
    "e6": e6_overhead,
}
