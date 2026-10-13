# Synthetic prediction reports verified

9 October 2026. Prediction-report component complete; full M1 and financial acceptance remain incomplete.

The reports measure momentum forecast errors against a zero-return forecast separately from portfolio results. Each daily decision uses its frozen feature cutoff, an H-session entry-to-exit price label, effective splits and the next-session label embargo. Dividends remain trading cash flows. Late labels/revisions/actions are omitted until available; missing labels are never replaced by zero returns.

Metrics include MSE, MAE, mean signed error, zero-forecast errors, fractional MSE improvement when defined, per-date Spearman correlation with average tie ranks, and explicit coverage/omission reasons. Feature eligibility, full-horizon eligibility and scored rows are separate counts. Every evaluated date has a correlation record; unavailable/constant cases are null with reasons.

## Fresh verification

| Check | Pass / fail / skip |
| --- | --- |
| Prediction plus simulation/data/saved-run source tests |105 /0 /0|
| Same tests against installed wheel |105 /0 /0|
| Full12-stock+SPY prediction reproduction |3 /0 /0 per environment|
| Exact source/wheel comparison |All3 reports and39 input chunks match|

The24 prediction tests include hand-calculated metrics, H1/5/21 timing, split-on-entry/exit cases, dividend exclusion, late revisions/actions, missing references, predecision scoring refusal, hostile Decimal settings, ties/undefined metrics and bounds. Full-watchlist reports contain516,468 and276 scored rows for H1,5,21 across44 synthetic sessions. These are engineering fixtures, not performance evidence.

Reproduction fingerprint: `9c27e72ede9ef91cf1c1c986befdf7f918daf5ba684671331824730be3544c81`. Each environment retained8,795,828 bytes of synthetic input/report content before its summary receipt.

Independent review corrected ambiguous eligibility counts and absent daily null records. A retained regression also demonstrated numeric underflow for an extreme standalone input; invalid magnitudes now fail explicitly. Review cleared the repairs. No financial thresholds or costs changed.

## Environment and evidence

Checkout `C:\Users\bgonn\Desktop\Compertum-development`; repository `https://github.com/BrennanCompertum/Compertum`; branch `local/m0-development`; published base `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781`. Source remains uncommitted/unpublished; use receipt/source-archive identities for this stage.

Windows11 Home x64 build26300; Python3.14.7 in both isolated environments; same39 distinct distributions and unchanged lock. Only the local wheel was rebuilt/installed offline/no-deps. No system or third-party installation.

- Code: `src/compertum/simulation/prediction.py`.
- Plan: `docs/M1_PREDICTION_REPORT_PLAN.md`.
- Receipt/review: `artifacts/m1/predictions.json`, `artifacts/m1/prediction_review.json`.
- Evidence: `.cache/test-runs/m1-predictions-20261009-01/`, with source/wheel JUnit, failed regressions, exact commands/logs, immutable inputs/reports, environment/comparison, wheel, source archive and final storage measurements.
- Library: `score_predictions(chunks,sectors,start,end,horizon,scoring_as_of=UTC_TIMESTAMP)` returns immutable canonical bytes/hash.
- Reproduction: `python -B tools/verify_predictions.py --output .cache/test-runs/NEW_NAMESPACE`; add `--installed` for the wheel environment. Requires fresh output path and32MiB headroom.

## Preserved boundaries and remaining work

Saved-run native recovery evidence remains in reports/M1_SAVED_RUNS.md:4 actual Windows process restart/stop tests passed per environment and18 recovered outputs matched. Its implementation is unchanged by this prediction addition. Its prior receipt/package/archive identity remains preserved, rather than retroactively relabeled as this package.

The prediction library is not yet wired into saved-run artifact publication or a production operator command. Operator-facing supervised integration, real-data/provider coverage/actions/fees, protocol sealing and financial acceptance remain unfinished. No training or protected evaluation was performed.

Original project/runtime, M0 and earlier M1 receipts/archives remain intact. No Strata requests, accounts, market-data collection, orders, spending, publishing, commits, pushes or administrator changes. Storage remains inside unchanged limits. Native Strata cancellation remains unverified and automatic dispatch disabled.
