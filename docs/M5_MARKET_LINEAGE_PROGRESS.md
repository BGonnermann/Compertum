# Durable lineage implementation11 checkpoint

14 October 2026. Increment11 verification is complete:696 matching cases per source/installed lane, zero failures/errors/skips, all children closed. Both complete environments and aggregate verification passed. Installed package contains release11 (535 frozen inputs/206 modules). Final independent review3/3 is CLEAR; publication is next. Aggregate SHA `7a17f4f2b3532bd73670bf6a6d32de9642776c228f4ec8b80a9de7dd1ed48041`. See [the complete report](../reports/M5_MARKET_LINEAGE_PUBLICATION.md). The execution notes below preserve intermediate history.

## Checklist

- [x] Add bounded capture/route records, immutable original bindings, checked writes and restart interruption.
- [x] Add explicit publication/status routing, queued capture, reserved opaque transfer and historical ACK recovery.
- [x] Reproduce review1 findings and implement targeted corrections.
- [x] Finish46 source refusal/recovery checks; independent implementation review2/3 CLEAR.
- [x] Finish final source compatibility inventory:695 unit cases plus one separate native lifecycle.
- [x] Freeze/build/install offline; qualify both complete environments and run matching installed checks.
- [x] Run one separately admitted native lifecycle fixture per lane; preserve each result before the next heavy job.
- [x] Preserve all failed/source inputs, aggregate evidence, final review3/3 and update README/report.
- [ ] Publish this verified checkpoint and synchronize the requested clone.

Current source: four new runtime modules (`paper_market_lineage_records`, `paper_market_lineage_routes`, `paper_market_lineage_transfer`, `paper_market_lineage_publication`), three new test modules, routing in existing market owner/publication and supervisor, and uncached lineage-status routing coverage. No original grant schema or resource limit changed.

## Evidence so far

N = `.cache/test-runs/m5-market-native-20261014-01`. All finished jobs below observed process exit, closed every child, and had zero errors/skips. These are source checks only.

| Label suffix after `source_lineage_` | Passed | Failed | Observation |
| --- | ---: | ---: | --- |
| `records_missing11` | 0 | 27 | Missing capture record module |
| `records_green11` | 27 | 0 | Initial record contract |
| `records_extendedred11` | 53 | 1 | New capture incorrectly allowed after original FRESH interruption |
| `records_routesred11` | 54 | 30 | Restart correction passed; coordinator route module absent |
| `records_routesgreen11` | 84 | 0 | Both persistence contracts |
| `transfer_probe11` | 0 | 1 | Public transfer integration absent |
| `transfer_greenb11` | 21 | 5 | Correct lineage states; redundant original HISTORY ACK during restart |
| `transfer_historyprobe11` | 0 | 2 | Redundant ACK downgrades published HISTORY while FRESH holds reader |
| `transfer_reviewprobe11` | 1 | 4 | Initial delivery retry, credential cleanup and a disclosed clock-test assumption |
| `transfer_reviewa11` | 23 | 0 | First half of expanded repaired recovery checks |
| `transfer_reviewb11` | 23 | 0 | Second half of expanded repaired recovery checks |

Implementation review1/3 found three issues: redundant ACK for durably PUBLISHED HISTORY, inability to retry the first private request before delivery, and missing FRESH invalidation when protection rejects credentials after capture. Corrections now verify the published HISTORY ledger without re-ACK; retain a REQUEST entry and genuine grant for explicit idempotent retry only within the original live coordinator; and invalidate FRESH around capture/protection failures while preserving uncertain cleanup. Route/identity failures do not revoke valid FRESH.

The extra clock-jump refusal expectation in `transfer_reviewprobe11` was incorrect: encryption preserves an already coherent historical capture; it does not restore current freshness. That failed test/source remains retained. Its replacement verifies the original capture bytes/time, false authority flags, and a subsequent composition refusal with FRESH invalidation. The uncertain-cleanup test now injects the actual credential refusal.

Frozen expanded plan: `plan_lineage_transfer_reviewgreenb11.json`, SHA `7d9cdfcd74dbe48ff73458461d94038167e6dd384db6e56e70087623cf4c95c5`, 46 cases/534 inputs. Two serial groups have23 cases each. First group passed in59.464743 seconds, peak224149504 bytes. Second group passed in57.445656 seconds, peak224333824 bytes; shell session81517 closed with exit0. Review2/3 is running with `/root/budget_explanation_review`. Exact next action: inspect the reviewer result, repair only evidence-backed findings, then freeze the native lifecycle test and compatibility inventory.

Failed source versions are retained under N with `-green11`, `-routesgreen11`, `-transfergreenb11`, `-transfergreen11`, `-historyred11` and `-reviewred11` suffixes. All failed fixtures/IDs remain stationary. Aggregate preservation is still pending; never label this increment complete from these partial results.

## Active verification

Implementation review2/3 is CLEAR; receipt `artifacts/m5/market_lineage_publication_implementation_review.json`. The later native test freeze binds535 files/206 product modules. Final inventory is696 distinct cases per lane:14 serial unit groups total695, followed by one separately admitted full1GiB native lifecycle. Source batch shell51145 is running; its first seven groups passed356 cases, zero failures/errors/skips and all children closed. Do not modify frozen source/tests while it runs.

Exact next action: observe all14 source group receipts, run `N/Build-Install-Lineage11.ps1`, then the identical installed groups using `O/Run-LineagePublication11.ps1 -Lane installed` (O=`.cache/test-runs/m5-lineage-package-20261014-01`). Prepare fresh native namespaces and verified passing-fixture maintenance before either native reserve. Preserve failed evidence and all frozen source versions, then aggregate and request the final review3/3. The earlier review-running paragraph above is historical.

Source batch51145 finished with exit0: all695 component cases passed, zero failures/errors/skips and every child closed. Exact final plan535 inputs/206 modules, total696 including the pending native test. Source fixture maintenance selected18 closed passing roots (6243 files,3075 directories,271 links,155141869 logical bytes). A planner list-versus-set comparison failed before writing its selection; the original script/failed receipt remain, and the corrected exact-set check passed. An old preparation-label collision refused before launch; no old receipt was overwritten. Archive verification is running as shell14072. Next: finish verified source cleanup, build/install/qualify release11, then identical installed checks. Native namespaces and final aggregate verifier are prepared but unexecuted; the verifier still requires final reviewed pins.

Source maintenance is complete: archive SHA `2e9062f70a6c6fc41f4e8655a649bb883b51da5b3dbbce784e89c97e8ebe291f`; all6243 files,3075 directories and271 links verified before removing the18 passing temporary roots. Failed fixtures and original result files remain. Release11 built/installed offline; full source and wheel qualification passed in25.533023 and24.693086 seconds. Release SHA `30238e3f037ce0c56de16cb90f61d37f572d8f0814f438187f94713bb41e2603`; source archive SHA `a0c0eea9e379cd15a039be4f217172cfb20d33176ccd2fe90641fd35c22d98fc`; wheel SHA `282d8d4624688aa1a56690394ae2cf5147524b7110e64d199e8e50ddad378fb0`. Python/38 dependencies unchanged. Installed695-case batch is running in O as shell26431. Next: observe its completion, run verified installed-fixture maintenance, then serial native source/installed lifecycle tests and aggregate verification.

Installed batch26431 finished with exit0:695/695 cases, zero failures/errors/skips and every child closed. The source and installed component inventories match. Installed maintenance selected14 attributable passing roots (5472 files,2622 directories,222 links,134021236 logical bytes); archive verification passed and cleanup runs in shell22047. The separate native test remains unexecuted in both lanes. Exact next action: verify cleanup completion, preserve all iteration sources with `preserve-lineage-publication11.py`, run `Run-NativeLineage11.ps1 -Lane source`, preserve that passing full-reserve fixture with its checked identity-preserving rename, then run the installed native test and pin its stationary evidence. Aggregate verifier and final review3/3 follow. A private input-context dependency is now specified in `M5_PAPER_ADMISSION_PLAN.md`; no implementation12 source has changed.

Source native lifecycle passed1/1 in83.577899 seconds, peak381.633MiB; every child closed. Its46 files/16 directories were preserved by checked same-volume rename with every byte/file/directory identity unchanged. Source archive maintenance and installed maintenance are complete; installed archive SHA `82b1cac089a4187b0df810e9f5ea030b2901dc44255dc9ea7ddb0428837d2348`. Source preservation covers95 plans/581 unique blobs, none missing; archive SHA `3a4ecb3f209db70f44ae9ed1f8d386a9a487c3181375fff8f189979445dcf40c`.

Installed native lifecycle is running in `.cache/test-runs/m5-lineage-installed-native-20261014-11` as shell43612. Next: observe its exact closed result, run `snapshot-stationary-native11.py` with preparation label `native-stationary11`; freeze final evidence through `freeze-publication-evidence11.py`; run `verify-lineage-publication-pair11.py` under a fresh bounded preparation label; review the aggregate and completed report independently3/3 before publication. The source reserve preservation leaves backups21109372896 bytes and scratch3774662880 bytes before the installed reserve; these observations do not admit another job in advance. No implementation12 source edits yet.

## Remaining boundaries

No actual provider/account/order request, new permission, spending, automation or Strata startup. Continue serial120-second/4GiB/fourCPU jobs,16GiB admission/12GiB stop, unchanged five-second storage scan and50GiB category budget. Recheck storage before each native1GiB fixture. Backups were19983556808 bytes after increment10 maintenance; at most one more uncompressed1GiB fixture fits that old observation, not an advance admission. Use a fresh checked test namespace if the current namespace cannot fit its reserve.

M3 remains terminally blocked; full M5 and financial qualification remain open; M6 is0/10 actual supervised sessions. Continue authorized local engineering through the publication plan.

## Exact next action

All verification jobs are closed. Both lanes total696 matching passes. Final aggregate command exited0 in8.876529 seconds; aggregate SHA `7a17f4f2b3532bd73670bf6a6d32de9642776c228f4ec8b80a9de7dd1ed48041`. Final independent review3/3 is CLEAR; receipt SHA `45058d860d8a67ec1da584dcf27a610d3955fbe1dfcaed9cbd24b0db32cba917`. Commit/push the explicit verified files to private `BGonnermann/Compertum` and fast-forward the requested clone, then implement the private input context in `M5_PAPER_ADMISSION_PLAN.md`. Existing account and origin were reverified. No implementation12 source has changed yet.
