# Design: candidate measures and contribution to the book

Status: draft for the owner's review. Nothing is built.
Owner, 2 November 2026: "ok write the design for those two", after the firm-precedents research.
Source: the precedents report (Quantopian's 888-strategy study, WorldQuant's 101 alphas, Numerai's meta-model contribution) and `docs/MATH_RESEARCH.md`.

## Why

- Quantopian studied 888 strategies with real out-of-sample results. The backtest Sharpe ratio explained less than 2.5% of the out-of-sample Sharpe ratio. Several backtest measures together explained 17%.
- We rank candidates by their deflated Sharpe ratio on VALIDATION. We do not know which other measures predict the vault result. We can learn that only from records that we start now. Measures cannot be recorded after the fact without rerunning old code.
- WorldQuant and Numerai value a signal by what it adds to the signals that they already hold. Our candidates are scored only alone, against equal weight or buy and hold.
- `docs/MATH_RESEARCH.md` found that the single signals are weak. Weak signals that do not move together can still make a useful combination. Today the engine cannot see that.

## What stays the same

- The judge: `score_signals`, `library_multi.score`, `PanelMarket.score`, the verdict, the lag check, costs by era and the cash rate.
- The gate: stage 1 eligibility, the quarterly quota of 3, the deflated Sharpe ratio with the global trial count, stage 2 in the vault, the vault budgets and the owner's OK before each batch.
- The Auditor, the sandbox, the trial count, the data tiers and the ledger rules.
- No new measure passes, rejects, ranks or queues a candidate. All new measures are records only.
- The measures add no trials. They test no new strategy. They use the positions or weights that the candidate already made.
Changing the gate with a measure would need a separate owner decision. That decision should come only after the study in part 3 shows that the measure predicts.

## Part 1: record the measures of each candidate

A new trusted module, `src/compertum/ai/engine/measures.py`, runs outside the sandbox. It joins `FIXED_FILES`, so the engine cannot change it.
It recomputes the candidate's daily active returns (strategy minus benchmark) with the judge's own functions (`market.nav_paths`, `library_multi.run_navs`). The judge files do not change.
It uses NumPy for the arithmetic. Both environments have NumPy (engine 2.5.4, product 2.5.3).

Measures for every scored candidate, on its VALIDATION sessions:

| Measure | Meaning |
|---|---|
| `tail_ratio` | 95th percentile of daily active returns divided by the absolute 5th percentile. Quantopian found it among the most useful. |
| `hit_rate` | Share of sessions with a positive active return. |
| `block_sharpes` | Sharpe ratio of active returns in each of 4 equal blocks of VALIDATION, with the minimum, the spread and the number of positive blocks. |
| `lag_drop` | Sharpe ratio minus the Sharpe ratio with every trade one session later (from the existing lag check). |
| `cost_2x_sharpe` | Sharpe ratio with double costs. This is a record only, not the owner's open "2x cost stress" gate item. |
| `autocorrelation` | Lag-1 autocorrelation of daily active returns, and a Newey-West t-statistic of their mean (a t-statistic corrected for returns that depend on earlier returns). |
| `exposure`, `turnover_per_year` | Share of sessions invested, and traded weight per year. |
| `concentration` | Panel only: the mean effective number of assets held (1 divided by the sum of squared weights), and the largest single weight. |
| `engineer_runs`, `code_bytes` | Sandbox runs that the Engineer used for this candidate, and the size of the submitted code. Quantopian found that more backtests per strategy predicted worse results. |

The existing score already holds the Sharpe ratio, annual mean excess, maximum drawdown, skewness, kurtosis and the deflated Sharpe ratio. Part 1 does not copy them.

Records:
- The validator's score step gets a `measures` object. The ledger stores it with the step, as it stores the score today.
- The daily active returns of each scored candidate go into one compressed file, `state/engine/series/<candidate_id>.json.gz` (about 40 KB). The ledger records the file's SHA-256.
- If a measure cannot be computed (for example, too few sessions), the record says `UNDEFINED` with the reason. A failed measure never stops the cycle.

Early proxy, decision D4: the vault opens rarely. A vault holds at most 12 candidates, so 12 data points cannot show much.
Part 1 therefore also computes every measure on the first two thirds of VALIDATION, and records the active Sharpe ratio of the last third.
This gives a study set from every scored candidate, including bench runs, long before the vault opens.
It is a weaker test than the vault: the models saw scores on the whole of VALIDATION, so the last third is not fully unseen. The study reports it as a proxy.

## Part 2: contribution to the book

The book, decision D2: the candidates that passed stage 1 (ELIGIBLE or later) on the same market and the same VALIDATION sessions, plus the library's stage-1 results on that market.
On french49 today, the book holds `xs_momentum` and `dual_momentum`. A market with an empty book records `BOOK_EMPTY`, and the candidate's measures stand alone.
The library is deterministic. Its members' series are made once from their recorded family and settings, and are stored like candidate series.
The engine's single-asset candidates have no stage-1 member on a real market yet. Their book is empty until one passes.

Measures against the book, on VALIDATION active returns:

| Measure | Meaning |
|---|---|
| `max_correlation`, `mean_correlation` | Correlation of the candidate's daily active returns with each book member's. |
| `combined_sharpe_gain` | Sharpe ratio of the equal-weight mix of the book plus the candidate, minus the Sharpe ratio of the book alone. Equal weights fit nothing, so they cannot overfit. |
| `residual_sharpe` | Sharpe ratio of the part of the candidate's active returns that the book does not explain (least-squares residual). This is close to Numerai's meta-model contribution. |

The book is read when the candidate is scored. The record names the book members and their series hashes, so the number can be recomputed later.
The book changes over time. Two candidates scored on different days can therefore have different books. The record keeps the book that was used.

## Part 3: the study

A report tool, `tools/measure_study.py`, reads the ledger and the series files. It changes nothing.
- Proxy study: Spearman rank correlation (correlation of the rank order) between each early measure and the late active Sharpe ratio, with a 95% bootstrap interval. It also fits one small combined model with cross-validation, to compare with Quantopian's 17%.
- Vault study: the same table against the vault results, when vault batches exist. It runs on the vault results that `evaluate_in_vault` already records. It opens no vault.
- The report states the sample size. Below 30 candidates it labels every result as too small to use.
- The report goes to `reports/`. Any change to ranking or the gate goes to the owner as a separate proposal.

## Sealed files and checks

- New sealed file: `measures.py`. Changed sealed file: `cycle.py` (one call after scoring, and the record). `audit.FIXED_FILES` and the sandbox probe target count grow by 1 (24 targets allow it).
- The judge files, `vault.py` and `audit.py` checks do not change.
- Tests: hand-computed values for each measure on short series; the measures do not change the score, verdict, status or queue of any candidate; the book is the same market only; a failed measure records `UNDEFINED`; the series file hash matches; the study tool on a fixture ledger.
- Cost: one more NAV pass and some NumPy arithmetic per scored candidate, below 1 s on the panel. Storage: about 40 KB per scored candidate. That is about 4 MB for 100 candidates, inside the storage budgets.

## Decisions for the owner

- D1. Do the roles see the measures? Recommendation: no, not until the study shows which measures predict. If the roles see a measure, they may aim at it, and it can stop being an honest test (Goodhart's law).
- D2. The book: stage-1 candidates and library stage-1 results on the same market. Recommendation: yes.
- D3. Series storage for every scored candidate, or only for candidates that beat the baseline. Recommendation: every scored candidate. The study needs the weak and failed candidates too.
- D4. The early proxy (first two thirds against the last third of VALIDATION). Recommendation: yes, reported as a proxy and never as vault evidence.

## Phases

1. Part 1, the measures and the series files, with tests and a full `tools/check.py` pass.
2. Part 2, the book and the contribution measures, with tests.
3. Part 3, the study tool. The proxy study can run after about 30 scored candidates on one market. The vault study waits for a vault batch.
Each phase gets a checkpoint entry and a commit. No phase starts a run that costs money. The usual bench and practice runs fill the records.
