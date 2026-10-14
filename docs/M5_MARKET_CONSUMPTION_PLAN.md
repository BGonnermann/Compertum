# Market grant consumption and owner-bound capture

14 October 2026. Next local lineage dependency after the capture foundation. This increment uses invented credentials and loopback fixtures only. The owner authorized continuing the roadmap; no new account, provider or order action is included.

Save the UTC and monotonic observation at consumption, tied to the exact original grant. Grant v1 and job v1 remain unchanged. Use a bounded, immutable purpose-prefixed record in the existing execution state table, committed in the same transaction as the original job's irreversible consumption. Verify both writes before constructing a producer. Recheck the original exclusive 60-second clock predicate immediately before the transaction; never infer consumption from later producer construction.

An internal capture entry point accepts the trusted subject, job ID and expected grant hash. Resolve both original job records and consumption proofs internally. Require the current completed FRESH producer, its original published HISTORY, exact context, live health and credential binding. Bind both proofs separately around the existing inert lineage schema. Recheck records and context after capture. Historical HISTORY may come from a prior generation; its proof binds that original generation. Capture adds no request or reservation.

Old records without consumption evidence stay readable. They cannot satisfy the new evidence claim. Do not backfill times, replay requests, resume interrupted identities or restore freshness on restart.

Checklist:

- [x] Strict bounded consumption schema and immutable storage, with atomic consumption before construction.
- [x] Internal owner-bound capture and historical reconstruction with exact original proofs.
- [x] Regression tests for clock boundaries/delays, ignored writes/rollback, constructor failure, repeated start, substitutions, missing proofs and restart.
- [x] Frozen source/package compatibility checks and final independent review3/3 CLEAR; publish this verified checkpoint.

Use the existing native test runner: exact frozen selections, 120-second jobs, 4 GiB memory, four CPUs, one heavy job, host admission16 GiB/stop12 GiB, current category caps. Preserve every failed case and exact source iteration. At most three evidence-led review/repair iterations for this increment. Encryption, coordinator reservation/publication, chunk transfer and lost-ACK integration follow this dependency and are not accepted by these checks.

Exact next action: publish the independently reviewed291-case paired checkpoint, then proceed to [encrypted publication and recovery](M5_MARKET_LINEAGE_PUBLICATION_PLAN.md). The initial45 missing-feature failures and five reproduced cleanup regressions remain preserved. Both full environments qualified; release09 binds525 inputs/201 modules.
