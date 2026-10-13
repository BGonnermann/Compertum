# Saved synthetic runs verified

9 October 2026. Saved-run component verified; full M1 remains incomplete.

The coordinator now retains immutable inputs, records attempts before computation and checkpoints each complete baseline replay. Runs start paused. Resume verifies input/output hashes plus package, Python, dependency and lock identities. Stop is terminal. Commands have idempotent UUID receipts. A new owner marks interrupted work conservatively and never resumes it automatically.

Checkpoints and controls operate between complete H/cost replays. This is an owner-backed library, not a production CLI, background service or immediate mid-replay cancellation facility. It does not alter existing supervisor controls.

## Fresh checks

| Check | Pass / fail / skip |
| --- | --- |
| Source plus data/baseline/contracts/config regressions |139 /0 /0|
| Installed-wheel saved/data/baseline tests |81 /0 /0|
| Native Windows restart/stop tests, source |4 /0 /0|
| Native Windows restart/stop tests, installed wheel |4 /0 /0|

Three separate-process crash cases cover exit before calculation, after durable output publication, and after file flush/fsync but before SQLite records written bytes. Each resumed run matches all six uninterrupted replay outputs exactly. Orphans remain intact; one unit receives two attempts but only one accepted result. Pause survives process replacement; stop survives a new owner without new work. The fourth native test verifies terminal stop. Source/wheel comparison checks18 unique recovered result files, excluding pytest's current-directory aliases.

Tests also verify changed code refusal, corrupt input/result refusal, owner release, immutable aggregate budgets, duplicate control conflict and bounded reads. Native tests use actual Windows leases/SQLite/process exits, not mocked restart receipts. This stage originally allowed three attempts. The current cap is two, corrected against BUILD_SPEC section6; see [policy correction](M1_RUN_POLICY.md). The original stage receipt and archive remain unchanged.

Independent review found two defects. Startup could re-save a damaged checkpoint with a new hash; it now verifies before any recovery mutation. Abandoned grants could undercount bytes written before a counter commit; their full allowance now stays charged. Both retained regressions failed before repair and pass afterward. Review cleared the repairs. No limits were weakened.

## Environment and evidence

Checkout `C:\Users\bgonn\Desktop\Compertum-development`, repository `https://github.com/BrennanCompertum/Compertum`, branch `local/m0-development`, published base `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781`. New code remains uncommitted/unpublished. Windows11 Home x64 build26300; Python3.14.7 and unchanged39-package environment. Local wheel built and installed offline/no-deps; prior wheels retained.

- Source: `src/compertum/simulation/runs.py`.
- Plan: `docs/M1_SAVED_RUNS_PLAN.md`.
- Receipt/review: `artifacts/m1/saved_runs.json`, `artifacts/m1/saved_runs_review.json`.
- Evidence: `.cache/test-runs/m1-saved-runs-20261009-01/`, including four final JUnit files, failed regressions, exact command receipts/logs, per-process stdout/stderr/exit codes, preserved fixture databases/artifacts, environment comparison, source archive and final storage measurements.
- Public library: `SavedRuns(storage).create/status/control/step`; caller must hold the existing live coordinator StorageManager. A step computes one of the six fixed replay units. No arbitrary code or network destinations are accepted.

Original project/runtime, M0 and previous M1 receipts/source archives are unchanged. No full-reserve fixture, Strata/model request, real data, account access, trading, spending, training, protected evaluation or publication. Storage stays inside unchanged category caps.

Next offline work: baseline prediction-error reporting. Operator-facing supervised integration and real-data/financial acceptance remain separate unfinished work.
