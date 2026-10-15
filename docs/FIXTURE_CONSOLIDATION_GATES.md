# Test-folder preservation decisions and history

15 October 2026. **The copies are verified, but the first approved removal preflight stopped before deleting anything.** The full inspection took 60.834 seconds and triggered the helper's additional 60-second start requirement. Independent verification proves all four originals, their 1,827 entries and the nine backup files unchanged. See [the refusal report](../reports/FIXTURE_REMOVAL_PREFLIGHT.md).

The owner has accepted the historical-copy limits and master-only incoming-link scope. Fresh checks found all 1,638 retained master links readable, no incoming dependencies inside master and no actual reservation rows. Scratch remains 310,888 bytes over its limit. The existing watchdog stop remains preserved, and the one later production check has not run. Ordinary work and clone updates stay stopped.

A [bounded recovery proposal](FIXTURE_REMOVAL_RECOVERY_PROPOSAL.md) requests one additional attempt and 8 MiB more cumulative execution records while preserving every failed record and all operating limits. It needs a new retry decision under the [existing procedure](FIXTURE_CONSOLIDATION_EXECUTION_PROCEDURE.md). The sections below retain earlier investigation results and failures as history.

## Owner-approved link cleanup, completed

The owner has now authorized removing the 31 old test links if they are no longer needed. That permission covers those exact shortcuts, not their target folders or the separate four-folder consolidation.

The access failure is now explained. Read-only checks failed for all 31 links both inside and outside Codex's restriction. A separate check requested deletion rights without deleting anything; all 31 requests also failed. The process runs as `HOLMES\bgonn` without administrator rights. All eight parent test folders are owned by `Holmes\CodexSandboxOffline` and explicitly give `HOLMES\bgonn` read and execute access only. Broader Codex access does not override those Windows permissions.

A narrow cleanup ran under the owner's explicit administrator approval. The final procedure is `artifacts/m5/OLD_TEST_LINK_CLEANUP_PROCEDURE_V4.md`. Before removing anything, the unchanged removal helper proved that all 31 entries were symbolic links pointing to numbered test folders beside their own shortcuts. It saved their identifiers, exact targets and original Windows link records, then saved each removal intent before removing that link through its checked handle. It used no recursive removal and changed no ownership, file permissions or enabled Windows privileges.

The first Windows approval request was canceled. The second administrator shell exited without a saved preflight exception or child receipt. A read-only check found that its process check rejected an idle web server serving the separate Vesper website folder. Round 3 permitted only that exact process, with fixed identity, command fingerprint, memory and recent CPU limits, but stopped before cleanup because PowerShell converted the saved timestamp into a date value. The owner approved one additional review round. Round 4 corrected that literal comparison, passed independent review and completed. Every earlier launch, review and failed preflight record remains saved. The unrelated server was not stopped or changed.

Exactly 31 links were removed. All 31 target folders existed and remained unchanged. The process exited with code 0 in 0.480002 seconds under its fifteen-second deadline. A separate live check verified every link absent and every target identifier and recorded property unchanged. It also matched 65 original reports, 112 original receipt fingerprints, 43 inspection evidence fingerprints and all 217 source plus 217 installed program files. No product tests ran: zero passed, failed or skipped cases.

The private completion record is `artifacts/m5/old_test_link_cleanup_completed_verified.json`, SHA-256 `a0fd42a3006479fff67accf9202eeb5482e50766bc4ac096c762007801fd8251`. The original link manifest, per-link journal, result and process exit record are retained beside it. Do not rerun the cleanup. It clears those specific denied entries from the earlier inventory; no complete storage scan or scratch write occurred, and current capacity remains unqualified. No backup or four-folder consolidation was performed.

## What the backup can preserve

The four selected folders come from completed, passing test runs. They contain 718 directories, 1,098 files and 11 links. Fresh checks matched all 1,827 entries against the earlier records, including file contents, Windows file identifiers, attributes, creation times and modification times.

The inspection saved the owner, group and discretionary access control list, or DACL, for each entry. The DACL states who may read or change a file. It also checked for additional named data streams, which are extra data attached to a Windows file or directory. None were found on the selected files, directories or links. The 11 link target strings and their stored Windows link data matched the earlier records.

The system access control list, or SACL, records audit rules about file access. It could not be read for any of the 1,827 entries. That does not prove audit rules are absent. Windows requires separate access to read them. [BackupRead also leaves out SACLs without that access](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-backupread). No extra privilege was enabled.

Other Windows properties were not captured. These include additional properties called extended attributes, Windows object-tracking identifiers and short legacy file names. Restoring the original security settings, Windows file identifiers, disk layout or a working program environment has not been proved. File access times may reflect the inspection itself.

The proposed backup contains the earlier measured compressed file contents and a separate compressed file with the readable file properties. These measurements counted compressed bytes in memory. They did not create backup files.

| Selected folder beneath `.cache/test-runs/` | File-content copy | File-properties copy | Combined bytes |
| --- | ---: | ---: | ---: |
| `m3-pair-validation-repair-20261013-01/source_native01-pytest` | 818,049 | 47,916 | 865,965 |
| `m3-review-health-20261013-01/installed_native11_r2-pytest` | 113,230 | 15,853 | 129,083 |
| `m3-review-health-20261013-01/source_native11_r2-pytest` | 112,886 | 15,753 | 128,639 |
| `m3-pair-validation-repair-20261013-01/source_green01-pytest` | 23,812 | 13,682 | 37,494 |
| Total | 1,067,977 | 93,204 | 1,161,181 |

The owner subsequently selected historical evidence copies with the restoration limits explained above. This choice does not authorize running an extracted environment or removing the originals. The current procedure carries that decision forward. Failed, mixed, unmapped and parent test evidence, along with files that reserve disk space, stays protected.

## Which retained links could break, original inspection and later resolution

The inspection counted 1,669 Windows links without reading the contents of their targets. It read the stored targets and link data for 1,638 links. For each readable link, it checked every intermediate target against the four selected folders. No incoming dependency was found among those 1,638 links.

The other 31 are old pytest `current` links. Windows refused access to their stored link data. A final check requested zero access rights, without changing permissions or enabling privileges. All 31 still returned `CreateFileW:5`, meaning access denied. That check exited normally in 0.4196186 seconds under a ten-second deadline, but all 31 metadata reads failed. Exact paths are retained in `artifacts/m5/fixture_gate_link_followup.json`.

At inspection time, those unknown targets left the dependency check incomplete. The later approved cleanup read and preserved all 31 original link records, confirmed their numbered sibling targets and removed only the shortcuts. Their target folders remain intact. This resolves those 31 denied entries. Links outside the master folder were not inspected, and no later complete inventory was taken. The original zero count among readable links remains a historical observation, not authority to remove the four selected folders. File permissions on failed test evidence remain unchanged.

All 320 links inside `backups/` were readable. Windows reported zero primary data length and allocation, with no additional named streams. Their targets were not counted again. This resolves the backup-link error that stopped the earlier preparation, while preserving its failed receipt.

## Disk use and promised space

The inspection counted disk allocation, additional named streams, links and directories. A small comparison showed why directory allocation needs care: directory enumeration reported zero bytes for `.cache`, while a direct `FILE_STANDARD_INFO` query reported 4,096 bytes. Both methods agreed for `README.md`. The inspection therefore used [direct Windows allocation information](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info) for directories. The product scanner was not changed.

These measurements came before the inspection's final reports were written. The 31 unreadable links mean total use could be higher. The final column is a calculation, not permission to write.

| Storage group | Limit in bytes | Observed use | Space held for later inspection output | Calculated space left |
| --- | ---: | ---: | ---: | ---: |
| Backups | 21,474,836,480 | 21,473,134,560 | 0 | 1,701,920 |
| Temporary test files, called scratch | 5,368,709,120 | 5,366,131,928 | 33,554,432 | -30,977,240 |
| Code, reports and other records | 5,368,709,120 | 1,117,115,696 | 0 | 4,251,593,424 |
| Data | 16,106,127,360 | 0 | 0 | 16,106,127,360 |
| Models | 5,368,709,120 | 0 | 0 | 5,368,709,120 |

Observed use totaled 27,956,382,184 bytes. Free disk space was 206,943,932,416 bytes, above the required 50 GiB floor. The actual coordinator database, `state/research.sqlite`, contained zero space-reservation rows. Reservations are space promised to unfinished work. The database contents stayed unchanged, and no database journal files were created. No other actual coordinator database or unreadable link was found under `state/`. Old test databases count as stored files, not additional active reservations. The 1 GiB emergency execution reserve remains charged and protected.

The 32 MiB inspection allowance in the table was held conservatively because reports follow the main count. It was not a production reservation. The count could not support that allowance.

The four later reports added 2,888,080 charged bytes. Direct checks of those four files establish **at least 5,369,020,008 bytes of scratch use, 310,888 bytes over its 5 GiB limit**. The inspection's retained reports caused this measured overage. Further scratch writes and synchronization of the requested clone have stopped. Remaining documents and receipts use the records group. No evidence was deleted to hide or repair the overage.

## A smaller proposed backup allowance

The earlier 1,835,008-byte proposal exceeds observed backup room by 133,088 bytes, before new folder overhead. It cannot be used.

A smaller maximum of **1,572,864 bytes, or 1.5 MiB**, fits the measured copies with margin. It assigns 917,504 bytes to the first folder, 163,840 to each of the next two, and 65,536 to the fourth. Each amount covers both compressed files and their allocation. It adds 131,072 bytes for the index and receipts, and 131,072 for folder allocation, unfinished files and staging. This leaves 129,056 bytes against the observed backup room before any later change.

This is a proposed size limit, not reserved space or proof of restoration. A later procedure must account for every simultaneous copy and refuse before writing if the complete amount does not fit. Future deletion cannot provide space needed before that deletion. Existing backups cannot be removed to make room under this proposal.

## Why maintenance remains blocked

The current decision is **do not execute broader maintenance before review and approval**. The separate 31-link cleanup and fresh procedure preparation are complete. The preservation choice and measurement barriers are resolved within master. Scratch still exceeds its limit, so the procedure proposes a one-time exception allowing no scratch growth. That exception and archive-only Stage A require approval; removal remains a later separate decision.

The proposed one-time maintenance exception would keep research and broker work stopped. It would add no scratch files, write bounded receipts under records, keep backup growth within the proposed 1.5 MiB allowance, and record the starting scratch overage honestly. Scratch use would fall only after separately approved removal. Ordinary work would remain blocked while any storage group exceeds its limit.

That exception is neither approved nor implemented. It must retain the existing CPU, memory, deadline, total-storage and free-space limits. It cannot ignore unknown link charges, use the emergency execution reserve, raise a storage limit, restart old work or replace the production scanner's five-second check.

## Retained results and next decisions

Private evidence remains in the three `.cache/test-runs/m5-fixture-consolidation-gates-20261015-01` through `-03` folders and `artifacts/m5/fixture_gate_*` files.

- The first inspection exited with code 1 after 1.2298111 seconds. Peak memory was 30,240,768 bytes. It captured the selected file properties, then stopped on the directory-allocation mismatch.
- The continuation exited with code 1 after 7.0084075 seconds. Peak memory was 28,667,904 bytes. It stopped on access denied.
- The final diagnostic exited with code 0 after 28.8998087 seconds. Peak memory was 36,446,208 bytes. Its result explicitly says capacity is unverified.

Each bounded inspection used one CPU and a 128 MiB memory limit enforced by Windows. All exits were observed and no child processes remained. The final deadline was reduced to 75 seconds. The separate 31-link check also exited normally but retained all 31 access failures. No product tests ran: zero passed, failed or skipped test cases. These are inspection results, not milestone acceptance. The 34 reader19 test drafts remain unexecuted; the remaining M5 requirements and all ten actual M6 sessions remain open.

The new owner request authorized a fresh bounded preparation after this closeout. Its [execution procedure](FIXTURE_CONSOLIDATION_EXECUTION_PROCEDURE.md) now supplies complete measurements and the accepted preservation policy. Review and approve or reject its one-time maintenance exception and archive-only Stage A. The archive helper needs independent review before writes, and the actual verified copies must be presented before separate removal approval. Outside-master link coverage remains a stated limit at that later approval. Documentation publication remains authorized; ordinary work and the requested clone wait for actual storage admission.
