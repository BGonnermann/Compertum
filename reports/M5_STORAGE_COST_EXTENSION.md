# Storage cost investigation, rounds 7 through 9

15 October 2026. The approved extension is exhausted and storage admission remains blocked. All three private candidates timed out under the unchanged five-second deadline. No candidate was promoted or installed. This is a failed timing investigation with verified closure, not a qualified scanner release.

## Measured results

All profiles ran read-only in actual one-CPU, 128MiB Windows Jobs. The scan clock includes cold loading, instrumentation and cleanup. Values below are partial observations at refusal, not complete inventories or fresh capacity estimates.

| Run | Change or observation | Wall seconds | CPU seconds | Files visited | Outcome |
| --- | --- | ---: | ---: | ---: | --- |
| Original scanner profile | Open plus first-query work took 2.478 seconds across 17,502 directory opens | 5.000524 | 4.312500 | 68,682 | Deadline |
| Round 7 private candidate | Held-parent relative opens, explicit depth-first traversal | 5.000116 | 4.531250 | Not instrumented | Deadline |
| Round 8 private candidate | Original probe cadence, per-call timings | 5.000207 | 4.515625 | 99,538 | Deadline |
| Round 9 private candidate | Checked thread-safe native function-pointer cache | 5.000133 | 4.421875 | 102,561 | Deadline |

Round 8 measured 78,732 module lookups and 78,732 procedure lookups, together 0.245 seconds. Round 9 reduced each to two, including cold initialization. That mechanism worked, but the scan still did not finish. Round 9 measured 2.543 seconds in 26,494 relative directory opens, 0.680 seconds in directory queries, 0.267 seconds in closes, 0.351 seconds in row parsing and 0.302 seconds in link resolution. These components do not include every wrapper cost and should not be summed into a complete performance model. Six ancestor frames remained at refusal and zero remained after checked cleanup.

Directory acquisition is the largest observed current cost. The experiment does not establish why earlier production scans passed or identify antivirus, power policy or disk behavior as the cause. Instrumentation and traversal changed between variants, so file counts are not controlled throughput comparisons. No production scan was repeated after these incomplete profiles.

The private relative-open contract preserves counted single-component names, held parent handles, ordinary-directory/reparse validation, noninheritance, synchronous access requirements and checked closure. Windows documents relative root handles and synchronous access in [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes) and [ZwOpenFile](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-zwopenfile). These references support API semantics only; they do not qualify the prototype.

## Verification and preserved history

- The original 106 pending installed cases are complete. Original release18 has 393 matching cases per source/installed lane, zero failures/errors/skips, 78 closed Jobs and independent final review3 CLEAR. This extension did not rerun or change that release.
- The historical native06 release has 43 matching cases per lane, zero failures/errors/skips, 18 C boundary checks, both complete environments and three full-master scans at 4.566, 4.948 and 4.930 seconds. A later post-maintenance07 scan passed in 4.586 seconds. Those receipts remain valid historical observations; current admission is blocked.
- The extension ran zero source product cases, zero installed product cases and zero reader19 cases. One private missing-interface probe failed as expected against the unchanged original API before the candidate scan. It is not product acceptance coverage.
- All eight native investigation Jobs closed with exit zero and no active children. Candidate wrappers returned zero after recording refusal and closing resources; wrapper exit zero does not mean scan success. One preliminary outer preparation wrapper failed a placeholder hash assertion before it could create a native Job; both the failed wrapper receipt and corrected bound-input launch are preserved.
- The final read-only audit verified 217 unchanged source/installed payload files, 326 unchanged historical native evidence pins, 34 unchanged syntax-valid reader drafts, three exact input archives and 66 investigation evidence pins. No private C/DLL/loader candidate entered the product package.
- Maintenance08 remains unexecuted after its initial admission refusal. No archive08 or cleanup08 occurred. All failed fixtures and frozen reserve identities remain preserved. The large source_components01 fixture is from a failed run and cannot be removed under passed-only cleanup authority.

The final audit is `.cache/test-runs/m5-native-portfolio-20261014-19/extension09-blocked-audit.json`, SHA `b3fc6ed61b6025043f5d248ece7c758c47463959c6291d9812ffdb857f5145ea`. It binds candidate receipts, source inputs, binaries and exact investigation archives. Approval provenance is `scanner-extension-approval07.json`, SHA `dfeceb3716c3416d60bd8485afd7f3e3e971c28215fb0119a5c148741d521b8c`. These private artifacts remain ignored by Git; this report publishes no credentials, runtime databases or local evidence payloads.

## Limits and next decision

Every limit stayed fixed. Storage scanning remains five seconds, one CPU and 128MiB. Private builds used one CPU and 4GiB with a 15-second Job deadline, within the existing worker limits. Namespace and growth bounds, host-memory guards, single-heavy-job exclusion, category budgets and the 50GiB total were retained. No installation, spending, service, priority/power/security change, Strata startup or broker action occurred. Partial scans do not prove current category headroom.

Rounds 1 through 9 are used. No further repair, compiler, test or equivalent scan launch is authorized by this extension. The concrete next choice is a separately bounded broader native batch-walker experiment, or leave storage admission blocked. Its proposed scope is to reduce per-directory Python/C traversal work with existing GCC while preserving every entry, allocation charge, parent lock, link check, strict row check, original caller-thread callback and checked close. Its performance benefit is unproven. A new experiment must freeze its case inventory and inputs, carry the nine used rounds, and specify its additional bound before launch.

Acceptance would require complete exact small-fixture inventory equivalence, boundary/fault/cleanup tests, matching source/installed checks, both complete environment qualifications and repeated complete full-master scans under the original watchdog. No cached inventory, skipped subtree or relaxed resource limit qualifies. Only then can the frozen 34 reader19 cases and M5 local gates 2 through 5 continue. Reader19 alone does not complete ownership/accounting. Actual paper actions remain separately gated; M6 is still 0/10 supervised sessions.

The documentation closeout is prepared for independent review and normal publication to the primary private repository. The ignored `artifacts/m5/native_storage_extension09_published.json` receipt records the final master/GitHub/clone commit and review hash after successful synchronization.
