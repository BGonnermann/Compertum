# Durable market-input lineage

14 October 2026. Required local dependency after verified market-owner integration. The owner's autonomous implementation direction covers this work. Actual account or order authority remains separate.

## Outcome and decisions

Retain the exact HISTORY source, FRESH ASSET/QUOTE responses and composed diagnostic used in one calculation, with the original grant, producer, subject, project, alias and credential bindings. A reader must reconstruct the diagnostic from those original bytes. Reopening always returns historical evidence and never creates a current view, grant, freshness assertion or order authority.

Use a separate versioned private lineage contract and purpose-prefixed publication record. Existing collection schemas and FRESH v1 grants stay readable and unchanged; those grants intentionally have no evidence reservation. Reuse the current owners, reservation ledger and encrypted transfer. Do not introduce another owner, database, journal, transport or request to a provider.

Capture composition and its underlying FRESH bytes in one operation. Reading FRESH a second time can change age fields and produce a different hash. Preserve the coherent original snapshot, original HISTORY metadata and publication manifest. Reference the existing HISTORY artifact instead of duplicating its near-limit payload. Reconstruction requires separately reopened, verified history originals. Retain the exact elapsed-clock observation used to compute MAX_WALL_MONOTONIC age, so a reader can check clock agreement and chronology. Check all bindings again after calculation and secret scanning, as the existing composition does.

Publication is an explicit operation. Status and compose remain read-only. The coordinator supplies a genuine reservation; execution captures and encrypts, then existing bounded transfer and exact ledger-linked acknowledgement publish it. Repeated requests must return the same identity. Lost acknowledgement retains the manifest. Restart never recollects data or restores live authority.

## Checklist and acceptance

- [ ] Immutable private capture and strict versioned validation. Reconstruct request/reply diagnostics, FRESH age qualification and combined diagnostic. Bind original grants and history publication. Reject context/hash substitution, altered originals, malformed clocks and secret reflection.
- [ ] Reserved encrypted publication and historical reopening. Keep 32 KiB chunks, the existing 3 MiB ciphertext ceiling and bounded scanned public summaries. Reject ignored writes, corrupt chunks, incorrect manifests and uncertain cleanup. Preserve idempotency and terminal history.
- [ ] Owner routing and recovery. Explicit publication only; preserve account priority, quotas, original deadlines, one producer, health and checkpoint rules. No new HTTP requests.
- [ ] Source/package tests, actual native restart/lost-ACK scenario and independent review. Keep collection compatibility and accurate provenance labels. At most three evidence-led repair/review iterations for this increment; preserve failures.
- [ ] Update checkpoint/README and publish verified implementation to the primary repository.

Validation proceeds from focused schema/capture tests to publication/owner tests, then frozen source/package regression groups and a bounded native fixture. Tests use invented credentials and loopback data. Keep memory admission, one-heavy-job exclusion, 120-second job deadline and storage budgets unchanged. Stop dependent work for unavailable authority, genuine external blockers or the recorded iteration bound.

The first increment factors the existing composition capture without changing its public result. A separate strict inert schema binds both original grants, producer instance/generation, history manifest/snapshot, exact FRESH bytes and composed diagnostic. Validation rebuilds request/reply diagnostics and mathematical qualification, including stale-data results. Tests must reject changed originals even when outer hashes are recomputed. Historical producer assertions do not establish native authentication.

Release07 market-owner closeout is independently CLEAR3/3 and published as `1dfe14fc93ee52d0d39d39a04a4e5a4d2b0e8126`; master, primary GitHub and the requested clone matched.

Capture foundation is verified in both environments:225 matching cases, zero failures/errors/skips, both complete environments qualified,521 frozen inputs/199 modules. Both review regressions were reproduced and corrected; all failing evidence is preserved. The public FRESH/composition shapes are unchanged. Final aggregate review3/3 is CLEAR. See [the foundation report](../reports/M5_MARKET_LINEAGE_FOUNDATION.md).

Exact next action: publish the verified foundation, then complete [original consumption evidence and owner-bound capture](M5_MARKET_CONSUMPTION_PLAN.md). Encryption, reservation/publication and lineage restart/ACK integration remain pending. Each dependency is verified as a bounded increment; none substitutes for complete durable-lineage acceptance.
