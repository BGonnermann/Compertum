# Why the storage scan still refuses

15 October 2026. The storage inventory still exceeds its unchanged five-second limit. The four approved folders are removed; the remaining directory workload is large. One new read-only timed profile confirms that directory acquisition plus the first query, followed by checked closure, are the largest measured costs. This preparation restores no admission and changes no product code.

## What is established

The last complete pre-removal census counted 29,338 directories, 110,827 files and 1,638 links. Removal eliminated 718 directories, 1,098 files and 11 links. The directory reduction is 2.447%, leaving a derived 28,620 directories before later record/Git growth. That is a workload calculation from preserved evidence, not a fresh complete inventory or capacity grant.

The latest uninstrumented production attempt already refused with `STORAGE_SCAN_DEADLINE`; it never returned an inventory or reached reservation/capacity evaluation. The new diagnostic ran the current function with timers, the same five-second checks, original caller-thread volume callback, one CPU and 128 MiB. It refused after 5.0007710 seconds, using 3.1875 CPU seconds, after visiting 42,982 files and opening and checked-closing 9,451 directories. Another 110 directories were still queued. These are incomplete observations.

| Timed phase | Completed calls | Wall seconds |
| --- | ---: | ---: |
| checked close | 9,451 | 0.677391 |
| directory open first query | 9,451 | 1.990421 |
| first copy | 9,450 | 0.074656 |
| link resolve | 839 | 0.485281 |
| next query and copy | 9,469 | 0.339777 |
| row parse | 9,469 | 0.307321 |
| volume callback | 37,820 | 0.042239 |

Open plus first-query and closure totaled 2.667811 seconds, about 53.3% of this partial run. The first component includes cold library setup and the first native query; it does not isolate raw file-open latency. Volume callbacks took only 0.042239 seconds, so dropping their checks would not address the measured main cost. Time outside the named phases includes Python bookkeeping, the instrumentation itself and possible scheduling delays. It must not be labeled entirely as disk wait or Python overhead.

The current source creates one native `Directory` for every ordinary directory. It queries pages, parses every returned row and closes that handle before continuing. The native reader also repeats function lookup for directory queries. An earlier relative-open prototype removed lookup repetition but still timed out. The later native walker also timed out. Neither is a qualified current replacement.

## What remains uncertain

The instrumented scan is slower and differently observed than a production scan, and it has no complete inventory. Its visited-file count cannot establish a controlled throughput regression. CPU time below elapsed time does not identify the source of waiting. No evidence establishes antivirus, power policy, storage hardware, Windows scheduling or another process as the cause of the difference from historical 4.566, 4.948, 4.930 and 4.586-second passes. One profile cannot settle that question.

The supported diagnosis is a serial directory-operation workload with insufficient timing margin. The precise external reason for timing variation remains unknown. Removing only 2.4% of directories did not establish enough margin, and capacity cannot be accepted without a completed scan.

## Concrete proposal for review

See [the bounded fix review](../docs/STORAGE_ADMISSION_FIX_REVIEW.md) and its unapplied source diff. Extend the existing private native walker with a per-walk cache of at most 16 checked-closed directory buffers. This keeps native reads and callbacks on the calling thread. It avoids repeatedly allocating and clearing the same 64 KiB buffers while retaining every open, identity/type/link check, row bound, query, callback and checked close.

This is a performance hypothesis, not a measured fix. The current production reader already reuses one buffer; buffer allocation is additional work in the unpromoted walker, not the cause assigned to the production scanner. Reuse might make that walker viable; its effect has not been timed. Raw directory open/close costs remain. Stop the proposal if that change cannot pass the existing actual-limit gate; do not combine unrelated changes to manufacture success.

Two-reader overlap was considered and rejected for this proposal because `test_native_reads_and_volume_callbacks_stay_on_caller` explicitly requires all native reads on the calling thread. Repeated lookups alone are also insufficient evidence for a fix, since the earlier cached prototype failed. No cached inventory, subtree exclusion, larger deadline, larger scan memory/CPU limit or deletion is proposed.

## Preservation and counts

The profile's parent closed with exit code 0, observed exit, zero children, 6.4703625 seconds elapsed and 47,599,616 bytes peak memory. Successful diagnostic recording does not mean a successful scan. All 820 frozen inputs, 217 source and 217 installed program files, completed backup payloads/index, previous failed receipts, actual coordinator bytes, reserve and watchdog stop are rechecked in the separate closeout receipt. The earlier twelve scanner experiment rounds and five maintenance reviews remain used.

Two in-memory diagnostic failure-record checks passed, zero failed or skipped. The earlier expected failures and first reviewed helper remain saved. One actual read-only profile refused at five seconds. No candidate was compiled, run, installed or promoted. Product tests are zero passed, failed and skipped. Reader19 stays at 34 drafts and zero executed cases; M5 requirements 2 through 5 remain open and M6 remains zero of ten actual sessions.

| Preserved local record | SHA-256 |
| --- | --- |
| Timed profile | `2e376cf8b26f64abcd5c78da34a9eec369e9c7ce67f7253f41c1bc9d1cb7148d` |
| Profile parent closure | `6a3d7cfe13498171c46b1994cd28c56255f1bdef8e1d99672076967299ec91b3` |
| Frozen inputs | `b1a277bc27d52ebff49ffd63499574de6666696c3ee4fa36e1a267db15e8cca6` |
| Prior production refusal | `c29e09bf4cc24ab49141709417b57bebe68ed4e7be48c8a607127c36b0dea7d2` |
| Proposed diff | `9a91717542f4b98372a5a4085a34d215024a90115db8c3c6a0c1fa608e7b04ce` |

Detailed records stay ignored under `artifacts/m5/storage-admission-diagnosis-20261015-01/`. Ordinary work, clone updates and the preserved `STORAGE_UNHEALTHY` watchdog stop remain unchanged. Approval of a later timing experiment would not approve clearing that stop or starting a runtime.
