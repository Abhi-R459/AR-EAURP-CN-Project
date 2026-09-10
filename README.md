# AR-EAURP — Review 2

Adversarial-Resilient and Energy-Harvesting Aware EAURP. Three implementations
and an honest comparison.

| | What it is | Source document |
|---|---|---|
| **A** | DRL-EAURP, re-implemented from the paper's equations (1)–(38) | `project_docs/Lekha.pdf` |
| **B** | The senior's delivered code, logic verbatim | `project_docs/senior_code.ipynb` |
| **C** | AR-EAURP — GAN trust defence, LSTM energy forecasting, CMDP routing | `project_docs/Date_ 24_07_26.docx` |

## Run it on Colab

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Abhi-R459/AR-EAURP-CN-Project/blob/main/colab/REVIEW2_FROM_GITHUB.ipynb)

Then **Runtime → Run all**. Nothing to install — Colab already ships numpy,
matplotlib, networkx, pandas and torch.

> ⚠️ **This repository is private.** A Colab session holds no GitHub
> credentials, so the badge above and the notebook's `git clone` will both fail
> until one of these is true:
>
> - the repository is **made public** (Settings → General → Danger Zone →
>   Change visibility) — then everything works with one click; or
> - a fine-grained **personal access token** with read access to this repo is
>   stored in Colab Secrets (key icon, left sidebar) under the name
>   `GITHUB_TOKEN` with notebook access enabled — the clone cell picks it up
>   automatically; or
> - you use `colab/REVIEW2_AR_EAURP.ipynb`, which needs no network at all.
>
> Upload it manually (File → Upload notebook) and it works regardless of
> visibility.

There are two notebooks. They contain the same analysis and differ only in how
the code reaches the session:

| notebook | size | how `src/` gets there |
|---|---|---|
| **`colab/REVIEW2_FROM_GITHUB.ipynb`** | 35 cells, 21 KB | clones this repository, then `cd`s into it |
| `colab/REVIEW2_AR_EAURP.ipynb` | 75 cells, 395 KB | 40 folded `%%writefile` cells that write the tree into the session |

Use the first one. Use the second only if you need it to work with no network
and no GitHub — it embeds every source file directly.

> **If `src/` appears to be missing in Colab**, the setup section has not run.
> In the GitHub notebook that is the clone cell; in the self-contained one it
> is the block of 40 folded `%%writefile` cells, which render as an
> empty-looking gap and are easy to scroll straight past. Run from the top, or
> Runtime → Run all.

Results checkpoint to CSV as each sweep finishes and are skipped on a re-run,
so an interrupted Colab session resumes rather than restarting. Mount Drive
when the notebook offers, and they survive the session entirely.

## Run it locally

### Peer-to-peer Flutter messenger

The `app/` folder contains RelayMesh, a real nearby-device text messenger.
It uses Wi-Fi Direct for Android-to-Android communication and Multipeer
Connectivity for Apple-to-Apple communication. Neither path requires internet
or a Wi-Fi router.

```bash
cd app
flutter devices
flutter run -d <device-id>
```

See [`app/README.md`](app/README.md) for physical-device setup and transport
limitations.

### Experiments

```bash
pip install -r requirements.txt
```

```bash
python experiments/run_all.py --profile quick
```

```bash
python experiments/run_all.py --profile full
```

`quick` (200 rounds × 2 runs) is a smoke test; `full` (400 rounds × 5 runs)
produces the numbers to present. Add `--only e3` to run just the attack sweep,
or `--out-dir <path>` to write results elsewhere.

Regenerate the notebooks and the report after any code change — `src/` is the
single source of truth and the notebooks are generated from it:

```bash
python tools/build_notebook.py && python tools/make_report.py
```

## Why there are two tracks

The senior's code is not a network simulator. `src` and `dst` are drawn at
random every round and never connected by a path; delivery is one coin flip
against a global average:

```python
success_prob = 0.45 + 0.25*avg_trust + 0.2*avg_energy + 0.1*avg_mobility
success = random.random() < success_prob      # this is the entire "routing"
```

Nothing forwards anything, so a gray-hole that drops 15% of what it relays
cannot be expressed in that model — and the advancement is entirely about
gray-holes. Hence:

- **Track 1 (as-is)** — each implementation in its native form. Preserves the
  senior's published numbers, which reproduce here bit-for-bit.
- **Track 2 (common harness)** — A, B and C as routing policies on one
  mechanistic simulator that walks every packet hop by hop, with identical
  seeds, topology, mobility, traffic and adversary placement. This is where the
  fair comparison and the attack sweep live.

Never compare a Track 1 number with a Track 2 number; they measure different
things. `experiments/report.py` prints the full caveat list with the results.

## Layout

```
src/common/       mechanistic harness: nodes, mobility, topology, channel,
                  energy, traffic, adversaries, metrics, the round loop
src/routing/      routing substrate from base.pdf: PT_NID/PT_GID/PT_CREV,
                  PFR trust with majority-vote revocation, energy-gated AODV
                  scored by R_Score = a*T + b*E, ECC payload protection
src/a_drl_eaurp/  A — the paper's five models, written from its equations
src/b_senior/     B — the delivered notebook, logic untouched
src/c_ar_eaurp/   C — threat model, GAN detector, LSTM forecaster, CMDP agent
experiments/      E1–E6, plotting, and the comparison report
tests/            26 numpy-only unit tests
tools/            regenerates the Colab notebook from src/
colab/            the deliverable, plus the senior's original notebook
```

`src/` is the single source of truth. The notebook is **generated** from it:

```bash
python tools/build_notebook.py
```

Never hand-edit `colab/REVIEW2_AR_EAURP.ipynb` — regenerate it, or the two
will drift.

## Experiments

| | Sweep | Output |
|---|---|---|
| E1 | Speed 10k–40k, plus a realistic annex | PDR, delay, loss, throughput, lifetime |
| E2 | Density 60–200 nodes | PDR, delay, unroutable traffic |
| **E3** | **Malicious 0–50% × {black-hole, gray-hole, trust poisoning}** | **PDR, delay, detection TPR/FPR** |
| E4 | Linear vs solar energy, long-horizon lifetime | lifetime, LSTM MAE vs baselines |
| E5 | Ablation of C, and CMDP floor feasibility | per-component attribution |
| E6 | Overhead | control packets/round, wall clock, ECC cost |

E3 is the headline, and the only experiment neither base paper can run.

## Verify

```bash
python -m compileall src experiments tests tools
```

```bash
python -m pytest tests/ -q
```

The test that matters most is `test_grayhole_evades_the_trust_threshold`: it
asserts the gray-hole's *observed* Packet Forwarding Ratio stays above
base.pdf's 0.6 revocation threshold (measured: 0.8414, evading it by +0.24).
If that failed, the advancement would have nothing to detect.
