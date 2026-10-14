# Durable market lineage publication

14 October 2026. **696 matching cases passed in each source/installed environment**, with zero failures, errors or skips and every child closed. Each lane ran695 component cases and one native lifecycle. Both complete environments and final aggregate verification passed. Independent implementation review2/3 is CLEAR; final review3/3 is CLEAR.

## Implemented behavior

An explicit publication retains one coherent historical market-input capture under its own immutable identity. The execution owner records the identity before capture and the exact encrypted evidence before transfer. The coordinator reserves storage, checks bounded chunks and records the committed manifest before acknowledgement. Exact retries preserve the original capture; neither restart nor reopening recollects data or restores freshness, a grant or trading authority.

Four private runtime modules implement the capture records, publication routes, execution transfer and coordinator recovery. Existing owner/supervisor routing supplies the authenticated subject. Read-only status is uncached. The original FRESH grant schema, account-first scheduling, provider request count and existing resource limits are unchanged.

Three review findings were reproduced and corrected:

- A restart re-acknowledged already published HISTORY and could downgrade it while FRESH held its reader. Recovery now verifies the committed ledger without redundant acknowledgement.
- A first request lost before private delivery could not be retried. The original live coordinator now permits explicit idempotent delivery while retaining its genuine grant; restart never reconstructs that grant.
- Credential refusal during protection left affected FRESH state active. Capture/protection failure now invalidates that state; uncertain cleanup keeps capacity blocked.

An additional test wrongly expected a clock advance during encryption to erase an already coherent historical capture. The corrected test preserves original bytes/time and verifies that subsequent live composition refuses stale input. The failed test and its source remain retained.

## Verification inventory

The final inventory contains696 distinct cases per environment:695 component checks and one real Windows lifecycle test. The freeze binds535 source/configuration/test inputs and206 product modules. The offline wheel build and installation passed; both complete environments qualified, with Python and38 dependencies unchanged.

| Group | Cases per environment |
| --- | ---: |
| Capture and route persistence |84|
| Transfer/refusal/recovery |46|
| Market grant and record contracts |116|
| Market owners |42|
| Existing publication and routing |39|
| Original consumption |29|
| Owner-bound capture |21|
| Encrypted lineage |43|
| Historical collection/encryption |105|
| Fresh inputs |20|
| Capture/reconstruction foundation |25|
| Account/read compatibility |125|
| Native full-reserve lifecycle |1|

The native test uses local replies and invented credentials. It requires a real nonsparse1GiB reserve, lost HISTORY and lineage acknowledgements, three process generations, identical retained evidence after restart, no extra collection, stale-input refusal, and a deliberate fatal private-command probe placed last. These are engineering fixtures, not actual market sessions.

All jobs retain the120-second deadline,4GiB/fourCPU/16-process limit,16GiB host-memory admission and12GiB stop floor,1.25GiB test namespace, five-second production storage scan and50GiB category budget. Native fixtures are admitted separately and run serially. Strata remains off.

## Release and retained evidence

N = `.cache/test-runs/m5-market-native-20261014-01`; O = `.cache/test-runs/m5-lineage-package-20261014-01`. Detailed local evidence is excluded from Git.

- Release11 SHA `30238e3f037ce0c56de16cb90f61d37f572d8f0814f438187f94713bb41e2603`.
- Source archive SHA `a0c0eea9e379cd15a039be4f217172cfb20d33176ccd2fe90641fd35c22d98fc`.
- Installed wheel SHA `282d8d4624688aa1a56690394ae2cf5147524b7110e64d199e8e50ddad378fb0`.
- Source passing-fixture archive SHA `2e9062f70a6c6fc41f4e8655a649bb883b51da5b3dbbce784e89c97e8ebe291f`. Every selected byte/link/directory was verified before removing18 disposable passing roots; all failed fixtures and original reports remain.
- Installed passing-fixture archive SHA `82b1cac089a4187b0df810e9f5ea030b2901dc44255dc9ea7ddb0428837d2348`;14 passing roots archived and verified before cleanup. Across both selections,11715 files,5697 directories and493 links were checked. Failed fixtures remain stationary.
- Iteration source archive SHA `3a4ecb3f209db70f44ae9ed1f8d386a9a487c3181375fff8f189979445dcf40c`; all95 plans resolve to581 retained exact source blobs, none missing.

The source native lifecycle passed in83.577899 seconds and the installed lifecycle in83.546493 seconds. Both exercised three process generations, request counts3/2/0, one lost HISTORY acknowledgement and one lost lineage acknowledgement, exact manifest/evidence retention, current-to-stale qualification and historical-only reopening. The second-generation fixture deadline and final deliberate `COMMAND_DENIED` are expected test closures, not unreported runtime failures. Maximum accepted job memory was826568704 bytes; maximum elapsed time was83.577899 seconds.

The passing source native fixture is preserved at `backups/m5-market-source-reserve-passed-lineage11-20261014-01/fixture`:46 files and16 directories, every byte and native identity unchanged. The checked rename records its brief unlock/relock interval and preserves the original historical link. It does not authorize runtime resumption or free physical disk space. The installed fixture remains in its original test location; its46 files and16 directory identities were separately pinned and verified. Neither fixture may be resumed as a production runtime.

The maintenance planner initially compared a set to a list and stopped before selecting/deleting anything. Its original script and failure remain. A preparation-label collision also refused before launch; a fresh label preserved the old receipt. Neither changes product-test outcomes or resource gates.

Aggregate receipt: `artifacts/m5/market_lineage_publication_pair_verified.json`, SHA `7a17f4f2b3532bd73670bf6a6d32de9642776c228f4ec8b80a9de7dd1ed48041`. The verifier pins254 final evidence inputs, checks the exact case sets, full release/environment bindings, every preserved source blob, all passing-fixture archives and both native fixture inventories. Verifier SHA `575da23e79f808db2ccb469f3e5f4cbefeddca82b19969d0efc16f254b325116`; reviewed-input map SHA `a73ee002ea63805a4feac1ddfac1bea62be1d2d7aec7d1cec206e21f9774ff93`. The aggregate command exited0 in8.876529 seconds under the unchanged production storage scan. Final independent review3/3 is CLEAR; receipt `artifacts/m5/market_lineage_publication_final_review.json`.

Seven failed source test iterations remain preserved and excluded from acceptance:27 cases/27 failures;54/1;84/30;1/1;26/5;2/2;5/4. Each recorded zero errors/skips and closed children. Their exact source versions are in the iteration archive; the clock-test expectation correction is disclosed above.

## Acceptance boundary

Financial qualification, full M5 acceptance and actual account/order authority remain open. M6 remains0/10 actual supervised sessions. M3's lost installed-audit exit receipt remains terminally blocked. After publication, continue [native paper admission](../docs/M5_PAPER_ADMISSION_PLAN.md), grant/risk/supervision and reconciliation integration in the existing execution owner/journal; connect M6 semantic readers when their real producers exist.
