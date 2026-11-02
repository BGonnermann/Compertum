# Trial spending: plan and options for the owner - 2 November 2026

Status: part 1 agreed; option 1 with option 3 agreed in principle. Owner, 2 November 2026: "ok go".
The exact option 1 rules (section "Option 1: exact rules"): owner, 2 November 2026, "build it as written". Built; see ENGINE_PLAN.md, "Two stages".
Option 3 research (2 November 2026): no free source covers delisted S&P 500 members before 2016 well. Free with partial delisted coverage and a
free sign-up: Nasdaq Data Link WIKI prices (frozen April 2018) and Tiingo's free tier (500 symbols a month). Paid and complete: Norgate US
Platinum (about USD 630 a year, from 1990, delisted names and historical index members). Yahoo's terms forbid automated download.
The owner chooses.
Only the owner changes the gate (AGENTS.md, "Never let the engine change the judge").
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

The engine's vault is the last 20% of each history: for SPY, 403 sessions from 2022-05-24 to 2023-12-29 (TRAIN 50%, VALIDATION 30%,
`market.split_market_tiers`). It gives these bars: N = 1: 1.30; N = 3: 1.99; N = 5: 2.26; N = 10: 2.57.
Correction: the first version of this plan used the product's protected final period (2024 to 2025) as the vault. That period is separate.

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

- Stage 1, exploration on TRAIN and VALIDATION: the gate becomes a screen. A candidate may go to the queue when it beats the benchmark
  and passes its tests and the Auditor; the DSR with the global N ranks the candidates (see "Option 1: exact rules").
- Stage 2, confirmation in the vault: N is the number of candidates evaluated in that vault so far, not the global count.
  The selection happened in stage 1 on other data; the vault data is new to every candidate, so only the vault tests are multiple tests.
- With the current DSR minimum in stage 1 (about 3.8), no candidate would reach stage 2. So stage 1 ranks by DSR and caps the count
  instead of requiring the minimum.
- With 3 candidates, a candidate needs an observed Sharpe of 1.99 on the 403 vault sessions; with 1, it needs 1.30.
  With option 3 (history from 1990, a vault of about 1,700 sessions): 3 candidates need 0.96, 12 need 1.28.
- Cost: the vault is a finite resource. Each batch uses it; a failed candidate cannot be tried again on the same vault.

### Option 1: exact rules (for the owner's yes)

1. Screen (stage 1). A candidate may enter the queue when it beats the baseline on VALIDATION, its tests pass and the Auditor passes.
   The DSR with the global N is still computed and recorded, but it is a ranking, not a minimum.
2. Quota. At most 3 candidates enter the queue in a calendar quarter: the 3 with the highest VALIDATION DSR among the eligible ones.
   The quarter closes before the owner may open a batch for it, so a later candidate cannot push out an earlier one after a look.
3. Vault budget. At most 12 candidates are ever evaluated in one vault. The vault for the current histories is spent after that.
4. Confirmation (stage 2). A candidate passes when it beats the baseline in the vault and its vault DSR is at least 0.95, with N equal to
   the number of candidates evaluated in that vault so far, this batch included, and V the null variance of its own estimate (option C).
   N counts every earlier batch, so repeated batches cannot test the same vault for free.
5. Unchanged: every trial still counts; the owner's note opens each batch; the look is counted before any vault row is read;
   no candidate is evaluated twice; the Engineer never sees vault rows; a failed vault test is final.
6. Timing. Build and test the rules now, with an Auditor re-seal and the canaries. Open no batch until the longer history (option 3)
   exists, because a 403-session vault spends a finite resource on a test that a realistic strategy is unlikely to pass.

Changed files would be `vault.py` and `cycle.py` (both sealed), the library sweep (a route into the queue), and their tests.
Risk: the language models may remember market history from their training. The vault test cannot rule that out for real data.

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
Agreed by the owner on 2 November 2026 ("ok go"). Next: the owner's yes on the exact option 1 rules; research on free long-history
sources for option 3 is running.

## What this plan does not do

It changes no code, threshold, ledger row or data tier. It does not open the vault. It records no trial.
The SPY tier dates above came from the history loader; no vault price or return was read or scored.
