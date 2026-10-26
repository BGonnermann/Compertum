# Native storage scanner plan

Status, 25 October 2026: plan only. The owner asked for this plan "for later". No code is changed. Nothing in this plan starts before the bench baseline and GEPA run 3, and nothing starts without the owner's OK.

## Why

Every owner-started engine run takes a full storage inventory before its first cycle (`StorageManager` in `src/compertum/storage.py`). The inventory must finish within `storage_scan_seconds` (30 seconds, `config/default.toml`).

On 25 October 2026 the first bench baseline start refused with `STORAGE_SCAN_DEADLINE`. Flint had just loaded and was still reading its model file, so the scan was slower than usual. The refusal came before any run row, request or trial.

After the owner-approved cleanup of one full-suite test folder, the scan takes 13.7 to 15.2 seconds with the model unloaded. That is about half of the limit. The project grows with every test run and every engine run, so the margin will shrink again.

## What the scanner does today

- `iter_storage()` walks the whole project from its root. It opens every directory through a small pinned C library, `src/compertum/_native/storage_scan.c` (77 lines), compiled to `storage_scan.dll`.
- The library has three calls: open a directory and read the first batch of rows, read the next batch, close. Python does everything else. It parses each 64 KiB batch of `FILE_FULL_DIR_INFORMATION` rows, decodes names, assigns categories, checks links, records each file and sums the charged bytes.
- Each directory handle stays open, without delete sharing, until its last batch is consumed. A directory cannot change under the scan.
- A link (reparse point) is resolved and must stay inside the project, or the scan refuses with `STORAGE_REPARSE_ESCAPE`. A link is recorded, never followed.
- The deadline and an optional volume probe are checked before and after every native call.
- `iter_storage()` is a generator. `runtime/managed_owner.py` drives it in 50 ms slices, so heartbeats and pipe replies keep their own deadlines during a long scan. `sample_storage()` drives it to the end in one call.
- The result holds the category totals, the free bytes, one entry per file (`files`) and the link paths.
- The DLL is pinned. `storage_scan.json` records the hashes of the source and the DLL, the compiler hash and the exact build command. `_native_storage.py` checks the manifest hash, the file hashes and the loaded file identity before use. `tools/build_storage_native.py` builds a new DLL offline into a fresh folder under `.cache/test-runs` for review. Nothing compiles at import time.

## Where the time goes

One read-only profile, 25 October 2026, model unloaded: 287,202 files, 93,749 directories, 6,544 links, 15.2 seconds.

| Work | Time | Who does it |
|---|---|---|
| Open each directory and read its first batch | 7.96 s | Windows kernel, through the DLL |
| Close each directory | 1.28 s | Windows kernel, through the DLL |
| Read later batches | 1.27 s | Windows kernel, through the DLL |
| Resolve 6,544 links | 0.75 s | Python (`Path.resolve`) |
| Parse rows, decode names, build the file list, check deadlines | about 4 s | Python |

About 10.5 seconds are kernel work for 93,749 directory handles, about 0.1 ms each. A native walker must still open every directory, so it cannot remove that part. It can remove most of the Python part: about 4 to 5 seconds, roughly 30 percent.

The number of directories drives the cost more than the number of files. Pytest working folders (`basetemp`) create tens of thousands of small directories.

## Option 1, no code: keep the directory count down

- Clean the working folders of completed, passing test jobs under `docs/TEST_RETENTION.md`, as on 25 October 2026. That cleanup removed 33,960 directories and cut the scan by about 4 seconds.
- Remaining large candidates, by file count on 25 October 2026: `scratch50-full-20261024-224412` (24,428 files; its result is unclear, so the owner decides first), `native-accounting-20261016-01` (24,079), `m5-local-economics-20261017-01` (17,469; capped folder with live fixtures, keep), and several M3 and M5 folders of 4,000 to 8,600 files each. Each needs its own result check before removal.
- Cost: no code, no requalification. Gain: proportional to the directories removed.
- Recommended first, and again whenever the scan exceeds about 20 seconds.

## Option 2: a native batch walker in the existing C library (recommended code change)

Extend `storage_scan.c` with a walker that processes many directories per call and returns compact results. Python keeps the generator, the deadline, the volume probe and the result format.

Design:
1. A new ABI version 2 adds one call, `cs_walk_step`. It takes a walker state, a directory budget per call (for example 256 directories) and a result buffer. It returns rows that are already parsed: the relative path, size, allocated bytes, a directory, link or file flag, and a status.
2. The walker keeps the same rules as today:
   - It opens each directory with the same flags and no delete sharing.
   - It holds each handle until all of that directory's rows are returned to Python.
   - It never follows a link. It returns each link with its final path, and Python checks that the path stays inside the project.
   - It rejects any malformed row (`STORAGE_SCAN_UNVERIFIED`).
3. Python calls `cs_walk_step` in a loop. It checks the deadline and the volume probe between calls and yields after each call. `managed_owner.py` and `sample_storage()` keep working unchanged.
4. Categories, charged bytes (the larger of size and allocated) and the result dictionary stay in Python. Those lines are short, and they hold the storage policy, which must stay readable.
5. Link resolution moves into the DLL (`GetFinalPathNameByHandleW` on a handle opened without following). This removes about 0.75 s of Python work.
6. The ABI 1 calls stay in the DLL, so a rollback is a one-line change in `_native_storage.py`.

Expected result: about 10 to 11 seconds today instead of 15, from about 30 percent less work. This estimate is unproven until measured.

Why C and not Rust or C++:
- The pinned MinGW `gcc` 16.1.0 that built the current DLL is installed and recorded by hash. The build script, the manifest format and the identity checks already exist.
- Rust (`cargo`, installed under `C:\Users\bgonn\.cargo`) would add a second toolchain to the pinned identity, a larger binary and new build records. It would not be faster for this work, because the kernel calls dominate.
- C++ adds nothing over C here.

## Option 3, rejected: read the volume's master file table

Reading NTFS metadata for the whole volume at once (for example `FSCTL_ENUM_USN_DATA`) would be much faster. It needs a volume handle with administrator rights. The project rules require the owner's explicit authority for administrator access, and the scan would read metadata outside the project. Not proposed.

## Option 4, owner decision only: a longer scan limit

`storage_scan_seconds` could be raised. The project rules say not to change limits merely to pass checks, so this plan does not propose it. The owner may decide it separately.

## Stages for option 2

1. **Measure.** Profile three scans with the model unloaded and three with Flint loaded. Record files, directories, links and seconds. Read-only.
2. **Write the walker** in `storage_scan.c` with ABI 2, and the Python driver in `storage.py` behind the same `iter_storage()` signature.
3. **Build offline** with `tools/build_storage_native.py` and the pinned compiler into a fresh folder under `.cache/test-runs`. Review the receipt. Install the DLL and the manifest into `src/compertum/_native` only after review.
4. **Test that it is the same:**
   - The inventory from ABI 2 must equal the ABI 1 inventory exactly: the same files, sizes, allocated bytes, totals and link paths on the full master tree.
   - Fixture tests: links inside and outside the project, a malformed row, a directory removed during the walk, the deadline, the volume probe, cancellation by closing the generator, and empty and very large directories.
   - The existing storage tests in both lanes.
5. **Requalify.** `storage.py` and the DLL are accepted product code under the M3 and M5 records. The runtime identity pins include the native payload. A change needs:
   - the full product suite in the source lane;
   - an installed-package build and its lane;
   - an independent review;
   - updated identity records.
6. **Measure again** with the same method as stage 1, and record the gain honestly, including no gain.

## Risks and history

- Storage admission was blocked for a long time in October 2026. Twelve scanner experiment rounds and five maintenance reviews are recorded as used. The checkpoint's older next action, "obtain a new bounded decision for a broader native batch-walker experiment, or leave admission blocked", is the decision this plan prepares. It is still the owner's decision.
- The scanner protects the storage limits. An error that undercounts bytes would let the project exceed its budgets silently. So the stage 4 equality test is the acceptance gate, not the speed.
- The gain is modest, about 30 percent. Option 1 can give a similar gain with no code risk.

## Approvals needed

- The owner's OK to start stage 1.
- The owner's OK to install the rebuilt DLL into `src/compertum/_native` after the offline build review.
- No new software install, account, spending or administrator access is needed.
