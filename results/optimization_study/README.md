# AR-EAURP CMDP routing study

## Question

Does training the CMDP route selector on clean commissioning traffic improve
AR-EAURP delivery under a grayhole attack, compared with EAURP?

## Experiment

- ns-3.45 native C++ simulation
- 24 nodes, 6 CBR flows, 25% grayhole nodes, 420 m square area
- 120 s simulation, 20 s warm-up, fixed seed 1
- Matched run numbers 21–50; each protocol uses the same run number
- AR-EAURP trains its detector/forecaster for 240 s on a separate clean
  commissioning network before evaluation
- The CMDP is now also trained on route outcomes during that clean phase
- EAURP runs without the AR models, as the baseline

## Result

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

## Files

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

## Reproduction

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
