# Offline walkthrough evidence plan

11 October 2026. Continue authorized local engineering without account access, credentials, transport, broker writes or changes to M4 owners. Primary writer, one bounded independent reviewer, at most3review passes. Existing M4 recovery and lifecycle behavior remains implemented by its existing owners and tests.

Build a pure paper_walkthrough.py checker over immutable PaperPortfolioBundle, PaperFixtureProposal and PaperResponse records. This checks a bounded synthetic evidence sequence, never runs a broker simulation or grants authority. Return an immutable result with INTERNAL_FIXTURE_SEQUENCE_VALID and actual M5/native-restart/economic/authorization acceptance false or UNVERIFIED. Reuse existing M4 recovery scenarios as the declared lifecycle requirements, without implementing a second fake broker or accepting a caller boolean as proof of native behavior.

Input: baseline portfolio; opening step; holding recovery portfolio; resting step; resting recovery portfolio; cancellation step; closing step. Each PaperFixtureStep binds a proposal, exact tuple of replies, and after-portfolio. At most12replies/children, eight portfolio pages and64KiB result, with all underlying records already bounded. Each proposal binds the exact preceding portfolio content; all input records stay immutable. Invalid or incomplete evidence raises ContractError with a fixed reason.

Validate initially empty, complete fixture portfolio; exact four kinds OPEN_BUY/RESTING_BUY/CANCEL/CLOSE_LONG; same paper origin/account/alias/symbol/session; timestamps in order; immutable draft request/reply equality; no error/404 or unknown submit response; matching broker/client IDs and immutable order fields; monotonic observed cumulative fills; complete terminal evidence after opening and cancel; initial resting acceptance and active order; no repeated submit/client IDs. All supplied portfolio/order evidence remains hashed in the final record.

Verify quantity conservation across every step, including any fills during a represented restart. Holding recovery must keep the opening filled order and holding. Resting recovery must keep the same order/client identity; unrecorded orders, changing old fills and unexplained positions reject. Cancellation acceptance alone is insufficient: its after-portfolio must prove the target terminal, retaining any fills and matching long quantity. Close can contain up to12children and must have no proposal residual for a complete walkthrough. Its after-portfolio must show each child terminal with cumulative fills equal to its planned quantity and a fresh empty position/open-order view. No cash/fee/ownership proof is inferred from these quantity checks.

The checker cannot establish the truth of supplied synthetic data, actual POST count, native process identity/restart, research pause<=30s, monitoring continuity, disarmed/halted finish, real operator approval, ownership, account binding or cash/fee reconciliation. Return that exact missing-evidence list even for a valid synthetic sequence. Prior M4 acceptance is historical independent evidence, not reclassified as a real paper walkthrough.

- [x] Admit a fresh64MiB namespace.
- [x] Red tests for sequence identity, bindings, conservation, cancellation terminal evidence, restart continuity, close residuals and immutable results.
- [x] Implement minimal pure checker and repair focused failures.
- [x] Bounded review, source/installed-wheel checks including prior314cases, exact retained sequence reproduction, lock/package/storage checks, report and checkpoint.

Next: reconcile the concrete remaining M3/M5/M6 gates and prepare the exact account-read qualification request. Actual paper credentials/account/data authority remains separate from the historical market-data permission; every actual order plan still has its own approval gate. M6 requires10actual supervised sessions and cannot be accelerated.
