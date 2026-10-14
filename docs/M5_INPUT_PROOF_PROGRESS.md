# Private final proofs for native intent integration

14 October 2026. Supporting work within the accepted exact native intent implementation, after integrity16 is closed and published. No new broker capability.

The independent integration check found a concrete ordering gap: validating presence after an account/market diagnostic can invalidate the already checked context, and reversing those calls can invalidate the already checked presence. Repeating callback-bearing diagnostics cannot establish a final combined proof.

- [x] Identify the required private interface and callback ordering.
- [ ] Finish and publish integrity16 before changing its frozen source.
- [ ] Freeze tests for late cross-dependency mutation, private/single-use proof handling and original clocks.
- [ ] Factor the existing final proof tails into private proof objects; preserve public diagnostic behavior.
- [ ] Verify matching source/package cases, complete environments and final review; publish/synchronize.
- [ ] Use the verified interface in exact intent/confirmation records.

Each context will prepare a private, nonserializable proof bound to the original context, original rows/publications and exact live resources. Presence will provide an equivalent private proof retaining original acknowledgement/revocation identity. All decryption, diagnostic, secrecy and health callbacks finish before the caller verifies both proofs. Verification then uses original durable bytes/rows, identity and raw slot checks, followed by original clocks. A proof is single-use. Failed dependency validation permanently invalidates its original context or presence; replay of an already consumed proof refuses without invalidating otherwise current originals. It is not a grant and must never be returned by public routing.

The exact-intent caller holds the owner scope throughout preparation and verification. After insertion, only checked readbacks and pure identity/clock checks may run. Roll back a failed insertion before calling revocation, since its transaction can commit shared state.

Required probes cover both dependency directions; mutation/restoration cannot revive authority. Verify no decryption/health/diagnostic callback occurs during final proof verification. Preserve account30-second freshness, presence300-second expiry, owner replacement/restart, verified nonempty history and borrowed market-resource lifetime. Native stores and DPAPI use labeled simulated origins, clocks and reserves. No actual account/order request or timed transport exchange.

Primary sole writer; one bounded independent reviewer, at most three implementation review/repair rounds. Existing120-second/4-GiB/four-CPU/16-process limits,16/12-GiB host gates,128-MiB namespaces, five-second production scan and50-GiB category budget remain. Preserve every failed input/fixture; archive only closed passing scratch with exact verification. No Strata or scheduled work.

Exact next action: close integrity16, then activate the proof-interface probes before changing source.

Preparation review is complete. Thirty-nine draft cases cover both callback directions, callback-free joint verification, private/single-use handling, caller-transaction refusal, distinct opening evidence, restart, nonempty history, presence authentication and borrowed-resource preservation. Static parsing passed; no17 test or product change has run. Helpers/drafts are in .cache/test-runs/m5-input-proof-20261014-17. Activate only after integrity16 publication, preserve its passing installed fixtures, then freeze/run the39 red cases in four bounded jobs.

Measured storage planning: the completed16 pair leaves about70.6MiB scratch headroom, below a fresh128MiB reservation. Archive/verify its17 passing installed roots before17 red tests. After green39 passes and review clears, preserve/archive those four passing roots before the full261-case source lane. Preserve/archive that lane before building/installing and starting the matching package lane. Keep all red failures stationary. Each maintenance step rechecks exact passing receipts and category capacity; no runtime cap or five-second scan changes.
