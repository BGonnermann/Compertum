# Read preparation and private response qualification

11 October 2026. Offline preparation only. No actual account/credential access or transport dispatch. Keep the existing M5 strict fixture modules unchanged; a preparation record is not a fixture response or a transport receipt.

Public immutable read plan contains only project identity, local alias, prepared/start-expiry timestamps, New York date, fixed paper origin and the bounded continuation algorithm. Preserve60second start expiry,30second packet deadline,10second request cap,13GET maximum,25orders/page and8pages. No public account UUID, arbitrary route/method/filter/body or write scope. Unknown account identity is allowed only on the initial ACCOUNT request and reported privately as discovered/unconfirmed. Later requests require that private ID and pinned credential envelope; no invented identity. Use actual dispatch timestamps, not plan creation timestamps.

Reuse existing account/clock/calendar/list field parsers without constructing inert PaperRequest/PaperResponse wrappers. An execution-owned secrecy gate must run before any parser-generated hashes: check raw and JSON-decoded keys/values, including unknown fields, for credential reflections. Malformed bodies fail with fixed errors and no raw/digest persistence. Parsed raw data/accountID remains private, redacted in repr and denied pickle; public summaries use alias and omit account UUID. Parsing does not establish account intention, ownership, atomicity, economic completeness, flatness or financial authority.

This component prepares the exact route/response boundary. A subsequent packet driver must enforce request order, bound cursors to previous full pages, pin credentials, count attempts, stop on incomplete eight-page coverage, check final freshness and preserve private evidence through the protected store. Native owner/grant integration follows; real approval is requested only after offline preparation is reviewable.

- [x] Fresh64MiB namespace and red tests.
- [x] Immutable alias-only plan/requests and private parsed responses with execution-owned secrecy.
- [x] Native synthetic credentials, malformed/reflected data, schema/time/context denial; no account/transport calls.
- [x] Independent review, paired source/package verification, reproduction, receipts and checkpoint.
