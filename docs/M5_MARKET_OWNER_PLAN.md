# Operational market reads in the existing owner

12 October 2026. Next M5 integration after the staged collection-retry dependency passes native/package verification. Autonomous local engineering remains authorized; no actual requests, credentials, purchases or account/order authority are implied.

The collection, fresh-input and composition components already exist. Their missing connection is an explicitly authorized lifecycle in the execution owner and opaque evidence publication in the coordinator. Reuse those components and the existing shared request queue. Do not add another owner, journal or transport.

## Contract

- Keep the account packet's exact 13-GET contract unchanged. Add separate public paper_market_read and private paper_market_transfer routes beside paper_read. Public operations: prepare, authorize, start, status, cancel and compose. Private transfer: chunk and ack. Accept only exact operation-specific keys. Reject supplied URLs, origins, clocks, priorities, fixture ports, manifests, raw observations and verification flags.
- Prepare one selected allowed symbol and mode, HISTORY, CURRENT_ACTIONS or FRESH. Freeze OperationalMarketPlan from native time/calendar before the original 09:25 cutoff. FRESH reuses that exact published history plan later in the session. Its separately created grant gets its own 60-second start lifetime; never refresh the historical plan's cutoff or old provenance.
- Bind the authenticated subject, project, execution instance/generation, alias, pinned credential digest, job/task/reservation IDs, mode, exact plan bytes/hash, prior history reference and fixed permitted routes/origins in the grant hash. Authorize/start require this grant hash, not the shared market-plan hash alone.
- Retain bounded purpose-prefixed records in existing execution/coordinator state tables. Maximum32 jobs, one active market producer/publication. Preserve strict account v1 records. The coordinator allocates task/reservation identities and injects genuine recorded publication references. Reserve at most the existing3MiB encrypted artifact ceiling for collection jobs; fresh-only work does not pretend to have a durable artifact.
- Persist consumed start before producer construction or any possible request. Exact repeats never dispatch twice. Restart marks unfinished work interrupted, invalidates current grants and private views, and never automatically recollects data. Keep any successful publication manifest after later transfer/ACK failure.

## Existing component integration

PaperReadOwner already owns the live execution lease, StateStore, JournalReserve, MutualHealth and credential slot. Add a private market helper there. Tick account reconciliation first, then one cooperative market step. Preserve current account preflight and confirmation when market work starts. Include pending handles, retained ciphertext, reopened handles and composition views in checkpoint and close handling.

Use _MarketCollection for HISTORY/CURRENT_ACTIONS and _MarketFresh for ASSET then QUOTE. Their dispatch/poll paths already acquire and bind genuine producer permits. Do not acquire an extra wrapper permit. Keep account priority0, fresh priority1 and collection priority2. ASSET uses the PAPER service; QUOTE uses DATA. A fresh grant explicitly names both fixed origins. Both independent100/min quotas, startup fence, queue capacity, attempt limits, original20/80-second deadlines and cutoff checks remain unchanged. WAITING consumes time and does not renew a grant.

Mirror the bounded PaperReadPublication lifecycle with the existing typed market evidence functions. Transfer ciphertext in32KiB chunks, with exact context/hash/offset checks and3MiB ceiling. Seal valid terminal partial/failed snapshots before disposing their producers. Publish via the existing reservation and PUBLISHED ledger. Execution independently verifies the exact encrypted artifact on ACK. Uncertain native cleanup blocks replacement and checkpointing.

Compose only the exact published/reopened HISTORY source and current private FRESH source, with matching original plan and credential binding. Retain the reopened context for the composition's lifetime. Recheck freshness on every use. Return only a bounded, scanned summary of IDs/hashes/counts/times/deficiencies, never the private payload through the64KiB RPC. Status/composition reads are uncached.

The current encrypted schema supports collection evidence only. This increment publishes HISTORY and CURRENT_ACTIONS; FRESH/composition stay private and temporary. Durable fresh/composed evidence is a required later dependency before actual order-input lineage/M6 semantic acceptance. No component completion clears that gap or the existing entitlement/action/fee/ownership/risk/supervision/grant gates.

## Verification and sequence

- [x] Bounded source-backed dependency review; existing signatures and routing/publication seams identified.
- [ ] Implement/test immutable grants and strict state records, then owner lifecycle.
- [ ] Implement/test coordinator routing, transfer and genuine publication; preserve failure evidence.
- [ ] Test cross-subject/project/alias/mode/credential/grant substitutions, expiry, repeated starts and both process restarts.
- [ ] Test account/market scope isolation, exact fixed origins, queue priority/quotas/startup fence and WAITING deadlines through actual producer permits.
- [ ] Test health loss, cancellation, uncertain cleanup, checkpoint refusal and replacement prevention.
- [ ] Test corrupt/replayed chunks, publication mismatch, interrupted publication/ACK, no implicit recollection and exact idempotency.
- [ ] Test frozen-plan reuse after09:25, late-history refusal, stale fresh data, source mismatch and historical reopening without renewed authority.
- [ ] Native loopback owner/coordinator/restart fixtures with invented credentials and no exposed production fixture switches; exact current-source/installed-package regression/replays.
- [ ] Independent implementation review, maximum3 passes; retain receipts/checkpoint and continue remaining M5/M6 dependencies.

Exact next action: complete the frozen M3 pair,77audits and Final. Verify/integrate staged retries and opening baseline in dependency order, then implement this integration with fresh storage/RAM admission. No native fixture suites run concurrently with M3. Active source/package Q remain frozen; this document does not change them.

Inspection references: paper_read_owner.py; paper_read_publication.py; managed.py; runtime/managed_owner.py; runtime/supervisor.py; domain.py; runtime/service_budget.py; runtime/paper_market_collection.py; runtime/paper_market_fresh.py; runtime/paper_market_evidence.py; runtime/paper_market_compose.py. Existing component plans/receipts remain authoritative for exact numerical and privacy limits.
