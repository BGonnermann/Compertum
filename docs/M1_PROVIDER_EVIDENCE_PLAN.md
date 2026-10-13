# Real-provider evidence and split normalization

Approved continuation, 9 October 2026. Extend the existing data package with a bounded, pure reader for the retained Alpaca bar pages and exact split normalization. Preserve the synthetic snapshot/replay contract and its financial gates. No strategy run or protocol seal is part of this supporting component.

- [x] SIP sample collected: 26 successful pages; all 104 exact minutes returned per adjustment.
- [x] Verify every request/page/hash/time/feed, terminal token, bar field and expected-row denominator. Preserve missing rows as explicit diagnostics.
- [x] Normalize raw daily prices/shares with exact rational arithmetic and only split events effective within the window and known by its cutoff. Later splits cannot alter earlier output; provider-rounded adjusted prices stay separate evidence.
- [x] Bind normalized output to original evidence and declared action sources; mark action coverage and financial acceptance unverified. Unknown required action knowledge must refuse normalization.
- [x] Reject malformed/nonfinite/duplicate/mixed-feed/protected-price inputs, missing pages/rows, future knowledge and forged in-memory evidence. Keep output deterministic under caller Decimal settings.
- [x] Verify the actual SIP sample and split case, source/wheel reproduction, independent review and unchanged legacy behavior. Update checklist, report and receipts.

Inputs are bounded byte envelopes containing frozen requests, exact body text and receipt metadata. Derived evidence is not a Snapshot and cannot enter the current synthetic-only engine by changing a provider label. This implements the evidence-backed normalization prerequisite; a complete real snapshot still needs action coverage, full warmup and the sealed protocol. Retain unknowns instead of assuming zero actions or inventing historical arrival times.

Use fresh .cache/test-runs/m1-sip-data-20261009-01 scratch within its checked headroom. Put original provider observations and derived data evidence in data/sip-probe-20261009-01. No new spending, deletion, account/order calls, protected evaluation, training, Strata changes or publication. Repair/review bound: three iterations per failure class; retain red/green evidence.
