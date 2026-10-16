# Timers and storage

## Current allocation - 16 October 2026

The owner approved 12 GiB scratch after an earlier 11 GiB approval. Backups remain 21 GiB.
The aggregate cap remains 50 GiB. The fully allocated 1 GiB emergency reserve remains protected.
The first native fixture retains its watchdog halt and allocated reserve.
A separately admitted fixture passed the current source and installed native stages.
Each fixture keeps its original path and records. No evidence was removed.

The final full census passed with 141,360,336 bytes of scratch headroom after recorded holds.
Backup headroom is 1,074,264,096 bytes. The census includes both activity namespaces and outstanding reservations.
Current namespace ceilings are 1152 MiB and 1056 MiB. An older 128 MiB scratch hold remains included.
The separate full metadata census retains its 70-second measurement deadline and 80-second job bound.
Production scans still allow 30 seconds. Inventory freshness remains 35 seconds.
Tests retain 120 seconds, four CPUs, 4 GiB RAM and 16 processes per job.
Host memory floors remain 16 GiB before start and 12 GiB while running.
Only one heavy job runs at a time. Strata and its model server remain off.

See `artifacts/m5/native-activity-20261016-01/capacity09-measurement.json` and `capacity09-result.json`.
The source and installed environment checks and native closures are in the same evidence folder.
See [the native activity report](M5_NATIVE_ACTIVITY_PRODUCER.md). Earlier allocations below are preserved history.


The latest complete census passed in 44.709 seconds after the activity parser checks. With all holds, scratch charges 10,427,707,384 bytes, records charge 1,214,080,896 bytes and backups charge 21,474,314,208 bytes. Scratch headroom is 309,710,856 bytes after a 128 MiB additional hold. Backup headroom is 1,074,264,096 bytes. All 437 original preservation pins and the new package bindings verified.

An extra 1 GiB native fixture would exceed the current scratch category by 764,030,968 bytes. The owner approved 21 GiB backups only. The separate 11 GiB scratch decision remains pending under the unchanged 50 GiB total. No new full-reserve activity lifecycle check or saved-stop recovery ran. See [current evidence and the exact next action](M5_ACTIVITY_BOUNDARY.md).

### Earlier native-record measurement

Later on 16 October, the owner approved **21 GiB backups**, retaining the 50 GiB total. This replaces the former 522,272-byte backup headroom. A complete follow-up census passed in 45.262 seconds. It verified the original allocated emergency reserve and 437 preservation pins. Backups have 1,074,264,096 bytes of headroom. Scratch has 321,240,632 bytes left after a 128 MiB additional hold. Complete allocation and reservation accounting remains in `artifacts/m5/native-accounting-20261016-01/capacity05-measurement.json`.

The native-record verification namespace has a 1280 MiB bound. It retains failed builds, prior package artifacts and a successful isolated test environment. Existing test limits remain 120 seconds, four CPUs, 4 GiB RAM and 16 processes. Host start/stop memory floors remain 16/12 GiB. The product scanner remains 30 seconds, inventory freshness 35 seconds and scratch 10 GiB. One heavy job runs at a time.

The next small activity protocol checks fit this capacity. Another fully allocated 1 GiB native reserve fixture does not fit. The owner's separate 11 GiB scratch decision remains pending. No evidence removal or saved-stop recovery is authorized by the backup amendment. Strata remains off. See [native record verification](M5_NATIVE_ATTEMPT_RECORDS.md).

## Earlier resource-policy measurements

16 October 2026. The owner authorized sizing scan deadlines and temporary storage for the actual workload, then continuing the blocked local work. This decision supersedes the earlier five-second scan and 1 GiB preparation allowance. It preserves the 50 GiB project budget, free-disk floors, CPU/RAM limits, emergency reserve and all historical evidence. Strata stays off.

## Selected limits

| Work or check | Limit | Reason |
| --- | --- | --- |
| Complete product storage inventory | 30 seconds | A full inventory visits over 110,000 files. The previous five-second boundary left little room for variation. |
| Maximum completed-inventory age | 35 seconds | Allows a bounded 30-second replacement scan with a short scheduling margin. Pending or stale inventories cannot admit work. |
| Watchdog scan work between control-loop turns | About 0.05 seconds | Traversal yields between checked native directory entries so heartbeat and control work can continue. |
| Disk-free observation | 1 second | Kept separate from the complete inventory. |
| Supervisor health relay during admission scans | 0.8 seconds | Services peer health without committing local state from inside a storage transaction. |
| Heartbeat / missing-peer limit | 5 / 15 seconds | Unchanged. A slow inventory is not permission to lose a worker. |
| Owner startup status | 35 seconds | Initial reserve verification can require a full scan. Normal owner calls retain five seconds. |
| Public authenticated command | 300 seconds | Covers recovery and its several sequential admission inventories. Authentication and final reply acknowledgement each retain five seconds. |
| Complete recovery barrier | 240 seconds | Shared deadline covers scan callbacks and the final manifest publication check. Expired recovery retains partial evidence without publishing completion. |
| Test/build job | 120 seconds, four CPUs, 4 GiB RAM | Existing bounded verification envelope. Jobs run serially; long suites are split. |
| Full metadata capacity census | 70 seconds, one CPU, 128 MiB RAM | Separately measures directories, file allocation, named streams and actual reservations. This is not a product scan. |
| This task's temporary namespace | 4 GiB | Three allocated 1 GiB native reserve fixtures, an isolated installed environment, source/wheel archives, and retained test failures. |
| Project scratch category | 10 GiB | Existing scratch was about 4.99 GiB. The task needs 4 GiB plus approximately 1 GiB working margin. |

The existing preview check was repaired separately to measure CPU consumed during a fresh observation interval. Process lifetime is not a measure of present CPU load. Its earlier capacity refusal remains valid historical evidence; this later owner-authorized allocation is a separate decision.

## Measurements and verification

The initial complete metadata census took **28.305 seconds**: 28,627 directories, 109,965 files, 1,627 links and one named-stream entry. No unreadable entries or reservation-ledger failures were reported. The actual coordinator contained no outstanding reservations. The original emergency reserve's identity, full allocation and non-sparse status matched retained evidence.

Three complete product inventories under one CPU and 128 MiB took **4.063, 4.113 and 4.061 seconds**. Disk-free observations continued at intervals no longer than 0.903 seconds. These timings explain why five seconds was fragile. Product inventory and the fuller metadata census use different accounting paths; their byte totals are not interchangeable.

Resource verification: source 112 passed, zero failed/errors, one non-Windows test skipped, with the previously passed native heartbeat case reused. Installed package 113 passed, zero failed/errors, the same one non-Windows skip. Both environments passed full dependency and program-byte verification. Native tests kept real worker heartbeats healthy through a deliberately delayed 16-second scan, detected a subsequently terminated peer, accepted a six-second authenticated command, and verified timeout cancellation and handle closure. The native reader binary was not replaced. Earlier failing runs remain saved.

Private measurements, exact test IDs, logs, XML results, environment manifests and process-exit receipts are in `artifacts/m5/resource-policy-20261016-01`. The fresh temporary namespace is `.cache/test-runs/resource-policy-20261016-01`; the original installed environment and saved master stop remain preserved.


After the new fixtures and installed environment were retained, three further complete product scans took **4.803, 4.834, 4.955 seconds** across 132,965 files. Disk-free checks stayed within 0.904 seconds. The final scanner job used 77.5 MiB at peak, below 128 MiB.

## Final capacity check

The final complete metadata census passed in **29.308 seconds**, with 33,173 directories, 130,919 files and 2,040 links. There were zero unreadable entries and zero ledger failures. It included an additional 512 MiB scratch hold and 40 MiB records hold for completion work.

| Category | Measured allocation | Ceiling |
| --- | ---: | ---: |
| data | 0.000 GiB | 15 GiB |
| models | 0.000 GiB | 5 GiB |
| scratch | 8.492 GiB | 10 GiB |
| records | 1.075 GiB | 5 GiB |
| backups | 20.000 GiB | 20 GiB |

Measured total: **29.567 GiB** of 50 GiB. Physical disk free: **187.673 GiB**. The task namespace peaked at 3,791,618,048 conservatively charged bytes before documentation, below its 4 GiB limit. The original emergency reserve, master coordinator bytes, saved stop and all 217 original installed files remained verified.

The final 10 GiB policy passed 11 focused source cases; its installed check plus the changed watchdog/seal case passed 12. The corresponding source watchdog/seal case passed separately. Installed native recovery passed one additional end-to-end case with actual separate worker owners and a full reserve; recovery timing on that small fixture is not a full-master recovery benchmark.

An early verification launcher allowed 32 processes; later jobs enforce 16. A brief overlap between two early reader jobs is retained in the private correction receipt. Later runs enforce exclusive execution with a file lock, and all affected final reader cases were rerun serially. These earlier timings are not used as capacity qualification.

## Will more space be needed?

The immediate constraint is the **backup allocation**, not the physical disk. At the initial census, backups occupied 21,474,314,208 bytes, leaving only **522,272 bytes** below their 20 GiB ceiling. Ordinary new recovery snapshots cannot be assumed to fit. No backup was removed and no backup cap was raised by this change.

The 50 GiB aggregate ceiling remains independent of category ceilings. Categories now total 55 GiB, but they cannot all reach their individual maxima simultaneously. The 1 GiB emergency execution reserve remains inside the records category and cannot fund research scratch. About 192 GiB of physical disk was free during the measured scans; the operating floor remains 50 GiB and large ingestion still requires 100 GiB free.

Before allocating more disk or changing another category, measure:

1. Actual daily growth of retained test evidence, checkpoints, backup blobs and source archives. Keep failed evidence; do not infer recoverability from compression alone.
2. A representative market-data batch: bytes per symbol/day, indexes, staging copies and retained versions. Forecast the selected universe and retention period from those measurements.
3. The largest admitted job's peak temporary allocation, including simultaneous input/output copies and its failure residue. Add this peak to retained usage rather than averaging it away.
4. Backup deduplication and the required seven daily/four weekly recovery manifests against verified restore requirements. Any proposed cleanup or larger backup allocation needs a concrete preservation plan.

Use `retained bytes + outstanding reservations + next job's peak + protected reserve gap` for each capacity decision. Record several measured samples before projecting a growth rate. More physical storage is not yet justified by these observations; backup headroom must be resolved before ordinary recovery work resumes. No periodic monitor or background service was created.
