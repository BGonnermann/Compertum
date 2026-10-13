# Offline baseline simulator verified

9 October 2026. Component complete; full M1 remains incomplete. Synthetic engineering evidence only, with no profitable-performance or live-readiness claim.

## Implemented

- Separate1-,5-,21-session momentum replays;252-session warmup;09:25 cutoff;09:35 raw minute-open fills and regular-close minute marks.
- Whole shares,20% targets, sector/gross/order limits, conservative numerical boundaries, sells before buys and maximum6 strategy submissions per checkpoint.
- $10,000 initial cash;10bp/side base or20bp stress costs;1% sizing buffer; explicit synthetic zero fees and no interest.
- Integer splits, dividend receivables/payments, economic NAV, sticky loss/exposure halts and separately labeled analytic terminal exits. Fractional or ambiguous actions fail explicitly.
- Synchronized60%SPY benchmark, full-SPY/static equal-weight diagnostics, zero-prediction cash reference and daily metrics. Undefined Sharpe stays undefined.
- Bounded snapshot assembly, cutoff/revision checks and reproducible Decimal arithmetic.

## Fresh verification

| Check | Pass / fail / skip |
| --- | --- |
| Source pytest: simulation,data snapshot/publication,contracts,config |127 /0 /0|
| Installed-wheel pytest: simulation,data snapshot/publication |69 /0 /0|
| Full12-stock+SPY replay: H1/5/21 at10/20bp |6 /0 /0 per environment|
| Exact reproduction |All6 outputs and39 input chunks match|
| Offline dependency compatibility |39 compatible packages per environment|

Fingerprint: `75f30023fb44decb1ffbfcf16b19ac122d6b01fe6d748085dcb9f079255d2d31`. Each environment retained8,881,209 bytes of synthetic inputs/results before its summary. Tests include hand-calculated cash/costs, dividend/split conservation, warmup, missing marks, horizon boundaries, sector ranking, loss/gap halts, zero variance and hostile caller decimal settings.

Windows11 Home x64 build26300; Python3.14.7 in both isolated environments. No lock/dependency changes, third-party source builds, downloads or system installs. Built only the project wheel offline and replaced only Compertum in the existing reproduction environment. Old wheels/logs remain.

Checkout: `C:\Users\bgonn\Desktop\Compertum-development`; repository `https://github.com/BrennanCompertum/Compertum`; branch `local/m0-development`; published base `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781`. Implementation remains uncommitted/unpublished. Exact current source/package/wheel hashes and archive are in the receipt; the base commit alone does not identify this work.

## Review and failures

Independent review found caller Decimal rounding/traps could change results. The retained regression failed with `decimal.Inexact`; pinning the complete context repaired it. Follow-up found a Git ignore exception was too broad. It now exposes only Python data-module source; JSON/CSV and nested runtime data remain ignored.

Initial tests also caught zero formatting and two fixture expectation/encoding errors. Failed logs/JUnit remain. No threshold was lowered. A storage invocation failed with `ABSOLUTE_ROOT_REQUIRED`; using the absolute checkout passed without product changes. No new full-reserve recovery fixture was allocated.

## Evidence and reproduction

- Plan: `docs/M1_BASELINE_PLAN.md`.
- Receipt: `artifacts/m1/baseline.json`; review: `artifacts/m1/baseline_review.json`.
- Evidence: `.cache/test-runs/m1-baseline-20261009-01/`: final JUnit, source/wheel inputs and results, comparison, wheel, source archive, storage/environment records, exact commands and copied logs.
- Original command records remain under `.cache/test-runs/m0-local-20261009-01/baseline-*`.
- Library: `compertum.simulation.replay(snapshots,sectors,start,end,horizon,cost_bps=10)` returns immutable bytes and SHA256.
- Reproduce: `python -B tools/verify_baseline.py --output .cache/test-runs/NEW_NAMESPACE`; add `--installed` with the wheel interpreter. Requires a fresh output path and64MiB scratch headroom. No provider or model requests.

## Remaining work and preservation

Saved-run/checkpoint integration, synthetic pause/resume/stop reproduction, predictive-score reporting, real-data coverage/actions/fees, sealed financial protocol and served-planner parity remain unverified or unimplemented. Synthetic active/sector metadata and action provenance are explicit assumptions. Full M1 and financial acceptance remain incomplete.

M0 archive/receipts, original project source/runtime and original Git index remain preserved. Native Strata cancellation stays unverified and automatic dispatch disabled. No Strata requests, broker/account access, market-data collection, spending, training, protected evaluation, commits, pushes or publishing occurred. Final native storage measurements remain within unchanged caps and are in the receipt.

Next: connect immutable snapshots and results to supervised saved runs, then verify pause/resume/stop using synthetic data. Owner explicitly removed the stale M0-only milestone restriction; routine local engineering needs no repeated scope confirmation.
