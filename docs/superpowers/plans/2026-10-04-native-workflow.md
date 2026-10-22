# Entire native workflow implementation plan

**Goal:** Fulfil “let everything be ns3”: run experiments, aggregate seeds, resume measurements, and generate reports/plots through compiled ns-3 C++.

**Architecture:** Extract the existing scenario into a callable contrib entry point, keeping the individual CLI. Add one native batch executable with E1–E6 configurations, checksum-verified checkpoint contents and build provenance. Use ns-3's Gnuplot helper for plot scripts and native C++ Markdown/HTML report generation. Shell scripts build and launch the binaries; Colab cells run shell commands only. Preserve previous Python tooling in a historical archive.

**Constraints:** Preserve user changes and historical output/paper material; use ns-3.45/OpenSSL; preserve paired seeds, commissioning and physical units. Upstream ns-3's own build dependencies are unchanged. No project Python runtime is needed.

- [x] Refactor the scenario entry point and verify unchanged native delivery, repeatability, attacks, feedback and depletion.
- [x] Add native sweeps, sample statistics, checkpoint/provenance checks and integration self-tests.
- [x] Add ns-3 Gnuplot output and C++ report generation; verify all 86 smoke configurations.
- [x] Replace project bootstrap/run/notebook generation with shell/C++; archive Python workflow files and update documentation.
- [x] Verify native model tests, native integration tests, repeat/resume and regenerated deliverables.

Verification completed: ns-3.45 native build; 8 model unit tests; 30 native integration checks and 3 CLI/provenance/path checks; all 86 smoke configurations across 8 aggregate tables; 32 SVG figures; second sweep resumed all 86 runs without simulation. Regenerated notebook shell cells pass bash syntax checks and their embedded sources match the workspace. Git diff whitespace checks pass. Full research sweeps and an actual fresh Colab session remain unrun.
