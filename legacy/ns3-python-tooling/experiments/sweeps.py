"""E1–E6 configurations; all network and learning work executes in ns-3 C++."""
from dataclasses import replace

from . import config
from .harness import POLICIES, sweep
from .ns3 import Scenario


def _params(profile, **changes):
    scenario = Scenario(duration=profile.duration, warmup=profile.warmup,
                        commission=profile.commission, gan_epochs=profile.gan_epochs,
                        lstm_epochs=profile.lstm_epochs)
    if profile.name == "smoke":
        scenario = replace(scenario, nodes=16, flows=6, area=200, max_speed=5)
    return replace(scenario, **changes)


def e1_speed(profile, *, runner, out_dir=None, **kw):
    speeds = (1.0, 5.0) if profile.name == "smoke" else config.SPEEDS
    configs = [(f"{label} @ {speed} m/s", _params(profile, protocol=protocol, max_speed=speed),
                {"policy_label": label, "sweep": "speed", "speed_value": speed})
               for label, protocol in POLICIES for speed in speeds]
    return sweep("e1_speed", configs, profile.runs, runner=runner, out_dir=out_dir, **kw)


def e2_density(profile, *, runner, out_dir=None, **kw):
    counts = (12, 24) if profile.name == "smoke" else config.NODE_COUNTS
    configs = [(f"{label} @ N={nodes}", _params(profile, protocol=protocol, nodes=nodes),
                {"policy_label": label, "sweep": "density", "node_count": nodes})
               for label, protocol in POLICIES for nodes in counts]
    return sweep("e2_density", configs, profile.runs, runner=runner, out_dir=out_dir, **kw)


def e3_attack(profile, *, runner, out_dir=None, **kw):
    fractions = (0.0, 0.3) if profile.name == "smoke" else config.MALICIOUS_FRACTIONS
    configs = [(f"{label} | {attack} @ {fraction:.0%}",
                _params(profile, protocol=protocol, attack=attack, malicious=fraction),
                {"policy_label": label, "sweep": "attack", "attack_type": attack,
                 "malicious_pct": 100 * fraction})
               for label, protocol in POLICIES for attack in config.ATTACKS for fraction in fractions]
    return sweep("e3_attack", configs, profile.runs, runner=runner, out_dir=out_dir, **kw)


def e4_energy(profile, *, runner, out_dir=None, **kw):
    configs = [(f"{label} | {mode}", _params(profile, protocol=protocol, harvest=mode == "solar"),
                {"policy_label": label, "sweep": "energy", "energy_mode": mode})
               for label, protocol in POLICIES for mode in ("battery", "solar")]
    rows, path = sweep("e4_energy", configs, profile.runs, runner=runner, out_dir=out_dir, **kw)
    lifetime = [(label, replace(scenario, duration=profile.lifetime,
                               energy=20.0 if profile.name == "smoke" else 350.0),
                 dict(extra, sweep="lifetime")) for label, scenario, extra in configs]
    sweep("e4b_lifetime", lifetime, profile.runs, runner=runner, out_dir=out_dir, **kw)
    return rows, path


def e5_ablation(profile, *, runner, out_dir=None, **kw):
    variants = (
        ("C full", {}), ("C without GAN", {"gan": False}),
        ("C without LSTM", {"lstm": False}), ("C without CMDP", {"cmdp": False}),
        ("C bare", {"gan": False, "lstm": False, "cmdp": False}),
        ("C without energy excuse", {"energy_excuse": False}),
    )
    configs = [(label, _params(profile, attack="grayhole", malicious=0.3, **flags),
                {"policy_label": label, "sweep": "ablation"}) for label, flags in variants]
    rows, path = sweep("e5_ablation", configs, profile.runs, runner=runner, out_dir=out_dir, **kw)
    floors = [(f"C floor={floor:.2f}", _params(profile, attack="grayhole", malicious=0.3, pdr_floor=floor),
               {"policy_label": "C: AR-EAURP (advancement)", "sweep": "cmdp_floor", "pdr_floor": floor})
              for floor in (0.70, 0.80, 0.90, 0.95)]
    sweep("e5b_cmdp_floor", floors, profile.runs, runner=runner, out_dir=out_dir, **kw)
    return rows, path


def e6_overhead(profile, *, runner, out_dir=None, **kw):
    configs = [(label, _params(profile, protocol=protocol, attack="grayhole", malicious=0.3),
                {"policy_label": label, "sweep": "overhead"}) for label, protocol in POLICIES]
    configs.append(("C without ECC", _params(profile, attack="grayhole", malicious=0.3, ecc=False),
                    {"policy_label": "C without ECC", "sweep": "overhead"}))
    return sweep("e6_overhead", configs, profile.runs, runner=runner, out_dir=out_dir, **kw)


EXPERIMENTS = {"e1": e1_speed, "e2": e2_density, "e3": e3_attack,
               "e4": e4_energy, "e5": e5_ablation, "e6": e6_overhead}
