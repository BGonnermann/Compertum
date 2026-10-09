# Windows verification handoff

Repository: https://github.com/BrennanCompertum/Compertum

The foundation and Task 3A/3B checkpoints are merged into `main`. Task 3C is developed on `codex/m0-worker-bootstrap` and merged after cloud review; use the actual published `main` head after that merge. The older branches remain historical checkpoints. Use the actual Git head, not a ZIP's historical local commit. The owner reassigned implementation to this cloud session on 8 October 2026 and authorized reviewed merges. Local code edits are paused; this document describes verification on the home PC.

## Establish the source before changing it

1. Inspect the existing `C:\Users\bgonn\Desktop\Compertum` folder read-only: guidance, Git status and recent commits, existing M0 acceptance report and current source. Its earlier 67 tests belong to the original project. Do not delete, reset, migrate, overwrite or import its runtime state.
2. Fetch the selected private repository through existing local Git authentication. Verify `origin`, the checkpoint branch/head and the tracked files. If the existing folder is already a clean checkout of that branch, it may be used. If its history/source differ or local changes would be overwritten, use an isolated clean checkout or worktree beside it. Do not force unrelated histories together or copy the old implementation over the checkpoint.
3. Read `AGENTS.md`, `docs/CLOUD_HANDOFF.md`, `docs/BUILD_SPEC.md`, `docs/M0_IMPLEMENTATION_PLAN.md`, `reports/M0_BOOTSTRAP.md`, `reports/M0_TASK2.md`, `reports/M0_TASK3A.md`, `reports/M0_TASK3B.md` and `reports/M0_TASK3C.md`. The original specification/plan and lock remain preserved. Detailed baseline cloud receipts, wheels and original local history remain in the saved `Compertum_M0_Checkpoint.zip`; they are not tracked in this checkout. That ZIP predates Task 3A.

## Resume M0 on native Windows

- Verify native Task 1 first: current Windows/interpreter capabilities, fresh project environment, locked third-party wheels, actual imports and a second clean reproduction. Keep Python 3.14.7 as the target; do not silently install a replacement interpreter, change the lock or build third-party source. A cloud wheel-resolution preflight is not native installation evidence.
- Rerun the portable source tests and installed-wheel contract/config/runtime checks against the locked clean environment. Record measured results and hashes. Current cloud measurements are in the stage reports. No skip or copied receipt establishes native acceptance.
- The existing environment-verification helper emits `VERIFIED_CLOUD_IMPORTS` and native validation `UNVERIFIED`. Do not rename that output into a native pass. Verify the actual required observations and record new native receipts; any helper adjustment must retain honest environment-specific evidence.
- Candidate ownership, pipe-inspection and private-bootstrap fixtures are available. After native Task 1 is established, run the explicit fixture entry point from a qualified project environment:

```powershell
.\.venv\Scripts\python.exe -B tools\verify_native_ownership.py --suite all --run-fixtures
```

- The entry point uses existing dependencies only and creates small, unique project-local fixture/evidence directories. Without `--run-fixtures` it performs no fixture writes. In Linux it exits 3 with `NATIVE_WINDOWS_UNAVAILABLE`, never a native pass. Read the output's exact counts/status and retain its `result.json`/JUnit/log directory. Any skip or failure keeps the ownership fixture suite unverified. Even a successful fixture suite leaves Task 1, full Task 3 and M0 unverified/incomplete; do not mistake exit 0 for milestone acceptance.
- `--suite all` now includes at least 30 native fixtures; `--suite bootstrap` isolates the ten new bootstrap checks. Any skipped/failed native fixture remains unverified. The bootstrap launches only trusted bounded test helpers using an explicit inherited handle list. It passes no capability in arguments, environment, metadata or output.
- Named-pipe/bootstrap inspection source is available, but native behavior remains unverified. Known enrolled workers receive scoped inspection rights; unregistered worker claims, operator impersonation and revoked capabilities are refused. Effectful requests remain disabled. Full Task 3 needs remaining native lifecycle checks, registration between separate owner processes and later durable replay integration. Task 4 stores or actual workers must wait for their prerequisites. No production launcher or Job limits are established here. Cloud implementation continues from measured receipts; the PC does not modify source in parallel.
- Continue Tasks 4-9 in dependency order once their prerequisites pass. Do not pause between passing tasks for routine confirmations. Record a concrete unavailable/failed gate and continue only work that does not depend on it. Keep M0 incomplete until every required acceptance gate passes.

## Ownership and operating limits

Cloud source development is the sole implementation writer under the latest owner decision. The home PC runs bounded verification and returns its measured report; local Codex may inspect/run it without making source changes. Do not run simultaneous writers. Every reviewed source stage uses an explicit GitHub commit and a brief measured status.

Spending remains $0 and all documented resource/storage/AI limits remain fixed. No administrator/OS security/power changes, drive migration, Strata restart/reconfiguration, broker credentials, trading, market-data collection, M1-M6, training or AVO/RSI/DREAM work. M0's existing proposal-only AI qualification is allowed only after the final wrapper limits and recorded budgets are verified. No unattended service is enabled.

Report briefly: completed task, native measurements, exact unresolved gate and next dependency. Engineering completion never implies strategy acceptance.
