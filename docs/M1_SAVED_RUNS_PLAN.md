# Saved synthetic runs

Owner authorized autonomous continuation on9October2026. Use executing-plans/test-first workflow, primary implementation and one bounded independent reviewer. Default at most3 review/repair rounds. No commits or publishing.

Goal: save immutable synthetic baseline inputs and six predeclared H/cost results; pause, resume, stop and restart without replacing evidence or duplicating accepted work. Library plus bounded native process verification, not a background service or financial acceptance.

Design: new compertum.simulation.runs.SavedRuns uses the existing coordinator-owned StateStore and StorageManager. No new DB owner or unguarded artifact writer. Inputs include validated snapshot chunks, sectors, dates, fixed H1/5/21 and10/20bp units, package/environment/lock identities. Run ID is a UUID. Create registers before publishing; attempt records precede computation. Immutable outputs live under artifacts/runs/RUN_ID. New source or input identity requires a new run.

Checkpoint granularity is one complete replay, not one trading session. This preserves the verified pure engine and makes each admitted step a bounded foreground unit. Control commands apply only between units; the interface does not claim immediate intrareplay cancellation. No background scheduler, public production CLI or broker capability is added. Native verification uses separate short-lived owner processes with frozen synthetic inputs.

States: PREPARING -> PAUSED -> READY -> RUNNING -> READY/COMPLETED. Pause READY -> PAUSED; resume PAUSED/INTERRUPTED -> READY after verifying all evidence; stop any inactive nonterminal state -> STOPPED, never resumable. An owner restart turns orphan RUNNING/PREPARING into INTERRUPTED/FAILED; never automatically executes. Every control has an idempotent UUID and exact-action binding. COMPLETED/STOPPED are terminal. Status reports counts/evidence, not just filenames.

Retry policy correction: at most two attempts for each fixed replay. I/O interruption or abrupt owner loss permits explicit resume; deterministic data/budget errors and unknown computation exceptions are terminal FAILED. No automatic retry or parameter change is admitted. See reports/M1_RUN_POLICY.md for fresh verification; older stage receipts remain historical.

Atomicity: retain immutable input/result artifacts via existing bounded writers. Commit accepted unit and next checkpoint in one SQLite transaction only after verifying artifact bytes. A crash before that commit leaves an interrupted attempt; preserve any published orphan and retry the same unit with a new attempt filename. Never adopt an orphan as success. Verify hashes/lengths through bounded reads on every resume and before advancing. Detect changed package/interpreter/dependency/lock identity. Stop can preserve a corrupted run without reading or executing it.

Bounds: input snapshots retain64chunks/16MiB cap; aggregate bundle max20MiB; each output max16MiB. Run artifact budget immutable, <=128MiB; default64MiB. Count failed/abandoned reservations and retries. At most2 attempts/unit,128runs and128control receipts/run, bounded journal. The two-attempt cap follows BUILD_SPEC section6. No arbitrary supplied code, paths, SQL, shell, model or network input. Secrets must not enter errors or logs.

- [x] Tests first: paused startup, exact six outputs, idempotent create/control, immutable budget, stop terminal, input/output corruption, code mismatch, owner-release rejection, interrupted publish and retry, bounded reads and attempts.
- [x] Implement SavedRuns with native ownership, immutable artifacts, journal/checkpoint and conservative recovery.
- [x] Native separate-process restart/pause/stop evidence; compare interrupted/resumed outputs with uninterrupted pure replay. Run focused source and installed-wheel checks and repair reviewed findings.
- [x] Retain result/JUnit/logs/identity/archive; update roadmap, handoff/progress and concise report. Keep M0, data and baseline receipts intact.

Validation uses fresh .cache/test-runs/m1-saved-runs-20261009-01 paths and existing allowlisted runner. No full-reserve recovery fixtures. Preflight headroom >=256MiB; all category caps unchanged. Financial/M1 acceptance remains incomplete until remaining operator integration, predictive metrics and authorized real-data evidence exist.
