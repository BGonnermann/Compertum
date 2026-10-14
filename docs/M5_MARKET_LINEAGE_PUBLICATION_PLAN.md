# Encrypted market-input publication and recovery

14 October 2026. Next accepted local dependency after owner-bound capture and original consumption evidence. Use existing owners, execution/coordinator state tables, storage reservations and bounded private transport. No actual provider/account/order actions, new permissions, paid data, services or Strata startup.

## Contract

Give each explicit publication a separate `capture_id`, deterministic task/path and purpose/version record. Keep FRESH grant v1 and its absent reservation unchanged. Bind trusted subject, project/alias, original FRESH job/grant hash, original HISTORY reference, reservation, original execution identity, plaintext/ciphertext hashes and immutable manifest. At most32 records and one pending transfer. Persist identity before capture. An exact retry returns retained bytes/status; an interrupted identity must never capture or encrypt again.

Use purpose-separated encryption with a new magic/entropy context and `market-lineage-{capture_id}.bin` path. Reuse bounded DPAPI, frame lengths/digests, wiping and pinned-file verification. The owner-bound plaintext retains its current bound; ciphertext stays within3MiB. Reopening checks the unique exact ledger publication, ciphertext, metadata and separately verified original HISTORY before historical reconstruction. All authority flags remain false; freshness is never restored.

The coordinator reserves a genuine3MiB records parent and exact-size child. Execution verifies the separate route/reservation before capture. Use32KiB chunks with exact context/hash/offset checks and only immediate-previous-chunk retry. Persist the manifest before private ACK. After restart, recover only the unique committed artifact matching parent/task/path/bytes and retry ACK. Never reconstruct a storage grant, recollect data or resume a failed capture. A rename without ledger commit or lost pre-publication bytes remains failed/interrupted.

Live FRESH already holds the sole opened HISTORY resource. ACK/reconstruction must borrow that exact verified resource without closing it; after restart it may open the original published history. Successful ACK releases retained transfer bytes only. It does not restore authority or implicitly close a held FRESH view. Status and compose remain read-only. Public routing uses the supervisor's authenticated subject; private chunk/ACK commands remain inaccessible publicly. Public summaries are scanned and bounded64KiB.

## Checklist

- [ ] Purpose-separated protection, exact historical reopen and strict manifest/context validation.
- [ ] Durable execution capture identity and coordinator publication route with immutable retention and reservations.
- [ ] Explicit owner/supervisor operation, bounded transfer and ACK-only recovery.
- [ ] Focused negative tests, frozen source/package compatibility, actual native restart/lost-ACK fixture and independent review.
- [ ] Update checkpoint/README, preserve evidence and publish verified checkpoint.

Required cases include encryption/context/frame tampering, original proof/history substitution, ignored writes, exact retry after age advances, multichunk corruption/replay, publication before route-save failure, lost ACK, both owners recreated, rename without ledger, held-HISTORY capacity and buffer cleanup failure. Capture/publication/recovery must add zero HTTP requests. Use existing120-second/4GiB/fourCPU limits, host16/12GiB gates, one heavy job and unchanged category caps/deadlines. Check storage headroom before full-reserve native tests; current backups are near their20GiB category ceiling. Preserve failed evidence and never change runtime identities to manufacture success.

Proceed in dependency order: protection/reopen, durable records/routes, owner transfer/recovery, paired/native acceptance. Record a bounded acceptance inventory and at most three evidence-led repair/review iterations before each implemented increment; every pending dependency remains visible until the whole publication contract is verified.

Exact next action: finish the consumption increment's installed verification and publication checkpoint, then reproduce missing protection/reopen behavior before implementation. Existing APIs to reuse: `paper_market_evidence`, `paper_market_publication`, `paper_opening`, `StorageManager.reserve_bytes/split_grant`, `MarketRecords` and authenticated supervisor/owner routing.
