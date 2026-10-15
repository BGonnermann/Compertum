# Test fixture consolidation plan

15 October 2026. **This initial plan is history. Copies are verified; the subsequent approved removal preflight refused before deletion.** Four wholly passing test roots contain 718 directories, 1,098 files and 11 links. Their eight backup files and index charge 1,179,648 bytes. All 1,827 originals and all copies remain unchanged. See [the archive report](../reports/FIXTURE_ARCHIVE_STAGE_A.md) and [the later preflight refusal](../reports/FIXTURE_REMOVAL_PREFLIGHT.md).

The owner accepted the historical-copy limits and master-only link scope and approved removal. The complete inspection passed, but the helper's extra time-margin condition stopped the attempt. No automatic retry or production admission check occurred. Scratch remains 310,888 bytes over its limit, and the existing watchdog stop remains preserved. Ordinary work and clone updates stay stopped.

The [execution procedure](FIXTURE_CONSOLIDATION_EXECUTION_PROCEDURE.md) supersedes this initial plan's older capacity proposals. The [recovery proposal](FIXTURE_REMOVAL_RECOVERY_PROPOSAL.md) asks only for one additional bounded attempt and its records/review allowance. It does not re-open the accepted four-folder choice or authorize execution. Scanner rounds 1 through 12 remain used; resource limits and the Strata prohibition are unchanged.

## Preparation and verification

- [x] Verify wholly passing job receipts and distinguish them from individual passes inside a failed job.
- [x] Record exact selected paths, file hashes, directory/link counts, identities and relevant metadata.
- [x] Measure compressed sizes into a counting sink, without writing archives or following link targets.
- [x] Reconcile all 65 group reports, all 234 frozen inputs and 217 unchanged source/installed product payload files.
- [x] Record the failed backup-capacity check and the remaining preservation/operating gates.
- [x] Complete final independent plan review3/3: CLEAR_FOR_PLAN_DOCUMENTATION_PUBLICATION. Synchronization is recorded separately in the ignored publication receipt.

Private evidence is retained under `C:\Users\bgonn\Desktop\Compertum\.cache\test-runs\m5-fixture-consolidation-plan-20261015-01` (P below). `plan-evidence.json` has SHA-256 `76012ef210139e1b37c4f182b49ccded8d2aa38eaad1810c9a8b91e33f67a3a7`. It indexes every exact root, per-file hash, measured size and report hash. Those private manifests stay out of GitHub.

The selected-tree worker used one CPU, a 128 MiB native Job memory cap and a 90-second deadline, within the general 120-second worker bound. It finished with exit 1 after 17.400211 seconds because the final backup-category walk encountered a reparse point and conservatively refused. Peak Job memory was 41,570,304 bytes; process exit was observed and zero children remained. All 65 selected-tree reports had already been written. There is no successful overall inspection receipt or current backup-capacity result. The later report-only reconciliation passed and rechecked all input/evidence pins. No product tests ran in this planning task.

This worker is a read-only preservation inspection, not the production scanner. The production five-second/one-CPU/128 MiB limit is unchanged, no storage grant was issued and admission remains blocked. Group reports total 9,562,865 bytes; the worker's final namespace observation was 10,291,158 charged conservatively by the parent. Neither observation is a current whole-category scratch allowance.

## Recommended first batch

All paths below are beneath `C:\Users\bgonn\Desktop\Compertum\.cache\test-runs\`. Each corresponding command receipt is VERIFIED, exit 0, with observed process exit and zero remaining children; each XML matches its retained hash and contains no failures, errors or skips. The 26 cases listed here are historical receipt counts, not newly executed tests.

| Exact root relative to that prefix | Historical passes | Directories / files / links | Measured compressed bytes | Proposed archive cap |
| --- | ---: | ---: | ---: | ---: |
| `m3-pair-validation-repair-20261013-01/source_native01-pytest` | 14 | 359 / 538 / 6 | 818,049 | 1,048,576 |
| `m3-review-health-20261013-01/installed_native11_r2-pytest` | 4 | 129 / 196 / 1 | 113,230 | 262,144 |
| `m3-review-health-20261013-01/source_native11_r2-pytest` | 4 | 129 / 196 / 1 | 112,886 | 262,144 |
| `m3-pair-validation-repair-20261013-01/source_green01-pytest` | 4 | 101 / 168 / 3 | 23,812 | 131,072 |

Exact inventories are P/`group-00.json`, `group-01.json`, `group-02.json` and `group-05.json`. Their SHA-256 values are in `plan-evidence.json`. These four roots contain 9,107,305 logical bytes and 9,612,976 charged file bytes. Directory/link metadata is additional and no net storage benefit has been measured. The proposed four archive caps total 1,703,936 bytes; add a 131,072-byte cap for the backup index/receipts, giving a **1,835,008-byte (1.75 MiB) batch ceiling**. This is a proposed write ceiling, not available capacity or a promise that a richer preservation format fits it. Stop before writing if full preservation exceeds any cap.

For a later separately reviewed execution plan, use a fresh exact destination such as `backups/fixture-consolidation-20261015-01`, only if absent. Bind each archive to its root and manifest; retain all parent command/XML/source/release evidence in place. Do not call the old maintenance08 helper or repurpose its evidence label.

## Other measured roots and protected evidence

| Classification | Roots | Directories / files / links | Logical bytes | Sum of separately measured streams |
| --- | ---: | ---: | ---: | ---: |
| Wholly passing jobs, including the first batch | 54 | 3,592 / 5,878 / 180 | 156,255,325 | 15,828,588 |
| Proposed individual passed-case roots inside the failed run | 10 | 370 / 675 / 0 | 3,751,590 | 568,869 |
| Entire failed mixed run, measurement only | 1 | 2,195 / 3,299 / 43 | 10,574,681 | 1,805,132 |

The last two rows overlap: the ten case roots are inside the whole failed tree. Never add their reductions or preservation sizes together. Whole passed roots are disjoint from that tree. No measured group had a named stream on an ordinary file/directory, multiple hard links, excess preallocation, sparse/compressed attributes, encrypted attributes or a full-reserve file. Reparse streams and ACL/SACL remain unqualified. The catalog's at-least-256 MiB group, including its real 1 GiB reserve, was excluded before inspection; this is not an inventory of all historical fixtures.

The mixed root is `m3-review-health-20261013-01/source_components01-pytest`. Its enclosing job is still **FAILED: 261 passed, one failed, zero errors/skips, exit 1**. All 262 unique XML IDs match the frozen `components01-plan.json` selections. The failed case is `tests.test_final_controller::test_supervisor_routes_final_and_halts_it_with_other_research`. Its diagnostic remains protected regardless of whether it created its own temporary directory.

Reconstructing pytest 9.1.1's sanitized 30-character names found 28 unambiguous candidate roots across all modules. Only ten exact `tests.test_final_controller` roots with the reviewed function-scoped dispatch fixture chain were measured separately. All are **proposals**, not historical per-case cleanup attestations or removal authority. Eighty-six other ordinary mixed-run case directories and all 43 top-level files/links stay protected. The seed's preliminary `entries` labels precede its multiple-directory collision filter; use its final `proposed_case_roots`/`protected_case_roots` lists, never the preliminary labels, for classification.

The hotspot `test_terminal_close_replay_doe0/source/venv` came from a passed case using a stub interpreter and invented wheel records. It is a test environment rather than the installed project environment. Its surrounding fixture still contains real path/lease/seal/SQLite identities. Moving or extracting it cannot restore an operational runtime. Neither the whole failed tree nor even its uniquely mapped passed cases is selected for the first batch.

Maintenance08's four passed intent roots were also rechecked: 72 historical passes, 507 directories, 1,004 files and 35 links. Its old JSON says 4 MiB, but the reviewed executable actually caps/preallocates **3 MiB**. Preserve that discrepancy. Its older combined-format estimate was 2,691,734 bytes; the current separately measured, metadata-enriched streams sum to 2,771,593 bytes. Different layouts are not interchangeable size proofs. Maintenance08 remains unexecuted after its production admission refusal, with no archive08 or cleanup08.

## Preservation requirements before any removal

The measured format is deterministic PAX tar plus gzip9. Ordinary file contents and empty directory members are included; links are recorded as target strings and raw reparse descriptors in a metadata member, not followed or recreated. File hashes and native IDs were checked during two reads. Timestamp/identity observations were recorded; access times may reflect inspection.

This format does **not** qualify ACL/SACL, reparse alternate streams, restored hard-link relationships, sparse/allocation semantics or recreation of original NTFS file/directory IDs. Windows exposes stream names and sizes through [FILE_STREAM_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_stream_info); recording those observations does not establish a complete restorable Windows backup. Do not promote a byte-verified tar into an identity-preserving backup claim.

Before removal, qualify a preservation format for all required metadata without new privileges, or obtain an explicit, concrete owner decision accepting the specified losses for these disposable passed copies. Stop on unqualified metadata. Archives would be historical evidence only: never resume a path-bound runtime from an extracted copy, reset attempts or rebind old identities. Preserve every failed receipt, original source archive, release, command/XML, lease/seal/journal and real reserve outside the selected roots.

Retained incoming links also need review. Preserve their exact target strings and descriptors, identify any target that would disappear, and record the consequence. Do not retarget a `current` link or erase a failed fixture to make a later scan pass. Do not extract a verification copy under master: that would add directories and identities rather than reduce traversal.

## Original capacity and operating gates, superseded by the procedure

Current backup headroom is **unknown**: the selected inspection refused `BACKUP_REPARSE_NEEDS_SEPARATE_REVIEW` before producing a capacity summary. Earlier roughly 5 MiB observations are historical, not current capacity. Qualify backup link charges without following targets, all category charges, outstanding reservations, the total 50 GiB budget and the 50 GiB free-space floor before any write. Keep category ceilings: backups 20 GiB, scratch 5 GiB, records 5 GiB, data 15 GiB and models 5 GiB. Retain 16/12 GiB host admission/stop, one heavy job, per-job limits and fresh checked namespaces.

The existing archive helper requires production admission first; that scan is currently blocked. Physical room alone does not authorize bypassing its check. A distinct, bounded offline preservation procedure would require an explicit operating decision and independent review of complete capacity/reservation accounting before it can run. This plan supplies neither that procedure nor a runtime/storage grant. It does not reset the exhausted scanner experiment or authorize another full-master timing scan.

## Proposed execution order, outside this preparation scope

1. Resolve the metadata preservation choice and the bounded offline-maintenance admission decision. Qualify backup links, complete capacity and reservations. Freeze the four-root allowlist, exact manifests, source inputs, archive caps and stop conditions in a new execution plan.
2. Independently review that concrete procedure before writes. Recheck original root identities, closed whole-job receipts, hashes and link dependencies; refuse any drift. Write only fresh bounded archives/index, never replace existing evidence.
3. Stream-verify every archived file's name, size and SHA-256, every empty directory, exact metadata/link records, cap/allocation and archive hash against a fresh locked inventory. Qualify restoration of the metadata promised by the chosen format. No extraction may confer old runtime authority.
4. Present the exact verified preservation receipt for any still-missing removal/metadata-loss authority. Only then remove the four checked disposable roots using a reviewed path-safe procedure. Do not touch mixed/failed/unmapped roots, parent evidence, environments or reserves. Stop on any mismatch and retain all partial/failure evidence.
5. Under separately scoped verification authority, measure unchanged actual production admission after preservation. A passing result must meet the original complete-inventory/watchdog limits; no subtree exclusions or cached replacement. Consolidation's performance benefit is unproven. Continue reader19 and M5 gates 2 through 5 only after admission qualifies.

## Exact checkpoint and next action

Plan preparation and independent review3/3 are complete. Review reconciled65 report hashes,112 receipt pins,234 frozen inputs and217 source/installed payload files. The ignored `artifacts/m5/fixture_consolidation_plan_published.json` receipt records the publication outcome and master/GitHub/clone equality. Exact next action: resolve the specific metadata, capacity and bounded maintenance-admission decisions above before preparing a separately reviewed execution procedure. Execution remains blocked on those gates. No scanner round13, archive or removal is authorized by preparing this plan. Original release18's 393 matching cases per lane and all106 formerly pending installed cases remain historical verified results; reader19 is still 34 private drafts, zero executed, and M6 remains 0/10 actual supervised sessions.

Closure receipt SHA-256: `c91584aa2073eb332dd4c139f1c9e2d2c90e1f19e17c3139b45cb472cf3bd4bc`. Exception receipt SHA-256: `f2d84e14bf91d999e99fdf127354e1e0d93d53b80907192ce7312f68f33791bc`. Frozen input manifest SHA-256: `1710f5da0b3f9612527573b101a5351ae5d9d15cc54e317fc6282ff11cdb0568`. Prelaunch review1 found two helper defects; both were corrected before execution and review2 cleared the read-only launch. The capacity refusal is preserved, not relabeled as a pass.
