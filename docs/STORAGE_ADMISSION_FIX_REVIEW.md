# Bounded storage fix for review

15 October 2026. **Review preparation only. No candidate execution or product change is approved by this document.** The owner requested diagnosis and a bounded fix proposal while keeping current limits and all evidence. See [the measured diagnosis](../reports/STORAGE_ADMISSION_DIAGNOSIS.md).

## Exact proposed change

The current scanner opens every directory separately. The profile found 1.990421 seconds in directory acquisition/first query and 0.677391 seconds in checked closes before reaching five seconds. Cleanup removed only 718 of the last complete 29,338 directories. Most of that work remains.

Use [this unapplied diff](proposals/storage-frame-reuse.patch) against a fresh copy of the existing round-12 private native walker. It changes only memory management for directory frames. The original private source remains untouched at `.cache/test-runs/m5-native-batch-20261015-10/round12/storage_scan.c`, SHA-256 `ee59969dde28954d29cc89d79d8fbbc797130892c8a1e8bc98d3d6c23095b79c`. Diff SHA-256 is `9a91717542f4b98372a5a4085a34d215024a90115db8c3c6a0c1fa608e7b04ce`. The expected normalized candidate-source SHA-256 is `a27f0725784cf910856966798d99152221e1b72fe954dd55d5f1eaddd006e321`. The diff has not been applied, compiled or executed; production's 217 source and 217 installed files are unchanged. This is not yet a complete production integration patch.

The walker currently allocates and clears a frame containing a 64 KiB buffer for each directory, then frees it on return. Reuse at most 16 already checked-closed frames inside that one walk. Reset every control field before reuse, preserve 8-byte buffer alignment, parse only the newly reported valid byte count, and free all active and spare frames on final cleanup. Do not cache names, rows, allocations, links or an inventory between scans. Microsoft documents [zero-initialized HeapAlloc memory](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heapalloc) and [checked HeapFree ownership](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heapfree); these describe API semantics, not a proven speedup.

The extra retained cache is at most 16 frame objects, slightly over 1 MiB including control fields. Active traversal depth is not shortened or excluded; the existing 128 MiB Job cap remains the total memory boundary. A close failure must never enter the cache. Cache eviction or final free failure must refuse qualification. One scan owns the cache, and all memory is released before reporting completion.

The current production reader already reuses its buffer. This proposal targets avoidable allocation work in the existing unpromoted walker so that its reduced Python traversal work can be tested fairly. Allocation was not separately timed in the current profile, so no speedup or successful admission is claimed. A change that still misses five seconds is rejected.

## Contracts kept intact

One CPU, 128 MiB, five seconds from cold candidate initialization through all checked closure; one heavy Job at a time; physical/commit start floors 16 GiB and stop floor 12 GiB. Native reads and original volume callbacks remain synchronous on the calling thread. Keep every native open/type/reparse/noninheritance check, strict row/UTF-16 validation, exact allocation charge, link-target validation while the parent is held, caller-thread refusal, native close and final probe. Preserve legacy ABI behavior and the original callback cadence. No background reader, async open, missing subtree, cached inventory, privilege/security/priority change, service or Strata start.

## Bounded proposed qualification

This is one proposed candidate attempt, not permission to resume exhausted rounds. Carry scanner rounds 1 through 12 as used. If approved later, label this new candidate round 13 and permit at most three review/repair passes for its exact source. Do not start round 14 or an unrelated candidate automatically. A failed timing result ends this experiment.

The later execution procedure must freeze exact compiler/runtime/source/installed hashes, all parameterized case IDs, job commands, expected counts, per-job growth and maximum eleven native Jobs before launch. No job may be started merely to discover its required allowance.

| Required stage | Maximum Jobs | Existing resource boundary |
| --- | ---: | --- |
| Fresh complete allocation/stream/reservation census before any scratch write | 1 | One CPU, 128 MiB, 70-second internal/75-second parent maintenance limits |
| Build original control, patched candidate and native fault harness with the existing pinned compiler | 1 | One CPU, existing 4 GiB build cap, 15 seconds |
| Native boundary/fault checks and two complete small-inventory comparisons | 1 | One CPU, 128 MiB, 15-second startup/cleanup envelope; each scan remains five seconds |
| First actual full-master candidate viability scan with original volume callback | 1 | One CPU, 128 MiB, five-second scan/15-second startup-cleanup envelope |
| Matching source and isolated installed-package affected cases | 2 | Existing product-test caps of four CPUs, 4 GiB and 120 seconds per Job |
| Complete source and isolated installed-package environment checks | 2 | Same existing test-worker ceilings |
| Three final complete actual-limit scans after all verification evidence exists | 3 | Each one CPU, 128 MiB, five seconds plus existing 15-second startup/cleanup envelope |

Stop at the first failed capacity, equivalence, fault, environment or timing gate. Preserve the exact refusal and all partial evidence. Do not run the later stages after a failed viability scan. All three final scans must pass, including cold initialization, every file/link record and checked cleanup. No retries of a failed full-master scan are included. Completion of a native Job wrapper alone is not a scan pass.

Required new behavior groups are buffer reuse and control-field reset; cap/eviction at 16; depth beyond the cache without dropped nodes; alignment; empty/dot-only directories; multi-page queries; poisoned stale bytes beyond the valid length; native-open failure; heap-allocation failure; failed-close exclusion; eviction/free failure; final free failure; callback/deadline refusal; reparse-yield/ack parent-lock lifetime; cleanup after partial traversal; and exact complete inventory/allocation/link equality. Freeze all parameterized subcases before execution. Retain the previous 18 native C boundary checks and account for the historical 43 matching source/installed scanner cases through fresh current case IDs. Those historical passes are not new candidate acceptance.

Small comparisons use the existing unchanged source and test trees, in one read-only comparison phase without intervening writes to those trees. Candidate/library initialization and all cleanup stay inside their respective scan clocks. The viability result must contain a complete current inventory, not a partial profile. Only after viability may a reviewed implementation bridge wire the walker into `sample_storage`, update the pinned native loader/source/DLL/manifest together and build a separately identified installed lane. Preserve the current installed package and every original runtime identity. Integration source must pass independent review before the matching lanes run.

## Storage and authority before execution

Current preparation uses a separate 2 MiB records folder and no scratch. Do not borrow or reopen the prior completed 24 MiB maintenance allowance. For the proposed future experiment, request at most 4 MiB of records and 8 MiB of actual new scratch, each as a cumulative hard growth ceiling, including builds, fixtures, isolated installed payload, failures and closure. Use a fresh checked `.cache/test-runs/m5-storage-frame-reuse-20261015-13` namespace with an 8 MiB total charge ceiling; no old folder is reused. Records go to `artifacts/m5/storage-frame-reuse-20261015-13` within 4 MiB. These are proposed bounds, not storage grants or proof that all required tests fit.

The current 217-file package totals 2,178,308 logical bytes; its allocated copy, wheels, all native build products and retained fixtures must be measured before granting their smaller fixed per-job holds. If the frozen full test inventory cannot fit the 8 MiB ceiling, stop before it starts. Do not delete evidence or waive required tests to make it fit.

The fresh complete census must charge all existing use, named streams and actual reservations, preserve the 1 GiB reserve, and include the full previous 34 MiB conservative records hold, this 2 MiB preparation hold, and the proposed new 4 MiB records/8 MiB scratch holds together. Require each unchanged category cap, total 50 GiB and 50 GiB free-volume floor. The derived scratch reduction is not a live grant. No backup write is proposed. Use only the existing compiler/interpreter/dependencies; no installation, credentials, account action, security change, extra deletion, clone write or ordinary runtime is included.

## Impact and review decision

| Surface | Status | Required action |
| --- | --- | --- |
| Private round-12 walker | Proposed change | Apply only to a fresh copy; preserve original and failed evidence |
| `storage.py`, `_native_storage.py`, native C/DLL/manifest | Later integration only | Keep pinned identity and legacy ABI coherent; no product edit in this preparation |
| Native C and five scanner/storage test files | Verify | Freeze complete expected case IDs; matching source/isolated installed results, zero failures/skips |
| `StorageManager._capacity`, actual reservation database, execution reserve | Preserve and verify | Same combined holds, real reservation handling, no actual database writes |
| Watchdog caller-thread callbacks, fresh/stale/free-space checks | Preserve and verify | No cached observations or weakened cadence; all closure inside scan bound |
| README/checkpoint and release evidence | Must update after actual qualification | Separate current preparation from a future qualified release |
| Credentials, Strata, paper runtime, reader19 and requested clone | Unaffected | Keep stopped and unchanged |

The review decision covers only whether to proceed with this one bounded candidate and its separately frozen executable procedure. This preparation does not activate it. A future capacity pass also cannot clear the existing `STORAGE_UNHEALTHY`/`RETAINED_WATCHDOG_HALT` stop. Any halt recovery requires a separate concrete operating decision after successful qualification. M5 and financial acceptance remain open.

## Preparation follow-up

The owner requested closure of the three preparation gaps and a separate review.
Read [the preparation result and storage decision](STORAGE_PREPARATION_GAPS.md).
The integration and regression patches are now prepared but remain unapplied.
The preservation receipt exists. A fresh calculation shows that complete
isolation requires at least 345,161,969 dependency bytes against an 8,388,608-byte
scratch ceiling. The executable procedure remains blocked and incomplete.
The owner instructed the implementation worker to hold execution. This follow-up
does not release that hold or authorize another admission check.
