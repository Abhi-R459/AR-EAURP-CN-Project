# Final review walkthrough: Colab to native ns-3

## Before the professor arrives

1. On this Windows laptop, open Ubuntu/WSL and go to the project:

   ```bash
   cd /mnt/c/dev/AR-EAURP-CN-Project
   export NS3_HOME="$HOME/.cache/ar-eaurp/ns-3.45"
   test -x "$NS3_HOME/build/scratch/ns3.45-ar-eaurp-sim-optimized" && echo 'Simulator ready'
   ```

   If the binary is absent, install the Ubuntu build dependencies listed in the root `README.md`, then run `bash ns3/scripts/setup.sh --download`. This is a one-time preparation step, not part of the live presentation.

2. In that WSL terminal, start the local server and leave the terminal open:

   ```bash
   python3 ns3/netanim/live_server.py --ns3-home "$NS3_HOME" --port 8767
   ```

3. In a Windows browser, open **http://127.0.0.1:8767/**. Keep a second tab with `results/final_review_ns3_results/FINAL_NS3_EVALUATION_REPORT.html`. Check that the projector shows the whole screen. The server is local to this laptop; no internet is needed after setup.

4. Keep the saved native files ready as a backup: `results/final_review_ns3_results/native_demo/eaurp.json`, `ar-eaurp.json`, and `results/ns3-live/final-demo/eaurp.xml`, `ar-eaurp.xml`. The XML traces were generated on this laptop and are ignored by Git; copy them with the project if presenting elsewhere.

## Suggested 8–10 minute speaking order

### 1. Connect the three reviews (one minute)

> In Review 1 we explained the MANET routing problem, malicious forwarding and energy constraints, and proposed AR-EAURP. In Review 2 we evaluated the idea with Colab experiments. Today I am showing how the routing implementation behaves in a native ns-3.45 Wi-Fi simulation, along with the exact output files behind the animation and metrics.

Show the architecture from the root `README.md`: native `ar-eaurp-sim` C++ scenario, routing protocol, traffic applications, detector/forecaster/CMDP, and experiment runner. The Flutter app is a separate messaging artifact, not the measured ns-3 routing experiment.

### 2. Explain where the data comes from (one minute)

> The C++ scenario creates moving wireless nodes, assigns IP addresses, starts UDP traffic, marks hostile relays, and executes the selected routing policy. ns-3 schedules the radio and application events. The scenario writes two outputs: NetAnim XML for positions and received wireless frames, and JSON for application packet delivery, delay and security counters. The local Python server only launches the compiled simulator and forwards those outputs to the browser.

Point to `ns3/contrib/ar-eaurp/model/ar-eaurp-scenario.cc`, `ns3/netanim/live_server.py`, and the saved `result.json`/`trace.xml`. For a live run, open its `launch.json` to show the exact binary arguments. Explain that **wireless receptions are not application deliveries**: a broadcast can create many receptions, while PDR is `app_rx / app_tx` in JSON.

### 3. Run the predecessor live (about 20 seconds plus explanation)

In the viewer select **EAURP**, **Grayhole**, **24 nodes**, **6 flows**, **0.25 hostile fraction**, **8 seconds**, and keep **Pace evaluation to wall time** checked. Click **Start ns-3 run**. Let it reach **Run complete · trace saved**. The visible animation also includes a 10-second cooldown for packets already in flight, so the trace ends near 18 simulated seconds.

> The colored points are recorded node positions. Red marks configured hostile nodes. The lines are actual wireless frame receptions, not invented paths. The top PDR and delay are application measurements; the complete saved JSON is the source of truth.

Click one node to show its role, IP, energy and recorded counters. After the run, point to the saved path under `results/ns3-live/<timestamp>/`, and show `launch.json`, `trace.xml`, `result.json`.

### 4. Run our protocol with the same visible settings

Select **AR-EAURP** and keep **Train models before AR-EAURP evaluation** checked. Do not change nodes, flows, attack, hostile fraction or duration. Click **Start ns-3 run**. The viewer first says **Commissioning models**. That is a separate clean run used to train the GAN and LSTM; the attack is introduced only in the evaluation that follows. The evaluation is then paced to wall time, subject to CPU load.

> We hold the evaluation scenario fixed and change the routing protocol. AR-EAURP performs clean commissioning first. The table below the run controls retains both native result JSON files. Its settings line warns if recorded conditions differ.

The live server uses seed 1, run 1, area 420 m, and the same settings for both runs. It uses the simulator's default full commissioning budget for AR-EAURP; therefore its result may differ from the prepared short-budget backup example below. Read the values on screen, not a memorized percentage.

### 5. Compare and interpret honestly (two minutes)

Scroll to **Measured protocol comparison**. Compare application sent/received, PDR, delay, control packets, GAN window TPR/FPR, contested consensus, training status and CMDP decisions. Do not use the number of wireless receptions as PDR. A run with no qualifying detector windows is **unmeasured**, not zero detection.

If asked about additional predecessors, the same viewer can also run the common-substrate `aodv`, `drl-paper` and `drl-senior` variants with matched settings. Focus the timed presentation on EAURP versus AR-EAURP, the direct predecessor comparison. `ns3-aodv` is the upstream implementation and is supported here only for clean runs, so do not select it for the grayhole comparison.

For the performance comparison, load the ten JSON files in `results/final_review_ns3_results/native_long_runs/` together in the viewer, or present the summary CSV and report. They contain five matched EAURP/AR-EAURP runs: 24 nodes, six flows, 25% grayhole nodes and 120 measured seconds per run. Mean PDR was **83.73% for EAURP** and **81.83% for AR-EAURP**. The mean paired difference was **-1.90 percentage points**, with a 95% interval from **-8.46 to +4.66 points**. So the ns-3 sample is inconclusive and does not support saying AR-EAURP performed better.

In these five runs, the GAN detector's average window-level TPR was **6.79%**, its FPR was **5.83%**, and mean score AUC was **0.55**. The two-honest-witness contested TPR was zero. The LSTM's mean holdout MAE was **0.60 W**, compared with **0.06 W** for persistence, so the updated implementation selected persistence in all five runs. Explain that this is a detected limitation and that the native implementation now scores distance to GAN-generated clean samples; the earlier native build incorrectly used the GAN discriminator's real-versus-generated output as the anomaly score. The short backup pair in `native_demo/` is for animation rehearsal only.

> The final review shows the protocol running in native ns-3 and the exact measurements behind the animation. In the five matched runs, AR-EAURP did not show a reliable delivery improvement. The detector and forecaster results tell us what needs further work, and the report separates those limits from the earlier Colab experiment.

### 6. Distinguish Review 2 evidence from this review (one minute)

Show one Review 2 Colab plot if needed, and say which simulation engine and settings produced it; Colab itself is only the machine that ran the notebook. Then show the verified native report. Do not put an earlier percentage and the new local ns-3 percentage in the same performance bar chart unless topology, horizon, attacks, training, seeds and measurement windows match. The older `results/final_review_ns3_results` CSVs/figures have unverified provenance; its replacement HTML/Markdown report identifies this. Do not cite the former `>70%` live ns-3 detection claim.

## Backup if the live run is slow

1. In the viewer click **Clear comparison**. Use **Native result JSON files** to select `eaurp.json` and `ar-eaurp.json` together from `results/final_review_ns3_results/native_demo/`. The table appears immediately with exact saved values.
2. Use **NetAnim XML** to select `results/ns3-live/final-demo/ar-eaurp.xml`; press **Play**. Repeat for `eaurp.xml` if useful. This is replay of a real native trace, not a generated animation.
3. Open each JSON file or the corrected HTML report to show the raw source. The saved XML does not itself contain final application PDR or delay; those come from JSON.

## Questions you may get

- **Is it real-world deployment?** No. It is native ns-3 discrete-event simulation with modeled Wi-Fi PHY/MAC, mobility, traffic and energy. It is more detailed than the earlier abstract harness, but still a model.
- **Why is the trace reception count so high?** NetAnim records each successful wireless reception, including multiple receivers of a broadcast. Application delivery is measured separately.
- **Why does AR-EAURP train before the animation?** It learns from a clean commissioning run. Only the later attack evaluation is animated, so training and evaluation do not get mixed.
- **Did AR-EAURP do better than EAURP in ns-3?** Not reliably in this evaluation. Across five matched runs its mean PDR was 1.90 points lower, and the 95% paired interval includes both a loss and a gain. We cannot claim a win from these runs.
- **Why are the Colab and ns-3 results different?** Colab is a computing environment. The notebooks and native ns-3 scenario may use different simulation engines and assumptions. Compare results directly only after matching the engine, topology, workload, attack, training, horizon and metrics.
- **What did the native evaluation uncover?** The prior discriminator score was not a sound maliciousness score; the native code now uses generated-manifold distance. The measured detector still has weak AUC and low TPR here. The LSTM also loses to persistence, so routing now uses persistence unless the LSTM wins on held-out commissioning data.
- **How would you establish improvement?** Run a preregistered multi-seed native sweep over the full attack and topology matrix, report paired PDR, delay, detection, false positives, energy and confidence intervals, and tune only on separate commissioning scenarios.
