# Design: portfolio-weight candidates from the AI firm (efficiency path, step 6)

Status: approved by the owner on 2 November 2026 ("approved"), with D1 to D4 as recommended: anonymous names and session numbers, long only with cash, one market kind per run, the vault route later. No code is written yet. Owner, 2 November 2026: step 6 "agreed, approved"; "write the design ill review it and we go from there."
Source: `docs/EFFICIENCY_RESEARCH.md` (second cycle, step 7) and `docs/IMPROVEMENT_RESEARCH.md` item 4.

## Why

- The firm can build only one kind of candidate: one position (0 or 1) per session for one market. In about 1,170 real-data requests it found 0 gate passes.
- Both real-data results that passed stage 1 came from the deterministic library on the 49 French industry portfolios (`library_multi.py`, route `french49`). Those were cross-sectional rules: weights across many assets.
- Timing one asset on these blocks pays up to 1% of NAV per switch in the oldest era, so long/flat timing loses after costs.
- Step 6 lets the firm propose portfolio weights on the same 49-industry panel, scored and audited by the same honest rules as the library.

## What stays the same

- The judge's rules: cash earns the daily T-bill rate; Sharpe ratios are above the rate; costs by era (`market.cost_at`); drift turnover is charged; the lag check; the deflated Sharpe ratio on active returns; the global trial count.
- The two-stage gate: stage 1 eligibility with the quarterly quota of 3; stage 2 vault confirmation; the 12-candidate vault budget of `french-v1`; the owner's OK before each vault batch.
- The data tiers: TRAIN from July 1926 to 1973-02-25 (12,824 sessions), VALIDATION 1973-02-26 to 2003-08-13 (7,694 sessions), vault from 2003-08-14. The firm never sees a vault row.
- The sandbox, the Auditor's freeze rules, the kill switch, request limits and the ledger.
- The single-asset path stays. A run uses either the single-asset task or the panel task, never both in one cycle.

## The candidate

1. Input files in the job folder (instead of `train.csv` and `validation.csv`):
   - `panel_train.csv`: `session,A01,...,A49,rate`, the 12,824 TRAIN sessions.
   - `panel_validation.csv`: the same columns for the VALIDATION sessions, the same as for single-asset candidates today.
   - Values are total-return index levels (closes), as in `french_panel`. An empty cell means the industry has no close that session.
   - Proposal for owner decision D1: anonymous names. Industries become A01 to A49 in a fixed random order, and dates become session numbers. The scorer keeps the real dates for costs, the cash rate and the lag check. This lowers the risk that a model recalls industry history (`IMPROVEMENT_RESEARCH.md` item 5).
2. Output file `weights.csv`: `session,asset,weight`, with rows only on sessions where the weights change. A session without rows keeps the previous weights.
   - Long only: every weight is 0 or more, and the weights of one session add up to 1 or less. The rest is cash at the T-bill rate.
   - Only assets with a close that session may have weight. Weights chosen at the close of session t earn the returns of session t+1, as in the library.
   - Limits: at most 4 MiB, and at most 200,000 rows. A bad row refuses the whole file (`ENGINE_SIGNALS_INVALID`).
3. Scoring: `library_multi.score` on the VALIDATION sessions against the equal-weight universe. This is the same function that scored `xs_momentum` and `dual_momentum`. One firm candidate counts as one trial.

## The Auditor for panel candidates

The checks mirror the current single-asset Auditor and the library's `causal` check:
- Reproducibility: the frozen code runs again in the sandbox and must write the same weights.
- Lookahead: the frozen code runs on VALIDATION with the closes of the last k sessions changed (k = 1, 4 and 8; each asset gets its own factor, as in `library_multi.causal`). Every weight before the changed tail must stay equal.
- Forbidden access and loopback connections freeze the engine, as today.
That is 4 sandbox runs per audited candidate, as today.

## The vault route (stage 2)

- A new route kind, `firm-panel`. At stage 1 the queue records the frozen code hash, the input file hashes and the score hash.
- Inside a counted look (owner's OK per batch), the frozen code runs once in the sandbox on TRAIN plus VALIDATION plus vault rows. Only the vault sessions are scored, against the equal-weight industries.
- Before the look, a rerun must reproduce the VALIDATION score hash, as `library_multi.vault_score` does.

## The firm's tasks

- `market_brief` for a panel market states the facts: the files, the columns, the output format, the long-only limits, the costs and the gate, the 120-second deadline, and the standard library only. It gives information, not strategy rules (no-steering rule, 29 October 2026).
- A panel starter `/main.py` (about 60 lines). It reads the panel, calls `decide(history, t)` on rebalance sessions, and writes `weights.csv`. The default `decide` returns equal weights every 21 sessions.
- The Researcher, Director, Mathematician and Engineer prompts stay. Only the brief and the starter change.

## The bench and the score

- A panel bench, `bench-french-panel-1`, from TRAIN years only: 3 blocks of about 4,000 sessions, each with an inner train and an inner test, and no VALIDATION or vault row.
- Per block, a library reference rule: the best library family and setting chosen on the inner train. The report gives the continuous score of step 5 (the Sharpe gap to equal weight) and the capture against the reference rule.
- GEPA can then rank prompts on a bench where research quality is visible.

## Run commands

- `tools\practice.ps1 -Panel french49 ...` for practice runs on the real panel (TRAIN and VALIDATION).
- `tools\practice.ps1 -Mode bench -BenchSet bench-french-panel-1 ...` for the panel bench.

## Files that change

Sealed (owner approval covers step 6; new fingerprints are recorded): `cycle.py` (panel candidates in the cycle), `execution.py` (panel files and `weights.csv`), `audit.py` (the panel Auditor), `run.py` (the panel market kind), `vault.py` (the `firm-panel` route).
Not sealed: `library_multi.py` (parse weights and a shared scorer entry), `tasks.py` (panel brief and starter), `bench.py` (panel bench), `practice.py` and `tools/practice.ps1` (`-Panel`), `preflight.py`, and new tests.

## Tests

- Equivalence: a firm program that implements a library family must get the same score as `library_multi.score` for that family and setting. This is the main correctness test.
- `weights.csv` parsing: every refusal (negative weight, sum above 1, weight on an asset without a close, an unknown session, size limits).
- The panel Auditor: an honest program passes; a program that reads the next session's close fails the lookahead check; a program that varies its output fails the reproducibility check.
- The vault route on a synthetic panel: reproduction, look counting, vault rows only in the look.
- Native sandbox runs of the starter, inside the 120-second deadline on 12,824 + 7,694 sessions and 49 assets.
- The existing engine, product and harness lanes.

## Phases

1. Panel candidates in practice runs: files, starter, `weights.csv`, scoring, ledger records. No vault route yet.
2. The panel Auditor.
3. The panel bench with the library reference rule; a bench baseline run (about $0.15 on GLM).
4. The `firm-panel` vault route. It is used only with the owner's OK per batch.
Each phase ends with its tests, a checkpoint entry and a commit.

## Owner decisions

- D1: anonymous industry names and session numbers instead of real names and dates. Recommended: yes.
- D2: long only with cash, the same as the library and the benchmark. Recommended: yes. Shorts would need a borrow-cost model first.
- D3: one market kind per run (single-asset or panel). Recommended: yes.
- D4: phase 4 (the vault route) now or later. Recommended: later, after phase 3 shows that the firm finds candidates at all.

## Risks

- Model ability: 49 assets and about 20,000 sessions are harder than one series. Small local models may fail more builds. The bench measures this.
- Runtime: quadratic code on 20,000 sessions can pass 120 seconds. The brief states the sizes and the deadline (facts, not rules). The concurrent sandbox slots of step 3 reduce the cost of a timeout.
- Selection on VALIDATION: step 1 already ends the Engineer's conversation after the first accepted run, and only that run is scored.
- Memory of history: D1 reduces it but cannot remove it. A vault pass of an AI-written portfolio rule still cannot rule out memory. Forward paper trading stays the clean test.
