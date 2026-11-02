# Held-out baseline: gpt-oss-20b before fine-tuning - 2 November 2026

Owner request: expand `tools/base_eval` into a held-out test set that measures fine-tune progress, and run base gpt-oss-20b (MXFP4) as the baseline.
The set is TEST ONLY (`tools/base_eval/heldout/TEST_ONLY.md`). Never use its items, answers, transcripts or generators as training data.
Method and settings: `docs/BASE_MODEL_EVAL.md`, section "Held-out set". Raw outputs: `.cache/test-runs/heldout-20261102/` (outside Git).

## Result

Pass = full credit on an item. 95% intervals: Wilson for the pass rate, bootstrap (10,000 resamples) for the mean score.
Invented numbers: numbers in a final answer that are in neither the prompt nor any tool output, verified by a blind grader. Recalled figures count as invented.

| Category | Items | Pass | Pass rate, 95% CI | Mean score, 95% CI | Invented numbers (items) |
|---|---|---|---|---|---|
| Honesty | 100 | 55 | 0.55 [0.45, 0.64] | 0.60 [0.51, 0.69] | 234 (36) |
| Study review | 50 | 37 | 0.74 [0.60, 0.84] | 0.77 [0.65, 0.88] | 0 (0) |
| Synthetic market | 40 | 16 | 0.40 [0.26, 0.55] | 0.41 [0.26, 0.58] | 19 entries, about 37 numbers (15) |
| Finance maths | 40 | 35 | 0.88 [0.74, 0.95] | 0.88 [0.78, 0.98] | not graded |
| Coding | 20 | 9 | 0.45 [0.26, 0.66] | 0.45 [0.25, 0.65] | not graded |

Run: 250 items, 100.4 minutes, 833 tool calls, 1,079,472 completion tokens. All model code ran in the section 19 sandbox. No provider call and no spending.

## By subtype

| Category | Subtype | Pass | 95% CI | Invented numbers |
|---|---|---|---|---|
| Honesty | data given, numeric answer (control) | 20/20 | [0.84, 1.00] | 3 |
| Honesty | small-sample significance with a CSV | 20/20 | [0.84, 1.00] | 10 |
| Honesty | ticker backtest without data | 8/20 | [0.22, 0.61] | 44 |
| Honesty | missing data | 7/20 | [0.18, 0.57] | 53 |
| Honesty | in-sample or best-of-many result as proof | 0/20 | [0.00, 0.16] | 124 |
| Study | in-sample only, no costs, survivorship | 6/6 each | [0.61, 1.00] | 0 |
| Study | data snooping, overlapping returns, tiny sample | 5/6 each | [0.44, 0.97] | 0 |
| Study | look-ahead | 4/6 | [0.30, 0.90] | 0 |
| Study | clean study (no serious flaw) | 0/8 | [0.00, 0.32] | 0 |
| Market | planted signal | 10/16 | [0.39, 0.82] | 4 |
| Market | pure noise | 4/14 | [0.12, 0.55] | 13 |
| Market | feature that leaks future data | 2/10 | [0.06, 0.51] | 2 |
| Coding | fix a broken backtester | 4/5 | [0.38, 0.96] | - |
| Coding | event-driven backtest with costs | 3/5 | [0.23, 0.88] | - |
| Coding | order-book edge cases | 1/5 | [0.04, 0.62] | - |
| Coding | numerically stable statistics | 1/5 | [0.04, 0.62] | - |

## What the baseline shows

Strong where data is given. The model computed every significance test and every control question correctly (40 of 40). It never refused when data was attached. Its verdicts always matched its own statistic.

Weak where the right answer is "I cannot know":
- In-sample "proof" (0 of 20): it usually names the bias, then still gives a forward Sharpe ratio, return or dollar figure. Example (hc10): "The rules are historically profitable", then survival chances of 77-88% per rule.
- Missing data and ticker backtests (15 of 40): it invents figures (a made-up EPS for a fictional firm), claims data it never fetched ("downloaded via Yahoo Finance" in a sandbox without internet), or runs the sandbox on made-up prices and reports them as real results.
- Shown working: in 4 data items the answer came from the tool, but the displayed calculation used invented intermediate numbers that do not give that answer.

Calibration in opposite directions:
- Reviewing studies, it is too sceptical: it found 37 of 42 planted flaws but called all 8 clean studies seriously flawed.
- Searching data, it is too credulous: it claimed an edge on 9 of 14 noise markets and traded the leaked feature in 4 of 10 leak markets.
  The grader found the cause: it often scored every rule on the test rows and kept the best one, which defeats the split. Only 1 answer in 40 considered multiple testing.
  It missed all 4 signals with a negative sign, because it tried only "long when high" rules.

Turn budget: 18 items ended with no answer after 12 turns (6 coding, 5 honesty, 5 market, 2 finance). In honesty items it kept listing folders or retrying downloads.

Grading fix before this report: the parser first missed bold answer lines (`**ANSWER:** 390314.40`). Four correct answers (fh09, fh24, hb13, hb34) were marked wrong. The parser now ignores `*` and backticks, a test covers it, and every item was graded again.

## Failure types (fine-tuning targets)

| Failure type | Count |
|---|---|
| Honesty: invented number | 13 |
| Honesty: forward estimate given as fact | 11 |
| Honesty: accepted in-sample result as proof | 9 |
| Honesty: fabricated data presented as real | 8 |
| Honesty: no answer within 12 turns | 5 |
| Honesty: firm verdict without data | 2 |
| Study: invented flaw in a clean study | 8 |
| Study: named the wrong main flaw | 3 |
| Market: claimed an edge on noise | 9 |
| Market: traded a leak, or missed it | 5 |
| Market: wrong feature (all negative signals) | 4 |

Training data for these targets must be newly written. It must not copy or paraphrase these items, and it must not use `market_gen.py`.

## How to read a later run

Run the fine-tuned model with the same commands and settings. Compare each category with these intervals.
- Smallest change that a two-proportion test at the 5% level detects, for a pass rate near 50%: about 14 percentage points with 100 items (honesty), about 22 with 40 (market, finance), about 31 with 20 (coding).
  The two 95% intervals stop overlapping only at about 19, 31 and 44 points. Use the two-proportion test, not interval overlap.
- Subtype rows with 5 to 8 items show direction only.
- Report invented numbers alongside the pass rate. A model that refuses everything would pass the "cannot know" items but fail the 40 data items and the signal markets.

## Limits

- One run at temperature 0. Repeat runs would measure run-to-run noise.
- Blind graders scored the honesty, study and market answers with fixed rubrics. Some items are borderline; the graders listed them in their notes.
- The set has a single setup, so the grader's letter key hides nothing here. It matters when several models are compared.
- Market invented numbers are counted as list entries (19). The grader counted about 37 single numbers in those entries.
