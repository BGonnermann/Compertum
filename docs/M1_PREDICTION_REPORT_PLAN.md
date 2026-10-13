# Synthetic prediction reporting

Autonomous offline continuation authorized9October2026. Implement after saved-run verification is recorded. No training, provider access or financial acceptance. Primary writes, one bounded read-only review after implementation, at most3 repair rounds.

Goal: report the baseline prediction's errors separately from trading results, using exact H-session entry/exit price labels and only then-available features/actions. This closes the remaining offline predictive-reporting omission in BUILD_SPEC section9.

Design: pure compertum.simulation.prediction module takes the same validated chunks/sectors/start/end/H. It reports eligible decision rows for every exchange session whose full H exit fits, independent of rebalance schedule. Preserve09:25 decision,09:35 entry/exit and next-session09:25 label embargo. Raw minute opens plus effective split factors define price return; dividends excluded. Label availability is the latest of embargo, reference/revision availability and applicable simulated action-known timestamps. An explicit scoring_as_of cutoff excludes unavailable labels. No protected-data or fit loop.

Metrics: row-weighted MSE/MAE/mean signed error for momentum and zero-return predictor, fractional MSE improvement only when zero baseline MSE>0, per-date Spearman rank correlation with average tie ranks, and eligible/scored/omitted coverage. Undefined cases remain null with reasons. Decimal ledger context pinned as in simulator; finite bounded outputs. Financial state always SYNTHETIC_UNVERIFIED.

Inputs/bounds: reuse validated Market and existing snapshot limits. No new provider schema. At most1024scored exchange sessions,13assets,12,288 rows and16MiB output. No persistence changes; caller may retain canonical bytes using admitted saved-run artifact paths in a later integration. Return immutable canonical bytes/hash; bind market identity,H,dates,scoring cutoff and explicit methodology.

- [x] Hand-calculated failing tests: H1/5/21 timing, price return vs dividends, split continuity, late-label/revision exclusion, future-feature refusal, ties/zero variance and exact MSE/MAE.
- [x] Implement bounded deterministic label extraction and metrics.
- [x] Review/repair; source and installed-wheel tests and exact output fingerprints.
- [x] Separate receipt/report/archive and roadmap update. Preserve all older completed components and evidence.

Ruling: daily eligible rows are predictive observations; scheduled portfolio checkpoints remain trading observations. They are reported separately to avoid presenting sparse trades as total prediction coverage. Late labels are omitted at scoring cutoff, never backdated or treated as zero return. Sector/active metadata remains synthetic, and no result qualifies a strategy.

Review clarified coverage: feature_eligible_rows counts available operational features, eligible_rows additionally requires a full horizon, scored_rows additionally requires a complete available label. Every evaluated session has an explicit rank-correlation record, including NO_SCORED_ROWS/null. Standalone numeric helpers reject nonzero magnitudes outside[1e-64,1e32] to prevent underflow/overflow; snapshot-derived values fit this range. This is input validation, not a changed financial threshold.

Completion:105 source/related and105 installed-wheel passes; three full-watchlist report files and39 input chunks match exactly.24 prediction tests cover these rules. See reports/M1_PREDICTIONS.md.
