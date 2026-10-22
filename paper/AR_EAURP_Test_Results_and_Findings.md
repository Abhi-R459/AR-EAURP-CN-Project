---
title: "AR-EAURP: Experimental Methods, Complete Test Results, and Findings"
author: "Karnati Abhinav Reddy; Sree Raj Muthaiya A.L.; Nidhurshek; Hansika Muntimadugu; Anish"
date: "22 October 2026"
---


## Research objectives, experimental logic, and decision rules

This report answers four practical research questions: how each native policy behaves across mobility, density, attacks, and energy modes; whether anomaly evidence becomes successful routing protection; whether individual components justify their complexity; and whether matched AR–EAURP differences are stable enough to support a performance claim. It is an experimental record, not an assertion that all results favor the proposed method. The appropriate unit of replication is a simulator run, not an individual packet or repeated detector window.

The native C++ study is the principal current implementation evidence. Historical Python results provide the earlier-review context. The earlier native five-run snapshot, exploratory optimization groups, and later thirty-pair commissioning study are distinct cohorts. They use different run ranges and, in some cases, implementation states. Their sample sizes are not pooled, and a change between cohorts is not interpreted as a controlled estimate of a code change's effect.

A result is described as a point advantage when the mean difference is positive. An interval spanning zero is inconclusive for direction. A nonzero exploratory interval is not automatically a confirmatory finding, particularly across eighteen selected contrasts and 180 all-pair comparisons. Missing runs are not filled with averages or zeros. A single run has no empirical SD. A disabled detector's zero/default outputs are not evidence of perfect classification. A censored lifetime is not an observed death time. These conventions apply to every table below.

## Native implementation and complete measurement definitions


### Network and routing substrate

The system consists of mobile wireless nodes that originate application traffic, discover routes, and relay packets over an IEEE 802.11 ad hoc network. Each node maintains neighbor information, residual energy, routing state, and locally available forwarding observations. Packets traverse actual ns-3 IP, MAC, and PHY events. Delivery therefore depends on route discovery, queueing, retransmission, interference, mobility, relay behavior, and battery state. A packet is not declared delivered by a single network-wide probability. This distinction is central to the transition from the earlier Python study to the native experiment.

The implementation is a native C++ ns-3.45 module. The detector, forecaster, neural-network operations, tabular agents, and constrained route selector execute within that module. Python scripts aggregate saved outcomes and prepare reports; they do not replace the packet path with an external predictor. The protocol uses route requests, route replies, route errors, neighbor advertisements, trust reports, and revocation-related control messages. A route can fail before an attacker is reached, so malicious-drop counters and total application loss measure different processes.

For a neighbor j, forwarding trust is smoothed as $T_j^{new}=0.7T_j^{old}+0.3PFR_j$, where PFR is the observed forwarding ratio. The trust and energy route score has the form $R_j=\operatorname{clip}(a_iT_j+b_iE_j^{eff},0,1)$. The adaptive energy weight uses the mean normalized energy of the node and its nonexpired neighbor advertisements; the trust weight is its complement. The link cost includes $(1-R_j)$ and a 0.35 hop penalty, represented internally in integer milli-cost units. This is a routing heuristic rather than a proof of an optimal path under the radio model.

Energy-aware variants exclude relays below 20% of their initial charge. The AODV-style reference uses equal hop costs and does not apply that energy gate. A contested AR neighbor receives an additional 0.5 trust multiplier for a 60 s contested interval. These choices can improve avoidance but also remove useful relays. Their possible cost is measured through PDR, delay, route failures, and component ablations.

### Threat model

Attacks are insider forwarding and reputation attacks. Malicious nodes participate in the network and can forward control traffic while withholding relayed application packets. A black-hole relay drops relayed data. A gray-hole relay forwards smaller packets and independently drops eligible larger packets with probability 0.25, using a 700-byte size threshold. The trust-poisoning configuration combines selective forwarding with dishonest reports: a colluder advertises favorable trust for fellow malicious nodes and low trust for honest nodes. The explicit collusion assumption allows an attacker to recognize its allies. Honest routing does not receive that ground-truth attacker list as an avoidance policy.

The experiment varies the configured hostile fraction from 0% to 50% in ten-percentage-point steps. With a finite number of nodes, configured prevalence is not a guarantee that every route encounters an attacker or that every adversarial node obtains a forwarding opportunity. Selective packet eligibility, sparse observations, and route changes further separate attack prevalence from the number of positive detector windows. Consequently, a 30% gray-hole condition is not equivalent to dropping 30% of all generated packets.

The evaluated scope excludes physical jamming, malicious radio hardware, cryptographic key theft, wormholes, and arbitrary compromise of the simulator itself. A low delivery ratio can still arise from benign link failure or a depleted relay. These competing explanations motivate careful watchdog accounting and an energy excuse before trust condemnation. No formal anonymity or traffic-unobservability property is established by the experiments.

### Watchdog observations and detection layers

The watchdog associates a forwarded packet digest with the intended next hop and confirms an overheard onward transmission using the neighbor MAC binding. A failed link-layer handoff cancels its pending watchdog entry, avoiding the automatic attribution of that failed handoff to malicious forwarding. A missing observation is therefore handled differently from a confirmed successful forwarding event. The watchdog timeout is 1 s. Published opinions require sufficient accumulated evidence, and an anomaly window requires at least six new observations.

The native detector consumes nine features: short-window PFR, long-window PFR, their difference, large-packet drop ratio, small-packet drop ratio, scaled mean forwarding latency, scaled latency standard deviation, report disagreement, and the difference between large- and small-packet drop ratios. Latencies are scaled by 0.1 s and capped at two; features are sanitized and clipped to the implemented range. Size-conditioned observations target selective forwarding that can remain hidden in a single average PFR.

Three measurement layers are retained. First, window-level TPR, FPR, and AUC describe thresholded anomaly scores and score ranking on eligible windows. Second, contested-node measurements describe corroborated suspicion with honest-witness requirements. Third, revocation measurements describe the protocol's final exclusion state. A correct anomaly score is not automatically a corroborated accusation, and an accusation is not automatically successful rerouting. The consensus logic requires at least two accusers and at least half of the relevant observers, subject to local evidence and energy checks. Ground-truth labels support evaluation; they are not a substitute for this inference path.

### Clean-trained generative anomaly model

The detector is trained during a separate 240 s attack-free commissioning simulation. For feature k, clean training statistics define $z_k=(x_k-\mu_k)/\max(\sigma_k,10^{-3})$. At least 32 clean windows are required. The generator maps an eight-dimensional latent vector through two 32-unit ReLU layers to nine outputs. The discriminator uses layers of 32 and 16 units with leaky ReLU activations and a sigmoid output. Adversarial training uses 120 epochs, batches of 16, a learning rate of $2\times10^{-4}$, and one-sided real-label smoothing to 0.9. These are native implementation settings, not parameters copied from the older Python detector.

Following training, the generator produces a bank B of 2,048 standardized normal behavior vectors. The inference score is the nearest generated-vector root-mean-square distance:

$$s(x)=\min_{b\in B}\sqrt{\frac{1}{9}\sum_{k=1}^{9}(z_k-b_k)^2}.$$

The threshold is the 95th percentile of scores on the collected clean training windows. The score is not a maliciousness probability and is not the discriminator's real-versus-generated output. The model is related to generative anomaly modeling, but the generated-bank inference procedure is specific to this project. In particular, it does not optimize a latent vector separately for every evaluation sample.

Detector parameters are frozen for attack evaluation. This separates attack observations from model fitting, but the same clean collection is used for fitting and threshold calibration. The threshold therefore lacks an independent clean calibration set, and nominal 5% calibration does not guarantee a 5% FPR on new network conditions. Mobility, neighborhood changes, sparse evidence, and channel-induced losses can alter the score distribution. The measured evaluation FPR is reported instead of assuming the calibration target was achieved.

### Harvest forecasting and fallback selection

The forecaster predicts mean harvested power over the next ten samples from a history of twenty samples. At each 1 s sample, the inputs are normalized harvested power and the sine and cosine of the modeled day phase. A 24-unit LSTM is trained for 30 epochs with learning rate 0.005. Its target is power in watts, not cumulative battery energy. Routing blends current normalized energy and normalized predicted harvested power for its energy-oriented action.

For each node's commissioning trace, the earliest 70% supplies training data and the last 30% supplies validation. Sequences crossing the split are purged, and normalization uses training power only. Persistence and a recent-window mean are evaluated on the same held-out targets. The LSTM is used for routing only when its validation MAE is strictly below persistence; otherwise prediction falls back to persistence. The field historically named seasonal MAE corresponds to a window-mean predictor, so this paper does not call it a seasonal forecasting baseline.

All traces contribute to shared model parameters. There is one fleet-trained detector and one fleet-trained forecaster, rather than a separately trained network at each node. Provisioning such models is a plausible deployment step, but training communication, model distribution, and hardware inference cost are not evaluated as a distributed field system. Reporting the fallback outcome is necessary: an experiment in which persistence is selected cannot be cited as evidence that the LSTM improved delivery.

### Constrained learning for route strategy selection

The CMDP-inspired agent chooses among trust-oriented, energy-surplus, balanced, and diversified routing strategies. Its six state variables are mean local trust, own residual-energy fraction, normalized speed, forecast surplus, contested-neighbor fraction, and rolling application feedback PDR. The feedback window contains the latest 100 delivery outcomes. Before feedback exists, its initial PDR value is one. This online state differs from the final measured application PDR and can be affected by timeout feedback.

The route selector uses a six-input, two-hidden-layer network with 64 ReLU units per layer and four action values. Its Double-DQN target is

$$y=r+0.9Q_{target}(s',\arg\max_a Q_{online}(s',a)).$$

The shaped reward is

$$r=(2I_{delivered}-1)-0.05c_E-5\lambda\max(0,\tau-\widehat{PDR}_{100}).$$

Here $c_E$ is a hop-based energy proxy, and $\tau$ is the target delivery floor. The proxy derives from a 2 mJ-per-hop assumption and internal scaling; it is not the radio energy consumed by the packet. Actual battery behavior is measured separately through the ns-3 energy model. Every ten source attempts, the dual variable is updated as $\lambda\leftarrow\operatorname{clip}(\lambda+0.05(\tau-\widehat{PDR}_{100}),0,20)$.

The replay buffer holds 5,000 transitions; batch size is 32, learning rate is 0.001, and training is attempted every four observations. Target parameters use a hard copy every 200 training calls and a 0.01 Polyak update otherwise. Epsilon decays from 0.30 toward 0.05 with an 800-decision time constant. Exploration and shared policy updates continue during evaluation. The current implementation also learns from clean commissioning outcomes, rather than first activating the route learner under attack.

One CMDP agent is shared through the native experiment coordinator. This parameter sharing is a substantive simulation assumption: the study evaluates a coordinated fleet policy, not independently learning decentralized agents. The Lagrangian construction is motivated by constrained decision processes, but no convergence, constraint-feasibility, or safety guarantee follows from the implemented finite-run learner. The floor sweep explicitly measures whether higher targets translate into higher observed delivery.

### Baseline definitions and protected payloads

All five comparison policies share the native packet harness. AODV denotes the custom equal-hop AODV-style reference; it is not ns-3's stock AODV implementation. A separate ns3-aodv integration option exists for clean checks but is not included in the attack matrix. EAURP is the project's trust/energy substrate adaptation, inspired by the base protocol. DRL-P and DRL-S denote native adaptations of the source-equation and delivered-implementation variants. Their tabular agent discretizes state, uses two actions, learning rate 0.1, discount 0.9, epsilon 0.1, and actual delivery feedback. Their behavior must not be described as verbatim reproduction of an external publication's complete original implementation.

Protected application traffic uses X25519 key agreement, HKDF-SHA256 key derivation, and AES-256-GCM authenticated encryption. A 12-byte nonce and 16-byte tag add 28 bytes per protected payload. The measured aggregate overhead includes the packets counted by the native instrumentation; it is not simply the number of measured source packets multiplied by 28. Key provisioning is trusted in the simulation. Payload protection does not prove authentication of every routing advertisement or traffic-analysis resistance. The no-ECC label in saved outputs disables the implemented payload protection path and should be interpreted in that operational sense.


### Metric dictionary and denominator audit

| Endpoint | Definition, unit, and interpretation |
|---|---|
| PDR | Unique received application packets / measured generated packets; fraction in raw data, percentage in tables |
| Mean delay | Delivered-packet arrival minus creation time, seconds; conditional on delivery |
| Throughput | Received application bytes × 8 / measurement_seconds, bit/s |
| Source feedback PDR | Rolling latest 100 success/timeout outcomes; learner state, not final application PDR |
| Detector TPR/FPR | Thresholded score outcomes over eligible positive/negative windows; not independent packet trials |
| Detector AUC | Ranking of window scores when both classes exist; default values without a class are not validation |
| Contested TPR/FPR | Native corroboration-state measures, separate from anomaly windows |
| Revocation TPR/FPR | Final exclusion-state measures, including ordinary trust logic |
| Residual energy | Sum of remaining network battery energy, J; not per-node charge |
| First death | Observed time to first dead node, s; use corresponding observation flag |
| 80% dead | Time to at least 80% dead; unobserved endpoints are right-censored |
| Control bytes | Aggregate native routing-control accounting, B; not application goodput |
| Crypto overhead | Aggregate protection bytes counted by instrumentation, B; no-ECC disables payload protection |
| Forecast MAE | Mean absolute power-prediction error on purged chronological holdout, W |
| Lambda | Nonnegative bounded learner penalty; increasing lambda is not proof that a constraint is satisfied |

### Statistical procedure and repeated clean conditions

For n completed run values, the sample SD uses n−1 in the denominator. The 95% t interval is mean ± t(0.975,n−1) × SD / sqrt(n). For five runs the critical value is approximately 2.776. Rate intervals in the saved report are bounded to [0,1]; this bounding does not make them exact binomial intervals. A paired PDR difference is 100 × (PDR_A − PDR_B) within a matched run number and is summarized across the five differences. The interval is calculated from their SD, not from the SD of either protocol alone.

The review master seed is 20260909 and run numbers are 1–5. Thus the study uses distinct run streams under one seed, not five distinct master seeds. Matching run numbers does not force identical random draws after protocols take different event paths. Zero-hostile rows under three attack labels describe the same clean setting and must not be counted as three independent confirmations. The 180-contrast appendix is exhaustive for the recorded E3 pairwise family but not for every possible network parameter combination.

### Detailed completion and missing-data explanation

E2 contains 100 completed runs at 60, 80, 100, and 120 nodes (five policies × five runs × four densities), five single runs at 150 nodes, and three single runs at 200 nodes. EAURP and AR have no 200-node checkpoint in the included evidence. The missing 42 runs therefore consist of the remaining replications at 150/200 nodes plus the two absent 200-node policy conditions. All other review experiments meet their planned five-run budget. No new runs were started during this document revision.

The aggregate settings key named measurement_duration_s=120 is a historical label. Raw measurement_seconds=100 is the actual base measurement denominator after the 20 s warm-up. The 900 s lifetime horizon has 880 s of measured generation. These distinctions should be preserved when quoting throughput, packet counts, commissioning cost, or experiment duration.

## Scope and evidence inventory

This document records the saved test results and the findings available on 22 October 2026. It accompanies the research manuscript and contains the detailed native ns-3 experiment tables, simulation settings, uncertainty estimates, all 180 E3 pairwise PDR contrasts, the separate CMDP commissioning study, exploratory tuning groups, an earlier native validation snapshot, and historical Python results.

The main native review matrix contains **179/181 conditions and 863/905 planned runs**. The remaining 42 density replications were deferred. Missing results are not imputed. The 30 matched CMDP commissioning pairs are a separate study with a different seed/run range, not an extension of the matrix's sample size. All numbers below come from saved artifacts; no additional simulation was run while preparing this document.

The evidence does not establish general AR-EAURP superiority. A positive PDR point estimate and a confidence interval spanning zero are reported as inconclusive. The single exploratory E3 interval excluding zero is unadjusted for multiple comparisons.

**Author and provenance note:** The five project authors are listed as provided. Institutional affiliation was not supplied and has not been invented. This record covers saved evidence as of 22 October 2026.

**Timing clarification:** the base native parameter `time=120` is the scenario duration, including the 20 s warm-up. The saved simulator metric `measurement_seconds` is 100 s; six 1-packet/s flows therefore send 600 measured application packets. Cooldown adds a further 10 s to allow final arrivals. Some earlier prose calls this a “120 s evaluation”; the exact metric window is 100 s, as recorded in the raw checkpoints. Clean commissioning is separate.



## Executive summary

This report summarizes the native ns-3.45 review matrix within the available time. The planned budget is five run numbers per condition with a fixed ns-3 seed of 20260909; the completion table records actual coverage, and incomplete replications are not imputed. The E3 attack sweep includes a paired AR-EAURP versus EAURP PDR analysis from the checksummed per-run checkpoints.

## Methods and reproducibility

Reproduction command from the project root: `bash ns3/scripts/run.sh --profile=review --only=e1,e2,e3,e4,e5,e6 --out=results/ns3-native-paper-review --render=0`. The experiment runner resumes only checksummed runs whose full parameter map and source/build identity match. Run `python generate_paper_report.py` from the result directory to rebuild the expanded settings ledgers and charts.

Execution provenance: this final E1–E6 report is assembled from verified native ns-3 run checkpoints. The root `manifest.json` selection field records the original C++ batch selection (`e3,e4,e5,e6`); E1 and the time-boxed E2 results were included from their verified checkpoint sets. The per-run ledger is the authoritative record of the 863 included runs.

## Simulation settings

Each row in `configuration_settings.csv` names the canonical run-1 CLI arguments and aggregate metrics for one condition, including the actual replicate count and run numbers. Each row in `run_settings.csv` records the exact CLI argument map for that completed run, simulator-reported cfg_* values, selected per-run metrics, and the SHA-256 of the checksummed raw checkpoint. Confidence intervals are omitted where fewer than two replications exist.

| Experiment | Factors varied | Conditions | Native runs |
|---|---|---:|---:|
| E1 mobility | 5 protocols × max speed 1, 5, 10, 15, 20 m/s | 25 | 125 |
| E2 density | 5 protocols × 60, 80, 100, 120, 150, 200 nodes | 30 | 150 |
| E3 attacks | 5 protocols × 3 attacks × 0–50% hostile nodes (10-point steps) | 90 | 450 |
| E4 energy | 5 protocols × battery/solar-kinetic harvesting | 10 | 50 |
| E4b lifetime | 5 protocols × battery/solar-kinetic harvesting, 900 s horizon | 10 | 50 |
| E5 ablation | 6 AR-EAURP component configurations | 6 | 30 |
| E5b CMDP floor | 0.70, 0.80, 0.90, 0.95 PDR constraints | 4 | 20 |
| E6 security overhead | 5 protocols plus AR-EAURP without ECC | 6 | 30 |

- Simulator: ns-3.45, native C++ source/build identity SHA-256 `45da34216e04a79d26b8e9db9e02270a2bcdb5c3edf8e63fea4d61eda8d9ed02`.
- Protocols: AODV, EAURP, DRL-EAURP (paper), DRL-EAURP (senior), AR-EAURP.
- Base review scenario: 24 nodes, six CBR flows, 420 m square area, 120 s scenario including 20 s warm-up (100 s measured), 10 s cooldown.
- AR-EAURP clean commissioning: 240 s; GAN 120 epochs; LSTM 30 epochs. The CMDP route selector also learns during clean commissioning before attack evaluation.
- RNG: fixed seed 20260909 and run numbers 1–5 planned per condition. Run numbers are matched between protocol comparisons; results are stochastic replications, not repeated packets from one run.
- Metrics are reported as mean ± sample SD when at least two replications are present. Per-condition 95% confidence intervals use a two-sided Student t interval with degrees of freedom based on the observed sample size; bounded rate intervals (PDR, TPR, FPR, and AUC) are constrained to [0, 1]. E3 primary paired differences compare AR-EAURP and EAURP using corresponding run numbers.
- All ten pairwise protocol contrasts are retained for each E3 attack/prevalence condition in `pairwise_e3_comparisons.csv`; their intervals are unadjusted and should be interpreted as exploratory across this multiple-comparison family.
- `configuration_settings.csv` records each condition’s canonical run-1 CLI parameter map, observed run numbers, aggregate metrics, and simulator-reported settings. `run_settings.csv` records the exact CLI map for every completed run, measured cfg_* values, seed/run number, and the checksum of its raw checkpoint. Aggregate tables in `csv/` retain cfg_* means and sample SDs.

The review profile retains the Colab notebook’s E1–E6 factor levels but uses a 120 s scenario (100 s measured) and the 24-node/six-flow review workload rather than the notebook full profile’s 400 s and larger default workload. The planned budget is five runs. Any time-boxed shortfall appears in the completion table; this is not a byte-for-byte rerun of the Colab full-profile configuration.

## Completion status

Completed 179 of 181 planned conditions and 863 of 905 planned native runs. The time-boxed E2 density sweep has missing replications; they are absent from the ledgers and are not imputed.

| Experiment | Completed conditions | Completed runs |
|---|---:|---:|
| e1_speed | 25/25 | 125/125 |
| e2_density | 28/30 | 108/150 |
| e3_attack | 90/90 | 450/450 |
| e4_energy | 10/10 | 50/50 |
| e4b_lifetime | 10/10 | 50/50 |
| e5_ablation | 6/6 | 30/30 |
| e5b_cmdp_floor | 4/4 | 20/20 |
| e6_overhead | 6/6 | 30/30 |

## E1 — Mobility

| Configuration | PDR | Delay (s) | Throughput (bit/s) |
|---|---|---|---|
| AODV @ 1 m/s | 94.53 ± 4.92 | 0.12 ± 0.10 | 34932.50 ± 1773.64 |
| AODV @ 5 m/s | 92.57 ± 3.41 | 0.12 ± 0.08 | 34212.93 ± 1181.96 |
| AODV @ 10 m/s | 90.13 ± 5.59 | 0.21 ± 0.10 | 33258.11 ± 2130.37 |
| AODV @ 15 m/s | 91.47 ± 2.22 | 0.21 ± 0.05 | 33777.76 ± 747.07 |
| AODV @ 20 m/s | 89.17 ± 5.34 | 0.24 ± 0.14 | 32930.64 ± 1999.54 |
| EAURP @ 1 m/s | 86.80 ± 9.64 | 0.10 ± 0.10 | 32071.52 ± 3523.84 |
| EAURP @ 5 m/s | 95.00 ± 4.99 | 0.18 ± 0.15 | 35081.84 ± 1894.53 |
| EAURP @ 10 m/s | 88.10 ± 7.01 | 0.23 ± 0.12 | 32486.45 ± 2707.45 |
| EAURP @ 15 m/s | 88.90 ± 6.38 | 0.30 ± 0.10 | 32870.02 ± 2304.32 |
| EAURP @ 20 m/s | 87.07 ± 6.41 | 0.29 ± 0.10 | 32138.88 ± 2366.01 |
| DRL-EAURP (paper) @ 1 m/s | 93.87 ± 5.78 | 0.09 ± 0.02 | 34676.83 ± 2041.94 |
| DRL-EAURP (paper) @ 5 m/s | 90.70 ± 8.69 | 0.19 ± 0.19 | 33476.00 ± 3202.31 |
| DRL-EAURP (paper) @ 10 m/s | 89.97 ± 5.21 | 0.24 ± 0.13 | 33172.64 ± 1953.22 |
| DRL-EAURP (paper) @ 15 m/s | 90.97 ± 4.89 | 0.30 ± 0.08 | 33570.30 ± 1859.21 |
| DRL-EAURP (paper) @ 20 m/s | 85.67 ± 8.71 | 0.28 ± 0.13 | 31650.02 ± 3159.78 |
| DRL-EAURP (senior) @ 1 m/s | 96.30 ± 3.57 | 0.12 ± 0.08 | 35571.57 ± 1307.86 |
| DRL-EAURP (senior) @ 5 m/s | 95.10 ± 4.18 | 0.14 ± 0.09 | 35086.50 ± 1611.90 |
| DRL-EAURP (senior) @ 10 m/s | 91.63 ± 3.48 | 0.19 ± 0.07 | 33805.54 ± 1327.14 |
| DRL-EAURP (senior) @ 15 m/s | 91.23 ± 3.54 | 0.22 ± 0.11 | 33687.44 ± 1365.07 |
| DRL-EAURP (senior) @ 20 m/s | 92.20 ± 2.78 | 0.28 ± 0.08 | 34059.62 ± 1042.92 |
| AR-EAURP @ 1 m/s | 86.60 ± 14.32 | 0.12 ± 0.14 | 31991.66 ± 5181.71 |
| AR-EAURP @ 5 m/s | 94.10 ± 5.56 | 0.19 ± 0.12 | 34783.52 ± 2094.29 |
| AR-EAURP @ 10 m/s | 83.93 ± 11.10 | 0.22 ± 0.09 | 30954.80 ± 4053.12 |
| AR-EAURP @ 15 m/s | 86.17 ± 6.90 | 0.31 ± 0.13 | 31847.71 ± 2513.57 |
| AR-EAURP @ 20 m/s | 89.23 ± 4.73 | 0.27 ± 0.06 | 32886.26 ± 1742.36 |


## E2 — Network density

Run count is shown for each condition. A single run is descriptive only and is not a replicated estimate; the settings ledgers show exact coverage.

| Configuration | Runs | PDR | Delay (s) | Throughput (bit/s) |
|---|---|---|---|---|
| AODV (reference baseline) @ N=60 | 5 | 81.93 ± 5.71 | 0.25 ± 0.13 | 30248.45 ± 2179.59 |
| EAURP (base substrate) @ N=60 | 5 | 89.47 ± 4.02 | 0.26 ± 0.06 | 32970.30 ± 1558.44 |
| A: DRL-EAURP (paper) @ N=60 | 5 | 92.00 ± 5.39 | 0.28 ± 0.04 | 33989.07 ± 1885.60 |
| B: DRL-EAURP (senior) @ N=60 | 5 | 91.40 ± 4.55 | 0.26 ± 0.05 | 33710.98 ± 1673.22 |
| C: AR-EAURP (advancement) @ N=60 | 5 | 92.40 ± 4.79 | 0.23 ± 0.07 | 34144.48 ± 1668.36 |
| AODV (reference baseline) @ N=80 | 5 | 77.43 ± 3.85 | 0.22 ± 0.07 | 28616.26 ± 1519.62 |
| EAURP (base substrate) @ N=80 | 5 | 87.03 ± 2.72 | 0.23 ± 0.03 | 32123.42 ± 1079.28 |
| A: DRL-EAURP (paper) @ N=80 | 5 | 83.60 ± 4.86 | 0.29 ± 0.06 | 30875.17 ± 1856.13 |
| B: DRL-EAURP (senior) @ N=80 | 5 | 89.53 ± 3.11 | 0.28 ± 0.06 | 33080.03 ± 1123.74 |
| C: AR-EAURP (advancement) @ N=80 | 5 | 88.00 ± 5.39 | 0.25 ± 0.05 | 32492.42 ± 1952.84 |
| AODV (reference baseline) @ N=100 | 5 | 64.60 ± 11.08 | 0.25 ± 0.01 | 23852.34 ± 4045.73 |
| EAURP (base substrate) @ N=100 | 5 | 70.00 ± 11.94 | 0.31 ± 0.07 | 25908.19 ± 4365.27 |
| A: DRL-EAURP (paper) @ N=100 | 5 | 75.40 ± 6.80 | 0.40 ± 0.11 | 27885.86 ± 2431.58 |
| B: DRL-EAURP (senior) @ N=100 | 5 | 74.23 ± 8.51 | 0.29 ± 0.04 | 27448.06 ± 3083.48 |
| C: AR-EAURP (advancement) @ N=100 | 5 | 67.87 ± 11.27 | 0.26 ± 0.07 | 25089.18 ± 4112.41 |
| AODV (reference baseline) @ N=120 | 5 | 56.90 ± 18.69 | 0.36 ± 0.16 | 21015.57 ± 6915.42 |
| EAURP (base substrate) @ N=120 | 5 | 65.50 ± 19.00 | 0.29 ± 0.10 | 24207.65 ± 6917.94 |
| A: DRL-EAURP (paper) @ N=120 | 5 | 59.20 ± 19.86 | 0.28 ± 0.14 | 21868.96 ± 7269.89 |
| B: DRL-EAURP (senior) @ N=120 | 5 | 59.83 ± 19.34 | 0.33 ± 0.17 | 22168.42 ± 7095.11 |
| C: AR-EAURP (advancement) @ N=120 | 5 | 60.70 ± 19.30 | 0.39 ± 0.20 | 22446.27 ± 7069.64 |
| AODV (reference baseline) @ N=150 | 1 | 38.67 (n=1) | 0.32 (n=1) | 14312.80 (n=1) |
| EAURP (base substrate) @ N=150 | 1 | 39.83 (n=1) | 0.35 (n=1) | 14856.24 (n=1) |
| A: DRL-EAURP (paper) @ N=150 | 1 | 41.17 (n=1) | 0.32 (n=1) | 15351.44 (n=1) |
| B: DRL-EAURP (senior) @ N=150 | 1 | 41.67 (n=1) | 0.38 (n=1) | 15483.04 (n=1) |
| C: AR-EAURP (advancement) @ N=150 | 1 | 34.17 (n=1) | 0.22 (n=1) | 12717.20 (n=1) |
| AODV (reference baseline) @ N=200 | 1 | 28.50 (n=1) | 0.12 (n=1) | 10568.80 (n=1) |
| A: DRL-EAURP (paper) @ N=200 | 1 | 34.33 (n=1) | 0.16 (n=1) | 12732.72 (n=1) |
| B: DRL-EAURP (senior) @ N=200 | 1 | 32.50 (n=1) | 0.21 (n=1) | 12058.00 (n=1) |


## E3 — Attack prevalence by protocol

PDR cells show mean ± sample SD across five run numbers; the table keeps attack types and hostile-node percentages separate.

### Blackhole

| Hostile nodes | AODV | EAURP | DRL-EAURP (paper) | DRL-EAURP (senior) | AR-EAURP |
|---:|---:|---:|---:|---:|---:|
| 0% | 89.17 ± 5.34 | 87.07 ± 6.41 | 85.67 ± 8.71 | 92.20 ± 2.78 | 89.23 ± 4.73 |
| 10% | 44.80 ± 3.62 | 71.33 ± 15.58 | 71.67 ± 13.16 | 41.27 ± 10.03 | 63.67 ± 16.29 |
| 20% | 28.57 ± 9.14 | 45.80 ± 23.59 | 50.17 ± 14.74 | 34.93 ± 9.25 | 45.47 ± 18.08 |
| 30% | 30.37 ± 6.55 | 40.80 ± 15.61 | 38.40 ± 14.38 | 25.97 ± 9.38 | 38.47 ± 15.13 |
| 40% | 23.13 ± 8.54 | 30.33 ± 15.43 | 29.30 ± 15.53 | 24.20 ± 12.06 | 33.77 ± 10.16 |
| 50% | 24.80 ± 11.27 | 20.53 ± 9.06 | 25.07 ± 9.73 | 21.77 ± 11.73 | 21.83 ± 7.74 |

### Grayhole

| Hostile nodes | AODV | EAURP | DRL-EAURP (paper) | DRL-EAURP (senior) | AR-EAURP |
|---:|---:|---:|---:|---:|---:|
| 0% | 89.17 ± 5.34 | 87.07 ± 6.41 | 85.67 ± 8.71 | 92.20 ± 2.78 | 89.23 ± 4.73 |
| 10% | 87.10 ± 7.19 | 90.53 ± 5.05 | 89.50 ± 4.62 | 90.83 ± 4.44 | 87.43 ± 7.86 |
| 20% | 84.27 ± 5.43 | 80.70 ± 8.88 | 84.63 ± 5.76 | 89.30 ± 5.79 | 87.37 ± 6.72 |
| 30% | 83.67 ± 9.62 | 82.67 ± 2.84 | 82.60 ± 10.65 | 86.40 ± 6.85 | 83.90 ± 8.08 |
| 40% | 82.50 ± 7.31 | 83.33 ± 8.92 | 83.03 ± 5.88 | 85.23 ± 7.72 | 81.23 ± 4.75 |
| 50% | 81.13 ± 7.15 | 83.63 ± 9.21 | 75.10 ± 8.81 | 85.10 ± 5.73 | 80.17 ± 8.99 |

### Trust Poisoning

| Hostile nodes | AODV | EAURP | DRL-EAURP (paper) | DRL-EAURP (senior) | AR-EAURP |
|---:|---:|---:|---:|---:|---:|
| 0% | 89.17 ± 5.34 | 87.07 ± 6.41 | 85.67 ± 8.71 | 92.20 ± 2.78 | 89.23 ± 4.73 |
| 10% | 87.10 ± 7.19 | 83.53 ± 9.72 | 78.83 ± 11.29 | 90.83 ± 4.44 | 80.47 ± 8.18 |
| 20% | 84.27 ± 5.43 | 61.13 ± 14.01 | 78.47 ± 11.74 | 89.30 ± 5.79 | 72.20 ± 17.50 |
| 30% | 83.67 ± 9.62 | 56.90 ± 14.72 | 70.47 ± 10.84 | 86.40 ± 6.85 | 54.60 ± 12.97 |
| 40% | 82.50 ± 7.31 | 48.13 ± 12.71 | 57.83 ± 8.58 | 85.23 ± 7.72 | 58.00 ± 14.81 |
| 50% | 81.13 ± 7.15 | 48.50 ± 11.02 | 54.00 ± 7.28 | 85.10 ± 5.73 | 47.03 ± 14.20 |

### E3 detection and paired delivery analysis

EAURP and the two DRL-EAURP baselines do not use the AR GAN detector; their detector-specific fields are not comparable. AR detector values below are the project’s per-window metrics.

| Attack | Hostile nodes | AR window TPR | AR window FPR | AR score AUC | AR−EAURP PDR (pp) | Paired 95% CI (pp) | AR wins |
|---|---:|---:|---:|---:|---:|---:|---:|
| blackhole | 0% | 0.00 ± 0.00 | 5.51 ± 2.94 | 0.50 ± 0.00 | 2.17 | [-4.68, 9.02] | 4/5 |
| blackhole | 10% | 96.00 ± 8.94 | 6.63 ± 3.82 | 0.98 ± 0.02 | -7.67 | [-21.75, 6.41] | 2/5 |
| blackhole | 20% | 100.00 ± 0.00 | 7.26 ± 6.98 | 0.97 ± 0.03 | -0.33 | [-9.36, 8.69] | 2/5 |
| blackhole | 30% | 93.42 ± 8.17 | 10.97 ± 5.12 | 0.97 ± 0.04 | -2.33 | [-11.33, 6.66] | 2/5 |
| blackhole | 40% | 100.00 ± 0.00 | 13.69 ± 13.12 | 0.97 ± 0.06 | 3.43 | [-9.16, 16.03] | 2/5 |
| blackhole | 50% | 99.05 ± 2.13 | 12.29 ± 12.89 | 0.98 ± 0.05 | 1.30 | [-6.35, 8.95] | 2/5 |
| grayhole | 0% | 0.00 ± 0.00 | 5.51 ± 2.94 | 0.50 ± 0.00 | 2.17 | [-4.68, 9.02] | 4/5 |
| grayhole | 10% | 6.19 ± 8.52 | 5.89 ± 3.45 | 0.55 ± 0.15 | -3.10 | [-8.64, 2.44] | 1/5 |
| grayhole | 20% | 2.36 ± 3.24 | 3.26 ± 2.49 | 0.62 ± 0.11 | 6.67 | [-3.90, 17.24] | 4/5 |
| grayhole | 30% | 7.82 ± 4.98 | 5.24 ± 5.14 | 0.55 ± 0.07 | 1.23 | [-9.06, 11.53] | 2/5 |
| grayhole | 40% | 9.83 ± 5.31 | 4.04 ± 4.53 | 0.59 ± 0.12 | -2.10 | [-12.75, 8.55] | 2/5 |
| grayhole | 50% | 9.29 ± 5.79 | 3.94 ± 3.54 | 0.56 ± 0.11 | -3.47 | [-10.35, 3.42] | 1/5 |
| trust poisoning | 0% | 0.00 ± 0.00 | 5.51 ± 2.94 | 0.50 ± 0.00 | 2.17 | [-4.68, 9.02] | 4/5 |
| trust poisoning | 10% | 3.33 ± 7.45 | 7.40 ± 1.32 | 0.46 ± 0.17 | -3.07 | [-16.22, 10.09] | 3/5 |
| trust poisoning | 20% | 8.30 ± 6.04 | 7.64 ± 5.16 | 0.51 ± 0.03 | 11.07 | [1.35, 20.79] | 5/5 |
| trust poisoning | 30% | 12.31 ± 8.77 | 5.00 ± 4.06 | 0.51 ± 0.13 | -2.30 | [-14.62, 10.02] | 2/5 |
| trust poisoning | 40% | 10.94 ± 3.96 | 7.70 ± 2.95 | 0.49 ± 0.04 | 9.87 | [-1.37, 21.10] | 4/5 |
| trust poisoning | 50% | 10.17 ± 3.20 | 7.21 ± 5.36 | 0.39 ± 0.05 | -1.47 | [-21.89, 18.95] | 2/5 |

The paired interval is for AR-EAURP minus EAURP PDR within that attack/prevalence condition. A positive point estimate is not, by itself, evidence of superiority; inspect the interval and the five paired outcomes in the raw checkpoints.

## E4 — Energy mode

| Configuration | PDR | Residual energy (J) | Dead nodes |
|---|---|---|---|
| AODV / battery | 89.17 ± 5.34 | 6022.93 ± 2.25 | 0.00 ± 0.00 |
| AODV / solar | 89.17 ± 5.34 | 7640.87 ± 207.91 | 0.00 ± 0.00 |
| EAURP / battery | 88.83 ± 2.98 | 6021.79 ± 1.85 | 0.00 ± 0.00 |
| EAURP / solar | 87.07 ± 6.41 | 7640.65 ± 207.70 | 0.00 ± 0.00 |
| DRL-EAURP (paper) / battery | 82.93 ± 13.70 | 6021.05 ± 4.12 | 0.00 ± 0.00 |
| DRL-EAURP (paper) / solar | 85.67 ± 8.71 | 7638.78 ± 208.57 | 0.00 ± 0.00 |
| DRL-EAURP (senior) / battery | 89.10 ± 4.57 | 6021.75 ± 2.39 | 0.00 ± 0.00 |
| DRL-EAURP (senior) / solar | 92.20 ± 2.78 | 7639.39 ± 207.71 | 0.00 ± 0.00 |
| AR-EAURP / battery | 87.47 ± 4.41 | 6022.38 ± 2.18 | 0.00 ± 0.00 |
| AR-EAURP / solar | 89.23 ± 4.73 | 7639.45 ± 207.81 | 0.00 ± 0.00 |


## E4b — Network lifetime

| Configuration | First death (s) | 80% dead (s) | Residual energy (J) |
|---|---|---|---|
| AODV / battery | 422.65 ± 0.56 | 424.55 ± 0.15 | 0.00 ± 0.00 |
| AODV / solar | 432.10 ± 2.28 | censored / mixed | 1395.71 ± 166.72 |
| EAURP / battery | 423.30 ± 0.58 | 424.90 ± 0.20 | 0.00 ± 0.00 |
| EAURP / solar | 432.84 ± 1.55 | censored / mixed | 1370.50 ± 190.10 |
| DRL-EAURP (paper) / battery | 423.50 ± 0.38 | 424.98 ± 0.33 | 0.00 ± 0.00 |
| DRL-EAURP (paper) / solar | 432.20 ± 2.51 | censored / mixed | 1402.79 ± 212.21 |
| DRL-EAURP (senior) / battery | 422.89 ± 0.58 | 424.76 ± 0.11 | 0.00 ± 0.00 |
| DRL-EAURP (senior) / solar | 432.12 ± 2.34 | censored / mixed | 1394.65 ± 167.13 |
| AR-EAURP / battery | 423.60 ± 0.69 | 425.12 ± 0.34 | 0.00 ± 0.00 |
| AR-EAURP / solar | 432.79 ± 1.90 | censored / mixed | 1360.29 ± 212.01 |


## E5 — AR-EAURP component ablations

| Configuration | PDR | Window TPR | Window FPR | Score AUC |
|---|---|---|---|---|
| C full | 83.90 ± 8.08 | 7.82 ± 4.98 | 5.24 ± 5.14 | 0.55 ± 0.07 |
| C without GAN | 85.63 ± 8.04 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.50 ± 0.00 |
| C without LSTM | 83.97 ± 7.25 | 8.89 ± 8.43 | 5.92 ± 3.67 | 0.56 ± 0.03 |
| C without CMDP | 84.50 ± 7.35 | 6.77 ± 8.57 | 5.55 ± 5.21 | 0.60 ± 0.09 |
| C bare | 82.67 ± 2.84 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.50 ± 0.00 |
| C without energy excuse | 83.90 ± 8.08 | 7.82 ± 4.98 | 5.24 ± 5.14 | 0.55 ± 0.07 |


## E5b — CMDP PDR floor

| Configuration | PDR | Final CMDP λ | Peak CMDP λ |
|---|---|---|---|
| C floor=0.70 | 70.77 ± 20.20 | 0.43 ± 0.54 | 0.50 ± 0.50 |
| C floor=0.80 | 88.63 ± 4.07 | 0.70 ± 0.65 | 0.86 ± 0.54 |
| C floor=0.90 | 83.90 ± 8.08 | 1.69 ± 0.76 | 1.71 ± 0.72 |
| C floor=0.95 | 78.20 ± 12.22 | 2.33 ± 0.99 | 2.33 ± 0.99 |


## E6 — Security overhead

| Configuration | PDR | Crypto overhead (B) | Control bytes | Delay (s) |
|---|---|---|---|---|
| AODV | 83.67 ± 9.62 | 30856.00 ± 1620.25 | 180906.20 ± 13723.64 | 0.21 ± 0.14 |
| EAURP | 82.67 ± 2.84 | 30654.40 ± 494.74 | 224338.60 ± 10550.78 | 0.27 ± 0.08 |
| DRL-EAURP (paper) | 82.60 ± 10.65 | 30699.20 ± 1761.51 | 223893.80 ± 31384.10 | 0.23 ± 0.10 |
| DRL-EAURP (senior) | 86.40 ± 6.85 | 31326.40 ± 1143.28 | 206686.40 ± 14286.77 | 0.21 ± 0.06 |
| AR-EAURP | 83.90 ± 8.08 | 30906.40 ± 1355.82 | 218395.00 ± 14430.38 | 0.28 ± 0.14 |
| C without ECC | 84.03 ± 4.51 | 0.00 ± 0.00 | 230747.60 ± 24773.70 | 0.24 ± 0.16 |


## Interpretation and limits

1. E3 is the direct attack-prevalence comparison. Read the protocol rows at each attack and prevalence rather than collapsing all hostile fractions into one score.
2. PDR is application packets received divided by packets sent in the measured window, with arrivals through cooldown. Delay and throughput are also application-level metrics.
3. The planned design uses five run numbers per condition. The completion-status table reports the actual number used for each experiment; single-run conditions have no empirical SD or confidence interval and support descriptive observations only. Multiple comparisons across many cells are exploratory and no family-wise error correction is applied.
4. Pairing matches the configured ns-3 seed and run number across protocols. It does not force event-by-event identical random draws; protocol-specific event paths can consume random streams differently.
5. AR’s TPR/FPR/AUC are detector measurements. Baseline protocols do not implement that detector, so a zero/default baseline detector value must not be interpreted as perfect classification or compared as a detector score.
6. The lifetime experiment includes censored runs. Censored observations must not be treated as observed death times; the raw observed/censored flags are preserved in the CSV.
7. These simulations support claims only for the stated ns-3 models and factor ranges. They do not establish real-world wireless performance without calibration and independent replication.

## Visual comparisons

Error bars show sample standard deviation. In the density figure, open circles mark single-run conditions (n=1), which are descriptive only.

![paper_e3_blackhole_pdr](../results/ns3-native-paper-review/figures/paper_e3_blackhole_pdr.png)
![paper_e3_grayhole_pdr](../results/ns3-native-paper-review/figures/paper_e3_grayhole_pdr.png)
![paper_e3_trust_poisoning_pdr](../results/ns3-native-paper-review/figures/paper_e3_trust_poisoning_pdr.png)
![paper_e1_mobility](../results/ns3-native-paper-review/figures/paper_e1_mobility.png)
![paper_e2_density](../results/ns3-native-paper-review/figures/paper_e2_density.png)
![paper_e4_residual_energy](../results/ns3-native-paper-review/figures/paper_e4_residual_energy.png)
![paper_e5_ablation](../results/ns3-native-paper-review/figures/paper_e5_ablation.png)

## Files and provenance

- Completed 179 of 181 planned conditions and 863 of 905 planned ns-3 runs; per-experiment coverage is tabulated above.
- `study_settings.json`: complete configuration and factor-level manifest.
- `configuration_settings.csv`: full settings plus aggregate result for every condition.
- `run_settings.csv`: settings and raw checkpoint provenance for each completed individual run.
- `pairwise_e3_comparisons.csv`: all ten matched protocol-pair PDR contrasts across the 18 attack/prevalence conditions, with 95% intervals and per-run differences.
- `csv/`: aggregate condition-level results, including simulator-reported cfg_* settings and sample SDs.
- `raw/`: checksummed per-run metric checkpoints used for the paired E3 PDR analysis.
- `report.md`, `report.html`, and `figures/`: native experiment-runner tables, plot scripts, and rendered SVG/PNG figures.
- `paper_results.md`: this expanded paper-style summary.

## Separate CMDP commissioning study

### Question

Does training the CMDP route selector on clean commissioning traffic improve
AR-EAURP delivery under a grayhole attack, compared with EAURP?

### Experiment

- ns-3.45 native C++ simulation
- 24 nodes, 6 CBR flows, 25% grayhole nodes, 420 m square area
- 120 s simulation, 20 s warm-up, fixed seed 1
- Matched run numbers 21–50; each protocol uses the same run number
- AR-EAURP trains its detector/forecaster for 240 s on a separate clean
  commissioning network before evaluation
- The CMDP is now also trained on route outcomes during that clean phase
- EAURP runs without the AR models, as the baseline

### Result

| Measure | EAURP | AR-EAURP, CMDP trained in commissioning |
| --- | ---: | ---: |
| Mean PDR | 79.81% | 80.97% |
| Mean delay | 0.256 s | 0.288 s |
| Mean route discovery failures | 11.3 | 10.9 |
| AR detector window TPR | — | 4.69% |
| AR detector window FPR | — | 4.94% |
| AR detector window AUC | — | 0.586 |

The matched mean PDR difference is **+1.16 percentage points** for AR-EAURP.
AR-EAURP had higher PDR in 16 of 30 pairs. The paired 95% confidence interval
is **−2.97 to +5.30 percentage points**, so the experiment does not establish
that the true PDR difference is positive. Mean delay was 32 ms higher for
AR-EAURP (paired 95% CI **−21 to +84 ms**). Treat both as inconclusive results,
not proof of superiority.

EAURP has no comparable AR anomaly detector in this experiment. Its zero TPR
and FPR fields and AUC 0.5 are output defaults, not detector measurements.

### Files

- `cmdp_commissioning_holdout/`: matched runs 21–30, JSON and full logs
- `cmdp_commissioning_extended/`: matched runs 31–50, JSON and full logs
- `tuning/`: pre-fix exploratory runs 6–10, including the no-CMDP ablation
- `exploration_tuning/`: pre-fix epsilon-greedy and greedy CMDP ablations
- `holdout/`: pre-fix validation runs 11–20, including the greedy CMDP ablation

The older tuning and validation folders tested the original evaluation-only
CMDP. The commissioning-trained implementation was introduced afterward and
was evaluated on the separate run range 21–50 above. The current scripts run
the commissioning-trained implementation.

Each JSON file contains the scenario configuration and raw summary metrics;
the adjacent `.log` contains the native simulator output.

The earlier greedy CMDP candidate did not outperform EAURP on its 10 held-out
pairs (−2.80 PDR points, 4/10 wins). Disabling CMDP was also worse on those
pairs. Lowering exploration was worse on the tuning runs. These ablations are
why commissioning training was tested instead of selecting an epsilon setting
that only looked favorable on a small seed subset.

### Reproduction

From the project root in WSL, set `NS3_HOME` to the ns-3.45 checkout used for
this build, then run:

```bash
export NS3_HOME="$HOME/.cache/ar-eaurp/ns-3.45"
bash ns3/scripts/run_cmdp_commissioning_study.sh \
  results/optimization_study/reproduction 21 50
```

Build and verify with:

```bash
bash ns3/scripts/setup.sh
bash ns3/scripts/run.sh --verify=1
```

The native verification suite passed after the CMDP commissioning-training
change.


## All saved exploratory optimization groups

The following table inventories every saved JSON group in the optimization study. These exploratory groups include earlier code states and different run ranges, and must not be pooled into a single confirmatory comparison. The held-out commissioning estimate is the separately reported 30-pair result above.

| Folder / candidate | Saved runs | PDR mean ± SD (%) | Delay mean ± SD (s) |
|---|---:|---:|---:|
| cmdp commissioning extended / ar-commission-trained | 20 | 80.98 ± 8.48 | 0.290 ± 0.163 |
| cmdp commissioning extended / eaurp | 20 | 80.44 ± 6.70 | 0.252 ± 0.076 |
| cmdp commissioning holdout / ar-commission-trained | 10 | 80.93 ± 6.86 | 0.282 ± 0.138 |
| cmdp commissioning holdout / eaurp | 10 | 78.53 ± 10.72 | 0.264 ± 0.089 |
| exploration tuning / ar-greedy | 5 | 83.70 ± 10.06 | 0.255 ± 0.125 |
| exploration tuning / ar-low-exploration | 5 | 79.67 ± 9.66 | 0.287 ± 0.149 |
| holdout / ar-default | 10 | 80.65 ± 9.59 | 0.280 ± 0.060 |
| holdout / ar-greedy | 10 | 81.75 ± 8.80 | 0.283 ± 0.113 |
| holdout / ar-no-cmdp | 10 | 77.82 ± 10.25 | 0.313 ± 0.144 |
| holdout / eaurp | 10 | 84.55 ± 5.82 | 0.286 ± 0.112 |
| tuning / ar-default | 5 | 85.00 ± 5.34 | 0.234 ± 0.116 |
| tuning / ar-no-cmdp | 5 | 86.53 ± 11.30 | 0.286 ± 0.161 |
| tuning / eaurp | 5 | 81.13 ± 11.64 | 0.287 ± 0.131 |


## Earlier native five-run validation

This earlier snapshot used seed 1 and runs 1–5, 24 nodes, six flows, 420 m square, 25% gray-hole prevalence, a 120 s scenario duration with 20 s excluded warm-up (100 s measured), and 240 s AR commissioning. It is separate from the later E1–E6 review matrix and the 30-pair commissioning follow-up.

| Metric | EAURP | AR-EAURP |
|---|---:|---:|
| PDR, mean ± sample SD | 83.73% ± 4.23% | 81.83% ± 4.60% |
| Delay | 257 ± 86 ms | 292 ± 108 ms |
| Detector TPR | Not applicable | 6.79% ± 3.32% |
| Detector FPR | Not applicable | 5.83% ± 6.14% |
| Detector score AUC | Not applicable | 0.55 ± 0.08 |
| Two-witness contested TPR | Not applicable | 0% in all five runs |

The paired PDR difference was −1.90 percentage points, 95% CI −8.46 to +4.66: inconclusive. The LSTM lost to persistence in all five commissioning evaluations and was not selected for routing. Source: `results/final_review_ns3_results/FINAL_NS3_EVALUATION_REPORT.md` and its `native_long_runs` records.

## Historical Python / prior Colab-review result

These saved Python full-profile results concern the earlier simulator and workload. They are historical context and are not pooled with the current ns-3 results. The table lists the 30% gray-hole slice across five saved runs. Values are mean ± sample SD. The execution location is not established by a CSV; this is the Python result used for the prior Colab-review context.

| Protocol | PDR (%) | Detection TPR (%) | Detection FPR (%) |
|---|---:|---:|---:|
| AODV (reference baseline) | 46.47 ± 5.75 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| EAURP (base substrate) | 47.92 ± 5.24 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| A: DRL-EAURP (paper) | 45.96 ± 6.01 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| B: DRL-EAURP (senior code) | 46.41 ± 5.93 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| C: AR-EAURP (advancement) | 50.25 ± 5.86 | 29.33 ± 7.42 | 1.43 ± 0.90 |


AR-EAURP's historical PDR point estimate was 2.32 percentage points above EAURP. That observation motivated the native evaluation, but does not establish that the native implementation retains the benefit: implementations, radio/channel models, topology, traffic and detector observation processes differ.

## Automated verification and data audit

The native integration verification workflow had passed during the implementation work. The checks cover repeatability of simulated metrics; protected UDP delivery and authentication; delivery for the protocol variants; Q-learning updates; disconnected-flow feedback during cooldown; trained model/CMDP activity; energy shutdown/recharge; black-hole/gray-hole behavior; sample-standard-deviation arithmetic; invalid configuration rejection; matching checkpoint reuse; corrupted checkpoint recomputation; changed source/configuration identity rejection; CSV escaping; content hashing; and the E1–E6 smoke configuration inventory. These engineering checks verify implementation properties and do not establish comparative protocol superiority. They were not rerun during this document-formatting task.

The separate native unit-test source inventories the following cases. This inventory is not a claim of a fresh unit-suite execution during this editing session:


- control headers serialise and deserialise.

- the dense network learns XOR.

- the LSTM learns a periodic signal.

- a gray-hole evades the scalar trust threshold.

- forecast validation requires disjoint temporal windows per node.

- X25519 peers agree and authenticated payloads reject tampering.

- tabular feedback changes routes and endpoint trust uses endpoint counters.

- warmup packets do not inflate evaluation PDR.



The earlier report audit reconciled all 863 ledger-referenced checkpoint hashes, aggregate means/sample SDs and all 180 E3 paired differences. The condition and per-run ledgers preserve exact settings. The main report is a composite of verified checkpoints; the root manifest's original `e3,e4,e5,e6` selection does not exclude the separately aggregated E1 and partial E2 data.

## All 180 matched E3 protocol contrasts

Each row is PDR(A) minus PDR(B) in percentage points, using five paired run numbers. Intervals are two-sided Student t 95% intervals and are unadjusted across this exploratory family. Wins count A above B; ties are retained. Zero-hostile rows appearing under multiple attack labels share an underlying clean condition and must not be interpreted as separate independent confirmation.

For compact tables, DRL-paper denotes DRL-EAURP (paper), and DRL-senior denotes DRL-EAURP (senior).


### blackhole — 0% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +2.10 | [-2.72, +6.92] | 4 | 0 | 5 |
| AODV − DRL-paper | +3.50 | [-8.01, +15.01] | 3 | 0 | 5 |
| AODV − DRL-senior | -3.03 | [-6.74, +0.67] | 0 | 0 | 5 |
| AODV − AR-EAURP | -0.07 | [-3.12, +2.99] | 3 | 0 | 5 |
| EAURP − DRL-paper | +1.40 | [-13.14, +15.94] | 3 | 0 | 5 |
| EAURP − DRL-senior | -5.13 | [-11.30, +1.04] | 0 | 0 | 5 |
| EAURP − AR-EAURP | -2.17 | [-9.02, +4.68] | 1 | 0 | 5 |
| DRL-paper − DRL-senior | -6.53 | [-17.11, +4.04] | 1 | 0 | 5 |
| DRL-paper − AR-EAURP | -3.57 | [-15.67, +8.54] | 1 | 0 | 5 |
| DRL-senior − AR-EAURP | +2.97 | [-0.78, +6.71] | 4 | 0 | 5 |



### blackhole — 10% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | -26.53 | [-47.64, -5.42] | 1 | 0 | 5 |
| AODV − DRL-paper | -26.87 | [-45.40, -8.34] | 0 | 0 | 5 |
| AODV − DRL-senior | +3.53 | [-5.62, +12.68] | 3 | 0 | 5 |
| AODV − AR-EAURP | -18.87 | [-42.75, +5.02] | 1 | 0 | 5 |
| EAURP − DRL-paper | -0.33 | [-7.07, +6.41] | 3 | 0 | 5 |
| EAURP − DRL-senior | +30.07 | [+5.84, +54.29] | 5 | 0 | 5 |
| EAURP − AR-EAURP | +7.67 | [-6.41, +21.75] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | +30.40 | [+9.55, +51.25] | 5 | 0 | 5 |
| DRL-paper − AR-EAURP | +8.00 | [-2.93, +18.93] | 4 | 0 | 5 |
| DRL-senior − AR-EAURP | -22.40 | [-50.16, +5.36] | 0 | 0 | 5 |



### blackhole — 20% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | -17.23 | [-50.36, +15.90] | 1 | 0 | 5 |
| AODV − DRL-paper | -21.60 | [-45.06, +1.86] | 1 | 0 | 5 |
| AODV − DRL-senior | -6.37 | [-8.40, -4.33] | 0 | 0 | 5 |
| AODV − AR-EAURP | -16.90 | [-43.13, +9.33] | 1 | 0 | 5 |
| EAURP − DRL-paper | -4.37 | [-18.38, +9.65] | 3 | 0 | 5 |
| EAURP − DRL-senior | +10.87 | [-20.58, +42.32] | 4 | 0 | 5 |
| EAURP − AR-EAURP | +0.33 | [-8.69, +9.36] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | +15.23 | [-6.98, +37.44] | 4 | 0 | 5 |
| DRL-paper − AR-EAURP | +4.70 | [-1.83, +11.23] | 4 | 0 | 5 |
| DRL-senior − AR-EAURP | -10.53 | [-35.15, +14.09] | 1 | 0 | 5 |



### blackhole — 30% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | -10.43 | [-28.63, +7.77] | 1 | 0 | 5 |
| AODV − DRL-paper | -8.03 | [-25.89, +9.82] | 1 | 0 | 5 |
| AODV − DRL-senior | +4.40 | [-5.57, +14.37] | 3 | 0 | 5 |
| AODV − AR-EAURP | -8.10 | [-25.26, +9.06] | 1 | 0 | 5 |
| EAURP − DRL-paper | +2.40 | [-4.29, +9.09] | 4 | 0 | 5 |
| EAURP − DRL-senior | +14.83 | [-11.77, +41.44] | 4 | 0 | 5 |
| EAURP − AR-EAURP | +2.33 | [-6.66, +11.33] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | +12.43 | [-11.83, +36.70] | 4 | 0 | 5 |
| DRL-paper − AR-EAURP | -0.07 | [-4.68, +4.55] | 2 | 2 | 5 |
| DRL-senior − AR-EAURP | -12.50 | [-35.45, +10.45] | 1 | 0 | 5 |



### blackhole — 40% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | -7.20 | [-21.37, +6.97] | 1 | 0 | 5 |
| AODV − DRL-paper | -6.17 | [-21.99, +9.65] | 1 | 0 | 5 |
| AODV − DRL-senior | -1.07 | [-8.06, +5.93] | 2 | 0 | 5 |
| AODV − AR-EAURP | -10.63 | [-18.34, -2.93] | 0 | 0 | 5 |
| EAURP − DRL-paper | +1.03 | [-6.98, +9.05] | 3 | 0 | 5 |
| EAURP − DRL-senior | +6.13 | [-7.80, +20.07] | 4 | 0 | 5 |
| EAURP − AR-EAURP | -3.43 | [-16.03, +9.16] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | +5.10 | [-12.96, +23.16] | 3 | 0 | 5 |
| DRL-paper − AR-EAURP | -4.47 | [-15.80, +6.86] | 1 | 0 | 5 |
| DRL-senior − AR-EAURP | -9.57 | [-23.12, +3.99] | 0 | 0 | 5 |



### blackhole — 50% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +4.27 | [-7.64, +16.17] | 3 | 0 | 5 |
| AODV − DRL-paper | -0.27 | [-16.46, +15.92] | 3 | 0 | 5 |
| AODV − DRL-senior | +3.03 | [-6.16, +12.23] | 3 | 0 | 5 |
| AODV − AR-EAURP | +2.97 | [-8.23, +14.16] | 4 | 0 | 5 |
| EAURP − DRL-paper | -4.53 | [-9.38, +0.32] | 1 | 0 | 5 |
| EAURP − DRL-senior | -1.23 | [-11.16, +8.69] | 1 | 0 | 5 |
| EAURP − AR-EAURP | -1.30 | [-8.95, +6.35] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | +3.30 | [-8.93, +15.53] | 3 | 0 | 5 |
| DRL-paper − AR-EAURP | +3.23 | [-7.94, +14.41] | 4 | 0 | 5 |
| DRL-senior − AR-EAURP | -0.07 | [-14.64, +14.51] | 3 | 0 | 5 |



### grayhole — 0% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +2.10 | [-2.72, +6.92] | 4 | 0 | 5 |
| AODV − DRL-paper | +3.50 | [-8.01, +15.01] | 3 | 0 | 5 |
| AODV − DRL-senior | -3.03 | [-6.74, +0.67] | 0 | 0 | 5 |
| AODV − AR-EAURP | -0.07 | [-3.12, +2.99] | 3 | 0 | 5 |
| EAURP − DRL-paper | +1.40 | [-13.14, +15.94] | 3 | 0 | 5 |
| EAURP − DRL-senior | -5.13 | [-11.30, +1.04] | 0 | 0 | 5 |
| EAURP − AR-EAURP | -2.17 | [-9.02, +4.68] | 1 | 0 | 5 |
| DRL-paper − DRL-senior | -6.53 | [-17.11, +4.04] | 1 | 0 | 5 |
| DRL-paper − AR-EAURP | -3.57 | [-15.67, +8.54] | 1 | 0 | 5 |
| DRL-senior − AR-EAURP | +2.97 | [-0.78, +6.71] | 4 | 0 | 5 |



### grayhole — 10% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | -3.43 | [-6.99, +0.13] | 0 | 0 | 5 |
| AODV − DRL-paper | -2.40 | [-8.19, +3.39] | 2 | 0 | 5 |
| AODV − DRL-senior | -3.73 | [-8.61, +1.14] | 1 | 0 | 5 |
| AODV − AR-EAURP | -0.33 | [-4.73, +4.07] | 2 | 0 | 5 |
| EAURP − DRL-paper | +1.03 | [-2.07, +4.13] | 3 | 0 | 5 |
| EAURP − DRL-senior | -0.30 | [-4.15, +3.55] | 2 | 0 | 5 |
| EAURP − AR-EAURP | +3.10 | [-2.44, +8.64] | 3 | 1 | 5 |
| DRL-paper − DRL-senior | -1.33 | [-6.43, +3.76] | 2 | 0 | 5 |
| DRL-paper − AR-EAURP | +2.07 | [-3.75, +7.88] | 3 | 0 | 5 |
| DRL-senior − AR-EAURP | +3.40 | [-4.29, +11.09] | 3 | 0 | 5 |



### grayhole — 20% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +3.57 | [-5.73, +12.86] | 3 | 0 | 5 |
| AODV − DRL-paper | -0.37 | [-10.79, +10.06] | 2 | 0 | 5 |
| AODV − DRL-senior | -5.03 | [-10.11, +0.04] | 1 | 0 | 5 |
| AODV − AR-EAURP | -3.10 | [-7.01, +0.81] | 1 | 0 | 5 |
| EAURP − DRL-paper | -3.93 | [-20.25, +12.39] | 1 | 0 | 5 |
| EAURP − DRL-senior | -8.60 | [-21.21, +4.01] | 2 | 0 | 5 |
| EAURP − AR-EAURP | -6.67 | [-17.24, +3.90] | 1 | 0 | 5 |
| DRL-paper − DRL-senior | -4.67 | [-15.99, +6.66] | 1 | 0 | 5 |
| DRL-paper − AR-EAURP | -2.73 | [-13.41, +7.94] | 2 | 0 | 5 |
| DRL-senior − AR-EAURP | +1.93 | [-4.17, +8.04] | 3 | 0 | 5 |



### grayhole — 30% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +1.00 | [-9.59, +11.59] | 3 | 0 | 5 |
| AODV − DRL-paper | +1.07 | [-17.17, +19.30] | 1 | 0 | 5 |
| AODV − DRL-senior | -2.73 | [-8.01, +2.54] | 1 | 0 | 5 |
| AODV − AR-EAURP | -0.23 | [-8.35, +7.89] | 2 | 0 | 5 |
| EAURP − DRL-paper | +0.07 | [-16.08, +16.21] | 2 | 0 | 5 |
| EAURP − DRL-senior | -3.73 | [-12.01, +4.55] | 1 | 0 | 5 |
| EAURP − AR-EAURP | -1.23 | [-11.53, +9.06] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | -3.80 | [-17.57, +9.97] | 3 | 0 | 5 |
| DRL-paper − AR-EAURP | -1.30 | [-13.37, +10.77] | 3 | 0 | 5 |
| DRL-senior − AR-EAURP | +2.50 | [-3.66, +8.66] | 3 | 0 | 5 |



### grayhole — 40% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | -0.83 | [-5.62, +3.95] | 2 | 0 | 5 |
| AODV − DRL-paper | -0.53 | [-13.73, +12.66] | 2 | 0 | 5 |
| AODV − DRL-senior | -2.73 | [-6.67, +1.21] | 1 | 0 | 5 |
| AODV − AR-EAURP | +1.27 | [-7.54, +10.08] | 2 | 0 | 5 |
| EAURP − DRL-paper | +0.30 | [-14.70, +15.30] | 2 | 0 | 5 |
| EAURP − DRL-senior | -1.90 | [-8.28, +4.48] | 2 | 0 | 5 |
| EAURP − AR-EAURP | +2.10 | [-8.55, +12.75] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | -2.20 | [-14.40, +10.00] | 3 | 0 | 5 |
| DRL-paper − AR-EAURP | +1.80 | [-3.21, +6.81] | 3 | 0 | 5 |
| DRL-senior − AR-EAURP | +4.00 | [-4.63, +12.63] | 3 | 0 | 5 |



### grayhole — 50% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | -2.50 | [-5.75, +0.75] | 1 | 0 | 5 |
| AODV − DRL-paper | +6.03 | [+0.44, +11.63] | 5 | 0 | 5 |
| AODV − DRL-senior | -3.97 | [-7.86, -0.08] | 1 | 0 | 5 |
| AODV − AR-EAURP | +0.97 | [-4.49, +6.43] | 3 | 0 | 5 |
| EAURP − DRL-paper | +8.53 | [+2.98, +14.09] | 5 | 0 | 5 |
| EAURP − DRL-senior | -1.47 | [-7.62, +4.68] | 1 | 0 | 5 |
| EAURP − AR-EAURP | +3.47 | [-3.42, +10.35] | 4 | 0 | 5 |
| DRL-paper − DRL-senior | -10.00 | [-18.82, -1.18] | 0 | 0 | 5 |
| DRL-paper − AR-EAURP | -5.07 | [-15.55, +5.42] | 1 | 1 | 5 |
| DRL-senior − AR-EAURP | +4.93 | [+0.48, +9.39] | 5 | 0 | 5 |



### trust poisoning — 0% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +2.10 | [-2.72, +6.92] | 4 | 0 | 5 |
| AODV − DRL-paper | +3.50 | [-8.01, +15.01] | 3 | 0 | 5 |
| AODV − DRL-senior | -3.03 | [-6.74, +0.67] | 0 | 0 | 5 |
| AODV − AR-EAURP | -0.07 | [-3.12, +2.99] | 3 | 0 | 5 |
| EAURP − DRL-paper | +1.40 | [-13.14, +15.94] | 3 | 0 | 5 |
| EAURP − DRL-senior | -5.13 | [-11.30, +1.04] | 0 | 0 | 5 |
| EAURP − AR-EAURP | -2.17 | [-9.02, +4.68] | 1 | 0 | 5 |
| DRL-paper − DRL-senior | -6.53 | [-17.11, +4.04] | 1 | 0 | 5 |
| DRL-paper − AR-EAURP | -3.57 | [-15.67, +8.54] | 1 | 0 | 5 |
| DRL-senior − AR-EAURP | +2.97 | [-0.78, +6.71] | 4 | 0 | 5 |



### trust poisoning — 10% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +3.57 | [-8.87, +16.00] | 2 | 0 | 5 |
| AODV − DRL-paper | +8.27 | [-8.85, +25.38] | 4 | 0 | 5 |
| AODV − DRL-senior | -3.73 | [-8.61, +1.14] | 1 | 0 | 5 |
| AODV − AR-EAURP | +6.63 | [-1.56, +14.82] | 4 | 0 | 5 |
| EAURP − DRL-paper | +4.70 | [-6.41, +15.81] | 3 | 0 | 5 |
| EAURP − DRL-senior | -7.30 | [-17.25, +2.65] | 0 | 0 | 5 |
| EAURP − AR-EAURP | +3.07 | [-10.09, +16.22] | 2 | 0 | 5 |
| DRL-paper − DRL-senior | -12.00 | [-26.92, +2.92] | 0 | 0 | 5 |
| DRL-paper − AR-EAURP | -1.63 | [-21.59, +18.32] | 3 | 0 | 5 |
| DRL-senior − AR-EAURP | +10.37 | [+1.70, +19.03] | 4 | 0 | 5 |



### trust poisoning — 20% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +23.13 | [+1.80, +44.46] | 5 | 0 | 5 |
| AODV − DRL-paper | +5.80 | [-8.98, +20.58] | 3 | 0 | 5 |
| AODV − DRL-senior | -5.03 | [-10.11, +0.04] | 1 | 0 | 5 |
| AODV − AR-EAURP | +12.07 | [-11.35, +35.48] | 3 | 0 | 5 |
| EAURP − DRL-paper | -17.33 | [-34.79, +0.12] | 1 | 0 | 5 |
| EAURP − DRL-senior | -28.17 | [-50.05, -6.28] | 0 | 0 | 5 |
| EAURP − AR-EAURP | -11.07 | [-20.79, -1.35] | 0 | 0 | 5 |
| DRL-paper − DRL-senior | -10.83 | [-26.86, +5.19] | 1 | 0 | 5 |
| DRL-paper − AR-EAURP | +6.27 | [-11.56, +24.09] | 4 | 0 | 5 |
| DRL-senior − AR-EAURP | +17.10 | [-6.36, +40.56] | 5 | 0 | 5 |



### trust poisoning — 30% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +26.77 | [+3.94, +49.59] | 5 | 0 | 5 |
| AODV − DRL-paper | +13.20 | [+3.61, +22.79] | 5 | 0 | 5 |
| AODV − DRL-senior | -2.73 | [-8.01, +2.54] | 1 | 0 | 5 |
| AODV − AR-EAURP | +29.07 | [+9.83, +48.30] | 5 | 0 | 5 |
| EAURP − DRL-paper | -13.57 | [-39.00, +11.86] | 2 | 0 | 5 |
| EAURP − DRL-senior | -29.50 | [-50.27, -8.73] | 0 | 0 | 5 |
| EAURP − AR-EAURP | +2.30 | [-10.02, +14.62] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | -15.93 | [-23.89, -7.97] | 0 | 0 | 5 |
| DRL-paper − AR-EAURP | +15.87 | [-3.39, +35.12] | 4 | 0 | 5 |
| DRL-senior − AR-EAURP | +31.80 | [+13.80, +49.80] | 5 | 0 | 5 |



### trust poisoning — 40% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +34.37 | [+15.60, +53.13] | 5 | 0 | 5 |
| AODV − DRL-paper | +24.67 | [+6.87, +42.46] | 5 | 0 | 5 |
| AODV − DRL-senior | -2.73 | [-6.67, +1.21] | 1 | 0 | 5 |
| AODV − AR-EAURP | +24.50 | [+1.60, +47.40] | 5 | 0 | 5 |
| EAURP − DRL-paper | -9.70 | [-24.89, +5.49] | 2 | 0 | 5 |
| EAURP − DRL-senior | -37.10 | [-55.07, -19.13] | 0 | 0 | 5 |
| EAURP − AR-EAURP | -9.87 | [-21.10, +1.37] | 1 | 0 | 5 |
| DRL-paper − DRL-senior | -27.40 | [-43.58, -11.22] | 0 | 0 | 5 |
| DRL-paper − AR-EAURP | -0.17 | [-14.74, +14.40] | 4 | 0 | 5 |
| DRL-senior − AR-EAURP | +27.23 | [+6.21, +48.26] | 5 | 0 | 5 |



### trust poisoning — 50% hostile


| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |
|---|---:|---:|---:|---:|---:|
| AODV − EAURP | +32.63 | [+16.26, +49.01] | 5 | 0 | 5 |
| AODV − DRL-paper | +27.13 | [+14.14, +40.12] | 5 | 0 | 5 |
| AODV − DRL-senior | -3.97 | [-7.86, -0.08] | 1 | 0 | 5 |
| AODV − AR-EAURP | +34.10 | [+18.00, +50.20] | 5 | 0 | 5 |
| EAURP − DRL-paper | -5.50 | [-21.45, +10.45] | 2 | 0 | 5 |
| EAURP − DRL-senior | -36.60 | [-53.91, -19.29] | 0 | 0 | 5 |
| EAURP − AR-EAURP | +1.47 | [-18.95, +21.89] | 3 | 0 | 5 |
| DRL-paper − DRL-senior | -31.10 | [-42.08, -20.12] | 0 | 0 | 5 |
| DRL-paper − AR-EAURP | +6.97 | [-3.77, +17.71] | 4 | 0 | 5 |
| DRL-senior − AR-EAURP | +38.07 | [+22.15, +53.98] | 5 | 0 | 5 |




## Consolidated findings and remaining work

1. The native attack matrix and 30-pair follow-up do not establish a reliable overall PDR advantage for AR-EAURP over EAURP.
2. Native gray-hole detection is weak in the selected workload; per-window TPR/FPR/AUC differ from consensus and revocation outcomes.
3. One of 18 AR-EAURP–EAURP attack/prevalence intervals excludes zero before multiplicity correction; it is exploratory evidence requiring confirmation.
4. E2 density is incomplete. The 42 deferred runs are absent; high-density n=1 points do not provide empirical SDs or confidence intervals.
5. Harvesting increases modeled residual energy and changes lifetime endpoints, some of which are censored. It does not directly validate field battery life.
6. Component ablations and CMDP-floor tests show trade-offs, rather than a uniform benefit from every added component.
7. Earlier Python results and native ns-3 outcomes are distinct experiments. Their raw PDR values should not be treated as a direct controlled cross-simulator treatment effect.
8. Next priorities are completing E2, improving detector validation, testing simpler baselines, defining a feasible delivery constraint, and running a confirmatory study with adequate power and planned multiplicity control.

## Experiment-by-experiment findings and qualified conclusions

### E1: mobility

The five speed levels do not produce a monotonic PDR curve. AR peaks at 94.10% at 5 m/s but is lower than EAURP at 1, 5, 10, and 15 m/s in the descriptive means. At 20 m/s AR is 89.23% versus EAURP 87.07%, while DRL-S is 92.20%. This does not support a universal AR mobility advantage. Between-run variation is large enough that mean rankings should not be treated as deterministic. Delay must be considered alongside delivery because it excludes lost packets.

### E2: density and incomplete high-density evidence

AR exceeds EAURP descriptively at 60 and 80 nodes, then falls below it at 100 and 120. At 120 nodes the SD is around nineteen percentage points for both. The n=1 high-density cells cannot support a stability or superiority claim. Density is varied at fixed area and six-flow workload, so neighbor count, contention, control traffic, connectivity, and traffic-per-node effects change together. The current data do not isolate a single cause for degradation. Forty-two missing runs are a coverage limitation rather than negative results.

### E3: attacks and policy dependence

Black holes reduce delivery sharply for every policy. At 30% hostile nodes, AR's 38.47% PDR is below EAURP's 40.80%, despite AR window TPR 93.42%. Local detection is therefore not equivalent to successful end-to-end mitigation. Gray holes are less destructive because selective packet eligibility and a 0.25 drop probability affect only part of relayed traffic. At 30%, AR's +1.23-point matched difference has CI [−9.06,+11.53], and DRL-S has the highest descriptive PDR among the five variants. Trust poisoning is particularly harmful to report-sensitive policies. The AODV-style and DRL-S aggregate PDR values match their gray-hole values in this study; this is an outcome under the implemented report-use semantics, not generic immunity to reputation attacks.

Only the 20% trust-poisoning AR–EAURP interval excludes zero before adjustment: +11.07 points, CI [+1.35,+20.79], five wins in five pairs. This is exploratory evidence within a multiple-comparison family. The negative 10% black-hole estimate (−7.67 points) and negative estimates at several gray-hole percentages must be retained. The study cannot be summarized as a consistent AR improvement.

### Detection layers and forecast quality

For 30% gray holes, AR window TPR/FPR/AUC are 7.82%/5.24%/0.55. Corroborated contested TPR is 0%, contested FPR 1.18%, revocation TPR 14.29%, and revocation FPR 11.76% as run means. Different state definitions, denominators, and ordinary trust exclusions explain why these are not interchangeable detector accuracy statistics. The same condition has LSTM MAE 0.495 ± 0.409 W, persistence 0.057 ± 0.013 W, and window-mean 0.095 ± 0.028 W. Persistence was selected in all five runs. An LSTM benefit must not be inferred from a fallback-equipped implementation in which the neural predictor lost validation.

### E4/E4b: modeled energy and censored lifetime

AR total residual energy rises from 6,022.38 J to 7,639.45 J with harvesting in the short experiment. Added environmental energy is a direct input, so the gain is not solely a routing-efficiency effect. All policies have zero deaths in that short horizon. Over 900 s, AR first death is 423.60 s battery-only versus 432.79 s with harvesting. For every harvested policy, the mean eighty_pct_death_observed flag is zero across five runs: none reaches the endpoint before the horizon. The generic saved-table phrase censored/mixed is therefore right-censored in all five harvested runs per policy. Battery-only endpoints are observed. No sentinel or horizon value is used as an exact harvested death time, and no full Kaplan–Meier or hazard-ratio analysis is claimed.

### E5/E5b: ablations and constrained learning

Full AR does not dominate its component removals. Without GAN, PDR is 85.63% versus full 83.90%; without CMDP it is 84.50%. No-energy-excuse endpoints match the full configuration here. Component removal changes route and observation distributions, so the effects are not independent contributions. No-detector TPR/FPR zeros and AUC 0.5 are defaults. A delivery target of 0.80 yields the highest descriptive floor-sweep PDR, while larger lambda at 0.90/0.95 does not ensure target satisfaction. Selecting the favorable target after looking at this sweep would require a new reserved evaluation cohort.

### E6: protection and control accounting

AR has about 218.4 kB of control traffic and 30.9 kB of cryptographic overhead under the selected attack. Removing payload protection sets cryptographic overhead to zero and gives 84.03% PDR versus full 83.90%, with considerable variation. Differences in packet size can change radio events, routes, and observations, so delay differences are not isolated cryptographic CPU benchmarks. Payload protection is X25519/HKDF/AES-GCM; the experiment does not validate every routing control message as authenticated or establish formal anonymity.

### Commissioning follow-up and historical consistency

The thirty-pair comparison gives AR +1.16 PDR points, CI [−2.97,+5.30], and 16/30 wins. This is a modest positive point estimate with an inconclusive interval. Its +32 ms delay difference also spans zero. Exploratory greedy and low-exploration candidates are retained below because excluding unsuccessful tuning would overstate the evidence. The earlier native five-run snapshot and earlier Python comparison differ in configuration and code state; neither is a clean causal before/after experiment. The Python +2.32-point gray-hole estimate motivates the investigation but does not override current native findings.

## Evidence-to-claim audit

| Candidate statement | Assessment and supported wording |
|---|---|
| AR is generally better than EAURP | Not established; report condition-specific estimates and intervals |
| The native simulation is more realistic than a single-probability model | It explicitly adds radio, packet, route, queue, energy, and observation mechanisms; field validity still needs calibration |
| Gray-hole detection is accurate | Not supported for this workload; native window TPR is low and AUC near chance |
| The LSTM improved routing | Not supported in the selected condition; persistence was selected in all five runs |
| Harvesting improves energy availability | Supported within the synthetic energy process; not a field battery-lifetime guarantee |
| Higher PDR floor guarantees delivery | Not supported; lambda reacts but measured PDR is nonmonotonic |
| All tests are complete | Incorrect; 863/905 runs and 179/181 conditions are included |
| Five independent master seeds were used | Incorrect; one review seed with five RngRun streams |
| All 180 contrasts prove a ranking | Incorrect; unadjusted exploratory contrasts, with repeated clean settings |
| Replay proves the protocol works in real time | Incorrect; replay visualizes a recorded run; JSON/CSV and repeatable experiments support quantitative claims |

## Limitations and prioritized next experiments

The main limitations are incomplete density replication, a small per-condition sample, unadjusted multiple comparisons, shared fleet learning, reused clean threshold-calibration data, continuing evaluation-time exploration, a synthetic harvesting process, and adapted rather than independently reproduced baseline implementations. No additional outcome is inferred from missing data or from visual appearance of a trace.

First complete the existing E2 plan without changing its original settings or silently replacing included checkpoints. Next reserve clean calibration and attack evaluation cohorts, compare simple size-conditioned thresholds and nonlearning routes, and measure whether sufficient forwarding evidence is available before optimizing neural capacity. For forecasting, retain persistence and test a longer, physically calibrated trace before attributing value to an LSTM. For routing, distinguish frozen evaluation from online adaptation and test a decentralized parameter-sharing alternative. Finally define a practical effect size, plan sample size and multiple-comparison control, and evaluate on independent settings. These are proposed experiments, not completed evidence.

## Reproducibility, file inventory, and trace provenance

| Artifact | Repository-relative location and purpose |
|---|---|
| Native routing and learning | ns3/contrib/ar-eaurp/model; actual C++ packet and model logic |
| Native unit-test source | ns3/contrib/ar-eaurp/test/ar-eaurp-test-suite.cc |
| Study settings | results/ns3-native-paper-review/study_settings.json |
| Condition settings | results/ns3-native-paper-review/configuration_settings.csv |
| Run settings and checkpoint hashes | results/ns3-native-paper-review/run_settings.csv |
| All E1–E6 aggregate outcomes | results/ns3-native-paper-review/csv |
| AR–EAURP paired estimates | results/ns3-native-paper-review/paired_e3_summary.json |
| All 180 E3 contrasts | results/ns3-native-paper-review/pairwise_e3_comparisons.csv |
| Commissioning follow-up and unsuccessful tuning | results/optimization_study; per-run JSON and logs |
| Earlier native comparison | results/final_review_ns3_results/FINAL_NS3_EVALUATION_REPORT.md |
| Earlier Python aggregate outcomes | output/full_results/csv |
| Presentation traces | results/ns3-live; inspect each run's XML together with its result.json |

Trace XML is created by native ns-3 animation instrumentation while the original simulation executes. It records node positions and packet events. Uploading an XML file replays those recorded events with the parameters already used. Changing a live-run form does not change the saved trace. A replay control can make a demonstration easier without recreating a simulation, but results must remain attached to their original settings. The XML is useful for explanation; the saved JSON, raw checkpoints, hashes, and ledgers supply the numerical evidence.

To reproduce the main matrix from the project root in WSL:

```bash
bash ns3/scripts/run.sh --profile=review --only=e1,e2,e3,e4,e5,e6 --out=results/ns3-native-paper-review --render=0
```

To reproduce the separate commissioning comparison:

```bash
export NS3_HOME="$HOME/.cache/ar-eaurp/ns-3.45"
bash ns3/scripts/run_cmdp_commissioning_study.sh results/optimization_study/reproduction 21 50
```

These commands are instructions, not evidence of new execution during this revision. Exact checkpoint identity and source matching control resumability. A future completed matrix must state its new coverage and revision rather than relabeling the current partial report as complete.
