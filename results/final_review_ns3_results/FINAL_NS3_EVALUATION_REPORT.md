# Final review: native ns-3 results and implementation correction

## Result to present

We reran EAURP and AR-EAURP with matched native ns-3.45 settings across five RNG runs. The result does **not** establish that AR-EAURP improves delivery in this scenario. Its mean PDR was lower by 1.9 percentage points, and the paired 95% t interval spans from -8.46 to +4.66 percentage points. Treat the delivery comparison as inconclusive; do not claim AR-EAURP beat EAURP in ns-3.

| Metric (mean ± sample SD across five runs) | EAURP | AR-EAURP |
|---|---:|---:|
| Application PDR | 83.73% ± 4.23 | 81.83% ± 4.60 |
| Mean application delay | 257 ± 86 ms | 292 ± 108 ms |
| GAN window detection TPR | n/a | 6.79% ± 3.32 |
| GAN window false-positive rate | n/a | 5.83% ± 6.14 |
| GAN score ROC AUC | n/a | 0.55 ± 0.08 |
| Two-honest-witness contested TPR | n/a | 0% in all five runs |
| LSTM holdout MAE / persistence MAE | n/a | 0.60 W / 0.06 W (mean) |
| LSTM selected for routing | n/a | no, in all five runs |

The paired runs sent 600 application packets each. The difference is noisy at five seeds and does not support a ranking. The security detector has weak discrimination in this native scenario: its mean AUC is only modestly above 0.5, and only a small fraction of malicious behavior windows cross its calibrated threshold. No node reached the two-honest-witness contested consensus. The LSTM lost to persistence on every commissioning evaluation, so the corrected implementation uses persistence for routing in these runs.

## What was corrected

The native detector previously used the GAN discriminator's real-versus-generated output directly as a maliciousness score. That score answers whether a sample resembles the GAN's generated samples; it does not directly score whether a relay's behavior is malicious. The native implementation now scores each observation by distance to a bank of GAN-generated clean feature vectors and calibrates its threshold on clean commissioning data. This matches the detector method described in the project paper.

The result accounting now reports per-window GAN TPR/FPR separately from two-witness contested consensus and revocation TPR/FPR. Earlier `detect_tpr` and `detect_fpr` fields represented consensus rates, which could mislead readers into thinking they were raw detector metrics. The native JSON now includes separate `contested_tpr` and `contested_fpr` fields.

The LSTM is selected for routing only when its commissioning holdout MAE beats persistence. Otherwise, routing uses the most recent harvest sample as the persistence forecast. In this evaluation the fallback was selected in all five runs.

These corrections improve method fidelity and reporting accuracy. They have **not** made the current ns-3 performance claim positive: delivery and detection remain open research issues. Colab results and these native ns-3 results must be described as different experiments unless their simulation engine, workload, topology, attack, horizon, training and metrics are demonstrably the same.

## Reproduction

Settings: 24 nodes, six UDP flows, 420 m square, 25% grayhole nodes, 120 seconds measured time, 20 seconds warmup, seed 1, run numbers 1–5. AR-EAURP uses 240 seconds clean commissioning, 120 GAN epochs and 30 LSTM epochs. Each pair has matching evaluation run numbers and network settings.

From the repository root in WSL, after the native ns-3 build is available:

```bash
export NS3_HOME="$HOME/.cache/ar-eaurp/ns-3.45"
SIM="$NS3_HOME/build/scratch/ns3.45-ar-eaurp-sim-optimized"
OUT="results/final_review_ns3_results/native_long_runs"
mkdir -p "$OUT"
for run in 1 2 3 4 5; do
  common=(--attack=grayhole --malicious=0.25 --nodes=24 --flows=6 \
    --area=420 --time=120 --warmup=20 --seed=1 --run="$run")
  "$SIM" "${common[@]}" --protocol=eaurp --train=0 \
    --json="$OUT/eaurp-run${run}.json"
  "$SIM" "${common[@]}" --protocol=ar-eaurp --train=1 \
    --commission=240 --ganEpochs=120 --lstmEpochs=30 \
    --json="$OUT/ar-eaurp-run${run}.json"
done
```

The saved paired source files are in [`native_long_runs/`](native_long_runs/); the compact per-seed comparison is [`NATIVE_FIVE_SEED_COMPARISON.csv`](NATIVE_FIVE_SEED_COMPARISON.csv). PDR is `app_rx / app_tx` from each simulator JSON. The mean paired-difference interval uses a two-sided Student t interval with four degrees of freedom. The short 8-second demo files in `native_demo/` remain useful for animation rehearsal, but are not evidence of comparative performance.

## Showing the simulation

For the live animation, start the local viewer from WSL:

```bash
python3 ns3/netanim/live_server.py --ns3-home "$NS3_HOME" --port 8767
```

Open `http://127.0.0.1:8767/`, run EAURP and AR-EAURP with the same visible settings, then explain that node movement and receptions come from native NetAnim XML while PDR, delay and detector metrics come from each run's JSON. The viewer server only launches ns-3 and relays its output. For the five-seed comparison, load the saved JSON files from `native_long_runs/` in the viewer. Avoid describing the animation alone as evidence that AR-EAURP is better.
