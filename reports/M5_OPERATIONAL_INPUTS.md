# Operational market-input qualification

11 October 2026. **273 matching source and installed-wheel tests passed**, with zero failures, errors or skips. Independent review closed on pass 2 of 3. All 165 installed Python modules match the frozen source. Receipt: artifacts/m5/operational_inputs.json.

The new pure qualifier retains original responses and derives one symbol's asset, quote and daily-history facts. It checks exact request parameters, explicit IEX feed, nanosecond timestamps, quote age, complete pagination, 252 preceding sessions and the last 20 sessions' dollar volume. Decimal calculations use a dedicated exact context. Missing, late, contradictory or malformed evidence stays visible and prevents qualification.

The existing fixture planner now supports an explicit matching IEX or SIP feed. Four prior SIP artifacts reproduce exactly before and after the change. Three invented operational cases (normal session, DST boundary and early close) each replayed three times, identically across source and installed wheel.

These are offline software results. No real credentials, provider requests or current market data were used. Native provenance, feed entitlement, current actions/halts, applicable fees, sector and account/ownership bindings remain unverified. This component cannot authorize transport or orders and does not accept M5 or M6.

Original failing logs remain: the missing-module test, the Windows test-ID length issue and the former SIP-only fixture restriction. The test-ID repair kept the oversized parser case intact. No test data or requirements were removed.

Source archive SHA256: `05f45d7e4ec6c1cce491de5c4fedfbb28dc7addef76bb045d22011e2b83ec85f`. Wheel SHA256: `6fd35dce331399a5bc8842bcde416a8b990b3b1962704ba0ceca61a7260dd5ae`. Final storage scan: 4.760 seconds. Test namespace: 2,223,201 bytes of 64 MiB. Available RAM: 8,152,920,064 bytes, below the unchanged M3 requirement of 8,589,934,592.

Next: current action/halt and applicable-fee evidence, then separately bounded native collection and order/reconciliation integration. Earlier component receipts remain historical evidence for their own frozen source.
