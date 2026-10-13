# Provider diagnostic saved runs

Extend existing SavedRuns, worker input decoding and result binding for an explicit provider-diagnostic input kind. Preserve synthetic schemas and default results, controls, owner identity, budgets, two-attempt limit and immutable history. This is the next authorized dependency after the pure real replay receipt.

- [x] Add tests for create/idempotency, exact result resume, pause/stop, input corruption, schema/result kind separation and native owner restart.
- [x] Retain provider evidence envelopes and scenario in the existing20MiB input artifact; rebuild/verify the provider snapshot in each worker. Record the diagnostic kind in durable state; never pass it through synthetic admission.
- [x] Use the same unit schedule and trusted computation for synchronous steps and native workers. Only explicit provider result headers are accepted for that run kind. No prediction reports or real financial seal are inferred.
- [x] Run focused source/wheel/native lifecycle tests and a retained real input fixture; outputs match the pure replay hashes. Reserve64MiB per verification lane and retain all failures and orphan receipts.
- [x] Independent review, update roadmap/checkpoint and issue M1 gate ruling. Then continue independent M2 mathematical contract work while remaining financial data gaps are recorded.

No broker, account, protected-market outcomes, spending or publishing. No changes to the original checkout or Strata. Real fee billing, action completeness and historical operational eligibility remain unresolved; diagnostics cannot authorize a strategy.
Verification completed: see artifacts/m1/provider_saved_runs.json and reports/M1_PROVIDER_SAVED_RUNS.md. Full financial M1 remains incomplete.
