# Encrypted market-input publication and recovery

14 October 2026. Next accepted local dependency after owner-bound capture and original consumption evidence. Use existing owners, execution/coordinator state tables, storage reservations and bounded private transport. No actual provider/account/order actions, new permissions, paid data, services or Strata startup.

## Contract

Give each explicit publication a separate `capture_id`, deterministic task/path and purpose/version record. Keep FRESH grant v1 and its absent reservation unchanged. Bind trusted subject, project/alias, original FRESH job/grant hash, original HISTORY reference, reservation, original execution identity, plaintext/ciphertext hashes and immutable manifest. At most32 records and one pending transfer. Persist identity before capture. An exact retry returns retained bytes/status; an interrupted identity must never capture or encrypt again.

Use purpose-separated encryption with a new magic/entropy context and `market-lineage-{capture_id}.bin` path. Reuse bounded DPAPI, frame lengths/digests, wiping and pinned-file verification. The owner-bound plaintext retains its current bound; ciphertext stays within3MiB. Reopening checks the unique exact ledger publication, ciphertext, metadata and separately verified original HISTORY before historical reconstruction. All authority flags remain false; freshness is never restored.

The coordinator reserves a genuine3MiB records parent and exact-size child. Execution verifies the separate route/reservation before capture. Use32KiB chunks with exact context/hash/offset checks and only immediate-previous-chunk retry. Persist the manifest before private ACK. After restart, recover only the unique committed artifact matching parent/task/path/bytes and retry ACK. Never reconstruct a storage grant, recollect data or resume a failed capture. A rename without ledger commit or lost pre-publication bytes remains failed/interrupted.

Live FRESH already holds the sole opened HISTORY resource. ACK/reconstruction must borrow that exact verified resource without closing it; after restart it may open the original published history. Successful ACK releases retained transfer bytes only. It does not restore authority or implicitly close a held FRESH view. Status and compose remain read-only. Public routing uses the supervisor's authenticated subject; private chunk/ACK commands remain inaccessible publicly. Public summaries are scanned and bounded64KiB.

## Checklist

- [x] Purpose-separated protection, exact historical reopen and strict manifest/context validation;243 matching source/package cases, full environments qualified. Final aggregate review3/3 is CLEAR.
- [x] Durable execution capture identity and coordinator publication route with immutable retention and reservations.
- [x] Explicit owner/supervisor operation, bounded transfer and ACK-only recovery.
- [x] Focused negative tests, frozen source/package compatibility, actual native restart/lost-ACK fixture and independent review.
- [x] Update checkpoint/README, preserve evidence and publish verified checkpoint.

Required cases include encryption/context/frame tampering, original proof/history substitution, ignored writes, exact retry after age advances, multichunk corruption/replay, publication before route-save failure, lost ACK, both owners recreated, rename without ledger, held-HISTORY capacity and buffer cleanup failure. Capture/publication/recovery must add zero HTTP requests. Use existing120-second/4GiB/fourCPU limits, host16/12GiB gates, one heavy job and unchanged category caps/deadlines. Check storage headroom before full-reserve native tests; current backups are near their20GiB category ceiling. Preserve failed evidence and never change runtime identities to manufacture success.

Proceed in dependency order: protection/reopen, durable records/routes, owner transfer/recovery, paired/native acceptance. Record a bounded acceptance inventory and at most three evidence-led repair/review iterations before each implemented increment; every pending dependency remains visible until the whole publication contract is verified.

Consumption dependency is published as `4e17cf9`. Protection/reopen increment10 acceptance: exact owner-bound originals survive encryption and historical reconstruction; current execution identity is required only for protection; reopening after owner recreation cannot renew authority. Verify unique exact ledger publication, strict purpose/context/framing, original grants/consumption/HISTORY, pinned bounded file reads, real DPAPI, buffer wiping, and borrowing the held HISTORY resource without closing it. Exact publication retry must preserve bytes; conflicting bytes or uncommitted renames refuse. No new public operation until durable capture identity is implemented. Maximum three evidence-led review/repair iterations for this increment; retain every failed receipt. Run focused source cases, independent review, matching frozen installed cases and affected encrypted-history/owner compatibility before publication. Existing120-second/4GiB/fourCPU and storage/memory gates apply.

Exact next action: publish independently reviewed increment10, then implement durable capture routes and transfer/recovery. Existing APIs to reuse: `paper_market_evidence`, `paper_market_publication`, `paper_opening`, `StorageManager.reserve_bytes/split_grant`, `MarketRecords` and authenticated supervisor/owner routing.

## Durable capture integration after increment10

Use separate `paper_market_lineage_capture:<capture_id>` execution records and `paper_market_lineage_route:<capture_id>` coordinator records, with version markers and checked transactional writes. Bind subject/project/alias, original FRESH job/grant hash, exact HISTORY reference, original execution identity, deterministic task and genuine reservation. Capture state proceeds from CAPTURING to READY, then PUBLISHED; failures/restarts preserve FAILED/INTERRUPTED identities. Commit identity before capture, commit exact plaintext/ciphertext hashes before transfer, and commit manifest before acknowledgement releases retained bytes. Exact retry returns retained status/bytes, never a new capture. Permit historical ACK from a terminal record only when the exact committed artifact and original evidence match.

Keep the existing public `paper_market_read` action. Add explicit `publish_lineage(capture_id, job_id, grant_sha256)` and uncached read-only `lineage_status(capture_id)` operations. Supervisor supplies the authenticated subject. Use distinct private `lineage_chunk`/`lineage_ack` shapes under the existing nonpublic `paper_market_transfer` RPC. Bind every chunk to capture/task/project/alias/original grant, ciphertext hash/length and exact offset. Do not expand RPC beyond5seconds/64KiB; measure capture/protection and ACK against that boundary.

The held FRESH producer requires a narrower capture-capacity check, without weakening ordinary `_capacity()`. Pending encrypted transfer must block checkpoint/replacement, including after FRESH cancellation. Cancellation must not erase the independent capture. ACK releases only retained transfer bytes. If capture is queued, progress it before `_MarketOwner.tick()`'s held-FRESH return, retaining account-first scheduling. Coordinator recovery may locate an exact ledger artifact and retry ACK; it may never recreate a grant or request a new chunk/capture after its own restart.

Native acceptance needs one fresh combined lifecycle fixture per environment, run serially with actual1GiB reserve. Exercise lost ACK, immutable capture reopening after both owners restart, and zero extra GETs; put deliberate fatal authorization probes last. Admit storage separately for each lane. Current backup headroom cannot retain two more uncompressed1GiB fixtures. Any cleanup must select only attributable passing disposable fixtures, archive and verify content first, and retain all failed fixtures/receipts. Content archives do not prove resumable runtime identity. Preserve existing limits and freeze the next acceptance inventory before implementation.

Next implementation11 acceptance checklist (maximum three evidence-led review/repair iterations):

- [x] Immutable bounded capture/route records with exact retry, ignored-write rollback, restart interruption and no identity reuse or reconstruction of grants.
- [x] Explicit authenticated publication and uncached status; one retained transfer; unchanged account-first scheduling, health/credential gates, ordinary producer capacity and checkpoint refusal.
- [x] Genuine parent/exact child reservations, strict32KiB transfer, manifest-before-ACK and historical ACK-only recovery after lost reply or both owners restart. No additional HTTP request or changed FRESH grant schema.
- [x] Negative/recovery/routing compatibility in identical frozen source/package groups, complete environment qualification, and one admitted native lifecycle fixture per environment within existing resource/storage/RPC limits.
- [x] Preserve failures and all source inputs, reconcile exact outcomes, independent final review, update status and synchronize master/GitHub/clone.

Increment10 maintenance completed before this dependency:46 passed temporary roots are archived and verified; failed fixtures and original reports remain. Production aggregate admission afterward measured scratch3730596600B and backups19983556808B. These are observations, not advance admission for future native fixtures. Recheck before each new job. Actual broker/account/order actions and M5 walkthrough/session acceptance remain outside this local engineering increment.

## Verified closeout - 14 October 2026

Increment11 completes this contract:696 identical source/package cases per lane, including one full Windows restart/lost-ACK lifecycle each; zero failures, errors or skips. Both full environments qualified and final independent review3/3 is CLEAR. See [the publication report](../reports/M5_MARKET_LINEAGE_PUBLICATION.md). The earlier next-action paragraphs are historical. Current next action: publish this verified checkpoint, synchronize the requested clone, then implement the private input context in [the admission plan](M5_PAPER_ADMISSION_PLAN.md). Publication completion is verified separately by exact remote/local HEAD equality.
