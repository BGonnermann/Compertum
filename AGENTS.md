# Compertum

Implement M0 only under the user's 8 October 2026 authorization. Read docs/BUILD_SPEC.md v1.1 and docs/M0_IMPLEMENTATION_PLAN.md. Primary agent owns implementation, repair, and integration; use one bounded independent reviewer for Task 9.

Keep new spending at $0. No broker credentials, authenticated market data, broker transport, real protected data, M1, API configuration, administrator elevation, or external repository. Preserve Strata's files/environment/configuration/server.

Record progress in artifacts/m0/progress.jsonl and verification receipts. Run meaningful task checks before dependencies. Native failures/skips stay unverified. Do not change interpreter or weaken limits without a concrete decision. Project files remain within the documented 50 GiB category budget; test scratch stays in a fresh checked .cache/test-runs namespace. Secrets and role capabilities never enter logs or commits.
