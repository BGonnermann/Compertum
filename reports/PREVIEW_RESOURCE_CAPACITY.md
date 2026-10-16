# Preview resource check and capacity census

16 October 2026. The preview check is corrected and independently reviewed.
Exactly one complete capacity census ran. It refused the requested 1 GiB scratch
hold because it would exceed the unchanged 5 GiB scratch category by
**1,063,722,952 bytes**. The saved stop remains unchanged. No retry is authorized
by this result.

## Corrected check

The previous launcher rejected the website preview after it accumulated five CPU
seconds over its lifetime, even when a fresh observation showed no CPU use.
The new helper, `tools/preview_resource_check.ps1`, records lifetime CPU time
but checks the increase between two fresh observations. It retains the existing
0.10 CPU-second allowance, a 500-millisecond wait, the 64 MiB working-memory
ceiling, and the saved process identity. It refuses a measurement interval
shorter than 0.5 seconds or longer than 2 seconds, identity changes, counter
regression, and competing Python or model processes. It contains no process-stop
action.

The preview was absent at both launch observations. A separate process query
afterward also found its saved process identifier absent. This work did not stop
or restart it. The live census therefore verified the no-preview path; the
running-preview behavior was checked with simulated observations.

This repair retains the reviewed five-second scanner deadline, one CPU and
128 MiB limit. Separate subsequent edits are described below. The
capacity census is a separate maintenance measurement with the existing
70-second internal, 75-second parent and 85-second outer limits. It does not
establish a production scanner pass or permit ordinary work.

## Review and checks

The original check rejected the idle, long-running preview fixture, reproducing
the defect. After correction, **20 simulated preview checks and 11 pure capacity
checks passed, with zero failures, errors or skips**. The independent reviewer
repeated those checks and verified all 933 historical bindings and 27 current
bindings. Three old documentation versions remain available as exact snapshots.
Review cleared one census before launch. Repeated checks are not additional
product coverage. New product tests: zero passed, failed, errors or skips.

The census and runner retain the previously reviewed behavior apart from their
new file names. The support verifier checks both retained historical inputs and
current inputs. The launcher preserves the earlier refusal, records a durable
exclusive start claim, and records the current outcome without replacing prior
evidence. Later stages remain disabled.

## Census result

| Measurement | Result |
| --- | ---: |
| Directories | 28,634 |
| Files | 109,979 |
| Links | 1,631 |
| Entries with additional named streams | 1 |
| Unknown entries, unreadable directories, ledger failures | 0 each |
| Existing scratch charge | 5,358,690,248 bytes |
| Scratch category limit | 5,368,709,120 bytes |
| Scratch headroom before proposed hold | 10,018,872 bytes |
| Proposed scratch hold | 1,073,741,824 bytes |
| Scratch shortfall after hold | 1,063,722,952 bytes |
| Backup headroom | 522,272 bytes |
| Complete measurement elapsed time | 23.095123 seconds |
| Native process closure elapsed time | 23.565197 seconds |
| Outer launcher elapsed time | 24.168475 seconds |
| Peak native Job memory | 33,792,000 bytes |

The complete measurement was saved before the capacity gate refused. All 40 MiB
of records holds, the full scratch hold, actual reservations, additional streams,
and the existing 1 GiB execution reserve were included. The process exited with
code 1, its exit was observed, and zero children remained. There was no timeout,
scratch write, candidate build, candidate scan, installation or second census.

Review verified 217 source files, 217 installed files, the coordinator database
and saved stop before launch. The installed files, database and saved stop still
match afterward. All prior evidence and failures are retained. Strata was
not started. M5 requirements 2 through 5 remain open, and M6 remains at zero of ten
actual supervised sessions.

## Concurrent source changes discovered at closeout

After the census, the preservation check found separate edits to
`config/default.toml` and several source files. Those edits change the scratch
category to 9 GiB and the scanner setting to 30 seconds, among other runtime
changes. They are outside this repair and were not written, reverted, tested or
accepted here. The census used the reviewed 5 GiB scratch category. Its result
is a retained measurement under that baseline, not admission for the changed
working tree. Final whole-source preservation therefore does not pass. The
database and saved stop still match their original hashes. Publication from
this task includes only the preview helper, its checks and this task's reports.

Private evidence is retained under
`artifacts/m5/storage-frame-reuse-20261015-13`, including `current-review.json`,
`current-census-start.json`, `current-census-measurement.json`,
`current-census-result.json`, `current-census-closure.json`,
`current-census-launch.json`, and `current-census-launch-failure.json`.
The original `checked-preflight-refusal.json` is unchanged.

Next action: choose a concrete storage arrangement that accommodates the
1,063,722,952-byte shortfall while preserving evidence and the existing category
limits. This completed request does not authorize cleanup, a smaller test scope,
another census, a scanner attempt, clone writes or clearing the saved stop.
