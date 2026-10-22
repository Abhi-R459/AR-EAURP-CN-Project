# Research manuscript and complete experimental report

The current deliverables at the repository root are:

- `AR_EAURP_Research_Paper.docx`: 16-page manuscript with methods, results,
  discussion, references, and reproduction instructions.
- `AR_EAURP_Research_Paper_Preview.pdf`: Microsoft Word PDF export.
- `AR_EAURP_Test_Results_and_Findings_Final.docx`: 27-page experimental record,
  including all 180 E3 pairwise contrasts and 13 exploratory optimization groups.
- `AR_EAURP_Test_Results_and_Findings_Final_Preview.pdf`: its Word PDF export.

Page counts describe the checked exports. Another Word version or printer/font
configuration can paginate differently. All five author names were supplied by
the project team; no institutional affiliation has been invented.

## Evidence and scope

The documents use the saved native study under `results/ns3-native-paper-review`,
the separate `results/optimization_study`, the earlier native validation snapshot,
and historical Python aggregates under `output/full_results/csv`. They do not
run new simulations. The native review includes 863/905 planned runs and 179/181
conditions. The 42 missing density replications remain absent. Earlier Python
results are not pooled with native results, and exploratory intervals are not
claims of general protocol superiority.

The base native scenario lasts 120 s including 20 s warm-up: its actual measured
window is 100 s, followed by 10 s cooldown. Clean AR commissioning is separate.
See the condition/run ledgers for exact overrides and checkpoint identities.

## Generate editable Word documents

From the repository root, install the optional document dependencies:

```powershell
python -m pip install -r paper/requirements.txt
```

Build directly from the checked Markdown sources:

```powershell
python paper/build_word_paper.py paper/AR_EAURP_Research_Paper.md AR_EAURP_Research_Paper.docx --submission
python paper/build_word_paper.py paper/AR_EAURP_Test_Results_and_Findings.md AR_EAURP_Test_Results_and_Findings_Final.docx
```

The builder uses bundled Pandoc and python-docx, Times New Roman body text,
editable mathematical equations, repeating table headings, academic table rules,
page numbers, and proportional line spacing for figures. The manuscript begins
with its abstract; the companion report includes an editable contents field.

On Windows with Microsoft Word installed, refresh fields and export PDFs:

```powershell
./paper/render_word_paper.ps1 -DocumentPath "$PWD/AR_EAURP_Research_Paper.docx" -PdfPath "$PWD/AR_EAURP_Research_Paper_Preview.pdf"
./paper/render_word_paper.ps1 -DocumentPath "$PWD/AR_EAURP_Test_Results_and_Findings_Final.docx" -PdfPath "$PWD/AR_EAURP_Test_Results_and_Findings_Final_Preview.pdf"
```

This opens a hidden Word automation instance and closes only its own documents.
It requires desktop Microsoft Word; the Python builder alone does not export PDF.

## Regenerate content from saved evidence

`build_test_report.py` assembles the detailed evidence tables.
`prepare_submission_documents.py` then adds the full native methods, manuscript
discussion, metric dictionary, evidence-to-claim audit, and qualified findings.
To regenerate both source drafts:

```powershell
python paper/prepare_submission_documents.py
```

This rewrites `AR_EAURP_Research_Paper_Submission.md` and
`AR_EAURP_Test_Results_and_Findings.md`. It can overwrite manual edits in those
generated files; retain edits before running it. The checked canonical manuscript
is `AR_EAURP_Research_Paper.md`. The generated submission source can be reviewed
and passed to the same Word builder before replacing that canonical source.

Temporary font experiments, duplicate exports, the original input PDF, and page
inspection images stay local. The canonical outputs and active generation scripts
are versioned. Document tooling is separate from the native simulation runtime.
