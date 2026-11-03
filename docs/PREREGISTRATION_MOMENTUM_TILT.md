# Pre-registration: the momentum_tilt library family

Status: registered before any code, TRAIN score or VALIDATION score of this family exists. Written on 3 November 2026.
Owner, 3 November 2026: "yes go ahead with all of it" (step 3 of the plan in this session: one pre-registered "momentum done well" family).
Source of the idea: `docs/RESEARCH_20261103.md`, section 3 (full-breadth tilt blended with equal weight; turnover control; volatility scaling of the tilt).

## Why

- `xs_momentum` holds only the top 10% or 20% of industries. A long-only top slice wastes most of the signal (Clarke, de Silva and Thorley, 2002).
- A tilt over all eligible industries keeps the benchmark's breadth and uses the whole ranking.
- Momentum has rare large crashes. Scaling its risk down when recent risk is high reduced crashes in the literature (Barroso and Santa-Clara, 2015). Counter-evidence: Cederburg et al. (2020) found that volatility management fails out of sample for most strategies.
- Lower turnover cuts costs. The era costs on french49 VALIDATION average about 0.4% one way.

## The rule (fixed)

At the close of a rebalance session t (every `hold` sessions, as for every library family):
1. For each eligible industry i, the momentum score is m_i = close(t−21) / close(t−21−lookback) − 1. An industry without both closes has no score.
2. Rank the scored industries from 1 (lowest m) to K (highest m). Rank weights: R_i = rank_i / (1 + 2 + ... + K). Unscored industries have R_i = 0.
3. Equal weight: E_i = 1 / N over all N eligible industries.
4. Tilt strength: k_t = k when `scale` is off. When `scale` is on, k_t = k · min(1, M_t / S_t), where:
   - D_s = Σ_i (R_i(s−1) − E_i(s−1)) · r_i(s) is the daily active return of the pure tilt, with the weights of the previous session (r_i(s) of an industry without a close counts as 0);
   - S_t is the standard deviation of D over the last 126 sessions up to t;
   - M_t is the median of S over the last 2,520 sessions up to t (about 10 years), using the sessions where S is defined.
   - When S_t or M_t is not defined, or S_t is 0, k_t = k.
5. Target weights: w_i = (1 − k_t) · E_i + k_t · R_i. The weights are 0 or more and add up to 1. The family holds no cash.

Every input uses closes up to t only. The library's lookahead check (closes of the last 1, 4 and 8 sessions changed) applies at admission.

## The grid (fixed, 16 settings)

| Knob | Values |
|---|---|
| lookback | 126, 252 |
| k | 0.5, 1.0 |
| hold | 21, 63 |
| scale | off, on |

## The test (fixed)

- Universe and data: french49, the 49 Kenneth French industry portfolios, as loaded by `library_multi.french_panel` without vault rows. TRAIN before 1973, VALIDATION from 1973 to before the vault start.
- Choice: the setting with the highest TRAIN Sharpe ratio (TRAIN only, as in `library_multi.choose`). Only that setting is scored on VALIDATION.
- Trials: all 16 settings are recorded in the ledger as one external trial source before the first VALIDATION score. They add to the global trial count.
- Scoring: unchanged (`library_multi.score`): equal-weight benchmark, cash at the T-bill rate, costs by era, drift turnover, the one-session lag check, deflated Sharpe ratio of active returns with the global trial count.
- Stage 1: the setting becomes ELIGIBLE only by the existing rule (beats the benchmark with the lag check, recompute and lookahead checks pass).
- The sweep runs this family only (`sweep --universe french49 --family momentum_tilt`). The other six families are not run again.

## What would count as success

- Primary: the chosen setting beats the benchmark on VALIDATION, with the lag check, and passes stage 1.
- Reported in every case, success or not: VALIDATION active Sharpe ratio (IR), the deflated Sharpe ratio, turnover, and the IR by decade.
- A vault test is not part of this registration. Whether this candidate, `xs_momentum` or another goes into the first french-v1 batch is the owner's written decision, made before any vault look.

## Addendum, 3 November 2026, before any code or score

- A session where no eligible industry has a momentum score (only the first months of TRAIN, 1926) uses k_t = 0: pure equal weight. Without this rule the weights would add up to 1 − k.
- Weights of exactly 0 (unscored industries when k_t = 1) are left out of the target. This changes no position.
- "Standard deviation" in step 4 is the sample standard deviation (divisor 125 for 126 sessions).

## What may not change after this point

The rule, the grid, the data, the choice rule and the scoring above. A changed family is a new family with its own registration and its own trials.
