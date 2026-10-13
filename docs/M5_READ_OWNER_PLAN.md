# M5 native read-owner integration

11 October 2026. Autonomous offline implementation; no real credentials or external account calls. Preserve all earlier receipts. The actual account-read scope remains ungranted.

- [x] Execution-owned read controller: exact native operator/owner/plan/credential/storage bindings, <=60 second start grant, consume durably before GET, idempotent retries and no restart replay.
- [x] Cooperative fixed-origin GET sequence: health/durability before each step, packet deadline, cancel and barrier behavior, sanitized HTTP status/correlation receipts.
- [x] Opaque evidence transfer: bounded chunks, exact sequence/context/hash, retained ciphertext until verified durable publication acknowledgment; reserve 3 MiB first.
- [x] Connect existing managed owner and authenticated supervisor controls; no supplied URL, headers, account UUID or clock.
- [x] Independent review, repair, paired source/wheel checks and genuine native loopback/restart reproduction. Label simulated reserve tests separately from actual 1 GiB native reserve checks.

Small tests use .cache/test-runs/m5-read-owner-20261011-01 (64 MiB admitted). Separately admit each full supervisor fixture before allocating its 1 GiB journal reserve. Serialize full fixtures, archive verified passing scratch before cleanup; preserve failure evidence. Keep the original checkout, interpreter, lock, financial gates and Strata untouched.

Assumption: cancellation stops further GETs and retains an incomplete read receipt; account identity remains unconfirmed and every financial acceptance flag remains false. The real read grant must come from the authenticated operator, never a fixture receipt, historical evidence or public payload claiming health.

Verified closeout: reports/M5_READ_OWNER.md and artifacts/m5/read_owner.json. 746 matching passes per lane, one nonapplicable skip each, independent review closed3/3. Actual1GiB native reserve and separate-process loopback/restart/cancellation passed.
