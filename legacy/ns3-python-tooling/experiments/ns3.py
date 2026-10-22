"""Run compiled ns-3 scenarios. This module contains no simulation logic."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = ("aodv", "eaurp", "drl-paper", "drl-senior", "ar-eaurp", "ns3-aodv")
ATTACKS = ("none", "blackhole", "grayhole", "trust_poisoning")
DEFAULT_HOME = Path.home() / ".cache" / "ar-eaurp" / "ns-3.45"


@dataclass(frozen=True)
class Scenario:
    protocol: str = "ar-eaurp"
    attack: str = "none"
    malicious: float = 0.0
    nodes: int = 100
    area: float = 1000.0
    min_speed: float = 1.0
    max_speed: float = 20.0
    pause: float = 2.0
    flows: int = 40
    rate: float = 1.0
    min_size: int = 512
    max_size: int = 1024
    duration: float = 300.0
    warmup: float = 30.0
    commission: float = 240.0
    cooldown: float = 10.0
    energy: float = 350.0
    harvest: bool = True
    panel_fraction: float = 0.7
    day_length: float = 600.0
    tx_power: float = 16.0206
    sensitivity: float = -96.0
    path_loss: float = 3.0
    seed: int = 20260909
    run: int = 1
    train: bool = True
    gan: bool = True
    lstm: bool = True
    cmdp: bool = True
    energy_excuse: bool = True
    ecc: bool = True
    pdr_floor: float = 0.90
    gan_epochs: int = 120
    lstm_epochs: int = 30
    flow_monitor: bool = False

    def __post_init__(self):
        for key, value in asdict(self).items():
            if isinstance(value, (int, float)) and not math.isfinite(value):
                raise ValueError(f"{key} must be finite")
        for key in ("nodes", "flows", "min_size", "max_size", "seed", "run", "gan_epochs", "lstm_epochs"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{key} must be an integer")
        checks = (
            self.protocol in PROTOCOLS, self.attack in ATTACKS,
            2 <= self.nodes <= 1000, 1 <= self.flows <= 1000,
            0 <= self.malicious <= 1, self.area > 0,
            0 < self.min_speed <= self.max_speed, self.pause >= 0,
            self.rate > 0, 1 <= self.warmup < self.duration,
            self.commission > 10, self.cooldown >= 6,
            32 <= self.min_size <= self.max_size <= 1400,
            self.energy > 0, 0 <= self.panel_fraction <= 1, self.day_length > 0,
            self.path_loss > 0, 0 < self.seed < 2**32, 0 < self.run < 2**32 - 500,
            0 <= self.pdr_floor <= 1, self.gan_epochs > 0, self.lstm_epochs > 0,
            self.attack != "none" or self.malicious == 0,
            self.protocol != "ns3-aodv" or self.malicious == 0,
        )
        if not all(checks):
            raise ValueError("invalid ns-3 scenario configuration")

    def arguments(self):
        names = {"min_speed": "minSpeed", "max_speed": "maxSpeed",
                 "min_size": "minSize", "max_size": "maxSize", "duration": "time",
                 "panel_fraction": "panelFraction", "day_length": "dayLength",
                 "tx_power": "txPower", "path_loss": "pathLoss", "pdr_floor": "pdrFloor",
                 "gan_epochs": "ganEpochs", "lstm_epochs": "lstmEpochs",
                 "energy_excuse": "energyExcuse", "flow_monitor": "flowMonitor"}
        return [f"--{names.get(k, k)}={int(v) if isinstance(v, bool) else v}"
                for k, v in asdict(self).items()]


def valid_result(result, scenario):
    """The same contract validates fresh measurements and saved checkpoints."""
    required = ("pdr", "app_tx", "app_rx", "rx_bytes", "measurement_seconds", "mean_delay_s",
                "cfg_seed", "cfg_run", "cfg_nodes", "cfg_duration", "cfg_warmup", "cfg_malicious")
    try:
        return (isinstance(result, dict) and result.get("engine") == "ns-3"
                and result.get("ns3_version") == "3.45"
                and result.get("protocol") == scenario.protocol
                and result.get("attack") == scenario.attack
                and all(isinstance(result[k], (int, float)) and math.isfinite(result[k]) for k in required)
                and all(not isinstance(v, (int, float)) or math.isfinite(v) for v in result.values())
                and 0 <= result["pdr"] <= 1 and result["measurement_seconds"] == scenario.duration - scenario.warmup
                and 0 <= result["app_rx"] <= result["app_tx"]
                and all(result["cfg_" + key] == getattr(scenario, key)
                        for key in ("seed", "run", "nodes", "duration", "warmup", "malicious")))
    except (KeyError, TypeError, ValueError):
        return False


class Ns3Runner:
    def __init__(self, home=None, timeout=3600):
        self.home = Path(home or os.environ.get("NS3_HOME", DEFAULT_HOME)).expanduser().resolve()
        self.timeout = timeout
        if not (self.home / "ns3").is_file():
            raise FileNotFoundError(f"ns-3 not found at {self.home}; run bash ns3/scripts/setup.sh --home <path> --download")
        version = (self.home / "VERSION").read_text().strip()
        if version != "3.45":
            raise ValueError(f"expected ns-3.45, found {version}")
        self._fingerprint = None
        self._metadata = None

    def build(self):
        subprocess.run(["bash", str(ROOT / "ns3/scripts/setup.sh"), "--home", str(self.home)],
                       cwd=ROOT, check=True)
        self._fingerprint = None

    @property
    def binary(self):
        candidates = list((self.home / "build/scratch").glob("ns3.45-ar-eaurp-sim-*"))
        if not candidates:
            raise FileNotFoundError("ar-eaurp-sim has not been built; run ns3/scripts/setup.sh")
        return max(candidates, key=lambda p: p.stat().st_mtime_ns)

    def fingerprint(self):
        # Metadata is cheap enough to check between every run. Rehash changed
        # files, so editing/rebuilding during a batch cannot reuse stale results.
        files = [p for p in (ROOT / "ns3").rglob("*") if p.is_file() and p.suffix in (".cc", ".h", ".txt")]
        files += list((self.home / "build/scratch").glob("ns3.45-ar-eaurp-sim-*"))
        files += installed_libraries(self.home)
        stamp_path = self.home / ".ar-eaurp-build.json"
        if stamp_path.is_file():
            files.append(stamp_path)
        metadata = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(files)]
        if self._fingerprint is None or metadata != self._metadata:
            source = source_digest(ROOT)
            installed = installed_digest(self.home)
            try:
                stamp = json.loads((self.home / ".ar-eaurp-build.json").read_text())
            except (OSError, ValueError) as error:
                raise ValueError("build provenance missing; rerun ns3/scripts/setup.sh") from error
            if stamp != {"source_sha256": source, "installed_sha256": installed}:
                raise ValueError("ns-3 build is stale or changed; rerun ns3/scripts/setup.sh")
            self._fingerprint = hashlib.sha256((source + installed).encode()).hexdigest()
            self._metadata = metadata
        return self._fingerprint

    def run(self, scenario):
        self.fingerprint()  # refuse to label a stale shared library as current
        # A fresh file per process avoids schema drift and partial CSV appends.
        with tempfile.TemporaryDirectory(prefix="ar-eaurp-") as temp:
            output = Path(temp) / "result.json"
            command = [str(self.binary), *scenario.arguments(), f"--json={output}"]
            completed = subprocess.run(command, cwd=self.home, capture_output=True, text=True,
                                       timeout=self.timeout)
            if completed.returncode:
                raise RuntimeError(f"ns-3 failed ({completed.returncode}):\n{completed.stderr[-4000:]}\n{completed.stdout[-4000:]}")
            try:
                result = json.loads(output.read_text())
                valid = valid_result(result, scenario)
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise RuntimeError("ns-3 did not produce a valid result") from error
            if not valid:
                raise RuntimeError("ns-3 produced incompatible or invalid measurements")
            return result


def source_digest(root):
    digest = hashlib.sha256()
    root = Path(root)
    for file in sorted((root / "ns3").rglob("*")):
        if file.is_file() and file.suffix in (".cc", ".h", ".txt"):
            digest.update(str(file.relative_to(root)).encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()


def installed_libraries(home):
    # Routing dynamically links ns-3 Wi-Fi, energy, mobility, core and other
    # modules. Include their implementations, not just the contrib library.
    return sorted(p for p in (Path(home) / "build/lib").glob("*ns3.45-*")
                  if p.is_file() and "-test-" not in p.name)


def installed_digest(home):
    home = Path(home)
    binaries = list((home / "build/scratch").glob("ns3.45-ar-eaurp-sim-*"))
    libraries = installed_libraries(home)
    if not binaries or not libraries:
        raise FileNotFoundError("AR-EAURP binary/shared library absent; run ns3/scripts/setup.sh")
    digest = hashlib.sha256()
    for file in [max(binaries, key=lambda p: p.stat().st_mtime_ns), *sorted(libraries)]:
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()
