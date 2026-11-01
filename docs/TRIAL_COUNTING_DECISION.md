# Trial counting: options for the owner - 1 November 2026

Status: proposal. Nothing is changed. Only the owner changes the gate (AGENTS.md, "Never let the engine change the judge").

## The question

The real gate passes a candidate when its deflated Sharpe ratio (DSR) is at least 0.95.
The DSR compares the candidate's Sharpe ratio with SR0, the best Sharpe ratio that luck alone gives over N trials.
SR0 depends on two inputs: the trial count N and the trial variance V (how widely the Sharpe ratios of the trials spread).
On 29 October 2026 the open question was N: count trials for the whole history, or per research question or market.

## What the data shows

Facts from `state/research.sqlite` on 1 November 2026 (read-only):
- N is 2,736 engine trials on 77 markets: 1,926 bench, 607 practice, 165 GEPA, 38 holdout.
- The trials mix two lengths: 1,455 scored trials have 1,227 validation returns (4,096-session markets), and 1,128 have 149 (500-session markets).
- V today is the sample variance of all 2,405 recorded per-period Sharpe ratios: 0.0132. The null variance of one estimate at 1,227 returns is 0.0008.
- With V = 0.0132, SR0 is 0.41 per period at N = 2,736, and still 0.19 at N = 12. No trial on a 4,096-session market has reached 0.31.
  The 69 trials above 0.31 all come from 500-session markets, where one estimate spreads widely by luck.

So V blocks the gate, not N. V is large for two reasons. Short-market trials have a large sampling spread.
Trials that really captured a planted pattern have high Sharpe ratios, so every success raises the bar for all later candidates.

Test of each option on every bench-3 and bench-4 candidate that beat buy-and-hold (recomputed with `deflation.py`, nothing recorded):

| Option | N | V | Patterned markets: pass of 277 | Empty markets: pass of 139 |
|---|---|---|---|---|
| A. Now | whole history (2,736) | all recorded trials | 0 | 0 |
| A2 | whole history | trials of 4,096-session markets only | 0 | 0 |
| A3 | whole history | trials of the same market | 0 | 0 |
| B. Per market | trials on the same market | trials of the same market | 5 | 0 |
| C. Whole history, null variance | whole history (2,736) | null variance of the candidate's own estimate | 74 | 0 |
| D. Per market, null variance | trials on the same market (at least 12) | null variance | 112 | 0 |
| (the bench gate today) | fixed 192 | null variance | 103 | 0 |

A pass on an empty market is a false discovery. No option produced one in 139 tries.
At that sample size, the false-pass rate is below about 2 percent with 95 percent confidence (3 / 139).

## The options

A. Keep the rule. Nothing can pass now, and the bar rises with every success. The gate becomes a wall, not a test.

B. Per market, both N and V. This is the textbook form (Bailey and López de Prado, 2014: trials on the same data).
It passes almost nothing, because V of a market rises when the firm solves that market.
It also stops counting trials on other markets, although lessons and GEPA carry ideas from market to market.

C. Whole-history N with the null variance. Recommended.
- N stays the whole history, as the owner set it and as section 19 requires ("Counts all trials").
- V becomes the sampling variance that pure luck gives one estimate, which the code already uses as the floor.
  The bench gate has used the same V since 26 October 2026, with 0 false discoveries.
- SR0 then grows slowly with N: 0.100 per period at 2,736 trials and 0.125 at 100,000 (1,227 returns).
- Risk: the null variance assumes that the trials have no real skill. Real skill makes the spread larger, so C is less strict than A.
  The empty markets measure that risk directly, and each bench run measures it again.

D. Per market with the null variance. Loosest. It forgets trials on other markets. Not recommended.

## Change needed for C

`src/compertum/ai/engine/cycle.py`, the gate step: pass no recorded Sharpe ratios to `trial_variance`, so V is the null variance.
The ledger keeps recording every trial score. The Auditor's check (`deflation_consistent`) is unchanged.
Update the docstring of `deflation.py` and `docs/ENGINE_PLAN.md`. Add a test that pins V to the null variance.
Earlier records stay as they are; they keep their old V.

## Limits that stay

- Real markets: 500 real sessions give 149 validation returns. With C, SR0 at 2,736 trials is then about 0.29 per period,
  an annualized Sharpe of about 4.6. Real-market research needs longer validation windows, whatever the owner chooses here.
- The holdout and the vault are still the final checks. A gate pass promotes a candidate to the queue, not to money.
