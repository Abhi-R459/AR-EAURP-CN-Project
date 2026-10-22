# AR-EAURP — native ns-3 workflow

The simulation and active workflow are **compiled ns-3.45 C++**: experiment selection,
network simulation, GAN/LSTM/tabular learning/CMDP, repeated seeds,
checkpointing, statistics, CSVs, reports and plot-script generation.
Plots use ns-3's `Gnuplot` helper and the gnuplot renderer. Shell scripts build
and launch the executables. There is no project Python runtime or Python
orchestrator. Upstream ns-3 keeps its standard build dependencies.

All network simulation must run in ns-3. Python may be used for analysis,
visualization or other utilities, but must not implement a simulation engine,
packet forwarding, mobility, energy evolution or protocol learning during a run.

## Build and run

Install a C++20 compiler, CMake, OpenSSL development files, curl and gnuplot.
On macOS: `brew install cmake openssl@3 gnuplot`. On Ubuntu:
`sudo apt-get install build-essential cmake pkg-config libssl-dev curl gnuplot-nox`.

```bash
bash ns3/scripts/setup.sh --download
bash ns3/scripts/run.sh --profile=smoke
```

The default installation is `~/.cache/ar-eaurp/ns-3.45`. To use an existing
installation:

```bash
export NS3_HOME=/path/to/ns-3.45
bash ns3/scripts/setup.sh --home "$NS3_HOME"
bash ns3/scripts/run.sh --verify=1
bash ns3/scripts/run.sh --profile=quick
bash ns3/scripts/run.sh --profile=full
```

`smoke` exercises 86 configurations with one seed, `quick` uses two seeds,
and `full` uses five. Lifetime runs have longer horizons. Results default to
`results/ns3-native-PROFILE/`: raw checkpoints, CSVs, SVG figures, Gnuplot
scripts, `report.md`, `report.html` and a manifest with build identity.

```bash
bash ns3/scripts/run.sh --profile=smoke --only=e3,e5 --out=results/native-attacks
bash ns3/scripts/run.sh --profile=smoke --fresh=1
bash ns3/scripts/run.sh --profile=smoke --render=0
```

`--only` selects experiments; `--fresh=1` recomputes matching checkpoints.
Rerunning normally resumes them. `--render=0` exports plot scripts without
invoking gnuplot. No plots are rendered in that mode. Source, linked ns-3
libraries and native binaries are hashed; stale builds are rejected. Raw
checkpoint checksums reject truncated or modified contents. Each configuration
uses the same seeds across protocols. Aggregation reports sample seed SD.

## Native entry points

| Executable | Responsibility |
|---|---|
| `ar-eaurp-sim` | One commissioning/evaluation scenario |
| `ar-eaurp-experiments` | E1–E6 selection, repeated runs, checkpoints, aggregation, reports, plots and native integration verification |
| `ar-eaurp-range` | PHY range calibration |
| `test-runner --suite=ar-eaurp` | Native model unit tests |

The experiment executable calls the scenario directly in the same C++
process. It never invokes a Python script or the ns-3 Python launcher.
Individual scenarios can also run through the compiled binary:

```bash
"$NS3_HOME/build/scratch/ns3.45-ar-eaurp-sim-optimized" \
  --protocol=ar-eaurp --attack=grayhole --malicious=0.3 --json=run.json
```

| Protocol | Behaviour |
|---|---|
| `aodv` | Hop-count baseline on the common custom substrate |
| `eaurp` | Watchdog trust, energy-aware routing and revocation |
| `drl-paper` | A: tabular Q-learning with watchdog trust |
| `drl-senior` | B: tabular Q-learning with own endpoint-counter trust; no revocation |
| `ar-eaurp` | C: GAN detection, LSTM harvest forecasting and CMDP/DQN routing |
| `ns3-aodv` | Upstream AODV comparator, clean runs only |

A/B adapt the paper's global probability model to local distributed route
discovery. B increments its receive counter on actual arrival; remote failed
attempts are unavailable. Diversification avoids the previous next hop;
complete node-disjoint paths are not claimed.

All protocols use the same UDP/ACK traffic. X25519/HKDF/AES-GCM protects
messages by default, adding 28 bytes per message. Per-flow deterministic keys
are simulation fixtures provisioned before a run. Key-exchange packets and
crypto CPU latency are not modelled in simulated time.

## Experiments and measurement limits

| Experiment | Sweep |
|---|---|
| E1 | Maximum speeds 1–20 m/s |
| E2 | Density 60–200 nodes |
| E3 | Blackhole, grayhole and trust poisoning; 0–50% malicious nodes |
| E4 | Battery/harvesting energy, forecast holdouts and lifetime |
| E5 | GAN/LSTM/CMDP/energy-excuse ablations and PDR-floor sensitivity |
| E6 | Generated control traffic, wall time, protected-message overhead and ECC-off comparison |

PDR counts measurement-window sends and their arrivals through cooldown;
ACK loss can penalise delivered data. GAN/LSTM train only on clean
commissioning. Check trained flags before interpreting learned results.
LSTM holdouts use disjoint temporal intervals per node.

Delay is seconds, energy joules, forecast error watts and throughput bits/s.
Unobserved deaths are censored at the horizon. First depletion permanently
disables the PHY, matching the former simulator. The source is an ideal
reservoir without a capacity ceiling; charge can exceed initial charge and
can recover after node failure. A small guard fixes ns-3.45 radio timer
reentrancy and ensures energy-model shutdown also shuts down the PHY.

Control counters count generated attempts, including attempts after PHY
shutdown. Diagnostic drops across layers are not additive application loss
categories. A violated CMDP target does not prove infeasibility. Wall time
includes commissioning and reflects host runtime. Smoke results validate
execution only; the full research sweep has not been run during migration.

## Tests and Colab

```bash
"$NS3_HOME/build/utils/ns3.45-test-runner-optimized" --suite=ar-eaurp --verbose
bash ns3/scripts/run.sh --verify=1
bash ns3/scripts/run.sh --notebooks=1
bash ns3/scripts/verify.sh
```

The native integration checks exercise delivery under all protocols,
repeatability, crypto, late feedback, battery shutdown, harvesting,
trained models, seed statistics and checkpoint integrity/resume.

Upload `colab/REVIEW2_AR_EAURP.ipynb` to Colab for an embedded source snapshot,
or use `colab/REVIEW2_FROM_GITHUB.ipynb` for a public repository clone.
Both notebooks contain shell-only executable cells; the Colab UI still
uses its standard kernel. They build C++ and launch the native runner.
Download the generated HTML report, SVGs and result folder through Colab's
Files panel. An actual Colab execution remains unverified.

## Historical material

The former Python simulator, its trace simulator and the original Python
simulation notebooks have been removed. They remain recoverable from Git
history. The intermediate Python ns-3 launcher and analysis utilities in
`legacy/ns3-python-tooling/` contain no simulation engine and are unsupported.
Existing `output/` and `paper/` material is historical and must not be
presented as native measurements.

The independent Flutter messenger remains in `app/`; see its README.
