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

Exact next action: R and S are verified and independently reviewed. Admit a fresh bounded namespace, write and observe failing immutable-grant/state tests, then implement increment1. Continue owner lifecycle, publication, routing/composition and native paired verification in order. Preserve the terminal M3 failure; no M3 restart or Strata startup.

Inspection references: paper_read_owner.py; paper_read_publication.py; managed.py; runtime/managed_owner.py; runtime/supervisor.py; domain.py; runtime/service_budget.py; runtime/paper_market_collection.py; runtime/paper_market_fresh.py; runtime/paper_market_evidence.py; runtime/paper_market_compose.py. Existing component plans/receipts remain authoritative for exact numerical and privacy limits.

## Implementation map after dependency verification

Read-only preparation on 13 October found no missing consequential decision for this local scope. Keep the sequence M3 closeout, collection-retry integration (R), opening-baseline integration (S), then these five increments. Fresh R/S checks must precede edits to their consumers.

1. Immutable grants and purpose-prefixed state records. Reuse OperationalMarketPlan and PaperReadOwner validation/commit patterns. Test exact grant binding, unknown fields,32-job bound, conflicts, consumed-before-construction,60-second expiry, clock rollback and restart invalidation.
2. Cooperative execution-owner lifecycle. Add the private helper to PaperReadOwner tick/checkpoint/close. Account work ticks first. Preserve existing producer permits, priorities0/1/2, quotas, original20/80-second deadlines and account confirmation state. Test WAITING, cancellation, health loss and uncertain cleanup blocking replacement/checkpoint.
3. Opaque collection publication and ACK. Reuse PaperReadPublication and typed market evidence functions. Coordinator allocates genuine IDs/reservations. Test32KiB chunks,3MiB ceiling, context/hash/offset corruption, partial/failed snapshots, publication/ACK interruption, retained manifests and both-owner restart without recollection.
4. Authenticated routing and private composition. Update the matching allowlists/dispatch in supervisor.py, managed.py, managed_owner.py and domain.py. Keep status/compose uncached. Retain reopened HISTORY context; reuse its exact plan after09:25 with a separate FRESH grant. Test subject/role isolation, original-plan reuse, stale inputs, replaced/closed views and scanned bounded summaries.
5. Serial native integration with invented credentials and loopback fixtures. Extend existing paper-read helpers; test actual owner/coordinator restart, publication, composition and cleanup. Preserve account/preflight/service-budget and R/S behavior. Freeze exact IDs, compare source/installed results and obtain independent implementation review, maximum3 passes.

HISTORY/CURRENT_ACTIONS publication is in scope; durable FRESH/composition lineage remains a later required dependency. No actual provider, account or order request is authorized by this plan. Local preparation receipt: artifacts/m5/market_owner_preparation.json.


## Integration readiness - 14 October 2026

R and S are verified and published; corrected S has221 matching fresh source/installed passes and final closeout CLEAR1/3. Continue the five accepted increments above.

A bounded read-only review confirmed the implementation seams. Keep market records separate from account v1; bind the entire grant and give FRESH its own60-second start lifetime around the exact historical plan. Refactor account tick into a separate step so an idle account does not starve market work. Account work remains first; market work must not clear account confirmation or preflight. Existing producers own quota permits and unchanged deadlines.

A closed flag alone is not proof of native cleanup. Retain failed cleanup references and block replacement/checkpoint. Seal terminal collection evidence before disposal, including valid zero-response failures. Keep fresh, reopened history and combined views alive together; public status/compose must be uncached and return only a scanned bounded summary.

Coordinator history lookup must verify both authenticated subjects before injecting the recorded manifest. The published child grant is distinct from the split parent reservation. Persist the manifest before ACK and retain it after failure; never recollect or silently publish another artifact after interruption. Private transfer stays outside public supervisor actions. Detailed review notes: `.cache/test-runs/m5-opening-native-20261014-01/market-owner-design-review01.json`.

Collection-only source checkpoint: strict grants and records plus the cooperative collection lifecycle pass271 distinct source checks, including five actual WinHTTP loopback cases. Independent reviews CLEAR3/3,2/3,2/3 respectively. Installed-package verification is pending. See `reports/M5_MARKET_OWNER_PROGRESS.md`; the detailed receipt lists the original failed checks and one unavailable preliminary passing test-source revision. Next implement opaque transfer/coordinator publication, then FRESH/composition and authenticated routing, followed by native process restart and paired verification. Do not mark the combined lifecycle checklist complete before FRESH is connected.
