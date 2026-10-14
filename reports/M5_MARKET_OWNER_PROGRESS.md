# M5 market-owner engineering progress

14 October 2026. **346 source tests and the same 346 installed-package tests pass. Native restart verification and aggregate closeout remain incomplete. M5 is not accepted.**

The existing execution owner connects HISTORY/CURRENT_ACTIONS collection, encrypted publication, fresh asset/quote reads and private composition. Grants bind the operator, project, credential digest, execution generation and exact historical plan. Consumption is recorded before producer construction. Account reconciliation retains priority and its confirmation/preflight state. FRESH has a separate 60-second start lifetime and private, temporary views; it has no durable artifact reservation.

This update defers the calendar library import until calendar calculations are requested. A focused test first reproduced the unwanted import through coordinator publication, then passed after the correction. Calendar calculations, numerical thresholds, dependencies and process memory limits are unchanged. The new native fixture uses invented credentials, loopback responses and the genuine 1 GiB journal reserve. It is committed as a **known failing integration test**, with the failed results retained.

## Passing component results

The exact same 346 case IDs passed against 518 frozen files and 198 product modules. Both complete environments verified with unchanged Python 3.14.7 and 38 dependencies. The project wheel was built and installed offline; every installed product module matches source.

| Group | Source pass | Installed pass | Source seconds | Installed seconds |
| --- | ---: | ---: | ---: | ---: |
| Grants, records, collection, transfer, publication, FRESH and routing |216|216|65.647|67.836|
| Account/preflight/read/publication/service compatibility |125|125|65.435|66.530|
| Lightweight import and calendar boundaries |5|5|3.895|4.648|
| Total distinct cases |346|346| | |

All six passing test jobs have zero failures, errors or skips; all children closed. Peak aggregate job memory was 246.254 MiB. Limits remained 120 seconds, 4 GiB/four CPU, 16 GiB host admission and 12 GiB stop headroom. Strata was not started. No actual provider/account/order request occurred.

These component tests use real SQLite, DPAPI and local WinHTTP where specified, invented credentials and 64 KiB test reserves. Most coordinator RPC/restart checks use in-process adapters and object recreation. Their passing results do not replace the failed real-process integration test.

## Native integration failures

Four native attempts each failed one test, with zero skips and all children closed. None counts toward the 346 passing cases.

1. `source_process01`: coordinator startup failed with `CreateToolhelp32Snapshot:1455`. A separate import regression reproduced eager calendar/numeric loading. Moving that import and fixture row generation out of the coordinator corrected the import boundary. Aggregate job memory does not establish coordinator RSS or prove the sole cause of 1455.
2. `source_process02`: the fixture sent a forbidden public transfer command too early, closing its supervisor before collection. Its child stderr was not retained; the diagnosis follows the test sequence and existing authorization behavior. Later revisions preserve stdout/stderr on every exit path.
3. `source_process03`: collection/publication, recovery after a lost acknowledgement, fresh composition and aging progressed; the fixture incorrectly expected shutdown to succeed while private FRESH views remained held. `MARKET_CHECKPOINT_BUSY` is the required refusal.
4. `source_process04`: the fixture explicitly verified that shutdown refusal, then intentionally sent the forbidden public command. Generation 2 exited with `COMMAND_DENIED` and exactly two fresh GETs. Its teardown left a watchdog halt, `NATIVE_CALL_FAILED:PeekOwnerPipe:109`. Third-generation registrations exist, but the retained halt prevents healthy admission. The helper discarded nonhealthy status details and reported a generic 15-second startup timeout. This attempt took 41.046 seconds, peak 382.57 MiB. It did not pass third-generation acceptance.

The final independent native review is **BLOCKED 3/3**. The limit of three repairs is exhausted. Preserve the halt and runtime identities; do not clear it, extend the timeout or claim general crash recovery. The next bounded diagnostic must retain each nonhealthy startup response and distinguish a retained-halt refusal from process startup failure. The test must then verify the supported restart/refusal contract without bypassing the halt.

## Closeout and preservation

The source and installed component results are recorded, but the combined closeout verifier **failed three times** because the repository storage scan exceeded its unchanged 5-second deadline. Attempts 1/2 reached that final scan after checking the case sets, source/package/environment bindings and preservation receipts. Attempt 3 moved storage admission before archive reads and added a planned 4 MiB output-headroom check; the initial scan failed before admission. No successful aggregate closeout receipt exists. Do not treat this partial checkpoint as full integration acceptance.

A separate initial calendar-test admission also exceeded that scan deadline before launching any tests; a fresh receipt with identical test IDs and limits passed. Failed post-rename scans for native 03/04 passed subsequent read-only checks. Every failed receipt remains.

The closed native 02/03/04 fixtures remain under `backups/m5-market-source-reserve-failed-processNN-20261014-01/fixture`. All file bytes and file/directory identities were verified unchanged after native rename. The brief unlock/relock intervals are recorded; continuous exclusion is not claimed. Nothing was deleted or authorized to resume. Native 01 remains stationary. `iteration-sources01.zip` retains 524 exact source blobs for all 9 native/final plans, with no missing inputs.

Local evidence:

- Partial status: `artifacts/m5/market_owner_partial_checkpoint.json`, SHAe837e4cdafd6f77b97f5390be251312799d5d4d4842aed582f14f8b6d94cd3d2.
- Release and complete environment proofs: `.cache/test-runs/m5-market-native-20261014-01/release01.json`, `market01-source-manifest.json`, `market01-wheel-manifest.json`, `qualify-source01` and `qualify-wheel01` receipts.
- Frozen source archive SHAed07806c5cd9de7eb1ed2956789651ced80586d7dafc97cf1981abf7fbdd1e55; wheel SHAb328f808bbfebad4bf49dfe917d80f2bd3afa7c200e7dac97e1f952a4ecbb563.
- Native review: `native-implementation-review03.json`; failed aggregate checks: `component-proof01`, `component-proof02`, `component-proof03` in that namespace.

Earlier 341-source/271-source checkpoints and their reviews remain historical. The original unavailable preliminary passing test revision stays excluded from acceptance; the current 346 cases all have retained exact inputs. Detailed evidence, environments, invented credential slots and runtime databases remain outside Git.

## Remaining work

1. Diagnose storage-scan timing without raising its deadline; obtain a successful bounded closeout.
2. Diagnose the native retained-halt path with complete startup observations; complete the actual authenticated restart tests and their installed equivalent within a new bounded repair.
3. Reconcile fresh results and review the integration before accepting it.

Durable fresh/composed evidence and an actual supervised walkthrough remain later dependencies. Financial qualification stays open. M3's installed Final audit remains blocked; M6 remains 0/10 actual supervised market sessions.
