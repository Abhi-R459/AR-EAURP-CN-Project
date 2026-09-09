# AR-EAURP — Review 2 Report

**Adversarial-Resilient and Energy-Harvesting Aware EAURP**

| | Implementation | Source |
|---|---|---|
| **A** | DRL-EAURP, re-implemented from the paper's equations (1)–(38) | `Lekha.pdf` |
| **B** | The senior's delivered code, logic verbatim | `senior_code.ipynb` |
| **C** | AR-EAURP — GAN trust defence, LSTM energy forecasting, CMDP routing | `Date_ 24_07_26.docx` |

> Every number below is read from a results CSV by `tools/make_report.py`.
> None of it is typed in by hand.

---

## 0. Why the evaluation has two tracks

The senior's code is not a network simulator. `src` and `dst` are drawn at
random every round and never connected by a path; delivery is one coin flip
against a global average:

```python
success_prob = 0.45 + 0.25*avg_trust + 0.2*avg_energy + 0.1*avg_mobility
success = random.random() < success_prob      # this is the entire "routing"
```

Consequences, all verifiable in the delivered code:

1. No route exists, so trust never selects a path.
2. `nodes[src].forwarded += 1` and `nodes[dst].received += 1` accumulate the
   forwarding ratio across *unrelated* nodes, so `node.trust` is a drift.
3. `node.malicious` is assigned and then never read by anything.
4. Action 0 always adds `+0.08` and action 1 always `+0.02`, so the Q-learning
   converges to a constant policy and the state has no influence.
5. "Existing" is EAURP's own output times fixed constants (Eq. 14–18).

**A gray-hole that drops 15% of what it relays cannot be expressed in that
model, because nothing relays anything** — and the advancement is entirely
about gray-holes. So the advancement needs real per-hop forwarding, and the
evaluation runs on two tracks: each implementation in its native form
(Track 1), and all three as routing policies on one mechanistic harness with
identical seeds (Track 2).

---

## 1. Track 1 — each implementation in its native form

A is written from Lekha.pdf's equations; B is the delivered notebook with its logic untouched. Both use the paper's own probabilistic model, so these two columns *are* comparable with each other.

| model | A · PDR | B · PDR | A · delay (ms) | B · delay (ms) | A · lifetime | B · lifetime |
|---|---|---|---|---|---|---|
| **Existing** | 0.551 | 0.551 | 125.5 | 125.1 | 587 | 966 |
| **EAURP** | 0.648 | 0.655 | 104.6 | 105.3 | 599 | 988 |
| **ATEAURP** | 0.884 | 0.904 | 93.3 | 92.1 | 599 | 1238 |
| **PSE-EAURP** | 0.892 | 0.932 | 81.3 | 80.8 | 599 | 1234 |
| **DRL-EAURP** | 0.948 | 0.946 | 81.0 | 80.2 | 599 | 1236 |

B reproduces the senior's published figures exactly — PDR `[0.9627, 0.9603, 0.9500, 0.9397, 0.9412, 0.9547, 0.9483]` and packet loss `[35631, 39346, 49325, 56558, 54077, 43027, 50425]` match the stored notebook outputs bit for bit.

### Finding 1 — B's network-lifetime advantage is a constant

Lekha.pdf Eq. (8) specifies one energy drain band, `dE ∈ [0.05, 0.15]`, and Sec. IV-D-6 states the DRL model depletes energy the same way. The delivered code uses `[0.04, 0.12]` for ATEAURP, PSE-EAURP and DRL-EAURP, and `[0.05, 0.15]` only for the base. Running the *same* model under both bands isolates it:

| drain band | network lifetime | PDR |
|---|---|---|
| Eq. (8) `[0.05, 0.15]` | 995.5 | 0.9156 |
| delivered code `[0.04, 0.12]` | 1237.0 | 0.9189 |

**+241.5 rounds** of "lifetime improvement" come from the undocumented constant alone, with the delivery ratio essentially unchanged. The paper attributes a comparable gap to its protocol.

## 2. Track 2 — one harness, identical worlds

Every policy sees byte-identical topology, mobility, traffic, channel and adversary streams for a given seed, so any difference is attributable to the policy alone.

### 2.1 Clean network

| implementation | PDR | PDR (routable) | delay (ms) | throughput |
|---|---|---|---|---|
| AODV (reference baseline) | 0.735 | 0.783 | 74.1 | 17.976 |
| EAURP (base.pdf substrate) | 0.740 | 0.782 | 73.8 | 18.310 |
| A: DRL-EAURP (paper) | 0.733 | 0.778 | 77.3 | 18.090 |
| B: DRL-EAURP (senior code) | 0.735 | 0.780 | 77.2 | 18.153 |
| C: AR-EAURP (advancement) | 0.732 | 0.777 | 77.3 | 18.000 |

`PDR (routable)` excludes packets for which no route existed at all. At the papers' own parameters (N=100, R=150) only ~90.7% of node pairs are mutually reachable before any protocol runs, so that gap is topology, not routing.

### 2.2 Black-hole — advertises a perfect route, drops 100%

| implementation | 0% mal. | 10% mal. | 20% mal. | 30% mal. | 40% mal. | 50% mal. |
|---|---|---|---|---|---|---|
| AODV (reference baseline) | 0.74 / 0.00 | 0.46 / 0.00 | 0.32 / 0.00 | 0.31 / 0.00 | 0.17 / 0.00 | 0.12 / 0.00 |
| EAURP (base.pdf substrate) | 0.76 / 0.00 | 0.40 / 0.65 | 0.25 / 0.53 | 0.22 / 0.37 | 0.11 / 0.31 | 0.08 / 0.24 |
| A: DRL-EAURP (paper) | 0.77 / 0.00 | 0.40 / 0.65 | 0.25 / 0.53 | 0.20 / 0.37 | 0.14 / 0.31 | 0.09 / 0.24 |
| B: DRL-EAURP (senior code) | 0.76 / 0.00 | 0.42 / 0.00 | 0.24 / 0.00 | 0.20 / 0.00 | 0.14 / 0.00 | 0.08 / 0.00 |
| C: AR-EAURP (advancement) | 0.74 / 0.00 | 0.43 / 0.65 | 0.29 / 0.57 | 0.29 / 0.53 | 0.14 / 0.52 | 0.10 / 0.43 |

_Each cell is PDR / detection recall._

### 2.2 Gray-hole — drops ~15%, observed PFR stays at 0.84

| implementation | 0% mal. | 10% mal. | 20% mal. | 30% mal. | 40% mal. | 50% mal. |
|---|---|---|---|---|---|---|
| AODV (reference baseline) | 0.74 / 0.00 | 0.68 / 0.00 | 0.64 / 0.00 | 0.62 / 0.00 | 0.58 / 0.00 | 0.55 / 0.00 |
| EAURP (base.pdf substrate) | 0.76 / 0.00 | 0.70 / 0.00 | 0.67 / 0.03 | 0.63 / 0.00 | 0.60 / 0.00 | 0.57 / 0.00 |
| A: DRL-EAURP (paper) | 0.77 / 0.00 | 0.70 / 0.00 | 0.64 / 0.00 | 0.64 / 0.00 | 0.58 / 0.01 | 0.53 / 0.00 |
| B: DRL-EAURP (senior code) | 0.76 / 0.00 | 0.68 / 0.00 | 0.63 / 0.00 | 0.62 / 0.00 | 0.57 / 0.00 | 0.55 / 0.00 |
| C: AR-EAURP (advancement) | 0.71 / 0.00 | 0.64 / 0.80 | 0.64 / 0.62 | 0.63 / 0.57 | 0.59 / 0.56 | 0.55 / 0.53 |

_Each cell is PDR / detection recall._

### 2.2 Trust poisoning — gray-hole plus PT_GID slander

| implementation | 0% mal. | 10% mal. | 20% mal. | 30% mal. | 40% mal. | 50% mal. |
|---|---|---|---|---|---|---|
| AODV (reference baseline) | 0.74 / 0.00 | 0.67 / 0.00 | 0.60 / 0.00 | 0.59 / 0.00 | 0.53 / 0.00 | 0.51 / 0.00 |
| EAURP (base.pdf substrate) | 0.76 / 0.00 | 0.68 / 0.00 | 0.64 / 0.00 | 0.60 / 0.00 | 0.52 / 0.00 | 0.51 / 0.00 |
| A: DRL-EAURP (paper) | 0.77 / 0.00 | 0.68 / 0.00 | 0.63 / 0.00 | 0.60 / 0.00 | 0.53 / 0.01 | 0.50 / 0.00 |
| B: DRL-EAURP (senior code) | 0.76 / 0.00 | 0.66 / 0.00 | 0.61 / 0.00 | 0.57 / 0.00 | 0.53 / 0.00 | 0.48 / 0.00 |
| C: AR-EAURP (advancement) | 0.76 / 0.00 | 0.71 / 0.65 | 0.66 / 0.50 | 0.62 / 0.45 | 0.55 / 0.42 | 0.52 / 0.56 |

_Each cell is PDR / detection recall._

### Finding 2 — the gray-hole is invisible to everything but C

| implementation | mean detection recall under attack |
|---|---|
| AODV (reference baseline) | 0.000 |
| EAURP (base.pdf substrate) | 0.005 |
| A: DRL-EAURP (paper) | 0.003 |
| B: DRL-EAURP (senior code) | 0.000 |
| C: AR-EAURP (advancement) | 0.617 |

This is the advancement earning its keep. A gray-hole that relays control traffic and small packets but drops a quarter of the packets over 700 bytes keeps its *observed* Packet Forwarding Ratio at **0.8414** — comfortably above base.pdf's 0.6 revocation threshold, so the scalar-PFR trust model of A and B cannot see it at any adversary fraction. Splitting the same observations by packet size opens a gap of **0.25** between the large-packet and small-packet forwarding ratios, and that is the feature the detector is given.

## 3. Inside C — what each component contributes

### 3.1 Ablation (gray-hole @ 30%)

| variant | PDR | detection recall | false-positive rate |
|---|---|---|---|
| C full | 0.631 | 0.600 | 0.057 |
| C without GAN | 0.640 | 0.000 | 0.000 |
| C without LSTM | 0.622 | 0.533 | 0.036 |
| C without CMDP | 0.637 | 0.483 | 0.021 |
| C bare (none) | 0.642 | 0.000 | 0.000 |

### 3.2 Finding 3 — the doc's 90% PDR floor is not reachable

The advancement doc asks for `PDR ≥ 0.90` under 30% adversarial nodes. Sweeping the requested floor shows where the real ceiling sits:

| requested floor | achieved PDR | constraint violation rate |
|---|---|---|
| 0.50 | 0.652 | 0.000 |
| 0.60 | 0.650 | 0.149 |
| 0.70 | 0.655 | 0.775 |
| 0.80 | 0.648 | 0.998 |
| 0.90 | 0.631 | 0.998 |

On a topology where ~9% of node pairs are unreachable before any attack, a 0.90 floor cannot be met, and the Lagrangian multiplier climbs without ever satisfying the constraint. This confirms the feasibility risk already flagged in the Review 1 critique — measured, rather than assumed. Re-scoping the constraint is Review 3 work.

### 3.3 Overhead

| implementation | control packets / round | wall clock (s) |
|---|---|---|
| AODV (reference baseline) | 13.5 | 0.6 |
| EAURP (base.pdf substrate) | 13.5 | 0.5 |
| A: DRL-EAURP (paper) | 13.5 | 0.7 |
| B: DRL-EAURP (senior code) | 13.5 | 0.6 |
| C: AR-EAURP (advancement) | 13.5 | 2.0 |

## 4. What is and isn't comparable

```
1. TRACK 1 AND TRACK 2 ARE NOT THE SAME EXPERIMENT.
   Track 1 numbers come from the papers' own probabilistic model: no routes, no
   relays, delivery decided by one coin flip against a global average. Track 2
   numbers come from a mechanistic simulator that walks every packet hop by hop
   through a real topology. A Track 1 PDR of 0.96 and a Track 2 PDR of 0.79 are
   not in disagreement; they are measuring different things. Compare within a
   track, never across.

2. B'S HEADLINE NUMBERS ARE PARTLY LITERALS.
   Cell 13 of senior_code.ipynb prints random.uniform values formatted as
   measured metrics (PDR 89.04, delay 498.64 ms, throughput 17.46 kbps,
   lifetime 99.28%). Those exact figures appear in Lekha.pdf Sec. IV-A-6 as
   "observed behaviour". Re-running the cell produces different values, because
   nothing is being measured. The simulated curves (the five models' sweeps)
   are genuinely computed; the summary block is not.

3. "EXISTING" IS NOT A PROTOCOL.
   Lekha.pdf Eq. (14)-(18) derives it by multiplying EAURP's own output by
   fixed constants. Every "improvement over Existing" is therefore arithmetic
   by construction. Track 2 replaces it with a real AODV implementation.

4. B'S LIFETIME ADVANTAGE IS A CONSTANT, NOT A PROTOCOL.
   Eq. (8) specifies one drain band. The delivered code uses a gentler one for
   the three proposed models. Running the same model under both bands isolates
   the effect; see the drain-band ablation above.

5. C IS EXPECTED TO LOOK WORSE THAN B ON RAW PDR IN TRACK 1.
   B computes delivery from a formula; C routes real packets through real
   adversaries across a topology in which about 9% of node pairs are not even
   connected. The comparison that means something is the Track 2 attack sweep,
   where both face the same world.

6. THE CHANNEL MODEL IS OUR ASSUMPTION.
   Neither paper contains a PHY or link model, so the per-hop reliability in
   Track 2 is a modelling choice, calibrated so a clean network lands in the
   same PDR regime the papers report. Conclusions rest on relative comparisons
   under identical channel settings, never on absolute values.

7. THE 90% PDR FLOOR IN THE ADVANCEMENT DOC MAY BE INFEASIBLE.
   The doc asks for PDR >= 0.90 under 30% adversarial nodes. On a topology
   where ~9% of pairs are unreachable before any attack, that ceiling cannot be
   reached, and the Lagrangian multiplier rises without ever satisfying the
   constraint. The CMDP feasibility table above measures where the real ceiling
   is instead of assuming one. This confirms the risk flagged in the Review 1
   critique.

8. A'S TRACK 1 LIFETIME IS CENSORED UNDER THE QUICK PROFILE.
   B always runs the senior's hardcoded SIM_ROUNDS = 2000. A runs 2000 only
   under --profile full; the quick profile stops it at 600, before any node has
   drained, so A's lifetime column reads as the run length rather than a first
   death. Compare the A and B lifetime columns only from a full-profile run --
   or use the drain-band ablation above, which controls for this directly.

9. DETECTION RATES ARE MEASURED AGAINST GROUND TRUTH.
   TPR and FPR compare each protocol's own verdicts with the known roles
   assigned by the threat model. B reports 0.00 everywhere because the
   delivered code sets node.malicious and never reads it - that is the honest
   consequence of the code, not a failure to measure it.
```

---

## 5. Status against the Review 2 brief

| Requirement | Status |
|---|---|
| Implement the base paper (A) | Done — all five models of Lekha.pdf from Eq. (1)–(38) |
| Include the senior's paper (B) | Done — logic verbatim; reproduces the published numbers bit-for-bit |
| Implement the advancement (C) | Done — threat model, GAN detector, LSTM forecaster, CMDP agent |
| Compare A, B and C honestly | Done — two tracks, with the caveats above stated rather than buried |
| Syntax-free execution | `python -m compileall src experiments tests tools` is clean; 26 unit tests pass |

### Known weaknesses, measured rather than hidden — all Review 3 work

**The discriminator contributes nothing.** Decomposing C's anomaly score on held-out attacked traffic: the generator's reconstruction residual scores AUC 0.969, the discriminator scores **0.056** — strongly *anti*-correlated, i.e. it confidently rates attacked behaviour as more "real" than honest behaviour. That is not a training bug; a discriminator separates real from generated, never normal from abnormal, and attacked samples are real. Its weight is therefore set to zero on evidence, and detection rests entirely on the generator's learned manifold (the AnoGAN residual). The discriminator score is still computed and reported so the claim stays checkable.

**Feature scaling was the whole ballgame.** The informative features have exactly zero variance across honest behaviour — an honest relay never drops a large packet. The conventional guard `std[std==0] = 1.0` asserts the opposite and flattens the signal: measured, it put validation AUC at 0.614 and gray-hole recall at **0.03**. Flooring the standard deviation at a small value instead took AUC to **0.967** and recall to ~0.6. Worth stating plainly at the review, because the failure was silent — the detector ran, produced numbers, and detected almost nothing.

**The GAN is over-provisioned for this feature space.** Losses barely move and validation AUC is flat at 0.963–0.968 across 60, 300 and 800 epochs. The generator spans an 8-dimensional, tightly-clustered manifold almost immediately, so more training neither helps nor hurts. A smaller model, or a straight one-class method, would likely do the same job more cheaply.

**The LSTM beats persistence but loses to seasonal-naive.** Measured MAE: LSTM 0.0150, persistence 0.0184, seasonal-naive 0.0092. The harvest signal is a diurnal sinusoid, so "same time yesterday" is a very strong baseline. The LSTM is not yet earning its place, which is exactly the risk the Review 1 critique raised.

**Remaining:** gray-hole recall is ~0.6, not 1.0, and the detection threshold is an untuned 95th percentile of clean scores. Under trust poisoning at 40–50% adversaries C's false-positive rate climbs — the slander attack partially succeeds. The CMDP floor of 0.90 is infeasible here and needs re-scoping.
