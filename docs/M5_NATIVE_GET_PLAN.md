# Native cooperative GET backend

11 October 2026. Authorized offline preparation only. No real credential/account requests, public paper CLI, financial grants, second journal, dependency changes or external service. Native verification uses an ephemeral127.0.0.1 HTTP fixture, invented headers and fresh64MiB test namespace. Existing source snapshots remain immutable.

Implement private runtime/_winhttp_get.py as one bounded async WinHTTP GET operation attached to an existing execution lease. It is a low-level backend, not an account authorization interface. A later fixed-paper-origin, scoped-grant factory must own every real call. No arbitrary transport arguments will be exposed through an owner command. Tests may call the private backend directly against loopback.

Use pointer-correct WinHTTP ctypes bindings, async/secure session defaults, explicit no-proxy, no automatic redirects/authentication/cookies, bounded headers and identity-only body. The callback only records bounded completion events; owner poll drives receive/read. Total monotonic deadline covers all stages. Read at most64KiB plus one overflow byte, require EOF for exact-cap success, reject late success. Retain callback/read/header memory through HANDLE_CLOSING; clear sensitive owned header buffers before release. Owner close cancels the child request before parent handles, waits a bounded interval and refuses uncertain cleanup. Fixed error codes contain no raw URL/headers/body/native exception text.

- [x] Admit namespace; expected red tests.
- [x] Native async start/poll/cancel backend; existing owner revocation.
- [x] Native loopback success, exact-cap/overflow, slow/stalled cancellation/deadline, redirect/auth/compression rejection and header behavior; failure injection for setup/cleanup.
- [x] Independent bounded review; source/installed wheel, exact semantic reproduction, package/storage/checkpoint receipts.

Follow-on dependencies: fixed paper GET grant/route factory and account-ID bootstrap without inventing identity; response reflection secrecy; protected local provisioning/store; owner start/poll/cancel integration with health/storage; only then actual read authority. Real TLS endpoint/account compatibility remains unverified by loopback tests.
