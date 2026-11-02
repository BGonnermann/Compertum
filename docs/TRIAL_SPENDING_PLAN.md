# Trial spending: plan and options for the owner - 2 November 2026

Status: proposal. The owner decides. Only the owner changes the gate (AGENTS.md, "Never let the engine change the judge").
Owner, 1 November 2026: "start the trial-spending plan". Nothing in the code or the ledger changed for this document.

## The question

Every strategy that the engine or a library sweep scores on VALIDATION counts as one trial.
The real gate passes a candidate only when its deflated Sharpe ratio (DSR) is at least 0.95 against all trials (option C,
`docs/TRIAL_COUNTING_DECISION.md`). More trials raise the bar for every later candidate. How should we spend trials?

## Facts

From `state/research.sqlite` on 2 November 2026 (read-only): N is 28,165 trials in 3,154 records.

| Source | Trials | Data |
|---|---|---|
| Single-symbol library sweeps | 24,790 | 371 real markets, 67 settings each |
| Engine cycles (bench, practice, GEPA, holdout) | 3,150 | Mostly generated markets |
| Multi-stock library sweeps | 225 | Real universes, 75 settings each |

The bar below comes from `deflation.py` with the gate's own formula. It assumes normal returns (no skew, no fat tails).
"Needed" is the observed annual Sharpe ratio that gives a DSR of 0.95. SR0 is the best annual Sharpe ratio that luck alone gives.
VALIDATION on the real histories has 603 sessions (about 2.4 years).

| Trials N | SR0, 603 sessions | Needed, 603 sessions | Needed, 1,000 sessions | Needed, 2,000 sessions |
|---|---|---|---|---|
| 1 | 0.00 | 1.07 | 0.83 | 0.58 |
| 12 | 1.08 | 2.15 | 1.67 | 1.18 |
| 100 | 1.65 | 2.72 | 2.11 | 1.49 |
| 1,000 | 2.13 | 3.20 | 2.48 | 1.75 |
| 28,165 (now) | 2.69 | 3.77 | 2.91 | 2.05 |
| 100,000 | 2.88 | 3.97 | 3.06 | 2.15 |

Correction: earlier reports called the bar "an annual Sharpe of about 2.66". That number is SR0.
A candidate must also beat SR0 by its own uncertainty, so the observed annual Sharpe ratio must be about 3.8.

Sessions that an observed annual Sharpe ratio needs to pass:

| Observed Sharpe | N = 1 | N = 100 | N = 1,000 | N = 28,165 |
|---|---|---|---|---|
| 0.8 | 1,086 (4.3 years) | 6,988 (28 years) | 9,837 (39 years) | 13,185 (52 years) |
| 1.0 | 697 (2.8 years) | 4,501 (18 years) | 6,338 (25 years) | 8,496 (34 years) |
| 1.5 | 312 (1.2 years) | 2,056 (8 years) | 2,759 (11 years) | 3,886 (15 years) |

The vault (2024-01-01 to 2025-12-31, about 502 sessions) gives these bars: N = 1: 1.17; N = 3: 1.78; N = 5: 2.02; N = 10: 2.30.

The best real results so far: annual Sharpe 0.81 (survivor stock list, 1 November 2026) and 0.54 (point-in-time S&P 500, 2 November 2026).

## What the facts mean

1. Spending more trials is no longer the main problem. The bar grows with the logarithm of N.
   1,000 more trials raise the needed Sharpe by 0.005; 20,000 more raise it by 0.08.
2. The length of the test is the main problem. With 603 VALIDATION sessions, even one trial needs an observed Sharpe of 1.07.
3. A realistic daily stock strategy has an annual Sharpe ratio between 0.5 and 1.5. Under the current rules no such strategy can pass,
   whatever we spend. The gate is honest; it says that 2.4 years of data cannot prove a strategy of that size.
4. So the plan has two parts: rules for spending trials, which change little, and decisions on the test design, which change a lot.

## Part 1: spending rules (no rule change; starts now if the owner agrees)

1. Count everything, as now. Every scored setting and every engine candidate stays a trial. No unrecorded look at VALIDATION.
2. No new broad grids. A library sweep needs a written question before it runs, in its `--note`.
   Do not repeat a grid on a new universe only to see what happens. The two single-symbol sweeps added 24,790 trials and found nothing that passed.
3. Soft ceiling: 100,000 trials in total until the owner reviews again. At that count the needed Sharpe at 603 sessions is 3.97.
4. Real-data bench runs (this week) count their candidates as trials, as the generated bench did. Expect a few hundred trials a run.
5. The vault stays closed. No candidate reaches it under the current gate.

## Part 2: decisions for the owner (each one changes the judge)

Each option below changes the gate or the data tiers. Each needs the owner's explicit approval, a new test, and an Auditor re-seal.

### Option 1, recommended: two stages, explore then confirm

- Stage 1, exploration on TRAIN and VALIDATION: the gate becomes a screen. A candidate goes to the queue when it beats the benchmark
  and passes the DSR with the current global N, as now. Only the stage-2 rule is new.
- Stage 2, confirmation in the vault: N is the number of candidates in the sealed vault batch, not the global count.
  The selection happened in stage 1 on other data; the vault data is new to every candidate, so only the vault looks are multiple tests.
- Problem: stage 1 still needs about 3.8, so no candidate reaches stage 2. Option 1 helps only together with option 2 or 3,
  or with a screen in stage 1 that does not use the global N (for example: beat the benchmark on TRAIN and VALIDATION, with at most 10
  candidates a quarter).
- With a batch of 3, a candidate needs an observed Sharpe of 1.78 on the 502 vault sessions; with 1, it needs 1.17.
- Cost: the vault is a finite resource. Each batch uses it; a failed candidate cannot be tried again on the same vault.

### Option 2: count correlated trials as fewer trials

- The 67 settings of one family on one market are not independent; neighbour settings give almost the same returns.
  Bailey and Lopez de Prado suggest an effective number of trials from clusters of correlated trial returns.
- Effect: N could fall from 28,165 to a few hundred or a few thousand. The needed Sharpe at 603 sessions would fall to about 2.9 to 3.4.
- Problem: still far above realistic strategies. The clustering method adds a choice that someone could tune. It needs a fixed rule.

### Option 3: longer real history

- Alpaca's daily bars start in 2016. A longer free history would give a longer VALIDATION.
  With 1990 to 2023 and the same split, VALIDATION would have about 2,500 sessions; the needed Sharpe at N = 28,165 would be about 1.9.
- Problem: it needs a new free source with clear terms, and its own evidence reader and checks. Paid data needs the owner's approval.
  Survivorship returns for years before the membership history (the S&P 500 dataset starts in 1996).

### Option 4: research higher-Sharpe strategy types (no rule change)

- The engine and the libraries are long-only. Long-short and market-neutral strategies remove most market risk and can reach higher
  Sharpe ratios, but they need short-sale costs and borrow rules in the scorer. That is a scorer change, so the owner decides it too.

### Not recommended: a lower DSR minimum

- A minimum below 0.95 lets more luck through. It does not fix the short test; it only hides it.

## Recommendation

Agree to part 1 now. For part 2, choose option 1 (two stages) together with option 3 (a longer free history), and keep options 2 and 4
for later. Until the owner decides, research continues under the current gate, and every result is reported against it.

## What this plan does not do

It changes no code, threshold, ledger row or data tier. It does not open the vault. It records no trial.
