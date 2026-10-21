"""Tests of the ns-3 process boundary; native model tests live in contrib/."""
import csv
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from experiments.ns3 import Scenario, Ns3Runner, ROOT, source_digest, installed_digest
from experiments.harness import aggregate, run_config, sweep


@pytest.mark.parametrize("changes", [
    {"protocol": "typo"}, {"nodes": 1}, {"malicious": -0.1},
    {"min_speed": 0}, {"max_speed": 0.5}, {"warmup": 20, "duration": 10},
    {"attack": "none", "malicious": 0.3}, {"rate": 0}, {"flows": 0},
    {"max_size": 10}, {"cooldown": 0}, {"pdr_floor": 1.1}, {"area": float("nan")},
    {"protocol": "ns3-aodv", "attack": "grayhole", "malicious": 0.3},
])
def test_invalid_scenarios_fail_before_launch(changes):
    with pytest.raises(ValueError):
        replace(Scenario(), **changes)


def test_aggregate_uses_sample_standard_deviation():
    result = aggregate([{"pdr": 0.5, "engine": "ns-3"}, {"pdr": 1.0, "engine": "ns-3"}])
    assert result["pdr"] == 0.75
    assert result["pdr_std"] == pytest.approx(0.35355339059)
    assert result["runs"] == 2


@pytest.fixture
def runner():
    if not os.environ.get("NS3_HOME"):
        pytest.skip("set NS3_HOME to run real ns-3 integration tests")
    return Ns3Runner(os.environ["NS3_HOME"])


@pytest.fixture
def small():
    return Scenario(protocol="aodv", nodes=6, flows=2, area=30, duration=5,
                    warmup=1, harvest=False, train=False)


def test_real_network_delivers_protected_udp_and_resumes(runner, small, tmp_path):
    one = run_config(runner, small, 1, out_dir=tmp_path)
    assert one["engine"] == "ns-3"
    assert one["app_rx"] > 0
    assert 0 <= one["pdr"] <= 1
    assert one["crypto_overhead_bytes"] > 0
    assert one["crypto_auth_failures"] == 0
    checkpoints = list((tmp_path / "raw").glob("*.json"))
    before = [p.stat().st_mtime_ns for p in checkpoints]
    two = run_config(runner, small, 1, out_dir=tmp_path)
    assert two == one
    assert [p.stat().st_mtime_ns for p in checkpoints] == before
    run_config(runner, replace(small, rate=2), 1, out_dir=tmp_path)
    assert len(list((tmp_path / "raw").glob("*.json"))) == 2


def test_repeated_seed_reproduces_every_simulated_metric(runner, small):
    a, b = runner.run(small), runner.run(small)
    assert {k: v for k, v in a.items() if k != "wall_clock_seconds"} == {
        k: v for k, v in b.items() if k != "wall_clock_seconds"}


@pytest.mark.parametrize("protocol", ["eaurp", "drl-paper", "drl-senior", "ar-eaurp", "ns3-aodv"])
def test_all_native_protocols_deliver(runner, small, protocol):
    result = runner.run(replace(small, protocol=protocol))
    assert result["app_rx"] > 0
    assert 0 <= result["pdr"] <= 1
    if protocol.startswith("drl-"):
        assert result["q_updates"] > 0


def test_corrupt_checkpoint_is_recomputed(runner, small, tmp_path):
    run_config(runner, small, 1, out_dir=tmp_path)
    checkpoint = next((tmp_path / "raw").glob("*.json"))
    checkpoint.write_text('{"engine":"python"}')
    result = run_config(runner, small, 1, out_dir=tmp_path)
    assert result["app_rx"] > 0
    assert json.loads(checkpoint.read_text())["result"]["engine"] == "ns-3"


def test_sweep_ignores_old_csv_and_quotes_labels(runner, small, tmp_path):
    (tmp_path / "csv").mkdir()
    (tmp_path / "csv" / "trial.csv").write_text("label,pdr\nold Python,0.99\n")
    rows, path = sweep("trial", [("A, \"quoted\"", small, {"sweep": "test"})],
                       1, runner=runner, out_dir=tmp_path, verbose=False)
    with open(path, newline="") as handle:
        saved = list(csv.DictReader(handle))
    assert saved[0]["label"] == 'A, "quoted"'
    assert saved[0]["engine"] == "ns-3"
    assert rows[0]["app_rx"] > 0


def test_native_csv_quotes_labels_and_rejects_incompatible_schema(runner, small, tmp_path):
    path = tmp_path / "native.csv"
    label = 'comma, "quote"\nnew line'
    command = [str(runner.binary), *small.arguments(), f"--csv={path}", f"--label={label}"]
    subprocess.run(command, check=True, capture_output=True, text=True)
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["label"] == label
    assert float(rows[0]["app_rx"]) > 0
    path.write_text("label,pdr\n")
    rejected = subprocess.run(command, capture_output=True, text=True)
    assert rejected.returncode == 3
    assert path.read_text() == "label,pdr\n"


def test_trained_components_execute_under_real_grayhole_attack(runner):
    scenario = Scenario(nodes=40, area=350, flows=30, duration=60, warmup=10,
                        commission=120, gan_epochs=5, lstm_epochs=1,
                        attack="grayhole", malicious=0.3)
    result = runner.run(scenario)
    assert result["gan_trained"] == 1
    assert result["gan_train_windows"] >= 32
    assert result["detector_windows"] > 0
    assert result["lstm_trained"] == 1
    assert result["lstm_validation_sequences"] > 0
    assert result["adversary_drops"] > 0
    assert result["cmdp_decisions"] > 0


@pytest.mark.parametrize("size,expected", [(680, False), (900, True)])
def test_grayhole_selects_plaintext_size_after_encryption(runner, size, expected):
    scenario = Scenario(protocol="aodv", nodes=30, flows=30, area=300,
                        duration=25, warmup=2, attack="grayhole", malicious=1.0,
                        min_size=size, max_size=size, train=False)
    result = runner.run(scenario)
    assert (result["adversary_drops"] > 0) is expected


@pytest.mark.parametrize("protocol", ["aodv", "ns3-aodv"])
@pytest.mark.parametrize("energy", [.01, .1, .3, 2])
def test_battery_depletion_is_observed_before_lifetime_horizon(runner, protocol, energy):
    result = runner.run(Scenario(protocol=protocol, nodes=2, flows=1, area=30,
                                duration=15, warmup=1, energy=energy, harvest=False, train=False))
    assert result["dead_nodes"] == 2
    assert result["first_death_observed"] == 1
    assert 0 < result["first_death_s"] < 5
    assert result["first_death_s"] <= energy / (.273 * 3) + .005
    assert result["mean_residual_fraction"] < 1e-6
    assert result["app_rx"] < 5  # a depleted PHY cannot keep receiving


def test_cooldown_completes_feedback_for_every_evaluation_send(runner):
    result = runner.run(Scenario(protocol="drl-paper", nodes=2, flows=1, area=1e6,
                                duration=4, warmup=1, harvest=False, train=False))
    assert result["app_tx"] > 0
    assert result["app_feedback_success"] + result["app_feedback_timeout"] == result["app_tx"]
    assert result["q_updates"] == result["app_tx"]


def test_harvesting_does_not_silently_disable_radio_current(runner):
    result = runner.run(Scenario(protocol="aodv", nodes=2, flows=1, area=30,
                                duration=30, warmup=1, energy=2, harvest=True,
                                panel_fraction=1, day_length=40, train=False))
    # Even the harvested energy cannot sustain both radios for the whole run.
    assert result["harvested_j"] + 4 < 2 * .273 * 3 * 30
    assert result["first_death_observed"] == 1


def test_depleted_nodes_remain_off_when_their_reservoir_recharges(runner):
    result = runner.run(Scenario(protocol="aodv", nodes=2, flows=1, area=30,
                                duration=80, warmup=1, energy=2, harvest=True,
                                panel_fraction=1, day_length=40, train=False))
    assert result["dead_nodes"] == 2
    assert result["residual_energy_j"] > 0
    assert result["radio_off_nodes"] == 2
    assert result["radio_current_a"] == 0


def test_partial_checkpoint_with_intact_signature_is_recomputed(runner, small, tmp_path):
    run_config(runner, small, 1, out_dir=tmp_path)
    path = next((tmp_path / "raw").glob("*.json"))
    saved = json.loads(path.read_text())
    saved["result"] = {"engine": "ns-3", "protocol": "aodv", "pdr": 1,
                       "app_tx": 1, "app_rx": 1}
    path.write_text(json.dumps(saved))
    result = run_config(runner, small, 1, out_dir=tmp_path)
    assert "mean_delay_s" in result


def test_single_hop_packet_does_not_count_loopback_dispatch(runner, small):
    result = runner.run(replace(small, nodes=2, flows=1))
    assert result["mean_hops"] == 1


def test_no_build_rejects_stale_source_stamp(runner, tmp_path):
    (tmp_path / "ns3").touch()
    (tmp_path / "VERSION").write_text("3.45")
    (tmp_path / "build").symlink_to(runner.home / "build", target_is_directory=True)
    stamp = json.loads((runner.home / ".ar-eaurp-build.json").read_text())
    stamp["source_sha256"] = "an older simulation"
    (tmp_path / ".ar-eaurp-build.json").write_text(json.dumps(stamp))
    with pytest.raises(ValueError, match="stale"):
        Ns3Runner(tmp_path).fingerprint()


def test_cached_fingerprint_rechecks_linked_ns3_library_changes(runner, tmp_path):
    (tmp_path / "ns3").touch()
    (tmp_path / "VERSION").write_text("3.45")
    (tmp_path / "build/scratch").mkdir(parents=True)
    (tmp_path / "build/scratch" / runner.binary.name).symlink_to(runner.binary)
    libraries = tmp_path / "build/lib"
    libraries.mkdir()
    (libraries / "libns3.45-ar-eaurp-optimized.so").write_bytes(b"module")
    energy = libraries / "libns3.45-energy-optimized.so"
    energy.write_bytes(b"original")
    (tmp_path / ".ar-eaurp-build.json").write_text(json.dumps({
        "source_sha256": source_digest(ROOT), "installed_sha256": installed_digest(tmp_path)}))
    cached = Ns3Runner(tmp_path)
    cached.fingerprint()
    energy.write_bytes(b"changed upstream library")
    with pytest.raises(ValueError, match="stale"):
        cached.fingerprint()
