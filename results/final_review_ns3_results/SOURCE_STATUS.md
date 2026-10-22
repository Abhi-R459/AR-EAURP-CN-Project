# Status of files in this directory

`native_demo/` contains reproducible short ns-3.45 outputs for animation rehearsal. These runs have too little traffic to support a protocol performance claim.

`native_long_runs/` contains the ten raw native JSON outputs used by the verified five-run matched comparison in `FINAL_NS3_EVALUATION_REPORT.md`. `NATIVE_FIVE_SEED_COMPARISON.csv` is derived directly from those files. Each pair uses the same seed, run number, topology, traffic, attack and measurement interval. AR-EAURP includes the clean commissioning parameters recorded in its JSON.

The final report reflects a native detector correction: generated-manifold anomaly distance is used instead of the GAN discriminator score, raw per-window detector rates are separate from contested consensus and revocation, and the LSTM is used for routing only when it beats persistence on its held-out clean commissioning samples.

The older CSV files and figures in this directory were prepared for an earlier dashboard. Their run provenance has not been established here. Keep them for historical reference, but do not present them as measured native ns-3 results or cite their headline gains until their source commands, raw checkpoints and seed aggregation are verified.
