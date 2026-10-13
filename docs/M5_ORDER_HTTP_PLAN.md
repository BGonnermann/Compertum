# Native order HTTP backend

11 October 2026. Required offline M5 preparation under autonomous roadmap authority. Bounded extension of the existing native GET lifecycle. No real keys, account calls, public write controls, spending or authority grants.

Reuse one native async lifecycle for buffers, deadlines, owner cancellation and handle closure. Keep the existing GET interface and behavior. Add a private fixed-paper-origin backend with only POST /v2/orders, DELETE /v2/orders/{id}, GET by order ID and GET by stable client ID. Reuse the inert request shape validators; the wire projection carries no synthetic authority or account identity. No arbitrary URL/method/route or bulk close. Whole shares, market/limit, day and extended_hours=false remain unchanged.

Retain an owned bounded request buffer through HANDLE_CLOSING, including cancellation and uncertain cleanup. No retry. Preserve numeric HTTP status on errors. Successful submit200 and cancel204 are transport observations only. Error replies remain bounded private bytes, never a confirmed financial effect. Qualifying actual replies and consuming durable plan authority are dependent components, not inferred here.

Acceptance and checklist:
- [x] Admit64MiB namespace, retain expected red tests.
- [x] Native exact method/path/canonical-body checks; owner release, timeout, disconnect, redirect/auth denial, no repeat, bounded body and cancellation-buffer lifetime.
- [x] Existing GET/read-owner regression checks remain valid.
- [x] Independent review, at most3passes; source/package identity and matching applicable test IDs; retained failed evidence and durable checkpoint.

Official interfaces checked11October2026: https://docs.alpaca.markets/us/reference/postorder documents POST200 and stable client ID; https://docs.alpaca.markets/us/reference/deleteorderbyorderid-1 documents individual DELETE204/422. https://learn.microsoft.com/en-us/windows/win32/api/winhttp/nf-winhttp-winhttpsendrequest requires optional request bytes to remain alive through receive completion or request closure. Keep them until verified native closure.

Assumption: this private low-level backend is not an operator capability. The eventual execution-owned factory must enforce exact account/credential/plan/health/storage/supervision before each call and consume durable intent before a write. Existing paper.arm/start/cancel/close remain unavailable throughout this component. Loopback proves native transport behavior only; real Alpaca TLS/account compatibility remains untested.

Verified receipt: artifacts/m5/order_http.json.795matching applicable passes per lane; full native read regression passed.
