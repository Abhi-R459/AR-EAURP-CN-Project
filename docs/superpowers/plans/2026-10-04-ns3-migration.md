# Complete ns-3 Migration Implementation Plan

> **For agentic workers:** Implement the tasks in order with the test-driven-development and verification-before-completion skills. The user's instruction to continue authorizes execution in this session.

**Goal:** Make ns-3 C++ the only active simulation engine for every experiment and notebook.

**Architecture:** Extend the existing contrib module and scenario. Python launches compiled ns-3 processes, checkpoints measurements, and renders results; it does not simulate packets, mobility, energy, attacks, or learning. Retain the former Python implementation under `legacy/python/` for historical provenance.

**Tech Stack:** ns-3.45, C++20, OpenSSL, Python standard library orchestration, NumPy/Matplotlib plotting.

**Spec:** User request: “continue replacing the entire simulation from python to ns3”; existing E1–E6 definitions and A/B policy semantics.

## Global Constraints

- Preserve the pre-existing uncommitted watchdog and oracle changes.
- Implement AODV, EAURP, A (tabular DRL), B (endpoint trust), and C in C++.
- Use seconds, metres/second, joules, watts, and bits/second in measurements.
- Train GAN/LSTM only on a separate clean commissioning run.
- Give mobility, traffic, panels, and attacker placement explicit RNG streams.
- Keep historical Python results separate from ns-3 results.

## Review Focus

- Reject unknown protocols and invalid ranges before constructing a network.
- Exclude pre-warmup sends from receive counts; drain in-flight evaluation traffic.
- Resume only matching source/configuration/run checkpoints.
- Preserve honest CSV quoting and reject incompatible append schemas.
- Do not claim a lifetime event or trained detector when it was not observed.

### Task 1: Complete native policies and measurement boundaries

Files: `ns3/contrib/ar-eaurp/model/ar-eaurp-tabular.{h,cc}`, routing protocol, oracle, native test suite, scenario.

- [x] Add failing native tests for Q-learning feedback, endpoint trust, and warmup receive accounting.
- [x] Implement two native DRL variants and GAN/LSTM/CMDP/energy-excuse/floor controls.
- [x] Add scenario validation, reproducible streams, cooldown, JSON output, safe CSV append, and lifetime censoring.
- [x] Build and run the `ar-eaurp` native test suite plus real scenario smoke runs.

### Task 2: Preserve payload protection in C++

Files: `ar-eaurp-crypto.{h,cc}`, traffic app, module CMake, native tests, scenario.

- [x] Add failing tests for symmetric X25519 key agreement, AEAD roundtrip, and tamper rejection.
- [x] Implement X25519/HKDF/AES-GCM protection and per-flow commissioning keys.
- [x] Run the native test suite and a protected UDP scenario.

### Task 3: Replace active experiment orchestration

Files: `experiments/{config,ns3,harness,sweeps,run_all}.py`, `ns3/scripts/setup.sh`, `tests/test_ns3.py`.

- [x] Add failing tests for argument validation, per-run checkpoint provenance/resume, aggregation, and scenario failure propagation.
- [x] Replace all Python simulation imports with ns-3 subprocess runs and port E1–E6 sweeps.
- [x] Add installation/build scripts; execute all experiment paths with a short smoke profile.

### Task 4: Migrate deliverables and archive historical implementation

Files: plotting/report tools, notebooks, README, requirements, `legacy/python/`.

- [x] Move the Python engine and its tests/old tooling into the historical archive.
- [x] Update plotting and reporting to ns-3 metric names/units and require ns-3 provenance.
- [x] Generate both Colab notebooks with ns-3 source/bootstrap cells.
- [x] Run Python tests, native tests, smoke experiments, plotting, report generation, and notebook syntax validation.
- [x] Review the final diff and document measurement limits.

## Completed validation

- Built ns-3.45 through the CMake bootstrap against the existing installation.
- All 8 native model tests passed.
- All 43 Python process/integration tests passed with `NS3_HOME` set, including protected UDP, all native protocols, real trained GAN/LSTM inference under a grayhole attack, measurement cohorts, late ACK rewards, permanent depletion, tiny batteries, CSV quoting, repeated-seed equality, resume and stale shared-library rejection.
- E1–E6 smoke profile completed 86 configurations across 8 CSV files. These validate execution; the full research sweep has not been run.
- Generated both Colab notebooks, validated notebook format and every code cell's Python syntax, and restored the embedded 48-file source snapshot in a temporary directory. Its native source digest matches the workspace. An actual Colab session and a fresh Linux build remain unverified.
- Regenerated the report and ten figures from current ns-3 measurements; report generation rejects mixed source/profile CSVs and always refreshes figures.
- Verified all 33 archived Python source files match their original Git contents. Pre-existing output/paper material was preserved.
- Read-only code review identified measurement, learning-feedback, radio-energy and provenance issues; regression tests cover their fixes. Depletion permanently disables the PHY, matching the former engine. The radio callback guard keeps upstream current accounting while avoiding orphaned shutdown timers.
