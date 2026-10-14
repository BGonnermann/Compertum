# M5 market-owner engineering progress

14 October 2026. **341 source checks pass; process-level and installed-package verification remain pending. M5 is incomplete.**

The existing execution owner now handles HISTORY/CURRENT_ACTIONS collection, encrypted publication, fresh asset/quote reads and private composition. Grants bind the authenticated operator, project, credential digest, execution generation and exact plan. Consumption is committed before producer construction. Account reconciliation retains priority and its existing confirmation/preflight state.

The coordinator allocates genuine collection reservations, transfers ciphertext in32KiB chunks and publishes through the durable storage ledger. Execution independently verifies the encrypted artifact before acknowledging it. Recovery reuses a verified publication solely for acknowledgement; it cannot silently recollect or manufacture a replacement artifact. Failed artifacts and successful manifests remain preserved.

FRESH has no artifact reservation. It reuses the exact published HISTORY plan with a separate60-second start lifetime. Execution retains the reopened history and fresh private views together. Public status/composition rechecks age on every request, including repeated request IDs, and returns a scanned bounded summary. Stale inputs remain blocked. Health, credential or clock/context failure interrupts the job and revokes private views. Uncertain native cleanup retains its producer and blocks checkpoint/replacement.

## Verification

Two serial guarded jobs passed **341 distinct current-source tests, zero failures/errors/skips**:

| Checks | Passed |
| --- | ---: |
| Immutable grants |90|
| Actual SQLite records |26|
| Native owner with simulated collection producers |25|
| Actual WinHTTP collection against loopback |5|
| Private encrypted transfer and acknowledgement |12|
| Coordinator publication and interrupted acknowledgement |34|
| Fresh reads, history reuse, composition and cleanup |20|
| Authenticated routing and uncached public reads |4|
| Account binding/preflight/read/publication/service compatibility |125|

The216-case market job took69.130seconds; the125-case compatibility job took70.979seconds. Peak job memory was777.125MiB; all children closed. Limits remained120seconds,4GiB/fourCPU,16GiB host admission and12GiB stop headroom. Strata was not started.

These fixtures use real native owners, SQLite, DPAPI and local WinHTTP where specified, with invented credentials and64KiB test journal reserves. Coordinator RPC is adapted in-process, and restart tests recreate owner objects. **They do not yet prove authenticated communication between real processes, process restart, full production reserve behavior for this integration, or installed-package equivalence.** No actual provider/account request occurred.

Independent component reviews: grants CLEAR3/3; records CLEAR2/3; private transfer CLEAR1/3; collection publication CLEAR2/3; fresh lifecycle/routing CLEAR2/3. Reviews exposed preparation-retry state drift and clock-error cleanup failure. Regression tests reproduced both before correction. The clock regression originally produced four failures and two teardown errors; all20 fresh cases pass after revocation was corrected to use the durable terminal summary without trusting invalid private state.

The checkpoint pins514 files and198 product modules. `artifacts/m5/market_owner_routing_source_checkpoint.json` binds the exact case, plan, XML, review and preservation hashes. `routing-proof01` exited0; the independent source-checkpoint audit is CLEAR1/3. Detailed evidence remains local under `.cache/test-runs/m5-market-owner-20261014-01` and excluded from Git.

All failed/current source inputs are retained by hash in `iteration-sources04.zip` (544 unique blobs,35 original plans). One previously disclosed61-case preliminary passing test revision remains unavailable and contributes no acceptance count. Its original receipt remains. No evidence was deleted or moved. Earlier271-case and212-case checkpoints are historical; the341 checks above ran against the current source map.

## Remaining accepted work

1. Exercise the actual authenticated owner/coordinator channels, interrupted acknowledgement, both process restarts and fresh composition using invented native loopback fixtures.
2. Freeze/build the completed release, qualify both complete environments without changing Python/dependencies, and compare exact current-source/installed-package results.
3. Reconcile results, obtain independent closeout review and publish the verified integration checkpoint.

Durable fresh/composed evidence and an actual supervised walkthrough remain later dependencies. This engineering checkpoint does not qualify a strategy. M3's installed Final audit remains blocked; M6 remains0/10 actual supervised market sessions.
