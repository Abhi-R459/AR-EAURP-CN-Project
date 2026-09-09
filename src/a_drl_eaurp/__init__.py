"""Implementation A -- DRL-EAURP, written from Lekha.pdf.

This is an independent re-implementation of the base paper from its published
equations (1)-(38). It was written from the paper alone; the senior's notebook
was consulted only afterwards, to compile the list of deviations reported in
``DEVIATIONS``.

The paper defines five models, and A implements all five:

    Existing      Eq. (14)-(18)   -- derived baseline, not a protocol
    EAURP base    Eq. (4)-(13)
    ATEAURP       Eq. (19)-(24)
    PSE-EAURP     Eq. (25)-(28)
    DRL-EAURP     Eq. (29)-(38)

Track 1 keeps the paper's own probabilistic structure. Track 2 mounts the same
DRL agent on the mechanistic harness (``policy_common``) so A can be compared
with B and C on a world where routes actually exist.
"""
