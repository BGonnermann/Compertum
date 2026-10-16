# Private activity request and parser boundary

16 October 2026. The activity request, page parser and bounded traversal are verified.
These are data records only. No native activity producer or ownership proof exists yet.
Every observation remains blocked, with financial and transport authority false.
M5 requirements 2 through 5 remain open. M6 remains 0/10 actual supervised sessions.

## Implemented behavior

The request fixes `GET /v2/account/activities`, ascending order and the original interval.
It omits activity-type, category and order filters.
It binds project, alias, opening, account context, retained history and credential identities.
The private account value cannot appear in prepared request bytes.
Activity IDs are bounded opaque cursors. They are not dates or UUID-only fields.

The bounds are eight pages of 25 rows, 64 KiB per reply and 512 KiB total.
The original traversal deadline is 20 seconds. Individual requests allow at most 10 seconds.
No retry is permitted by these records. The future producer must retain any shorter original context lifetime.
A short terminal page completes only the requested traversal.
Duplicate IDs, changed bindings, broken cursor chains and invalid timing refuse.
An eighth full page remains incomplete.

Fill observations retain exact broker IDs, quantities, cumulative fills, residual quantities, prices and timestamps.
Fill chronology and interval comparisons preserve nanoseconds.
Local receipt clocks reject unsupported precision before text normalization.
Fractional fills are observations only. Later ownership rules must decide whether they are supported.
Unknown activity remains preserved and blocking.

Creation-date filtering does not prove that all economic liabilities are posted.
Alpaca can create fee entries the next UTC day.
Nontrade dates can describe occurrence or settlement rather than creation.
See [the activity endpoint](https://docs.alpaca.markets/us/reference/getaccountactivities-2)
and [activity objects](https://docs.alpaca.markets/us/docs/account-activities).
Complete traversal always retains native provenance, ownership, economic, fee and action blockers.
No account-flat claim is made.

## Verification

| Final activity cases | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Source | 99 | 0 | 0 | 0 |
| Installed package, identical inventory | 99 | 0 | 0 | 0 |

These are pure tests with invented records. They claim no new native activity lifecycle result.
Both complete environment byte checks passed with 220 program payload files and unchanged locked dependencies.
Independent review round 3 is clear. All three rounds for this boundary are used.
Every accepted native Job closed with zero remaining children.

The earlier 272 component cases retain unchanged code and selected test dependencies.
The new module is the only added program payload.
The combined nonoverlapping inventory is **371 passed per environment**, zero failures, errors or skips.
The 99 new cases are included in that total.
Existing native loopback evidence remains valid for unchanged components.
New activity-producer native checks have not run.

Private evidence is under `artifacts/m5/native-accounting-20261016-01`.
Use `activity-aggregate.json`, `activity-accepted-frozen.json`, `activity-boundary-release.json`,
`activity-independent-review3.json`, both final XML files and their native Job closures.
Current environment records use the `activity-boundary-source` and `activity-boundary-wheel` manifest names.
Their results are `activity-verified-source.json` and `activity-verified-wheel.json`.

## Preserved failures and repairs

The absent-feature run had 93 failed cases and two error events on one other case.
There were 94 collected IDs. That case failed during setup and teardown.
Its default pytest name exceeded the Windows environment-variable limit.
Only its name was shortened. Its 65,537-byte payload remains unchanged.
The original test source, failed XML, logs and exact case-name mapping remain saved.

The next run had 93 passed and one failed, with zero errors or skips.
It exposed rejection of a valid millisecond receipt timestamp just before expiry.
Review then found that unconditional normalization could discard precision and weaken a deadline.
The frozen precision reproduction ran all 99 IDs and returned 95 passed and four failed.
No errors or skips occurred in that reproduction.
The final repair rejects unsupported local clock precision and compares fill times exactly.
No deadline, payload limit or acceptance case was weakened.
All failed inputs and results remain preserved.

## Capacity barrier and exact next action

The complete final census passed in 44.709 seconds.
Scratch has 309,710,856 bytes left after a 128 MiB additional hold.
Backups have 1,074,264,096 bytes left under the approved 21 GiB ceiling.
The total remains 50 GiB. The scratch category remains 10 GiB.
An additional 1 GiB native fixture exceeds current scratch headroom by 764,030,968 bytes.
The separate 11 GiB scratch decision remains pending.
See `capacity06-result.json` and `capacity06-measurement.json` for complete accounting.

Exact next action: resolve that allocation, then implement and qualify the private native activity producer.
Freeze its original-input bindings and exact native lifecycle cases before execution.
Its new queue binding, actual loopback requests, encrypted publication and restart need fresh full-reserve evidence.
Then complete ownership/economics, risk, durable dispatch/recovery and the integrated local rehearsal.
Keep missing evidence blocking. Stop before any actual broker order, cancellation or close.
The saved master stop, terminal M3 audit failure and all failed evidence remain preserved.
Strata remains off.
