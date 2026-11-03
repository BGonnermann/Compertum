# Vault policy for french-v1: draft for the owner

Status: DRAFT for the owner to edit and approve. Claude wrote it on 3 November 2026 (owner: "yes go ahead with all of it", step 5 of the plan:
"your decisions, made on principle before any new result"). Not in force. Items marked [OWNER] need the owner's choice.
Basis: `docs/RESEARCH_20261103.md` section 3, `src/compertum/ai/engine/vault.py`, `docs/PANEL_CANDIDATES_DESIGN.md`.

## Facts that do not change

- The french-v1 vault holds the French industry sessions from 2003-08-14 to 2023-12-29 (about 5,130 sessions). No role and no run has seen them.
- At most 12 candidates are ever tested in french-v1 (`VAULT_BUDGET`). A vault test is final. A failed candidate is never tested again.
- Stage 2 deflates with N = the number of candidates counted in french-v1 looks up to and including this one. Each batch needs the owner's written note.
- A quarter can only be closed after it ends. 2026-Q4 closes on 1 January 2027 or later (`control close-quarter --quarter 2026-Q4`). The close queues at most 3 of that quarter's ELIGIBLE candidates, highest deflated Sharpe ratio first.

## Why the batch size matters (from the DSR study, inferred)

| Candidates counted (N) | Observed vault IR needed | Pass chance at true IR 0.4 |
|---|---|---|
| 1 | about 0.37 | about 56% |
| 3 | about 0.55 | about 24% |
| 12 | about 0.73 | about 7% |

Every candidate spent raises the bar for every later one in the same vault. The first batches decide how much of the vault stays useful.

## Proposed rules

1. Batch size: the first french-v1 batch holds exactly one candidate. [OWNER: confirm, or choose another size]
2. Choice of that candidate, fixed before the look: the QUEUED french-v1 candidate with the highest stage-1 deflated Sharpe ratio, recomputed at the close (the rule `close_quarter` already uses). [OWNER: confirm, or name a different rule; never a choice made after seeing any vault number]
3. Order of later batches: written down before the first look, and never changed after a result. Recommended: one candidate per batch, in the order of the same rule, until the owner stops. [OWNER]
4. Stop rule: after a failure, the next batch still needs a new owner note. The firm does not retest a changed copy of a failed candidate. [OWNER: confirm]
5. Report: every batch is reported whatever the result: the vault IR, the vault deflated Sharpe ratio with its N, turnover, and the IR by decade inside the vault.
6. Memory risk: an AI-written strategy can pass the vault from the models' memory of market history (arXiv 2504.14765). A vault pass of an engine panel candidate is therefore followed by forward paper trading before any real money. Library rules (written by code, not by a model) carry less of this risk. [OWNER: confirm]

## Candidates in view today

- Library rules already ELIGIBLE on french49: `xs_momentum` and `dual_momentum` (sweep `library-multi-20261102-c1d7704d`). Neither passed the stage-1 gate of 0.95; both beat the benchmark with the lag check.
- `momentum_tilt`: pre-registered on 3 November 2026 and ELIGIBLE since its sweep the same day: VALIDATION IR 0.678, deflated Sharpe ratio 0.359
  (the highest stage-1 value on french49), turnover 1.13 a year. If 2026-Q4 is closed under the current rule, it ranks first.
- Engine panel candidates: since 7d4f830 an audited panel candidate becomes ELIGIBLE on french-v1 with the `firm-panel` route (panel design, phase 4). None exists yet.

## Owner sign-off

[OWNER: write "approved" with the date, and any changes, here. Until then no french-v1 batch opens.]
