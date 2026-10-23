# Test retention and first cleanup

## Result

The owner approved routine cleanup of verified disposable test files on 19 October 2026.
`docs/TEST_RETENTION.md` now replaces blanket retention for those files.
`AGENTS.md` requires this rule during future work.
No storage allowance increased. Scratch remains 15 GiB, backups 21 GiB, and total storage 50 GiB.

The first cleanup removed two completed jobs' temporary `pytest` trees.
Both parent folders remain, preventing reuse of their attempt names.
All 114 external evidence files retained their exact SHA-256 hashes.
Failed registration runs, preparation files, real runtime data, and the real emergency reserve remain untouched.

| Temporary tree | Historical passes | Failures | Errors | Skips | Removed entries | Removed storage charge |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ai-history-tests03/pytest` | 121 | 0 | 0 | 0 | 1,882 | 28,971,008 bytes |
| `ai-review-tests03/pytest` | 58 | 0 | 0 | 0 | 483 | 4,956,160 bytes |

These are historical source-test results. Cleanup ran zero new product tests: zero passed, failed, errors, or skipped.
Both historical jobs recorded successful exit and zero remaining children.
Their passing tests include expected failure-handling scenarios. Those scenarios are not unresolved failed jobs.

## Fresh verification

The dry run passed. Independent review found no blocking issue in eligibility, policy, or the exact cleanup script.
The cleanup completed in 39.6957291 seconds and removed all 2,365 selected entries.
It removed 55 symbolic links without following them, 1,280 files, and 1,030 directories.
It checked every ancestor and removed directories only when empty.
No Python or pytest process was present before removal. Neither historical process ID was active.
The script enforced one CPU, a 120-second deadline, and 16/12 GiB available-memory floors.
It also checked its own working memory against a 512 MiB ceiling.
No child process was started by the cleanup script.

Two preparation issues were corrected before removal.
PowerShell ancestor objects needed their directory attribute checked instead of an unavailable provider property.
A separate CIM process query was denied. The script used the available process-list API without changing permissions.
The first dry run stopped before creating cleanup records or removing files.

The local folder measurement uses the existing `tools/fresh_namespace_usage.py` accounting method.
It charges directories and links at 4 KiB and rounds file lengths to 4 KiB.
These are project storage charges, not measured physical free-disk changes.

| Measurement | Bytes |
| --- | ---: |
| Folder before cleanup | 448,077,824 |
| Removed temporary storage charge | 33,927,168 |
| New cleanup records, including their directory | 618,496 |
| Folder after cleanup | 414,769,152 |
| Net reduction | 33,308,672 |
| Existing folder limit | 469,762,048 |
| Available folder allowance | 54,992,896 |

The saved per-path inventory preserves historical fixture sizes used by the earlier registration verification estimate.
The external job templates remain available to preparation tools.
No complete category census ran. Local cleanup does not establish fresh product-test admission or clear operating stops.

## Records and next action

Private records are beneath `.cache/test-runs/m5-local-economics-20261017-01/test-retention01`.
`plan.json` records exact paths, types, sizes, link targets, timestamps, and external evidence hashes.
`result.json` records verified removal and elapsed time. Do not reuse this cleanup attempt.
`tools/Remove-CompletedTestFiles.ps1` is the exact two-tree cleanup script, not a general deletion command.

Routine cleanup now follows the retention rule without another owner storage approval.
Future jobs must remove eligible temporary files during completion or before the next admitted batch.
No scheduler or unattended service was added.
The next product task is fresh storage admission followed by the pending registration repair tests.
The local folder now has more than the earlier 32 MiB forecast available. Full admission still needs verification.
Registration remains unverified. No milestone or financial qualification changed.
The project map refresh records this distinction separately in its external output folder.
