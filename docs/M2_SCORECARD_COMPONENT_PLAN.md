# M2 synthetic campaign scorecard

Pure reporting over existing hash-bound CandidateResult artifacts. This does not confer origin authentication or replace coordinator-owned artifact/identity verification. No fitting, provider access, protected reads, strategy admission or publication.

- [x] Keep exactly12registered candidates and36candidate/year slots for2021/2022/2023. Retain missing and terminally failed folds explicitly; duplicate/conflicting outcomes fail. No success inferred from absent evidence.
- [x] Validate artifact hash/canonical form, synthetic labels, candidate/year/cost identities, date/symbol coverage and supplied metrics by recalculation. Require same source, training/scoring windows and scoring timestamp among each year's variants. Bound36inputs,16MiB each and128MiB total.
- [x] Aggregate daily strategy/benchmark returns across independently initialized folds, not raw NAVs across resets. Recompute mean excess, volatility, Sharpe, CAGR/drawdown and normal/stress metrics; record turnover, rebalance/holding counts and each fold's annual excess. Recompute pooled prediction errors versus zero/momentum on identical rows, date ranks and fixed12asset coverage.
- [x] Diagnostic rankings require all3synthetic folds; apply mean excess, lower total turnover, simpler momentum, lexicographicID. No financial shortlist or promotion is emitted. Keep ML contribution and financial status separate.
- [x] Hand/independent checks for reset discontinuity, metrics and coverage, tampering, missing/failed/conflicting evidence, source mismatch and tie rules. Compare all12retained candidate outputs in source/wheel. One independent reviewer, at most3targeted repair rounds, fresh <=64MiB namespace,120seconds per command.
- [x] Record results/checkpoint and continue saved campaign integration with model/fold checkpoint boundaries. Financial qualification and fullM2 remain incomplete.
