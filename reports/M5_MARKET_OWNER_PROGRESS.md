# M5 market-owner engineering progress

14 October 2026. **Collection-only source checkpoint verified; M5 remains incomplete.**

The existing execution owner now hosts a private HISTORY/CURRENT_ACTIONS lifecycle. Immutable grants bind the operator, project, credentials, execution generation, exact plan and fixed GET routes. Up to32 jobs are retained in separate purpose-prefixed SQLite records. Start is committed before constructing a producer; repeated starts and restarted owners cannot recollect automatically. Account reconciliation ticks first, and market work preserves account confirmation/preflight state.

Terminal collection evidence is sealed before disposal, including canceled zero-response collections and uncertain native cleanup. Cleanup failures retain their references and prevent replacement/checkpointing. Saved consumption, evidence and publication manifests cannot be erased by stale updates. Invalid preparation requests return bounded refusals so they do not terminate the shared owner.

## Verification

**271 distinct current-source tests passed, zero failures/errors/skips**, in two serial guarded jobs:

| Checks | Passed |
| --- | ---: |
| Inert grant contracts |90|
| Actual SQLite record behavior |26|
| Native-owner lifecycle with simulated producers |25|
| Actual WinHTTP collection against local loopback |5|
| Existing account binding/preflight/read/publication/service behavior |125|

The native fixtures use invented credentials, real owners/SQLite/DPAPI and a64KiB test journal reserve. They do not establish full production reserve capacity or actual provider/account behavior. No actual provider request occurred. The longest job took68.022seconds; peak job memory was779.191MiB. All children closed. Limits remained120seconds,4GiB/fourCPU,16GiB host admission and12GiB stop headroom. Strata was not started.

Independent review: grants CLEAR3/3; persistence CLEAR2/3; collection lifecycle CLEAR2/3. Reviews found and corrected terminal-summary contradictions, stale-write regression, missing live schema checks and unbounded invalid-input exceptions. An actual loopback failure reproduced cancellation raising before sealing; its correction passed the native regression. Original failing receipts remain.

The source checkpoint pins509 files and197 modules. `artifacts/m5/market_owner_collection_source_checkpoint.json` contains exact case/plan/XML/review hashes. Detailed local evidence resides in `.cache/test-runs/m5-market-owner-20261014-01` and remains excluded from Git.

All failed-run and current checkpoint source inputs are retained by hash in `iteration-sources03.zip`. One earlier61-case preliminary passing test revision could not be reconstructed; its original receipt remains, the gap is explicitly recorded, and that run contributes no checkpoint acceptance count. No evidence was deleted or moved.

## Remaining accepted work

1. Add bounded encrypted transfer, coordinator allocation/publication and independently verified ACK.
2. Add FRESH lifecycle around the exact published HISTORY plan, private composition and authenticated routes. Keep status/composition uncached.
3. Verify publication interruptions, both process restarts, composition freshness, queue behavior and native cleanup.
4. Freeze the completed implementation and compare exact current-source/installed-package results. The installed environment still contains the prior verified opening release.

This checkpoint does not complete M5 or qualify a strategy. Durable fresh/composed lineage and the actual supervised walkthrough remain later dependencies. M3's installed Final audit remains blocked; M6 remains0/10 actual supervised market sessions.
