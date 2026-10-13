# Shared native service admission

12 October 2026 UTC. Authorized offline M5 engineering. One private execution-owner queue, native commit gate and producer waiting. No new request authority, retries, real service calls, deployment or changed financial acceptance.

- [x] Owner-lifetime anchor and queue, independent DATA100/PAPER100 sliding-minute budgets, bounded single-use tickets, reconciliation priority and FIFO.
- [x] Claim before producer attempt/preparation; ordinary waiting preserves current task/grant/cutoff deadlines. Native commit immediately before potential send counts uncertain attempts without refund.
- [x] Direct native calls use the same gate; startup fence and queue recreation cannot reset capacity. Revocation/cancellation/uncertain cleanup remain safe.
- [x] Explicit loopback-only synthetic clock fixture, same gate; production TLS rejects that queue before native setup. Exact 60s-1ns/60s boundary and clock regression checks.
- [x] Independent review up to three passes, source/package regressions and replays, resource receipts and roadmap update.

Queue attaches once to execution owner state; owner acquisition records monotonic start. First readiness at acquisition+60 seconds; no automatic task or old-ticket restoration. Closing a producer cancels its ticket, never the shared budget. Closing/poisoning queue cannot create a replacement within the same owner. Bounded 16 queued tickets and at most one claimed permit. Sliding windows use integer nanoseconds and count immediately before potential native SendRequest; no refund after uncertain send. Existing global four/native one-per-owner concurrency and cleanup retirement remain independent constraints.

Priority: account/order reconciliation before fresh inputs, then historical ingestion, then unclassified direct calls; FIFO within priority among currently eligible services. PAPER100/min is a conservative local ceiling, not a provider entitlement; DATA100 follows BUILD_SPEC. Service/type comes from validated native adapter/request and authenticated producer type, not caller service strings. Permits carry no credentials or body and grant no endpoint/account/financial rights.

Collection/fresh dispatch returns a private WAITING outcome while retaining READY; read-owner tick returns cooperatively. Claim occurs before request IDs, exchanges, packet issue or durable request rows. Existing 80/20/30-second bounds and history cutoff continue. Actual native timeout stays real even for synthetic queue fixtures. Direct constructors perform one immediate claim and statically refuse if waiting, before native handles; they cannot jump ahead of queued reconciliation.

The private fixture installer may run only before an owner has any queue. Its queue permanently allows only loopback. It accepts a clock but no fence bypass or arbitrary start anchor; tests advance exactly 60 seconds before constructing normal fixtures. Dedicated boundary tests exercise the unchanged fence, counting and native commit. No production environment switch/launcher flag.

Preserve Retry-After observations. Full 1/4-second delays, three-attempt read lifecycle, durable error evidence, POST no-retry and uncertain-write reconciliation schedule remain separate requirements, not acceptance claims of this increment. No sleep inside owner/native constructors or heartbeat handlers. Primary integration stays serial; /root/paper_contract_review supplied bounded design inspection.

Verified in reports/M5_SERVICE_BUDGET.md and artifacts/m5/service_budget.json. The review receipt pins the pre-completion checklist hash.
