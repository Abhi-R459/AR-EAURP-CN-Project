# Source documents

Two of the four source documents are **deliberately not committed**, because
they are not ours to redistribute. Nothing in the code reads them at runtime —
they are the papers the implementations were written *from*, and the repository
runs end to end without them.

## Not in this repository

### `base.pdf` — EAURP

> A. Chandra and A. S. N. Chakravarthy, "EAURP: An Energy-Efficient and
> Trust-Aware Unobservable Routing Protocol for Secure Mobile Ad Hoc Networks",
> *Sustainable Computing: Informatics and Systems*, 2025.
> DOI: [10.1016/j.suscom.2025.101285](https://doi.org/10.1016/j.suscom.2025.101285)

An Elsevier Journal Pre-proof; Elsevier's sharing policy applies to that
version, so it is not republished here. Obtain it through the DOI or your
institution's library.

This is the paper the native routing substrate in `ns3/contrib/ar-eaurp/` implements: the
`PT_NID` / `PT_GID` / `PT_CREV` control packets (§3.6), packet-forwarding-ratio
trust with majority-vote revocation (§3.7), energy-gated AODV scored by
`R_Score = a·T + b·E` (§3.3–3.5), and ECC payload protection (§3.9).

### `Lekha.pdf` — DRL-EAURP

An unpublished manuscript by **Lekha S.**, Vellore Institute of Technology —
the senior's paper, and the base paper for this project. Not ours to publish.
Request it from the author or your project supervisor.

This is the paper implementation **A** is written from. The former Python
reproduction and its equation notes are available in Git history only.

The active `drl-paper` C++ variant adapts its tabular policy to local route
discovery. See the root README for the native model's assumptions.

## In this repository

| File | What it is |
|---|---|
| `Date_ 24_07_26.docx` | The AR-EAURP advancement roadmap — the five steps implementation **C** follows |
| `Review_1.pdf` | Our Review 1 presentation: the critique of DRL-EAURP and the work plan |

The original Python simulation notebook for **B** was removed; it remains in
Git history. The native implementation is `drl-senior`.
