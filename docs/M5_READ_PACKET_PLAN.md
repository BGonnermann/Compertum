# Bounded read packet driver

11 October 2026. Next offline integration component after read preparation. Primary owns implementation; one bounded independent reviewer, at most three review/repair passes. No real credentials, external account requests, order methods, persistence of raw private data or financial authority. Synthetic responses under native execution ownership exercise the same boundary.

Freeze one validated plan and credential envelope for the packet. Start once before the plan's60second start expiry; no retry/resume after interruption. The execution-owned driver creates requests in sequence ACCOUNT, CLOCK, CALENDAR, POSITIONS, one to eight ORDERS pages, final CLOCK. It counts an attempt when issued, permits one pending request and accepts only that exact request. Unknown account identity is bootstrapped only from the first qualified ACCOUNT reply and held privately. Every reply passes the existing secrecy/parse gate before use.

Each dispatch and reply stays within the30second packet deadline and frozen New York date; dispatch timeout is min(10seconds,remaining packet budget). Pin actual dispatch/receipt timestamps. The native adapter must also enforce monotonic deadlines and generate timestamps itself; supplied timestamps in these offline tests are not proof of real transport.

Orders use all statuses, ascending order,25rows/page, no symbol/side/class/time filter and nested=false. A continuation cursor must be the immediately preceding full page's last valid UUID. Keep unsupported and foreign rows visible. Reject oversized pages, duplicate IDs/client IDs, repeated cursor, invalid last cursor, future or decreasing submission times; equal times are permitted. Eight full pages stops incomplete, never success. A short terminal page establishes only bounded observed list coverage, not atomicity or ownership. Final clock timestamp must be within five seconds of completion and all account/list observations within30seconds. No actual-flat or economic reconciliation claim.

Public status includes alias, plan/request references, counts, fixed reasons and incomplete/complete preparation scope. Private replies/account identity remain execution-owned and nonserializable. Owner release closes the driver and clears retained private references. The later native adapter/protected evidence store must enforce storage, health, generation, real read grant and cancellation before dispatch; no generic callback or URL entrypoint is added here.

Acceptance:
- [x] Fresh64MiB admitted namespace; red tests and exact sequencing/credential pinning.
- [x] Empty and multipage completion, equal-time cursors, eighth full page, unsupported/foreign activity, duplicate/cursor/time denial, failed attempt/cancel/release.
- [x] Review; matching source/package regression IDs; exact deterministic synthetic replay; immutable receipts and checkpoint.

Official interface rechecked11October2026: [Alpaca order listing](https://docs.alpaca.markets/us/v1.4.2/reference/getallorders-1) documents ascending submission-time sorting and exclusive after_order_id pagination; no timestamp filter is combined with the ID cursor. Runtime response coverage remains subject to actual verification.

Precision decision: local execution timestamps use the native/Python microsecond precision and reject finer supplied values; provider order/clock timestamps retain up to nine fractional digits for exact ordering/future/freshness comparisons. Cleanup uses the existing owner mutex and drops owned private ID, cursor, credential and response references. This is reference cleanup, not guaranteed erasure of immutable Python strings.
