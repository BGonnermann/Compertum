# M3 interruption recovery

13 October 2026. Status: **recovery verified; serial campaign continuing**. Strata and its model server must stay off under the owner's explicit instruction after a reported out-of-memory crash.

## Preserved evidence

- The source campaign has 63 completed outcomes. The installed-package campaign has 48 completed outcomes and one interrupted in-flight attempt for unit 48. No completion receipt exists for that attempt.
- Copied SQLite/WAL evidence and both saved outcome prefixes were checked against the last verified exports. Windows boot time is later than the recorded worker creation time; the old worker cannot still exist. This does not establish a successful exit or prove the crash cause.
- The frozen 483-file release and matching 545 historical test cases per environment were rechecked. No product source, runtime identity, numerical threshold or interpreter was changed.

## Recovery and resource checks

New helpers live only in master. Normal owner restart/resume will retain unit 48 attempt 1 as `INTERRUPTED/OWNER_RESTART` and use attempt 2 with a new native process and output reservation. The interruption-aware comparison retains all ordinary output and process checks.

Holder/driver review cleared 1/3; comparison-helper review cleared 2/3. Six memory-boundary assertions passed. Launch requires 16 GiB free physical memory and commit headroom; running work requests pause below 12 GiB. The original 4 GiB worker cap, 4 CPU threads and 120-second worker deadline remain. Before the attempted launch, available RAM exceeded 49 GiB and no Python/Strata/model process was present.

Recovery command `campaign-wheel50` failed the existing five-second disk inventory **before creating a Supervisor or numerical worker**. Two read-only inventory diagnostics also failed that unchanged limit. No numerical attempt was consumed. The failed command and diagnostics are retained; there will be no identical retry until a material correction is verified.

## Verified correction and recovery

Eight passing test basetemps were archived and verified before their working copies were removed: 728 regular files, 602 directories and 85 link entries, with no link targets followed. Failed evidence, environments and the active runtime were excluded. The 2,076,053-byte archive is in master at `backups/m3-interruption-recovery-20261013-01/passing-fixtures01.zip`, SHA-256 `2d4948ef0e12a8a77078642d71d2aad35e0357cc22d15fb7d612ee730aee84ee`. Independent cleanup review cleared 1/3.

The unchanged native inventory then passed in **3.925125 seconds**, including all category and free-disk checks. Recovery command `campaign-wheel51` completed unit 48 as attempt 2; the output verifier confirmed all 49 common source/package results matched exactly, retaining attempt 1 as interrupted without a successful exit receipt. Minimum observed physical headroom was **48.62 GiB**, commit headroom **78.5 GiB**. A shell pin-check typo before that launch emitted errors; the immediately corrected read-only check confirmed both reviewed helper hashes. The typo is retained and is not counted as a passing preflight.

The reviewed serial continuation now verifies every saved output after each chunk and stops on any failure. Its pin inventory and fresh-label guards cleared repair review 2/3. As of 2026-10-13T13:22:30.5642019Z, source has 63 and package has 52 verified outcomes (`campaign-wheel54`). Detailed current progress is in master recovery evidence `live-progress.json`. No product source changed.

Ten checks of the additional audit memory guard passed, including the native query, both threshold boundaries, pause on low headroom and refusal when the query fails. These are guard checks, not evidence that the later audit jobs ran.

## Next action

Let the current serial campaign runner finish, inspect its receipts, then execute the independently reviewed audit/Final sequence with memory guards. Do not run another heavy job concurrently or restart a used label. No Strata process has been started.

Local evidence: `.cache/test-runs/m3-interruption-recovery-20261013-01` in master; historical campaign outputs remain in development's `.cache/test-runs/m3-final-native-20261012-01`. These local runtime records are excluded from Git. M3 acceptance, 77 audits/reviews, Final verification and the three-ridge exercise remain incomplete.
