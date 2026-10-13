# Native retry timing observations

12 October 2026 UTC. Prerequisite to shared admission and explicit producer retries. Objective: retain bounded normalized Retry-After evidence on native responses before status rejection. No retry, queue, authority, deadline extension or public route added.

- [x] Pure strict normalization: decimal nonnegative seconds and all three HTTP-date forms, UTC, obsolete two-digit year rule, leap second normalization, exact integer nanoseconds.
- [x] Native single-header acquisition before status acceptance; metadata survives refused status and is attached to successful private result. Duplicate/malformed/overflow values fail statically and close native handles.
- [x] Verify native GET/DATA/ASSET/order paths; no automatic resend, unchanged response/body/header/deadline/origin limits.
- [x] Independent review up to three passes, frozen paired source/package regressions, exact replay and storage receipt.

Bound header text to 128 characters after native 16 KiB header cap. Bound decimal delay to 2^31-1 seconds; larger values are invalid rather than ignored. Accept only RFC date grammar, check calendar/weekday and UTC, normalize leap second 23:59:60 to the following instant. Obsolete RFC850 years use the most recent matching year no more than 50 calendar years ahead of the header-observation clock. Reject clock/range overflow. Use integer UTC delta nanoseconds, clamp past HTTP dates to zero delay, and anchor delay to monotonic time captured at header observation. Retain sanitized kind, wait and clock references only, never arbitrary response header strings.

These observations do not authorize retry. Producer deadlines, first/second retry delays of 1/4 seconds, maximum three attempts, preserved error evidence and single queue remain downstream. PAPER100/min is a conservative local ceiling distinct from DATA100/min, not provider entitlement. A 60-second startup fence prevents immediate reset into a full bucket; no old tickets/task grants restored.

Primary references checked 12 October 2026 UTC: [RFC 9110 sections 5.6.7 and 10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html); [Microsoft WinHTTP SDK declarations](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/winhttp.h), WINHTTP_QUERY_RETRY_AFTER=36. SDK declarations establish the native identifier, not provider support or account entitlements. Native local tests are required; no actual service request needed.

Completion marks added after frozen verification; reviewed hash remains in receipt.
