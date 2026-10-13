# Offline baseline simulator plan

Use executing-plans and test-driven-development. Primary implements; one bounded read-only reviewer at completion. Owner approved this component and removed the stale M0-only restriction on 9 October 2026. No routine plan approval or commits.

Goal: deterministic synthetic replay of the specified momentum portfolio for H=1,5,21, with economic cash/action accounting and synchronized benchmarks. This library is not M1 acceptance, a live planner or a profitable strategy claim.

Architecture: compertum.simulation.market assembles bounded validated snapshot chunks; policy holds reusable sizing and boundary rules; engine replays cash, shares, actions, trades, observations and sticky halts; metrics computes economic daily returns. Python3.14.7, Decimal precision28 and existing calendar, no dependencies or lock changes.

Decisions: at most64 snapshots/16MiB and1024 exchange sessions per replay. Chunking preserves existing1MiB/1024-bar snapshot limits. One consistent synthetic source/vintage and asset mapping; conflicting or duplicate bars/actions rejected. Raw prices plus only effective splits determine returns. All252 warmup rows must be consecutive and cutoff-available. Frozen caller-supplied synthetic sectors bind the result hash. Synthetic zero commissions are explicit and never provider-verified. The reference is the09:35 minute open and close NAV uses the last regular minute close.

Portfolio: $10,000 initial cash; top3 momentum predictions, symbol tie order, each20% target, gross60%, sector40%; base10bp/side or stress20bp and1% sizing buffer. Threshold is2*side cost+10bp with1e-10 ambiguity rejection. Sells precede buys. Each strategy child capped at min($2000,1% prior20-session dollar volume), max6 submissions. Missing liquidity or execution inputs block an intended trade. Existing holdings are marked even when no longer eligible. Risk checks after each fill and at entry/close; loss2%, drawdown10% or realized exposure breach creates a sticky segment halt. No automatic liquidation on halt. Terminal analytic liquidation is separately labeled and never broker authority.

Actions: splits adjust integer shares and basis; fractional entitlements are refused pending a cash-in-lieu rule. Dividends become receivables at ex-date and cash at pay-date or next exchange session. Unknown/late effective actions refuse replay. Simultaneous split/dividend for an asset is ambiguous and refused. Future splits do not alter earlier raw-derived features.

Scheduling: first operationally eligible session anchors each H calendar. New entries require full H exit inside segment. Terminal reductions at last09:35 reference. Rebalance holdings persist when unchanged; completed H intervals counted independently from trades and excluded if interrupted by halt/partial boundary. Cash days included. Benchmarks share schedule, costs, marks and actions:60%SPY primary, full SPY and initially60%-gross equal-weight watchlist diagnostics. Strategy concentration and loss caps do not silently redefine these diagnostic portfolios. Missing benchmark references refuse a result. Zero-return candidate included as cash reference.

Results: canonical bytes/hash bind source chunks, sectors, dates, H, costs and versioned policy. Record signals, omissions, fills, turnover, action cash flows, entry/close observations, daily NAV/returns and metrics. Financial status always SYNTHETIC_UNVERIFIED. Full M1 workflow, persistent pause/resume and real coverage remain later work.

- [x] Task1: failing tests, bounded tape, cutoff eligibility and shared sizing.
- [x] Task2: ledger/replay/actions/benchmarks/metrics and hand-computed tests for all H, boundaries, missing inputs, zero variance and risk halts.
- [x] Task3: source regressions; one review and at most3 repair iterations; offline wheel build/install; matching installed-wheel tests and exact deterministic hashes.
- [x] Task4: separate receipt/report, source manifest and README/progress update. Preserve M0 receipts and original state.

Validation: tests/test_simulation.py plus existing data tests and small contract/config regressions. Every run gets a fresh checked .cache/test-runs/m1-baseline-20261009-01 namespace. Do not run full-reserve recovery fixtures. Use existing allowlisted verification runner; inspect actual child exit code. Stop only for missing external authority or an unresolved material ambiguity, never lower thresholds. Keep50GiB total and5GiB scratch caps.

Completion:127 source/regression passes,69 installed component passes, zero failures/skips. Six full-watchlist source/wheel replays match byte-for-byte. Review repaired ambient Decimal context inheritance; ledger now pins ROUND_HALF_EVEN and full context. Reports preserve unrounded Decimal strings; no cent-rounded statement is presented. Scheduled full-H exits can precede a partial segment tail; analytic terminal exits handle remaining positions. See reports/M1_BASELINE.md.
