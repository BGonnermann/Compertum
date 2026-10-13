# Offline fixture proposals

11 October 2026. **314 matching source/package checks passed, zero failures/errors/skips.** Independent source review closed in one pass. Seven complete synthetic proposal examples match exactly: 117,985 bytes, SHA256 `4d6678705d4375e928fca18739ca1347f7c8f5b5644f5581f3fd5e34aa137a6f`. Installed package contains all146 matching Python modules; config, schemas and dependency lock also match.

The immutable proposals cover one-share opening buys, discounted resting buys, individual cancellations and bounded closing children. Each approval-request envelope binds the exact proposal hash and stays NOT_GRANTED. Existing paper commands remain unavailable. No account or credential call occurred.

Checks cover the $250 total exposure ceiling, cash rather than margin buying power, all represented holdings and pending buys, 09:35-10:05 New York opening window, early closes, calendar/clock agreement, quote/portfolio freshness, supervision expiry, stable intent IDs, cancellation without effect claims, and at most12 serial close children with an explicit residual. Closing can reduce holdings above the buy ceiling without requiring alpha eligibility. Actual ownership, fees, ticks, reconciliation and native authority remain unverified.

A boundary regression exposed upward rounding for excessively precise declared liquidity. Bounded decimal input representation fixes it without weakening the notional limit. Failed receipts remain; only verified passing disposable directories were archived and removed. Price/quantity representational bounds and the session-date restriction for cancellation are recorded in the plan.

Source archive `bd7fea503ddbca236290b0b75cf6fc3cbd75590427ca21d41b49c6070a3dcdd0`; wheel `b190da68a4737591f9f9f067d7dd7491eac078c1b21e0bb3bf520328e4ca24e8`. [Receipt](../artifacts/m5/fixture_proposals.json). Detailed evidence: `.cache/test-runs/m5-fixture-proposals-20261011-01`. This verifies a component, not M5 acceptance. Next: walkthrough sequence checking.
