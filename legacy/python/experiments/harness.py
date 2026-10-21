"""Shared experiment plumbing: policy registry, sweeps, CSV checkpointing.

Checkpointing matters on Colab. Every sweep writes its CSV as soon as it
finishes and checks for that file on start, so a session that disconnects
half-way through costs only the sweep that was in flight rather than the whole
run. Set ``AR_EAURP_RESULTS`` (or pass ``out_dir``) to a Google Drive path and
results survive the session entirely.
"""

import csv
import os
import time

import numpy as np

from src.a_drl_eaurp.policy_common import TabularDrlPolicy
from src.b_senior.policy_common import SeniorDrlPolicy
from src.c_ar_eaurp.protocol import ArEaurpPolicy
from src.common import config, metrics as metrics_mod, seeding
from src.common.simulator import SimParams, Simulation
from src.routing.eaurp import AodvPolicy, EaurpPolicy

DEFAULT_OUT = os.environ.get("AR_EAURP_RESULTS", "results")
BASE_SEED = 20260909


def out_path(*parts, **kwargs):
    """Build a path under the results directory, creating parents."""
    root = kwargs.get("out_dir") or DEFAULT_OUT
    path = os.path.join(root, *parts)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def csv_path(name, out_dir=None):
    return out_path("csv", name, out_dir=out_dir)


# --------------------------------------------------------------------------
# Policy registry
# --------------------------------------------------------------------------

def make_policies(shared_c=None):
    """The Track-2 line-up. ``shared_c`` reuses one pre-trained AR-EAURP."""
    return [
        ("AODV (reference baseline)", lambda: AodvPolicy()),
        ("EAURP (base.pdf substrate)", lambda: EaurpPolicy()),
        ("A: DRL-EAURP (paper)", lambda: TabularDrlPolicy()),
        ("B: DRL-EAURP (senior code)", lambda: SeniorDrlPolicy()),
        ("C: AR-EAURP (advancement)", (lambda: shared_c) if shared_c else
         (lambda: ArEaurpPolicy())),
    ]


def pretrained_c(profile, n_nodes=100, seed=9001, verbose=True, **kwargs):
    """Train C's detector and forecaster once and reuse across the sweeps."""
    policy = ArEaurpPolicy(**kwargs)
    summary = policy.pretrain(
        n_nodes=n_nodes,
        rounds=max(200, profile.rounds),
        seed=seed,
        gan_epochs=profile.gan_epochs,
        lstm_epochs=profile.lstm_epochs,
        verbose=verbose,
    )
    return policy, summary


# --------------------------------------------------------------------------
# Sweeps
# --------------------------------------------------------------------------

def run_config(policy_factory, params, runs, base_seed=BASE_SEED):
    """Run one configuration over ``runs`` seeds and average the results."""
    rows = []
    for run_index in range(int(runs)):
        params.seed = seeding.run_seed(base_seed, run_index)
        policy = policy_factory()
        rows.append(Simulation(policy, params).run())
    aggregated = metrics_mod.aggregate(rows)
    return aggregated


def sweep(name, configs, runs, out_dir=None, resume=True, verbose=True,
          base_seed=BASE_SEED):
    """Run a list of ``(label, policy_factory, SimParams, extra)`` configs.

    Returns the rows and writes them to ``csv/<name>.csv``.
    """
    path = csv_path(name + ".csv", out_dir=out_dir)
    if resume and os.path.exists(path):
        if verbose:
            print("  [skip] {0} already present at {1}".format(name, path))
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle)), path

    rows = []
    started = time.perf_counter()
    for index, (label, factory, params, extra) in enumerate(configs, start=1):
        row = run_config(factory, params, runs, base_seed=base_seed)
        row["label"] = label
        row.update(extra or {})
        rows.append(row)
        if verbose:
            print("  [{0}/{1}] {2:44s} PDR={3:.3f} routable={4:.3f} "
                  "delay={5:6.1f} TPR={6:.2f} FPR={7:.2f}".format(
                      index, len(configs), label[:44],
                      row.get("pdr", 0.0), row.get("pdr_routable", 0.0),
                      row.get("avg_delay_ms", 0.0),
                      row.get("det_tpr", 0.0), row.get("det_fpr", 0.0)))

    write_rows(rows, path)
    if verbose:
        print("  -> {0}  ({1:.1f}s)".format(path, time.perf_counter() - started))
    return rows, path


def write_rows(rows, path):
    """Write dict rows to CSV, unioning keys across rows."""
    if not rows:
        return path
    fieldnames = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return path


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(rows, key, default=0.0):
    """Pull a numeric column out of CSV-read (string-valued) rows."""
    out = []
    for row in rows:
        try:
            out.append(float(row.get(key, default)))
        except (TypeError, ValueError):
            out.append(default)
    return np.asarray(out)
