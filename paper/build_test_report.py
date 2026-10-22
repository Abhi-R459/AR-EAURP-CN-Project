"""Assemble the complete test evidence document from saved project results."""
from pathlib import Path
import csv
import json
import re
import statistics as st

ROOT = Path(__file__).resolve().parents[1]
result = ROOT / 'results/ns3-native-paper-review'
text = (result / 'paper_results.md').read_text(encoding='utf-8-sig')
text = text.split('\n', 1)[1]
text = re.sub(r'\]\(figures/([^)]*)\.svg\)', r'](../results/ns3-native-paper-review/figures/\1.png)', text)
intro = '''---
title: "AR-EAURP: Complete Test Results and Findings"
author: "AR-EAURP Project"
date: "22 October 2026"
---

## Scope and evidence inventory

This document records the saved test results and the findings available on 22 October 2026. It accompanies the research manuscript and contains the detailed native ns-3 experiment tables, simulation settings, uncertainty estimates, all 180 E3 pairwise PDR contrasts, the separate CMDP commissioning study, exploratory tuning groups, an earlier native validation snapshot, and historical Python results.

The main native review matrix contains **179/181 conditions and 863/905 planned runs**. The remaining 42 density replications were deferred. Missing results are not imputed. The 30 matched CMDP commissioning pairs are a separate study with a different seed/run range, not an extension of the matrix's sample size. All numbers below come from saved artifacts; no additional simulation was run while preparing this document.

The evidence does not establish general AR-EAURP superiority. A positive PDR point estimate and a confidence interval spanning zero are reported as inconclusive. The single exploratory E3 interval excluding zero is unadjusted for multiple comparisons.

**Timing clarification:** the base native parameter `time=120` is the scenario duration, including the 20 s warm-up. The saved simulator metric `measurement_seconds` is 100 s; six 1-packet/s flows therefore send 600 measured application packets. Cooldown adds a further 10 s to allow final arrivals. Some earlier prose calls this a “120 s evaluation”; the exact metric window is 100 s, as recorded in the raw checkpoints. Clean commissioning is separate.

'''
parts = [intro, text]
opt = (ROOT / 'results/optimization_study/README.md').read_text(encoding='utf-8-sig')
opt = re.sub(r'^## ', '### ', opt, flags=re.M)
opt = re.sub(r'^# .+\n', '## Separate CMDP commissioning study\n', opt, count=1)
parts.append(opt)
parts.append('''
## All saved exploratory optimization groups

The following table inventories every saved JSON group in the optimization study. These exploratory groups include earlier code states and different run ranges, and must not be pooled into a single confirmatory comparison. The held-out commissioning estimate is the separately reported 30-pair result above.

| Folder / candidate | Saved runs | PDR mean ± SD (%) | Delay mean ± SD (s) |
|---|---:|---:|---:|
''')
groups = {}
for p in sorted((ROOT / 'results/optimization_study').rglob('*.json')):
    d = json.loads(p.read_text(encoding='utf-8-sig'))
    if 'pdr' not in d:
        continue
    key = p.parent.name + ' / ' + re.sub(r'-r\d+$', '', p.stem)
    groups.setdefault(key, []).append(d)
for key, rows in groups.items():
    ps = [r['pdr'] * 100 for r in rows]
    ds = [r['mean_delay_s'] for r in rows]
    parts.append(f'| {key.replace("_", " ")} | {len(rows)} | {st.mean(ps):.2f} ± {st.stdev(ps) if len(ps)>1 else 0:.2f} | {st.mean(ds):.3f} ± {st.stdev(ds) if len(ds)>1 else 0:.3f} |\n')
parts.append('''
## Earlier native five-run validation

This earlier snapshot used seed 1 and runs 1–5, 24 nodes, six flows, 420 m square, 25% gray-hole prevalence, a 120 s scenario duration with 20 s excluded warm-up (100 s measured), and 240 s AR commissioning. It is separate from the later E1–E6 review matrix and the 30-pair commissioning follow-up.

| Metric | EAURP | AR-EAURP |
|---|---:|---:|
| PDR, mean ± sample SD | 83.73% ± 4.23% | 81.83% ± 4.60% |
| Delay | 257 ± 86 ms | 292 ± 108 ms |
| Detector TPR | Not applicable | 6.79% ± 3.32% |
| Detector FPR | Not applicable | 5.83% ± 6.14% |
| Detector score AUC | Not applicable | 0.55 ± 0.08 |
| Two-witness contested TPR | Not applicable | 0% in all five runs |

The paired PDR difference was −1.90 percentage points, 95% CI −8.46 to +4.66: inconclusive. The LSTM lost to persistence in all five commissioning evaluations and was not selected for routing. Source: `results/final_review_ns3_results/FINAL_NS3_EVALUATION_REPORT.md` and its `native_long_runs` records.

## Historical Python / prior Colab-review result

These saved Python full-profile results concern the earlier simulator and workload. They are historical context and are not pooled with the current ns-3 results. The table lists the 30% gray-hole slice across five saved runs. Values are mean ± sample SD. The execution location is not established by a CSV; this is the Python result used for the prior Colab-review context.

| Protocol | PDR (%) | Detection TPR (%) | Detection FPR (%) |
|---|---:|---:|---:|
''')
with (ROOT / 'output/full_results/csv/e3_attack.csv').open(newline='', encoding='utf-8-sig') as f:
    old = list(csv.DictReader(f))
for r in old:
    if r.get('attack_type') == 'grayhole' and float(r['malicious_pct']) == 30:
        label = r['policy_label'].replace('base.pdf substrate', 'base substrate')
        fmt = lambda key: f"{float(r[key])*100:.2f} ± {float(r[key+'_std'])*100:.2f}"
        parts.append(f"| {label} | {fmt('pdr')} | {fmt('det_tpr')} | {fmt('det_fpr')} |\n")
parts.append('''
AR-EAURP's historical PDR point estimate was 2.32 percentage points above EAURP. That observation motivated the native evaluation, but does not establish that the native implementation retains the benefit: implementations, radio/channel models, topology, traffic and detector observation processes differ.

## Automated verification and data audit

The native integration verification workflow had passed during the implementation work. The checks cover repeatability of simulated metrics; protected UDP delivery and authentication; delivery for the protocol variants; Q-learning updates; disconnected-flow feedback during cooldown; trained model/CMDP activity; energy shutdown/recharge; black-hole/gray-hole behavior; sample-standard-deviation arithmetic; invalid configuration rejection; matching checkpoint reuse; corrupted checkpoint recomputation; changed source/configuration identity rejection; CSV escaping; content hashing; and the E1–E6 smoke configuration inventory. These engineering checks verify implementation properties and do not establish comparative protocol superiority. They were not rerun during this document-formatting task.

The separate native unit-test source inventories the following cases. This inventory is not a claim of a fresh unit-suite execution during this editing session:

''')
tests = (ROOT / 'ns3/contrib/ar-eaurp/test/ar-eaurp-test-suite.cc').read_text()
for name in re.findall(r'TestCase\("([^"\n]+)"\)', tests):
    parts.append('- ' + name + '.\n')
parts.append('''

The earlier report audit reconciled all 863 ledger-referenced checkpoint hashes, aggregate means/sample SDs and all 180 E3 paired differences. The condition and per-run ledgers preserve exact settings. The main report is a composite of verified checkpoints; the root manifest's original `e3,e4,e5,e6` selection does not exclude the separately aggregated E1 and partial E2 data.

## All 180 matched E3 protocol contrasts

Each row is PDR(A) minus PDR(B) in percentage points, using five paired run numbers. Intervals are two-sided Student t 95% intervals and are unadjusted across this exploratory family. Wins count A above B; ties are retained. Zero-hostile rows appearing under multiple attack labels share an underlying clean condition and must not be interpreted as separate independent confirmation.

For compact tables, DRL-paper denotes DRL-EAURP (paper), and DRL-senior denotes DRL-EAURP (senior).

''')
rows = list(csv.DictReader((result / 'pairwise_e3_comparisons.csv').open(newline='', encoding='utf-8-sig')))
for attack in ['blackhole', 'grayhole', 'trust_poisoning']:
    for pct in [0, 10, 20, 30, 40, 50]:
        selected = [r for r in rows if r['attack'] == attack and float(r['malicious_pct']) == pct]
        parts.append(f'### {attack.replace("_", " ")} — {pct}% hostile\n\n')
        parts.append('| A minus B | Mean Δ (pp) | 95% CI (pp) | A wins | Ties | n |\n|---|---:|---:|---:|---:|---:|\n')
        for r in selected:
            short = lambda label: label.replace('DRL-EAURP (paper)', 'DRL-paper').replace('DRL-EAURP (senior)', 'DRL-senior')
            parts.append(f"| {short(r['protocol_a_label'])} − {short(r['protocol_b_label'])} | {float(r['mean_delta_pp']):+.2f} | [{float(r['ci95_low_pp']):+.2f}, {float(r['ci95_high_pp']):+.2f}] | {r['wins_a']} | {r['ties']} | {r['n_paired_runs']} |\n")
        parts.append('\n')
parts.append('''
## Consolidated findings and remaining work

1. The native attack matrix and 30-pair follow-up do not establish a reliable overall PDR advantage for AR-EAURP over EAURP.
2. Native gray-hole detection is weak in the selected workload; per-window TPR/FPR/AUC differ from consensus and revocation outcomes.
3. One of 18 AR-EAURP–EAURP attack/prevalence intervals excludes zero before multiplicity correction; it is exploratory evidence requiring confirmation.
4. E2 density is incomplete. The 42 deferred runs are absent; high-density n=1 points do not provide empirical SDs or confidence intervals.
5. Harvesting increases modeled residual energy and changes lifetime endpoints, some of which are censored. It does not directly validate field battery life.
6. Component ablations and CMDP-floor tests show trade-offs, rather than a uniform benefit from every added component.
7. Earlier Python results and native ns-3 outcomes are distinct experiments. Their raw PDR values should not be treated as a direct controlled cross-simulator treatment effect.
8. Next priorities are completing E2, improving detector validation, testing simpler baselines, defining a feasible delivery constraint, and running a confirmatory study with adequate power and planned multiplicity control.
''')
out = ROOT / 'paper/AR_EAURP_Test_Results_and_Findings.md'
joined = '\n'.join(parts)
joined = re.sub(r'(?m)(^\|[^\n]*\|)\n(?:[ \t]*\n)+(?=\|)', r'\1\n', joined)
# Some saved configuration labels contain literal pipes (e.g. AODV | battery).
# Preserve the label while keeping the intended number of numeric columns.
clean = []
columns = None
for line in joined.splitlines():
    if line.startswith('|'):
        cells = line.strip().strip('|').split('|')
        if columns is None:
            columns = len(cells)
        elif len(cells) > columns:
            extra = len(cells) - columns
            cells = [' / '.join(c.strip() for c in cells[:extra + 1])] + cells[extra + 1:]
            line = '| ' + ' | '.join(c.strip() for c in cells) + ' |'
    else:
        columns = None
    clean.append(line)
out.write_text('\n'.join(clean) + '\n', encoding='utf-8')
print(out)
print(f'Included {len(rows)} paired contrasts and {len(groups)} optimization groups.')
