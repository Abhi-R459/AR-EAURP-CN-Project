"""Generate the self-contained Colab notebook from the source tree.

    python tools/build_notebook.py

``src/`` is the single source of truth. This walks it, emits one ``%%writefile``
cell per module, and appends the setup, run and analysis cells. Regenerate after
every code change; never hand-edit the ``.ipynb``, or the two will drift.

The result is one file: upload it to Colab, Runtime > Run all, done. No Drive
required (though it is used for checkpointing if you allow it), no GitHub, no
pip install beyond a guard cell that only acts if something is genuinely absent.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Two notebooks are generated from the same source tree and the same analysis
# cells; only the way the code reaches Colab differs.
#
#   selfcontained  40 %%writefile cells carry the project inside the notebook.
#                  Works with no network, no GitHub and no account. Long.
#   github         one git clone. Short, and guaranteed to match the repo,
#                  which makes it the better default now that the repo exists.
MODE_SELFCONTAINED = "selfcontained"
MODE_GITHUB = "github"

REPO_URL = "https://github.com/Abhi-R459/AR-EAURP-CN-Project.git"
CLONE_DIR = "/content/AR-EAURP-CN-Project"

OUTPUTS = {
    MODE_SELFCONTAINED: os.path.join(ROOT, "colab", "REVIEW2_AR_EAURP.ipynb"),
    MODE_GITHUB: os.path.join(ROOT, "colab", "REVIEW2_FROM_GITHUB.ipynb"),
}
OUTPUT = OUTPUTS[MODE_SELFCONTAINED]

# Order matters only for readability; Python resolves imports at call time.
MODULE_ORDER = [
    "src/__init__.py",
    "src/common/__init__.py",
    "src/common/config.py",
    "src/common/seeding.py",
    "src/common/node.py",
    "src/common/mobility.py",
    "src/common/topology.py",
    "src/common/channel.py",
    "src/common/energy.py",
    "src/common/traffic.py",
    "src/common/adversary.py",
    "src/common/metrics.py",
    "src/routing/__init__.py",
    "src/routing/packets.py",
    "src/routing/ecc.py",
    "src/routing/aodv.py",
    "src/routing/trust.py",
    "src/common/simulator.py",
    "src/routing/eaurp.py",
    "src/a_drl_eaurp/__init__.py",
    "src/a_drl_eaurp/paper_model.py",
    "src/a_drl_eaurp/variants.py",
    "src/a_drl_eaurp/run_track1.py",
    "src/a_drl_eaurp/policy_common.py",
    "src/b_senior/__init__.py",
    "src/b_senior/senior_asis.py",
    "src/b_senior/policy_common.py",
    "src/c_ar_eaurp/__init__.py",
    "src/c_ar_eaurp/threat_model.py",
    "src/c_ar_eaurp/gan_detector.py",
    "src/c_ar_eaurp/lstm_energy.py",
    "src/c_ar_eaurp/cmdp_agent.py",
    "src/c_ar_eaurp/protocol.py",
    "experiments/__init__.py",
    "experiments/harness.py",
    "experiments/sweeps.py",
    "experiments/plots.py",
    "experiments/report.py",
    "experiments/run_all.py",
    "tests/test_harness.py",
]


def markdown(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").split("\n")}


def code(text, collapsed=False):
    metadata = {}
    if collapsed:
        metadata = {"cellView": "form", "jupyter": {"source_hidden": True}}
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata,
        "outputs": [],
        "source": text.strip("\n").split("\n"),
    }


def writefile_cell(relative_path):
    """One ``%%writefile`` cell carrying a module verbatim."""
    absolute = os.path.join(ROOT, relative_path)
    with open(absolute, "r", encoding="utf-8") as handle:
        body = handle.read()
    header = "%%writefile {0}".format(relative_path)
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"jupyter": {"source_hidden": True}},
        "outputs": [],
        "source": [header + "\n"] + body.splitlines(keepends=True),
    }


def build(mode=MODE_SELFCONTAINED):
    if mode not in OUTPUTS:
        raise ValueError("unknown mode {0!r}".format(mode))
    cells = []

    how_code_arrives = {
        MODE_SELFCONTAINED: (
            "> **How the code gets here:** this notebook carries the whole "
            "project inside it. Section 0.1 is 40 folded `%%writefile` cells "
            "that create `src/`, `experiments/` and `tests/` in the session. "
            "They render as an empty-looking gap, which is exactly why `src/` "
            "goes missing if you skip them. Nothing is downloaded.\n>\n"
            "> Prefer **`REVIEW2_FROM_GITHUB.ipynb`** if you would rather it "
            "clone the repository - that one is a tenth the size and always "
            "matches the latest commit."
        ),
        MODE_GITHUB: (
            "> **How the code gets here:** section 0.1 clones "
            "[the repository](" + REPO_URL.replace(".git", "") + ") into the "
            "session and changes into it, so `src/` and everything else is "
            "present on disk. Re-run that cell any time to pull the latest "
            "commit.\n>\n"
            "> Use **`REVIEW2_AR_EAURP.ipynb`** instead if you need a version "
            "that works with no network and no GitHub - it embeds every source "
            "file directly."
        ),
    }[mode]

    cells.append(markdown("""
# AR-EAURP - Review 2

**Adversarial-Resilient and Energy-Harvesting Aware EAURP**

Three implementations and an honest comparison:

| | What it is | Source |
|---|---|---|
| **A** | DRL-EAURP, re-implemented from the paper's equations (1)-(38) | `Lekha.pdf` |
| **B** | The senior's delivered code, logic verbatim | `senior_code.ipynb` |
| **C** | AR-EAURP - GAN trust defence + LSTM energy forecasting + CMDP | `Date_ 24_07_26.docx` |

Run order: **Runtime > Run all**. Section 0 puts the project into the Colab
session, then Track 1 and Track 2 run in turn.

__HOW_CODE_ARRIVES__

---

### Read this before reading any number below

The senior's code is not a network simulator; it is a metric generator.
`src` and `dst` are drawn at random every round and never connected by a path,
and delivery is a single coin flip against a *global average*:

```python
success_prob = 0.45 + 0.25*avg_trust + 0.2*avg_energy + 0.1*avg_mobility
success = random.random() < success_prob      # <- this is the entire "routing"
```

Because nothing forwards anything, a gray-hole that drops 15% of the packets it
relays **cannot be expressed in that model at all** - and the whole advancement
is about gray-holes. So the evaluation runs on two tracks:

* **Track 1 (as-is)** - each implementation in its native form. Preserves the
  senior's published numbers.
* **Track 2 (common harness)** - A, B and C as routing policies on one
  mechanistic simulator where packets are walked hop by hop, with identical
  seeds, topology, mobility, traffic and adversary placement. This is where the
  fair comparison and the attack sweep live.
""".replace("__HOW_CODE_ARRIVES__", how_code_arrives)))

    # ---------------------------------------------------------------- setup
    cells.append(markdown("## 0. Setup"))

    cells.append(code("""
# Dependency guard. Colab already ships everything needed, so this normally
# installs nothing at all and just prints what it found.
import importlib, subprocess, sys

REQUIRED = ["numpy", "matplotlib", "networkx", "pandas", "torch"]
missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]

if missing:
    print("installing:", missing)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + missing)
else:
    print("all dependencies already present - nothing to install")

import numpy, matplotlib, networkx
print("numpy", numpy.__version__, "| matplotlib", matplotlib.__version__,
      "| networkx", networkx.__version__)
try:
    import torch
    print("torch", torch.__version__, "| CUDA:", torch.cuda.is_available())
except Exception as exc:
    print("torch unavailable ->", exc)
    print("The GAN/LSTM/DQN will fall back to their documented non-learned")
    print("baselines and every result will say so explicitly.")
"""))

    if mode == MODE_GITHUB:
        cells.append(markdown(
            "### 0.1 Fetch the project from GitHub\n\n"
            "This clones the repository into the Colab session and changes into "
            "it, so every relative path (`src/`, `results/`, `tests/`) resolves. "
            "Re-running the cell pulls the latest commit instead of cloning "
            "again, so you can pick up changes without restarting the runtime."
        ))
        cells.append(code("""
import os, subprocess, sys

REPO_URL  = "{repo}"
CLONE_DIR = "{clone}"

if os.path.isdir(os.path.join(CLONE_DIR, ".git")):
    print("already cloned - pulling latest")
    subprocess.run(["git", "-C", CLONE_DIR, "pull", "--ff-only", "--quiet"],
                   check=False)
else:
    print("cloning", REPO_URL)
    subprocess.run(["git", "clone", "--depth", "1", "--quiet",
                    REPO_URL, CLONE_DIR], check=True)

# chdir matters: the experiment scripts write to relative paths like
# results/csv, and the package is imported as `src.*` from the repo root.
os.chdir(CLONE_DIR)
if CLONE_DIR not in sys.path:
    sys.path.insert(0, CLONE_DIR)

print("working directory:", os.getcwd())
print("commit:", subprocess.run(["git", "log", "-1", "--oneline"],
                                capture_output=True, text=True).stdout.strip())
print("contents:", sorted(p for p in os.listdir(".") if not p.startswith(".")))
""".format(repo=REPO_URL, clone=CLONE_DIR)))

    cells.append(code("""
# Optional: mount Google Drive so results survive a disconnected session.
# Every sweep writes its CSV the moment it finishes and is skipped on re-run,
# so a dropped session costs only the sweep that was in flight.
import os

RESULTS_DIR = "results"
try:
    from google.colab import drive
    drive.mount("/content/drive")
    RESULTS_DIR = "/content/drive/MyDrive/cn_project_lekha/results"
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print("checkpointing results to", RESULTS_DIR)
except Exception as exc:
    print("Drive not mounted (", exc, ")")
    print("-> results stay in this session at ./results and are zipped at the end")

os.environ["AR_EAURP_RESULTS"] = RESULTS_DIR
"""))

    if mode == MODE_SELFCONTAINED:
        cells.append(code("""
# Create the package directories before the %%writefile cells below run.
import os
for path in ["src/common", "src/routing", "src/a_drl_eaurp", "src/b_senior",
             "src/c_ar_eaurp", "experiments", "tests", "results/csv",
             "results/figures"]:
    os.makedirs(path, exist_ok=True)
print("source tree ready")
"""))

        cells.append(markdown(
            "### 0.1 Source modules\n\n"
            "**These cells are what create `src/`.** They are folded away "
            "because they duplicate the files in the repository, so the section "
            "looks like an empty gap - but if you skip them, nothing below can "
            "import and `src/` will not exist in the file browser. Run the "
            "notebook from the top, or Runtime > Run all.\n\n"
            "The notebook is generated from the source tree by "
            "`tools/build_notebook.py`, so the two cannot drift."
        ))

        for relative_path in MODULE_ORDER:
            cells.append(writefile_cell(relative_path))

    cells.append(code("""
import sys
if "" not in sys.path:
    sys.path.insert(0, "")

# Fail loudly here rather than three cells later.
from src.common import config
from src.common.simulator import SimParams, Simulation
from src.routing.eaurp import AodvPolicy, EaurpPolicy
from src.a_drl_eaurp.policy_common import TabularDrlPolicy
from src.b_senior.policy_common import SeniorDrlPolicy
from src.c_ar_eaurp.protocol import ArEaurpPolicy

print("imports OK")
print("profile FULL: rounds={0}, runs={1}".format(
    config.FULL.rounds, config.FULL.runs))
"""))

    cells.append(markdown(
        "### 0.2 Self-check\n\n"
        "26 unit tests over the harness. The one that matters most is "
        "`test_grayhole_evades_the_trust_threshold`: it asserts that the "
        "gray-hole's *observed* Packet Forwarding Ratio stays above base.pdf's "
        "0.6 revocation threshold. If that failed, the advancement would have "
        "nothing to detect."
    ))

    cells.append(code("""
!python -m pytest tests/ -q 2>&1 | tail -5
"""))

    cells.append(code("""
# The premise of the whole advancement, measured rather than asserted.
import numpy as np
from src.common import seeding, node as nm, config, adversary
from src.routing import trust as trust_mod

bundle = seeding.make_seed_bundle(11)
nodes = nm.NodeState(20, bundle.topology)
nodes.role[3] = nm.FLAG_GRAYHOLE

class _Pkt:
    def __init__(self, size): self.size = size
    @property
    def is_large(self): return self.size >= config.LARGE_PACKET_THRESHOLD

rng = np.random.default_rng(21)
for _ in range(20000):
    pkt = _Pkt(int(rng.integers(512, 1025)))
    trust_mod.observe_forward(nodes, 0, 3, pkt,
                              adversary.forwards_data(nodes, 3, pkt, bundle.adversary))

pfr = nodes.observed_pfr()[0, 3]
large = nodes.fwd_seen_large[0, 3] / nodes.sent_large[0, 3]
small = nodes.fwd_seen_small[0, 3] / nodes.sent_small[0, 3]
print("observed scalar PFR   = {:.4f}   (revocation threshold {})".format(
    pfr, config.TRUST_THRESHOLD))
print("  -> evades it by       {:+.4f}".format(pfr - config.TRUST_THRESHOLD))
print("large-packet PFR      = {:.4f}".format(large))
print("small-packet PFR      = {:.4f}".format(small))
print("size-conditioned gap  = {:.4f}   <- the signal the GAN detector is given"
      .format(small - large))
"""))

    # ---------------------------------------------------------------- track 1
    cells.append(markdown("""
---
## 1. Track 1 - each implementation in its native form

### 1A. A - DRL-EAURP from `Lekha.pdf`

Written from the published equations alone. All five of the paper's models:
Existing (Eq. 14-18), EAURP (Eq. 4-13), ATEAURP (Eq. 19-24), PSE-EAURP
(Eq. 25-28) and DRL-EAURP (Eq. 3, 29-38).

Where the paper is under-specified, the assumption is recorded in
`paper_model.py` and listed in `DEVIATIONS`.
"""))

    cells.append(code("""
from src.a_drl_eaurp import run_track1 as a_track1
from src.a_drl_eaurp import paper_model as pm

a_speed, a_policy_notes = a_track1.run_speed_sweep(rounds=2000, runs=3)
a_density = a_track1.run_density_sweep(rounds=2000, runs=3, verbose=False)
a_track1.write_csv(a_track1.to_rows(a_speed, a_density),
                   os.path.join(RESULTS_DIR, "csv", "a_paper_track1.csv"))
"""))

    cells.append(markdown(
        "#### The DRL agent's action space is degenerate\n\n"
        "Eq. (36) gives action 0 a `+0.08` bonus and action 1 a `+0.02` bonus, "
        "unconditionally. Action 0 therefore dominates in every state, the "
        "optimal policy is the constant \"always exploit\", and the learned "
        "state `<T,E,M>` has no influence on anything. Measured below rather "
        "than asserted."
    ))

    cells.append(code("""
for speed, note in sorted(a_policy_notes.items())[:3]:
    print("v={:6d}  states visited={:3d}  action-0 share={:.3f}  "
          "states preferring action 0: {}/{}".format(
              speed, note["q_states_visited"], note["action0_share"],
              note["states_preferring_action0"], note["states_total"]))
"""))

    cells.append(markdown(
        "#### Where does the 'network lifetime improvement' come from?\n\n"
        "Eq. (8) specifies one energy drain band, `dE in [0.05, 0.15]`, and "
        "Sec. IV-D-6 says the DRL model depletes energy the same way. The "
        "delivered code uses `[0.04, 0.12]` for ATEAURP, PSE-EAURP and "
        "DRL-EAURP, and `[0.05, 0.15]` only for the base. Running the *same* "
        "model under both bands isolates the effect."
    ))

    cells.append(code("""
ablation = a_track1.drain_band_ablation(rounds=1400, runs=3)
for band in ("paper_Eq8_0.05-0.15", "code_0.04-0.12"):
    print("{:22s} lifetime={:8.1f}   PDR={:.4f}".format(
        band, ablation[band]["network_lifetime"], ablation[band]["pdr"]))
print()
print("=> {:+.1f} rounds of 'lifetime improvement' come from the drain "
      "constant alone,".format(ablation["lifetime_delta"]))
print("   with the delivery ratio essentially unchanged.")
"""))

    cells.append(code("""
import textwrap
print("DEVIATIONS between Lekha.pdf and the delivered code")
print("=" * 74)
for item in pm.DEVIATIONS:
    print()
    print(item["topic"].upper())
    for field in ("paper", "code", "impact"):
        print("  {:7s}: {}".format(
            field, textwrap.fill(item[field], 66, subsequent_indent=" " * 11)))
"""))

    cells.append(markdown("""
### 1B. B - the senior's code, verbatim

Logic copied character-for-character; the only additions are a `main()` guard,
a headless matplotlib backend and CSV output. `random.seed(42)` is set in the
same place the notebook sets it, so the published numbers reproduce exactly.

This cell takes ~3 minutes: the original does an O(N^2) neighbour rebuild in
pure Python on every one of 2000 rounds.
"""))

    cells.append(code("""
from src.b_senior import senior_asis

b_results = senior_asis.run_all(runs=5)
senior_asis.write_csv(senior_asis.to_rows(b_results),
                      os.path.join(RESULTS_DIR, "csv", "b_senior_as_is.csv"))

print()
print("Published in Lekha.pdf:      PDR up to 0.96, delay ~80 ms, "
      "lifetime ~1230 rounds")
print("Reproduced here:             PDR {:.4f},  delay {:.2f} ms,  "
      "lifetime {:.0f}".format(
          max(b_results["DRL-EAURP"]["pdr"]),
          min(b_results["DRL-EAURP"]["delay"]),
          sum(b_results["DRL-EAURP"]["lifetime"]) / 7.0))
"""))

    cells.append(markdown(
        "#### Which of B's numbers are measured?\n\n"
        "Cell 13 of the original notebook prints `random.uniform` literals "
        "formatted as measured metrics. Those exact values appear in "
        "Lekha.pdf Sec. IV-A-6 as \"observed behaviour\". Re-running it "
        "produces different numbers every time, because nothing is being "
        "measured."
    ))

    cells.append(code("""
print("Cell 13 of senior_code.ipynb, run three times:")
for attempt in range(3):
    block = senior_asis.hardcoded_metrics_block()
    print("  PDR={PacketDeliveryRatio:6.2f}  delay={AverageDelaynsec:7.2f}  "
          "throughput={Throughput_kbps:5.2f}  lifetime={NetworkLifetime_percentage:5.2f}%"
          .format(**block))
print()
for key, value in senior_asis.PROVENANCE.items():
    print("  {:20s} {}".format(key, value))
"""))

    # ---------------------------------------------------------------- track 2
    cells.append(markdown("""
---
## 2. Track 2 - one harness, identical worlds

Every policy below sees byte-identical topology, mobility, traffic, channel and
adversary streams for a given seed (six independent generators spawned from one
`SeedSequence`), so any difference in the numbers is attributable to the policy
and nothing else.

### 2.1 Pre-training C

The GAN is trained on a **clean commissioning run with no adversaries present**,
then frozen. It never sees an attack before being evaluated on one. The LSTM is
trained on generated harvest traces and scored against two naive baselines.
"""))

    cells.append(code("""
from experiments.harness import pretrained_c
from src.common import config

PROFILE = config.FULL          # switch to config.QUICK for a fast smoke run
shared_c, pretrain_summary = pretrained_c(PROFILE, verbose=True)

for key in sorted(pretrain_summary):
    print("  {:34s} {}".format(key, pretrain_summary[key]))
"""))

    cells.append(code("""
from experiments import plots

plots.plot_gan_training(shared_c.detector, out_dir=RESULTS_DIR)
plots.plot_lstm_accuracy(shared_c.predictor, out_dir=RESULTS_DIR)

evaluation = shared_c.predictor.evaluation
print()
print("LSTM vs baselines (MAE, lower is better)")
print("  LSTM            {:.6f}".format(evaluation.get("lstm_mae", float("nan"))))
print("  persistence     {:.6f}".format(evaluation.get("persistence_mae", float("nan"))))
print("  seasonal naive  {:.6f}".format(evaluation.get("seasonal_naive_mae", float("nan"))))
print()
print("  beats persistence:    ", evaluation.get("beats_persistence"))
print("  beats seasonal naive: ", evaluation.get("beats_seasonal_naive"))
if not evaluation.get("beats_seasonal_naive"):
    print()
    print("  NOTE: the harvest signal is a diurnal sinusoid, so a")
    print("  'same time yesterday' lookup is a strong baseline. Reported as")
    print("  measured - this is exactly the risk the Review 1 deck flagged.")
"""))

    cells.append(markdown("""
### 2.2 E1-E2 - speed and density

The paper's own sweeps, run on the mechanistic harness.
"""))

    cells.append(code("""
from experiments import sweeps

sweeps.e1_speed(PROFILE, shared_c=shared_c, out_dir=RESULTS_DIR)
sweeps.e2_density(PROFILE, shared_c=shared_c, out_dir=RESULTS_DIR)
"""))

    cells.append(markdown("""
### 2.3 E3 - the attack sweep

**The headline experiment, and the one neither base paper can run.**

Three attacks x six adversary fractions (0-50%) x every implementation:

* **black-hole** - advertises a perfect route, drops 100% of the data
* **gray-hole** - relays control and small packets, drops ~25% of packets over
  700 bytes. Observed PFR ~0.84, comfortably above the 0.6 revocation threshold
* **trust poisoning** - a gray-hole that also publishes false PT_GID reports:
  trust 1.0 for its colluders, 0.15 for the most trusted honest nodes
"""))

    cells.append(code("""
sweeps.e3_attack(PROFILE, shared_c=shared_c, out_dir=RESULTS_DIR)
"""))

    cells.append(markdown("""
### 2.4 E4-E6 - energy, ablation, overhead
"""))

    cells.append(code("""
sweeps.e4_energy(PROFILE, shared_c=shared_c, out_dir=RESULTS_DIR)
sweeps.e5_ablation(PROFILE, out_dir=RESULTS_DIR)
sweeps.e6_overhead(PROFILE, shared_c=shared_c, out_dir=RESULTS_DIR)
"""))

    # ---------------------------------------------------------------- figures
    cells.append(markdown("""
---
## 3. Figures
"""))

    cells.append(code("""
from experiments import plots
import glob
from IPython.display import Image, display

plots.plot_all(out_dir=RESULTS_DIR)

for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "figures", "*.png"))):
    print(os.path.basename(path))
    display(Image(filename=path))
"""))

    # ---------------------------------------------------------------- report
    cells.append(markdown("""
---
## 4. A vs B vs C - the comparison
"""))

    cells.append(code("""
from experiments.report import build_comparison, print_report

report = build_comparison(out_dir=RESULTS_DIR)
print_report(report)
"""))

    cells.append(code("""
# Bundle everything for download.
import shutil
archive = shutil.make_archive("ar_eaurp_review2_results", "zip", RESULTS_DIR)
print("wrote", archive)
try:
    from google.colab import files
    files.download(archive)
except Exception:
    print("(not on Colab, or download unavailable - the zip is on disk)")
"""))

    notebook = {
        "cells": cells,
        "metadata": {
            "colab": {"provenance": [], "toc_visible": True},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }

    destination = OUTPUTS[mode]
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(notebook, handle, indent=1, ensure_ascii=False)

    size = os.path.getsize(destination)
    embedded = len(MODULE_ORDER) if mode == MODE_SELFCONTAINED else 0
    print("wrote {0}".format(destination))
    print("  mode={0}, {1} cells, {2:.0f} KB, {3} modules embedded".format(
        mode, len(cells), size / 1024.0, embedded))
    return destination


if __name__ == "__main__":
    requested = sys.argv[1:] or [MODE_SELFCONTAINED, MODE_GITHUB]
    for name in requested:
        build(name)
    sys.exit(0)
