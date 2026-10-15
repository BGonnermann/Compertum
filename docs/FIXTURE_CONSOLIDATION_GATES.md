# Decisions needed before combining old test folders

15 October 2026. **The maintenance work cannot start. No execution procedure is ready.** This report explains what was checked, what remains unknown, and which owner decisions are needed before the four-folder [consolidation plan](FIXTURE_CONSOLIDATION_PLAN.md) can proceed.

No compressed backup was created. No folder was moved, extracted or removed. File permissions and program code were not changed. Strata remains off. The twelve scanner experiment attempts remain used.

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

The owner must choose whether to keep the originals until complete restoration is proved, or accept these copies as historical evidence with the missing properties listed above. Accepting historical copies would not authorize running an extracted environment or removing the originals. Removal still needs a separately reviewed procedure and approval. Failed, mixed, unmapped and parent test evidence, along with files that reserve disk space, stays protected.

## Which retained links could break

The inspection counted 1,669 Windows links without reading the contents of their targets. It read the stored targets and link data for 1,638 links. For each readable link, it checked every intermediate target against the four selected folders. No incoming dependency was found among those 1,638 links.

The other 31 are old pytest `current` links. Windows refused access to their stored link data. A final check requested zero access rights, without changing permissions or enabling privileges. All 31 still returned `CreateFileW:5`, meaning access denied. That check exited normally in 0.4196186 seconds under a ten-second deadline, but all 31 metadata reads failed. Exact paths are retained in `artifacts/m5/fixture_gate_link_followup.json`.

Their unknown targets could still depend on the selected folders. Links outside the master folder were not inspected either. The zero count from readable links therefore does not justify removing anything. No `current` link was changed. Changing permissions on failed test evidence is not an accepted remedy. Further inspection needs an owner-approved way to read those link records without changing them, or verified observations supplied by the owner.

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

The current decision is **do not start maintenance**. The preservation choice, unknown link targets and insufficient scratch capacity must be resolved before an execution procedure is prepared. A diagnostic program exiting with code zero does not resolve those problems.

The proposed one-time maintenance exception would keep research and broker work stopped. It would add no scratch files, write bounded receipts under records, keep backup growth within the proposed 1.5 MiB allowance, and record the starting scratch overage honestly. Scratch use would fall only after separately approved removal. Ordinary work would remain blocked while any storage group exceeds its limit.

That exception is neither approved nor implemented. It must retain the existing CPU, memory, deadline, total-storage and free-space limits. It cannot ignore unknown link charges, use the emergency execution reserve, raise a storage limit, restart old work or replace the production scanner's five-second check.

## Retained results and next decisions

Private evidence remains in the three `.cache/test-runs/m5-fixture-consolidation-gates-20261015-01` through `-03` folders and `artifacts/m5/fixture_gate_*` files.

- The first inspection exited with code 1 after 1.2298111 seconds. Peak memory was 30,240,768 bytes. It captured the selected file properties, then stopped on the directory-allocation mismatch.
- The continuation exited with code 1 after 7.0084075 seconds. Peak memory was 28,667,904 bytes. It stopped on access denied.
- The final diagnostic exited with code 0 after 28.8998087 seconds. Peak memory was 36,446,208 bytes. Its result explicitly says capacity is unverified.

Each bounded inspection used one CPU and a 128 MiB memory limit enforced by Windows. All exits were observed and no child processes remained. The final deadline was reduced to 75 seconds. The separate 31-link check also exited normally but retained all 31 access failures. No product tests ran: zero passed, failed or skipped test cases. These are inspection results, not milestone acceptance. The 34 reader19 test drafts remain unexecuted; the remaining M5 requirements and all ten actual M6 sessions remain open.

The next required decisions are the owner's preservation choice, a way to read the 31 denied link records without changing them, and approval or rejection of the proposed one-time maintenance exception. No further complete inspection, backup or removal is covered by this closeout. The execution procedure waits for those decisions and verified capacity. Documentation publication remains authorized; the requested clone waits for sufficient scratch capacity.
