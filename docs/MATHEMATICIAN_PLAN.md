# Mathematician plan: three changes, one at a time, after the bench baseline

Status, 25 October 2026: plan only. The owner asked for it "for after the bench". No code or prompt is changed. Each change starts only with the owner's OK, after the bench baseline (`run-20261026-84433f03`) is recorded.

## Why

Today the Mathematician turns a memo into a four-part specification (features, model, assumptions, failure modes) and reviews the Engineer's code. It never sees a number. In a quant firm the same person would also study the training data, judge whether the sample can detect the effect, and choose parameters by a stated rule. Three changes move the role in that direction without letting it touch the judge.

## Fixed rules for all three changes

- The Validator, the deflation gate, the Auditor, the vault and the ledger stay unchanged.
- No model sees a validation or vault row, or a statistic computed from one. The preflight check keeps refusing any task that shows a validation row.
- Every new piece of task text is built by code (in `tasks.py`, like the market brief), so GEPA cannot remove or change it.
- Each change is measured alone on the bench (`tools\practice.ps1 -Mode bench`, 4 cycles per market) and compared with the baseline. The comparison uses the bench report: patterns found, capture, false discoveries on the two empty markets, mean bench level, requests per cycle and minutes per cycle.
- A change that adds a false discovery on an empty market is rejected, however much it helps elsewhere.
- The holdout is used only once, for the final combination, before the owner applies anything permanent.

## Change A: a power check in every specification (first, smallest)

**What.** The specification gets a fifth heading, "5. Detectability". The Mathematician states the edge the rule expects and compares it with the edge the sample can detect. Code puts the reference numbers into the specify task, so the model does not compute them:

| Trials counted | Smallest per-session Sharpe that passes | Annualized |
|---|---|---|
| 1 | 0.135 | 2.15 |
| 15 | 0.281 | 4.46 |
| 60 | 0.328 | 5.21 |
| 100 | 0.343 | 5.45 |

These are for 150 validation sessions and a one-sided 95 percent level, with the null variance only and no skew or kurtosis correction, so they are lower bounds. They match the bench finding: the exact planted rule has a per-session Sharpe of 0.30 to 0.39, and only values above about 0.33 passed at 60 trials.

**Effect expected.** Fewer candidates that cannot pass by construction, for example slow rules with a handful of trades. A specification may end with "not detectable in this sample". The Director then sees that outcome in the lessons table.

**Build.** A code-built table in `tasks.specify_task`, using the real trial count of the ledger at task time; one line in `config/engine_prompts/mathematician.md`; preflight and content tests. About half a day.

**Open point.** Whether "not detectable" should skip the Engineer step. First version: no. It is recorded only, so the bench measures the effect of the information alone.

## Change B: a train-only data summary

**What.** The specify task (and the memo task) gets a summary of the TRAIN rows, built by code:
- session count, mean and standard deviation of returns, share of up sessions;
- autocorrelation of returns at lags 1 to 10;
- the mean return after N up sessions and after N down sessions, for N from 1 to 5;
- volatility in the first and second half of the train period.

**Effect expected.** Hypotheses and parameters grounded in the data instead of guesses. On the synthetic markets this summary will often show the planted pattern directly, for example the lag structure of a momentum window. That is legitimate, because it is training data, and the same thing a quant would look at. It also makes the empty markets more important: a harness that reads noise in the summary as a pattern must show up as a false discovery there.

**Build.** A `train_summary(train_rows)` function in `tasks.py`, product environment, deterministic; tests that it uses no validation row; preflight extended to check that it is present and computed from train rows only. About one day.

**Risk.** Data snooping. Many statistics shown to a model invite fishing. The summary stays short and fixed, and the deflation gate still counts every candidate.

## Change C: parameters chosen on train data by a stated rule

**What.** The specification may say "choose the window from {3, 5, 10} by the highest train Sharpe" instead of hard-coding 5. The Engineer's program does the choice inside `decide()` on `train.csv` only, before it sets any validation position.

**Effect expected.** Parameters that fit the market instead of the model's habit.

**The hard part: hidden trials.** A grid of 3 values searched inside one candidate is 3 tries, but the ledger counts one trial. The deflation gate would then understate the selection effect. Options, for the owner to decide before building:
1. The specification declares the grid size, and the ledger counts it as that many trials. This changes trial accounting, which is part of the judge, so only the owner decides it.
2. A fixed small maximum grid, for example 5 values in total, and no change to the count. Simpler, but it understates selection by up to 5 times.
3. Not allowed: parameter search without declaration.

The Auditor already reruns the frozen code with the last validation rows perturbed, so a choice that peeks at validation data is caught. The plan adds a test candidate that chooses on validation and must fail the Auditor.

**Build.** Specification and Engineer prompt lines, the declared-grid field in the specification, the trial accounting the owner chooses, and Auditor and bench tests. About two days.

## Order and cost

1. Change A, then a bench run (about 80 minutes with Flint).
2. Change B, then a bench run.
3. The owner decides the trial accounting for change C; then change C and a bench run.
4. The best combination, one holdout run, then the owner decides what to keep.

Each bench run is owner-started. No change here needs new software, spending or account access.
