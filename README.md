# AR-EAURP — native ns-3 workflow

The simulation and active workflow are **compiled ns-3.45 C++**: experiment selection,
network simulation, GAN/LSTM/tabular learning/CMDP, repeated seeds,
checkpointing, statistics, CSVs, reports and plot-script generation.
Plots use ns-3's `Gnuplot` helper and the gnuplot renderer. Shell scripts build
and launch the executables. Evaluation needs no project Python runtime or Python
orchestrator. The optional local trace viewer uses Python's standard library to
serve output from the compiled simulator. Upstream ns-3 keeps its standard
build dependencies.

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
`review` uses the five-run, 24-node review settings below, and `full` uses five
runs with the larger full-profile workload. Lifetime runs have longer horizons. Results default to
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

### NetAnim and live trace viewer

The scenario can write a genuine ns-3 NetAnim XML trace for the **evaluation**
phase. If AR-EAURP trains models first, the clean commissioning phase is kept
out of that trace. Packet records represent wireless transmissions and actual
receptions; a received wireless frame is not an application delivery.

```bash
"$NS3_HOME/build/scratch/ns3.45-ar-eaurp-sim-optimized" \
  --protocol=ar-eaurp --attack=grayhole --malicious=0.25 \
  --nodes=24 --flows=6 --area=420 --time=40 --warmup=5 \
  --netanim=trace.xml --netanimPoll=0.25
```

Open `trace.xml` in the [official NetAnim application](https://www.nsnam.org/docs/models/html/animation.html),
or open `ns3_netanim_viewer.html` and select the XML. The browser viewer also
accepts split trace files together (`trace.xml`, `trace.xml-1`, and so on).
`--netanimStart`, `--netanimStop` and `--netanimMaxPackets` control the trace
window and file size. Large research runs can produce very large XML files, so
choose a short window for inspection.

For a live run, start the local viewer server from the project root:

```bash
python3 ns3/netanim/live_server.py --ns3-home "$NS3_HOME"
```

On Windows, run this command in WSL alongside the Linux ns-3 build.

Open the address it prints, choose the scenario and press **Start ns-3 run**.
The server launches the compiled binary and relays its native NetAnim elements
as they are written. The **Pace evaluation to wall time** option uses ns-3's
best-effort real-time scheduler; if a run needs more CPU time, it can fall
behind wall time. The page reads final application PDR and delay from the
scenario's JSON result. XML replay alone does not contain those metrics.
Live traces and results are saved under `results/ns3-live/`.
Each live run also saves `launch.json` with the exact simulator command and
requested viewer settings. Completed runs appear in the viewer's measured
protocol comparison table; saved native `result.json` files can be loaded there
for a fast replay of results. A checked, short EAURP/AR-EAURP demonstration and
its limits are documented in
`results/final_review_ns3_results/FINAL_NS3_EVALUATION_REPORT.md`.

### Protocol variants

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
execution only. The `review` results below are time-boxed and do not complete
the planned five-run density sweep or establish protocol superiority.

## Latest review results and evidence

The native `review` profile uses ns-3.45, 24 nodes, six CBR flows, a 420 m
square area, a 120 s scenario including 20 s warm-up (**100 s measured**),
10 s cooldown, and five matched run numbers
(master seed 20260909; runs 1–5). AR-EAURP receives a separate 240 s clean
commissioning phase with 120 GAN and 30 LSTM epochs. This is a shorter review
profile than the 400 s full-profile evaluation.

The time-boxed review report contains results for all five protocol variants
under mobility, density, blackhole, grayhole, trust-poisoning, energy, lifetime,
component-ablation, CMDP-floor, and security-overhead scenarios. It records
**179/181 conditions and 863/905 planned native runs**. E1, E3, E4, E4b, E5,
E5b, and E6 are complete at five runs per condition. E2 density is partial:
108/150 runs across 28/30 conditions. Densities from 60–120 nodes have five
runs; the 150- and 200-node observations are single-run descriptive points,
and EAURP and AR-EAURP at 200 nodes are missing. The report and ledgers do not
impute missing runs.

The matched E3 AR-EAURP versus EAURP PDR comparison has one of 18 attack/fraction
cells whose unadjusted paired 95% interval excludes zero: trust poisoning at
20% hostile nodes, +11.07 percentage points [1.35, 20.79]. The other 17
intervals include zero. Since 180 pairwise protocol contrasts are exploratory
and are not corrected for multiple comparisons, this does **not** establish
overall AR-EAURP superiority. See the report for all protocols, attack
fractions, settings, uncertainty, and limitations.

An additional held-out CMDP commissioning study used matched run numbers
21–50, separate from the review’s runs 1–5. The commissioning-trained
AR-EAURP mean PDR was 80.97% versus 79.81% for EAURP (paired difference
+1.16 points, 95% CI −2.97 to +5.30; 16/30 paired wins). Mean delay was
32 ms higher for AR-EAURP. This result is inconclusive and is not evidence of
superiority. Earlier exploration and tuning runs are labeled separately in
the study README so they are not mixed with the held-out comparison.

The finished documents and study evidence are included in the repository.
Editable manuscript sources and document-generation tools are kept locally in
`paper/` and are not published to GitHub:

- [Current research paper (Word)](project_docs/AR_EAURP_Research_Paper.docx)
- [Complete tests and findings (Word)](project_docs/AR_EAURP_Test_Results_and_Findings_Final.docx)
- [Combined paper and findings (PDF)](project_docs/AR_EAURP_Research_Paper_and_Test_Results_and_Findings.pdf)
- [Paper-style report (HTML)](results/ns3-native-paper-review/paper_results.html)
- [Paper-style report (Markdown)](results/ns3-native-paper-review/paper_results.md)
- [Study settings and completion manifest](results/ns3-native-paper-review/study_settings.json)
- [Condition settings and aggregate metrics](results/ns3-native-paper-review/configuration_settings.csv)
- [Per-run settings and checkpoint checksums](results/ns3-native-paper-review/run_settings.csv)
- [All 180 matched E3 contrasts](results/ns3-native-paper-review/pairwise_e3_comparisons.csv)
- [Aggregate CSV tables](results/ns3-native-paper-review/csv/)
- [Figures (SVG and PNG)](results/ns3-native-paper-review/figures/)
- [CMDP commissioning study, method and findings](results/optimization_study/README.md)
- [Matched native JSON outputs and simulator logs](results/optimization_study/)

All 863 ledger-referenced checkpoint files were checked against their SHA-256
checksums; aggregate means/SDs and all 180 E3 pairwise deltas were independently
reconciled against the per-run records. The report is assembled from verified
checkpoints. The root `manifest.json` records the original C++ batch selection
(`e3,e4,e5,e6`); the final E1/E2 data were also aggregated from their verified
checkpoint sets. Rebuild the report from its folder using
`python generate_paper_report.py`.

The current manuscript explains the native implementation, nine detector features,
clean commissioning, forecasting fallback, shared CMDP policy, comparator
adaptations, statistical methods, all experiment families, and limitations. The
companion report retains all 180 E3 pairwise contrasts and 13 exploratory
optimization groups. Both list the five project authors. The Word/PDF exports
were checked for table parsing and chart visibility; they describe saved
evidence rather than new simulation runs. In the selected 30% gray-hole workload,
persistence beat the LSTM in all five runs. Neither these component results nor
the overall comparisons establish general AR-EAURP superiority.

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
Existing `output/` measurements are historical Python results and must not be
presented as native measurements. The documents in `project_docs/` separate
those historical results from the native ns-3 study.

The independent Flutter messenger remains in `app/`; see its README.
