# Private paper order qualification

Required next offline M5 component after native order HTTP verification. The primary owns source changes; one independent reviewer, at most3review/repair passes.64MiB fresh admitted test namespace. No real keys/account requests, operator write routes, new journal, or synthetic authority.

Create immutable execution-private request context for submit, individual cancel, and order/client-ID lookup. Pin native project/owner generation, private account UUID, credential-envelope hash, local request ID, existing durable intent reference and exact validated method/path/body. Reuse paper_contracts.order_body and native _wire projection; omit actual account UUID from public content. Plan/grant/health/expiry consumption belongs to the later owner integration and remains explicit, unavailable authority here.

Qualify replies within existing native execution ownership. Validate the exact request and credential context; reject credential reflections in raw bytes, decoded JSON and canonical metadata before hashing or retention. Success200 uses existing paper_responses._order identity/quantity validation. Cancel204 requires empty body and remains request-accepted/unconfirmed.404,422,5xx and missing status remain unconfirmed, never absence, retry authority or final cancellation. Require bounded64KiB raw reply and a0-10second request interval; preserve exact raw bytes privately after qualification. Non-JSON errors are refused with fixed safe reasons; numeric HTTP status belongs to the transport receipt and must survive qualification failure.

Private results cannot be directly constructed as accepted evidence or pickled. Native owner release/context mismatch blocks further qualification. Public receipt contains only local alias/request/intent references, fixed outcome, sanitized timing/status and validated order observation; actual account UUID and secret reflections are rejected. Raw/private values never enter logs. No account identity is inferred from an order response, whose account association remains a private request context.

Acceptance:
- [x] Native synthetic credential-context tests; request shape/immutability and public privacy.
- [x] Exact submit/lookup binding, mismatch/late/oversize/duplicate-JSON rejection,204empty and uncertain404/422/5xx semantics.
- [x] Raw and escaped/base64 secret reflection rejection, private account reflection rejection, owner/context revocation.
- [x] Independent review; paired source/package regressions and deterministic qualified receipt reproduction; source/wheel hashes and durable checkpoint.

After this component: durable native write admission and incident reconciliation within the existing execution store, followed by paper-aware recovery and M6 session evidence. These dependencies are not completed by a valid request/reply record.

Verified: artifacts/m5/order_qualification.json and reports/M5_ORDER_QUALIFICATION.md.855matching passes per lane, independent review closed1/3, seven exact reply records.
