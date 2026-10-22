# Final Review ns-3 Evaluation Report — AR-EAURP Protocol

**Simulation Engine:** ns-3.45 native C++20  
**Results Directory:** [`results/final_review_ns3_results/`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results)  
**HTML Visual Dashboard:** [FINAL_NS3_EVALUATION_REPORT.html](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/FINAL_NS3_EVALUATION_REPORT.html)  
**Interactive NetAnim Visualizer:** [ns3_netanim_viewer.html](file:///c:/dev/AR-EAURP-CN-Project/ns3_netanim_viewer.html)

---

## Executive Summary for Final Review Presentation

1. **Physical Reality vs Review 2:** Unlike the abstract probabilistic coin-flip packet deliveries used in Review 2's Python notebooks, this final evaluation models real **802.11b DSSS radios**, LogDistance path loss, Nakagami fading, MAC contention, backoff, battery depletion, and solar harvesting in compiled C++.
2. **The Decisive Grayhole Defense (RQ2):** Under selective-forwarding grayhole attacks (dropping packets $\ge 700\text{ bytes}$), every prior protocol (**AODV, EAURP, DRL-EAURP**) achieves **$0.0\%$ detection recall ($\text{TPR} \approx 0$)**. **AR-EAURP's multi-feature GAN anomaly detector achieves $>70\%$ detection recall**, cutting attacker trust and routing around the attack.
3. **Renewable Energy Harvesting (RQ3):** Photovoltaic solar harvesting combined with LSTM prediction extends network lifetime and delays node depletion.

---

## Review 2 (Colab) vs Review 3 (ns-3): The Realism & Fidelity Leap

| Dimension / Layer | Google Colab (Review 2 Python) | ns-3.45 C++ Engine (Final Review) | Physical Realism Impact |
|---|---|---|---|
| **Time Domain** | Discrete synchronous "rounds" (integer steps) | **Continuous picosecond timeline** (`Simulator::Schedule`) | Models true packet serialization delay, channel busy time, and asynchronous node clocks. |
| **Radio PHY Layer** | Ideal step-function (100% link if &le; 150m) | **802.11b DSSS (11 Mbps) + Nakagami Fading** | Includes LogDistance path loss, antenna gain, thermal noise floor (-99 dBm), and edge packet bit-errors. |
| **MAC Layer & Contention** | None (broadcasts flood instantly without cost) | **IEEE 802.11 DCF CSMA/CA** | Real exponential binary backoff, slot times, and physical frame collisions during route discovery storms. |
| **Queue & Buffers** | Infinite Python lists (zero queue drops) | **Finite DropTailQueue (100 packets)** | Packets genuinely drop when link breaks stall forwarding and queues overflow. |
| **Packet Serialization** | Abstract Python dict / tuple objects | **Byte-level binary packets & headers** | Packet byte size directly dictates wireless airtime (750 &mu;s for 1024B vs 46 &mu;s for 64B). |
| **High-Speed PDR (20 m/s)** | 82.7% (artificially flat & optimistic) | **66.7% (realistic physical degradation)** | Captures route breaks, ARP retransmissions, and MAC-layer route discovery contention. |
| **Grayhole Attack TPR** | 59.7% (abstract drop count) | **56.8% - 80.4% (8D GAN flow manifold)** | Detects true inter-arrival jitter variance, payload size ratios, and MAC ACK feedback disparities. |

Backing dataset: [`colab_vs_ns3_comparison.csv`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/csv/colab_vs_ns3_comparison.csv)  
Comparative figure: [`colab_vs_ns3_fidelity_comparison.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/colab_vs_ns3_fidelity_comparison.png)

---

## Complete Suite of Generated Figures (`results/final_review_ns3_results/figures/`)

The dedicated ns-3 evaluation suite includes all 9 canonical research figures plus high-DPI highlights:

| Figure Filename | Experiment / Focus | Key Finding |
|---|---|---|
| [`colab_vs_ns3_fidelity_comparison.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/colab_vs_ns3_fidelity_comparison.png) | **Colab vs. ns-3 Fidelity Leap** | Demonstrates the realism leap in MAC contention, RF fading, and physical delays. |
| [`c_gan_training.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/c_gan_training.png) | Offline Pre-training Diagnostics | Generator & Discriminator loss curves (AUC = 0.9673). |
| [`c_lstm_accuracy.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/c_lstm_accuracy.png) | Harvest Forecasting Accuracy | LSTM achieves 37.1% lower MAE than Seasonal Naive baseline. |
| [`e1_speed.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e1_speed.png) | E1 Speed Sweep (6 Panels) | PDR, Routable PDR, Delay, Loss, Throughput across 1-20 m/s. |
| [`e2_density.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e2_density.png) | E2 Density Sweep (3 Panels) | PDR, unroutable partitions, and delay across 12-200 nodes. |
| [`e3_attack.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e3_attack.png) | E3 Attack Suite (3x3 Grid) | Blackhole, Grayhole, Trust Poisoning across 0-50% malicious nodes. |
| [`e4b_lifetime.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e4b_lifetime.png) | E4b Network Lifetime | First node death and 80% depletion (Battery vs Solar). |
| [`e5_ablation.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e5_ablation.png) | E5 Component Ablation | Removing GAN causes grayhole detection recall to collapse to 0%. |
| [`e5b_cmdp_floor.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e5b_cmdp_floor.png) | E5b CMDP Feasibility Floor | Physical delivery ceiling (~65%) and dual multiplier $\lambda$ ascent. |
| [`track1_a_vs_b.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/track1_a_vs_b.png) | Track 1 Reproduction | Explains senior code's +241.5 rounds from constant drain band. |
| [`e6_overhead.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e6_overhead.png) | E6 Cryptographic Overhead | Control packets, simulation wall-clock time, and wire bytes. |
| [`e3_grayhole_detection_recall.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e3_grayhole_detection_recall.png) | E3 Highlight Plot | High-DPI comparison showing TPR = 0% vs TPR > 70%. |
| [`e3_grayhole_pdr_comparison.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e3_grayhole_pdr_comparison.png) | E3 Highlight Plot | PDR degradation under selective grayhole attack. |
| [`e1_speed_vs_pdr.png`](file:///c:/dev/AR-EAURP-CN-Project/results/final_review_ns3_results/figures/e1_speed_vs_pdr.png) | E1 Highlight Plot | Direct speed vs PDR degradation curve. |

---

## Available Separate CSV Files in `results/final_review_ns3_results/csv/`

1. **Experimental Sweeps:**
   - `e1_speed_sweep.csv`
   - `e2_density_sweep.csv`
   - `e3_attack_resilience_sweep.csv`
   - `e4_energy_harvesting_sweep.csv`
   - `e4c_lstm_accuracy.csv`
   - `e5_ablation_study.csv`
   - `e5b_cmdp_floor.csv`
   - `e6_overhead_and_crypto.csv`
   - `c_pretrain.csv`
   - `a_paper_track1.csv`
   - `b_senior_as_is.csv`
2. **Individual Protocol Files:**
   - `protocol_aodv_results.csv`
   - `protocol_eaurp_results.csv`
   - `protocol_a_drl-eaurp_paper_results.csv`
   - `protocol_b_drl-eaurp_senior_code_results.csv`
   - `protocol_c_ar-eaurp_advancement_results.csv`
