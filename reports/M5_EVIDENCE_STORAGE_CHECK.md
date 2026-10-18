# One bounded full storage check

The authorized full storage check passed. No retry ran.
The scan took 71.160717 seconds. Its parent job passed in 104.068814 seconds.
The parent observed exit code 0 and zero remaining child processes.
The complete measurement contains 59,287 directories, 220,813 files, and 4,480 links.
It reports zero unknown entries, access barriers, and ledger failures.
No post-result failure exists. The result matches the measurement hash.
Execution copies, the plan, the evidence helper, and the proposal retained their recorded hashes.

## Limits and evidence

The check retained 1 CPU, 128 MiB, 16 processes, and the 120-second parent deadline.
The scan retained its 110-second deadline.
Host memory checks retained the 16 GiB start floor and 12 GiB stop floor.
The parent recorded 56,193,024 bytes of peak job memory.
All original 28 folder checks remained. The new 8 MiB folder added the 29th check.
The new folder contained 16,384 charged bytes during measurement.
The scan reserved its unused allowance, so actual use and the remaining allowance totaled exactly 8 MiB.
The folder served this storage check only. Broker adapters remain disabled.

| Category | Charged bytes, including holds | Remaining bytes |
| --- | ---: | ---: |
| Scratch | 16,020,702,728 | 85,424,632 |
| Records | 1,418,477,432 | 3,950,231,688 |
| Backups | 22,060,320,736 | 488,257,568 |
| Total | 39,499,500,896 | 14,187,590,304 |

C: remains limited to 50 GiB. Scratch remains 15 GiB, records 5 GiB, and backups 21 GiB.
The separate D: archive allowance remains 200 GiB. This check did not scan or change that archive.
The total includes reservations. It does not represent only files already stored.
Scratch remains the tightest category. Total free allowance cannot replace a category allowance.

Private evidence uses `storage-evidence-admission01` under `artifacts/m5/simulated-evidence-next-01`.
The measurement, result, parent closure, and both progress journals remain preserved.
Preparation hashes remain under `artifacts/m5/local-economics-20261017-01/storage-evidence-admission01-pins.json`.
Only two exclusive execution copies removed the preparation stop. Original prepared files remain unchanged.

## Review and scope

Independent result review found no blocking issue.
The reviewer verified hashes, complete measurement, unchanged limits, the passing parent closure, and the absence of post-result failure.
The reviewer performed read-only inspection and ran no scan or test.
This run performed one storage check: 1 passed, 0 failed. It did not run a source or installed-package test suite.
The earlier 31 source checks remain historical results.
This measurement proves capacity at the check time. It is not permanent storage admission.
The Windows pipe access restriction remains unresolved. This check does not establish successful simulated broker operation.
Only M0 remains fully accepted.
No permission change, saved-stop change, or broker action ran. Strata remained off.
