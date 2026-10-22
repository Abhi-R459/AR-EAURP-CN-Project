# AR-EAURP — entirely native ns-3 evaluation

Profile: **smoke**; engine: ns-3.45 C++.

Build identity: `023a40d52ab982d6967d0d9e349be3334ab24641f106088cf2ebc7229ab4b78b`.

These short single-seed runs validate execution only.

## e1_speed

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| AODV (reference baseline) @ 1 m/s | 1 | 1 | 0 | 0.080685 | 38384 | 0 | 0 |
| AODV (reference baseline) @ 5 m/s | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| EAURP (base substrate) @ 1 m/s | 1 | 1 | 0 | 0.068834 | 38384 | 0 | 0 |
| EAURP (base substrate) @ 5 m/s | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) @ 1 m/s | 1 | 1 | 0 | 0.067322 | 38384 | 0 | 0 |
| A: DRL-EAURP (paper) @ 5 m/s | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) @ 1 m/s | 1 | 1 | 0 | 0.31889 | 38384 | 0 | 0 |
| B: DRL-EAURP (senior) @ 5 m/s | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| C: AR-EAURP (advancement) @ 1 m/s | 1 | 1 | 0 | 0.06933 | 38384 | 1 | 1 |
| C: AR-EAURP (advancement) @ 5 m/s | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |

## e2_density

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| AODV (reference baseline) @ N=12 | 1 | 0.91667 | 0 | 0.33657 | 35530 | 0 | 0 |
| AODV (reference baseline) @ N=24 | 1 | 1 | 0 | 0.035778 | 38384 | 0 | 0 |
| EAURP (base substrate) @ N=12 | 1 | 1 | 0 | 0.46584 | 38384 | 0 | 0 |
| EAURP (base substrate) @ N=24 | 1 | 1 | 0 | 0.19836 | 38384 | 0 | 0 |
| A: DRL-EAURP (paper) @ N=12 | 1 | 1 | 0 | 0.069808 | 38384 | 0 | 0 |
| A: DRL-EAURP (paper) @ N=24 | 1 | 1 | 0 | 0.20071 | 38384 | 0 | 0 |
| B: DRL-EAURP (senior) @ N=12 | 1 | 1 | 0 | 0.06951 | 38384 | 0 | 0 |
| B: DRL-EAURP (senior) @ N=24 | 1 | 1 | 0 | 0.20072 | 38384 | 0 | 0 |
| C: AR-EAURP (advancement) @ N=12 | 1 | 1 | 0 | 0.46584 | 38384 | 0 | 1 |
| C: AR-EAURP (advancement) @ N=24 | 1 | 1 | 0 | 0.19836 | 38384 | 1 | 1 |

## e3_attack

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| AODV (reference baseline) / blackhole @ 0% | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| AODV (reference baseline) / blackhole @ 30% | 1 | 0.33333 | 0 | 0.0092858 | 12916 | 0 | 0 |
| AODV (reference baseline) / grayhole @ 0% | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| AODV (reference baseline) / grayhole @ 30% | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| AODV (reference baseline) / trust_poisoning @ 0% | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| AODV (reference baseline) / trust_poisoning @ 30% | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| EAURP (base substrate) / blackhole @ 0% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| EAURP (base substrate) / blackhole @ 30% | 1 | 0.53333 | 0 | 0.063175 | 20579 | 0 | 0 |
| EAURP (base substrate) / grayhole @ 0% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| EAURP (base substrate) / grayhole @ 30% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| EAURP (base substrate) / trust_poisoning @ 0% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| EAURP (base substrate) / trust_poisoning @ 30% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) / blackhole @ 0% | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) / blackhole @ 30% | 1 | 0.61667 | 0 | 0.0050628 | 23771 | 0 | 0 |
| A: DRL-EAURP (paper) / grayhole @ 0% | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) / grayhole @ 30% | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) / trust_poisoning @ 0% | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) / trust_poisoning @ 30% | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) / blackhole @ 0% | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) / blackhole @ 30% | 1 | 0.4 | 0 | 0.0060278 | 14790 | 0 | 0 |
| B: DRL-EAURP (senior) / grayhole @ 0% | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) / grayhole @ 30% | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) / trust_poisoning @ 0% | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) / trust_poisoning @ 30% | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| C: AR-EAURP (advancement) / blackhole @ 0% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C: AR-EAURP (advancement) / blackhole @ 30% | 1 | 0.53333 | 0 | 0.063175 | 20579 | 0 | 1 |
| C: AR-EAURP (advancement) / grayhole @ 0% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C: AR-EAURP (advancement) / grayhole @ 30% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C: AR-EAURP (advancement) / trust_poisoning @ 0% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C: AR-EAURP (advancement) / trust_poisoning @ 30% | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |

| Configuration | Contested TPR | Contested FPR | Revocation TPR | Revocation FPR | Detector windows |
|---|---:|---:|---:|---:|---:|
| AODV (reference baseline) / blackhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| AODV (reference baseline) / blackhole @ 30% | 0 | 0 | 0 | 0 | 0 |
| AODV (reference baseline) / grayhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| AODV (reference baseline) / grayhole @ 30% | 0 | 0 | 0 | 0 | 0 |
| AODV (reference baseline) / trust_poisoning @ 0% | 0 | 0 | 0 | 0 | 0 |
| AODV (reference baseline) / trust_poisoning @ 30% | 0 | 0 | 0 | 0 | 0 |
| EAURP (base substrate) / blackhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| EAURP (base substrate) / blackhole @ 30% | 0 | 0 | 0.2 | 0 | 0 |
| EAURP (base substrate) / grayhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| EAURP (base substrate) / grayhole @ 30% | 0 | 0 | 0 | 0 | 0 |
| EAURP (base substrate) / trust_poisoning @ 0% | 0 | 0 | 0 | 0 | 0 |
| EAURP (base substrate) / trust_poisoning @ 30% | 0 | 0 | 0 | 0 | 0 |
| A: DRL-EAURP (paper) / blackhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| A: DRL-EAURP (paper) / blackhole @ 30% | 0 | 0 | 0.2 | 0 | 0 |
| A: DRL-EAURP (paper) / grayhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| A: DRL-EAURP (paper) / grayhole @ 30% | 0 | 0 | 0 | 0 | 0 |
| A: DRL-EAURP (paper) / trust_poisoning @ 0% | 0 | 0 | 0 | 0 | 0 |
| A: DRL-EAURP (paper) / trust_poisoning @ 30% | 0 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / blackhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / blackhole @ 30% | 0 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / grayhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / grayhole @ 30% | 0 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / trust_poisoning @ 0% | 0 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / trust_poisoning @ 30% | 0 | 0 | 0 | 0 | 0 |
| C: AR-EAURP (advancement) / blackhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| C: AR-EAURP (advancement) / blackhole @ 30% | 0 | 0 | 0.2 | 0 | 0 |
| C: AR-EAURP (advancement) / grayhole @ 0% | 0 | 0 | 0 | 0 | 0 |
| C: AR-EAURP (advancement) / grayhole @ 30% | 0 | 0 | 0 | 0 | 0 |
| C: AR-EAURP (advancement) / trust_poisoning @ 0% | 0 | 0 | 0 | 0 | 0 |
| C: AR-EAURP (advancement) / trust_poisoning @ 30% | 0 | 0 | 0 | 0 | 0 |

## e4_energy

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| AODV (reference baseline) / battery | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| AODV (reference baseline) / solar | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| EAURP (base substrate) / battery | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| EAURP (base substrate) / solar | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) / battery | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) / solar | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) / battery | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) / solar | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| C: AR-EAURP (advancement) / battery | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| C: AR-EAURP (advancement) / solar | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |

| Configuration | Residual (J) | Harvested (J) | LSTM MAE (W) | Persistence MAE (W) | Window mean MAE (W) | Holdout sequences |
|---|---:|---:|---:|---:|---:|---:|
| AODV (reference baseline) / battery | 5441.9 | 0 | 0 | 0 | 0 | 0 |
| AODV (reference baseline) / solar | 5479.7 | 35.247 | 0 | 0 | 0 | 0 |
| EAURP (base substrate) / battery | 5441.9 | 0 | 0 | 0 | 0 | 0 |
| EAURP (base substrate) / solar | 5479.6 | 35.247 | 0 | 0 | 0 | 0 |
| A: DRL-EAURP (paper) / battery | 5441.8 | 0 | 0 | 0 | 0 | 0 |
| A: DRL-EAURP (paper) / solar | 5479.6 | 35.247 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / battery | 5441.9 | 0 | 0 | 0 | 0 | 0 |
| B: DRL-EAURP (senior) / solar | 5479.6 | 35.247 | 0 | 0 | 0 | 0 |
| C: AR-EAURP (advancement) / battery | 5441.9 | 0 | 0 | 0 | 0 | 0 |
| C: AR-EAURP (advancement) / solar | 5479.6 | 35.247 | 0.14221 | 0.075565 | 0.10049 | 64 |

## e4b_lifetime

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| AODV (reference baseline) / battery | 1 | 0.55263 | 0 | 0.019855 | 20916 | 0 | 0 |
| AODV (reference baseline) / solar | 1 | 0.82018 | 0 | 0.015123 | 31233 | 0 | 0 |
| EAURP (base substrate) / battery | 1 | 0.50877 | 0 | 0.021919 | 19279 | 0 | 0 |
| EAURP (base substrate) / solar | 1 | 0.79825 | 0 | 0.038822 | 30381 | 0 | 0 |
| A: DRL-EAURP (paper) / battery | 1 | 0.5307 | 0 | 0.040392 | 20131 | 0 | 0 |
| A: DRL-EAURP (paper) / solar | 1 | 0.82456 | 0 | 0.028067 | 31380 | 0 | 0 |
| B: DRL-EAURP (senior) / battery | 1 | 0.5307 | 0 | 0.040259 | 20131 | 0 | 0 |
| B: DRL-EAURP (senior) / solar | 1 | 0.82456 | 0 | 0.027588 | 31380 | 0 | 0 |
| C: AR-EAURP (advancement) / battery | 1 | 0.50877 | 0 | 0.021928 | 19279 | 0 | 0 |
| C: AR-EAURP (advancement) / solar | 1 | 0.79825 | 0 | 0.039132 | 30381 | 0 | 1 |

| Configuration | First depletion (s) | 80% depletion (s) | Horizon (s) |
|---|---:|---:|---:|
| AODV (reference baseline) / battery | 24.242 | 24.293 | 40 |
| AODV (reference baseline) / solar | 24.558 | censored | 40 |
| EAURP (base substrate) / battery | 24.216 | 24.275 | 40 |
| EAURP (base substrate) / solar | 24.548 | censored | 40 |
| A: DRL-EAURP (paper) / battery | 24.208 | 24.289 | 40 |
| A: DRL-EAURP (paper) / solar | 24.541 | censored | 40 |
| B: DRL-EAURP (senior) / battery | 24.225 | 24.295 | 40 |
| B: DRL-EAURP (senior) / solar | 24.548 | censored | 40 |
| C: AR-EAURP (advancement) / battery | 24.217 | 24.275 | 40 |
| C: AR-EAURP (advancement) / solar | 24.547 | censored | 40 |

## e5_ablation

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| C full | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C without GAN | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C without LSTM | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| C without CMDP | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C bare | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| C without energy excuse | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |

| Configuration | PDR target | Final multiplier | Peak multiplier | Violations | Decisions | Trust actions | Energy actions | Balanced actions | Diversified actions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C full | 0.9 | 0.03 | 0.03 | 1 | 7 | 0 | 1 | 1 | 5 |
| C without GAN | 0.9 | 0.03 | 0.03 | 1 | 7 | 0 | 1 | 1 | 5 |
| C without LSTM | 0.9 | 0.03 | 0.03 | 1 | 7 | 0 | 1 | 1 | 5 |
| C without CMDP | 0.9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C bare | 0.9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C without energy excuse | 0.9 | 0.03 | 0.03 | 1 | 7 | 0 | 1 | 1 | 5 |

## e5b_cmdp_floor

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| C floor=0.70 | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C floor=0.80 | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C floor=0.90 | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C floor=0.95 | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |

| Configuration | PDR target | Final multiplier | Peak multiplier | Violations | Decisions | Trust actions | Energy actions | Balanced actions | Diversified actions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C floor=0.70 | 0.7 | 0.02 | 0.02 | 1 | 7 | 0 | 1 | 1 | 5 |
| C floor=0.80 | 0.8 | 0.025 | 0.025 | 1 | 7 | 0 | 1 | 1 | 5 |
| C floor=0.90 | 0.9 | 0.03 | 0.03 | 1 | 7 | 0 | 1 | 1 | 5 |
| C floor=0.95 | 0.95 | 0.0325 | 0.0325 | 1 | 7 | 0 | 1 | 1 | 5 |

## e6_overhead

| Configuration | Runs | PDR | PDR seed SD | Delay (s) | Throughput (bit/s) | GAN trained | LSTM trained |
|---|---:|---:|---:|---:|---:|---:|---:|
| AODV (reference baseline) | 1 | 0.88333 | 0 | 0.040595 | 33523 | 0 | 0 |
| EAURP (base substrate) | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 0 |
| A: DRL-EAURP (paper) | 1 | 0.88333 | 0 | 0.085532 | 33523 | 0 | 0 |
| B: DRL-EAURP (senior) | 1 | 0.88333 | 0 | 0.085597 | 33523 | 0 | 0 |
| C: AR-EAURP (advancement) | 1 | 0.88333 | 0 | 0.040351 | 33523 | 0 | 1 |
| C without ECC | 1 | 0.88333 | 0 | 0.040184 | 33523 | 0 | 1 |

| Configuration | Generated control messages | Wall time (s) | Protected messages | Crypto overhead (bytes) | Authentication failures |
|---|---:|---:|---:|---:|---:|
| AODV (reference baseline) | 174 | 0.079264 | 116 | 3248 | 0 |
| EAURP (base substrate) | 181 | 0.08025 | 114 | 3192 | 0 |
| A: DRL-EAURP (paper) | 153 | 0.074621 | 113 | 3164 | 0 |
| B: DRL-EAURP (senior) | 151 | 0.072884 | 113 | 3164 | 0 |
| C: AR-EAURP (advancement) | 181 | 0.67119 | 114 | 3192 | 0 |
| C without ECC | 181 | 0.66406 | 0 | 0 | 0 |

## Measurement and modelling limits

- Every experiment, commissioning run, network event, learning update, checkpoint and aggregation runs in compiled ns-3 C++. Plots use ns-3's Gnuplot helper and the gnuplot renderer.
- A/B adapt paper policies to local distributed routing. A uses watchdog trust; B advertises its own send/receive-counter trust and never revokes nodes. Diversification avoids the previous next hop, not every node on the previous route.
- The adversarial AODV baseline shares the custom substrate. Upstream ns3-aodv supports clean runs only.
- PDR counts sends in the measurement window and their arrivals through cooldown. Lost ACKs can penalise delivered data. Delay is seconds, energy joules, forecasts watts, throughput bits/s.
- GAN/LSTM train only during clean commissioning. An untrained flag means its zero error is a placeholder. LSTM holdouts are disjoint chronological intervals per node; persistence and window mean are baselines.
- Lifetime flags identify observed deaths. Unobserved events are censored at the horizon; mixed censored/observed seed means are not lifetime estimates.
- The solar/kinetic source is a model with compressed days and an ideal reservoir without a capacity ceiling. First depletion permanently disables the PHY, as in the archived Python simulation. A ns-3.45 radio callback guard prevents premature model shutdown while the PHY remains active.
- X25519/HKDF/AES-GCM adds 28 bytes per protected message. Keys are deterministic simulation fixtures, provisioned before the run. Key-exchange traffic and crypto CPU latency are not injected into simulated time.
- Control counters are generated message attempts, including attempts after PHY shutdown, rather than successful radio transmissions. Layer drop counters are not additive end-to-end loss categories.
- CMDP multipliers, actions and violations include warmup/cooldown policy activity. An unmet PDR target does not prove mathematical infeasibility. Wall time includes commissioning and is host runtime.
- Detection scores nodes flagged by honest witnesses: contested flags require two witnesses; revocations require one. The AUC placeholder is 0.5. A smoke run is an execution check, not evidence of comparative performance.

![e1_speed_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e1_speed_pdr.svg>)

![e1_speed_mean_delay_s](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e1_speed_mean_delay_s.svg>)

![e1_speed_loss_packets](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e1_speed_loss_packets.svg>)

![e1_speed_throughput_bps](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e1_speed_throughput_bps.svg>)

![e2_density_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e2_density_pdr.svg>)

![e2_density_mean_delay_s](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e2_density_mean_delay_s.svg>)

![e2_density_loss_packets](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e2_density_loss_packets.svg>)

![e2_density_throughput_bps](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e2_density_throughput_bps.svg>)

![e3_blackhole_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_blackhole_pdr.svg>)

![e3_blackhole_detect_tpr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_blackhole_detect_tpr.svg>)

![e3_blackhole_detect_fpr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_blackhole_detect_fpr.svg>)

![e3_grayhole_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_grayhole_pdr.svg>)

![e3_grayhole_detect_tpr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_grayhole_detect_tpr.svg>)

![e3_grayhole_detect_fpr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_grayhole_detect_fpr.svg>)

![e3_trust_poisoning_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_trust_poisoning_pdr.svg>)

![e3_trust_poisoning_detect_tpr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_trust_poisoning_detect_tpr.svg>)

![e3_trust_poisoning_detect_fpr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e3_trust_poisoning_detect_fpr.svg>)

![e4_energy_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e4_energy_pdr.svg>)

![e4_energy_residual_energy_j](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e4_energy_residual_energy_j.svg>)

![e4_energy_harvested_j](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e4_energy_harvested_j.svg>)

![e4_energy_lstm_mae_w](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e4_energy_lstm_mae_w.svg>)

![e4b_lifetime_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e4b_lifetime_pdr.svg>)

![e4b_lifetime_first_death_s](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e4b_lifetime_first_death_s.svg>)

![e5_ablation_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e5_ablation_pdr.svg>)

![e5_ablation_cmdp_lambda](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e5_ablation_cmdp_lambda.svg>)

![e5b_cmdp_floor_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e5b_cmdp_floor_pdr.svg>)

![e5b_cmdp_floor_cmdp_lambda](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e5b_cmdp_floor_cmdp_lambda.svg>)

![e6_overhead_pdr](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e6_overhead_pdr.svg>)

![e6_overhead_control_packets](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e6_overhead_control_packets.svg>)

![e6_overhead_wall_clock_seconds](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e6_overhead_wall_clock_seconds.svg>)

![e6_overhead_crypto_overhead_bytes](</Users/sreerajmuthaiya.a.l/AR-EAURP-CN-Project/results/ns3-native-smoke/figures/e6_overhead_crypto_overhead_bytes.svg>)
