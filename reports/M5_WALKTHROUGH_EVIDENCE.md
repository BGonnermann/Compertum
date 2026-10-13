# Offline walkthrough evidence

11 October 2026. **347 matching source/package checks passed, zero failures/errors/skips.** Independent source review closed2/3. Three complete synthetic sequences reproduce exactly, covering ordinary cancellation, a fill during recovery and a fill during cancellation. Ten distinct portfolio records and all underlying wire observations are retained in227,717bytes, SHA256 `8c3db49a5e11d660676a1a3dacab516ba95bd99eddeb35c17308f96a70d7ecd1`. All147Python package modules, configuration, schemas and lock bytes match.

The checker binds each opening, resting, cancellation and closing proposal to its preceding portfolio. It requires complete ordered replies, unchanged order and asset identity, monotonic fills, matching long quantities, terminal cancellation evidence, confirmed closing quantities and an empty final fixture view. Recovery snapshots must retain known activity. A cancellation204 alone cannot prove cancellation. A final empty list cannot erase an unfilled closing order. New-order submission times stay between their bound draft creation and response receipt.

Review exposed four counterexamples across three defects: changed position/order asset IDs, backdated submissions, and an unchanged fill whose altered numeric spelling hid a changed average price. Each failed before targeted correction. Additional tests cover a future submission timestamp and valid equivalent numeric formatting. Earlier failure receipts remain preserved.

This is a pure evidence checker, not another broker or recovery engine. Existing M4 behavior is unchanged. Every result still names missing real-account authority, real operator approvals, actual native restart/no-resubmission, dispatch timing/count, owner/journal/health, supervision, cash/fees/ownership, final halted/disarmed state and independent real audit. M5 remains incomplete.

Source archive `2284006a91f8169451cc1decf52a8cda29596d0934698ef1ec8fa053b71321fc`; wheel `e9efacce6b23d85120e0acc7c44019fb5da9d6c0f32cc545d3b8f39967916f14`. [Receipt](../artifacts/m5/walkthrough_evidence.json). Detailed evidence: `.cache/test-runs/m5-walkthrough-evidence-20261011-01`.

Next: prepare the native read-only account integration offline so its scope is concrete before the separate account-read approval. Current paper capabilities remain unavailable. M3 is independently RAM-blocked; M6 requires ten actual supervised market sessions.
