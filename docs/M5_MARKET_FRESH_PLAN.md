# Private fresh asset and quote producer

12 October 2026 UTC. Authorized offline M5 continuation. Implement one execution-owned ASSET then QUOTE pair using the existing frozen OperationalMarketPlan, request schemas and semantic validators. No actual credentials, external/account calls, new grant or financial acceptance.

- [x] Tests first: native exact route/provenance, immutable context, raw/privacy checks, two-request sequencing, timing/freshness, cancellation/revocation and incomplete results.
- [x] Missing fixed paper-origin ASSET GET; narrow existing market-exchange adapter selection/provenance. Existing data-only, generic GET and order endpoint policies stay intact.
- [x] Private producer: one pair per owner, one pending request, two attempts maximum; ten seconds per request and twenty seconds total including setup/validation; no retry. Owner-observed pre-send/receipt/validation, clock regression rejection and fixed errors.
- [x] Independent review at most three passes; repair/reproduce; frozen source/package checks, exact replay and resource receipt.

Fresh asset/quote requests may follow 09:25 on the plan's session day. They do not revise or fetch historical features. Recalculate asset/quote validity from exact original responses at each private diagnostic access; keep 30-second exact-nanosecond tests and future/invalid quote checks. A private view is point-in-time evidence with its observed timestamp, never continuing freshness or authority. Keep HISTORY_MISSING and all other existing deficiencies. Preserve safe partial replies; refuse generated secret reflection before exposing diagnostics. Retain at most two 64 KiB replies and a 512 KiB private serialized view. No public worker/retrieval/journal path.

Twenty-second pair budget and private bound are conservative engineering choices. Same-plan composition with qualified frozen history, the shared 100/minute service queue and priority/retry policy, actual read permissions, account/risk/economic checks and M5 acceptance remain downstream. Independent design inspection by /root/paper_contract_review informed this scope.

Verified in artifacts/m5/market_fresh.json. Reviewed plan identity is retained in the receipt; completion marks added afterward.
