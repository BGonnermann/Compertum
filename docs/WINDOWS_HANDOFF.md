# Windows handoff for local Codex

Repository: https://github.com/BrennanCompertum/Compertum

Checkpoint branch: `codex/m0-bootstrap`. The default `main` initially contains starter documentation, not this implementation. Use the actual checkpoint branch head; do not assume a ZIP's historical local commit is the GitHub commit.

## Establish the source before changing it

1. Inspect the existing `C:\Users\bgonn\Desktop\Compertum` folder read-only: guidance, Git status and recent commits, existing M0 acceptance report and current source. Its earlier 67 tests belong to the original project. Do not delete, reset, migrate, overwrite or import its runtime state.
2. Fetch the selected private repository through existing local Git authentication. Verify `origin`, the checkpoint branch/head and the tracked files. If the existing folder is already a clean checkout of that branch, it may be used. If its history/source differ or local changes would be overwritten, use an isolated clean checkout or worktree beside it. Do not force unrelated histories together or copy the old implementation over the checkpoint.
3. Read `AGENTS.md`, `docs/CLOUD_HANDOFF.md`, `docs/BUILD_SPEC.md`, `docs/M0_IMPLEMENTATION_PLAN.md`, `reports/M0_BOOTSTRAP.md` and `reports/M0_TASK2.md`. The original specification/plan and lock remain preserved. Detailed cloud receipts, wheels and original local history remain in the saved `Compertum_M0_Checkpoint.zip`; they are not tracked in this checkout.

## Resume M0 on native Windows

- Verify native Task 1 first: current Windows/interpreter capabilities, fresh project environment, locked third-party wheels, actual imports and a second clean reproduction. Keep Python 3.14.7 as the target; do not silently install a replacement interpreter, change the lock or build third-party source. A cloud wheel-resolution preflight is not native installation evidence.
- Rerun the existing portable source tests and the installed-wheel contract/config checks against the locked clean environment. Record measured results and hashes. Historical cloud counts are 68 source checks and 58 installed-wheel checks. No skip or copied receipt establishes native acceptance.
- The existing environment-verification helper emits `VERIFIED_CLOUD_IMPORTS` and native validation `UNVERIFIED`. Do not rename that output into a native pass. Verify the actual required observations and record new native receipts; any helper adjustment must retain honest environment-specific evidence.
- Implement Task 3 using real Windows canonical identity, exclusive owner handles and authenticated named pipes. Run its simultaneous-start, live-owner, prior-exit, spoofed-peer, wrong-role/generation and request-replay fixtures. Complete a focused independent review and repairs. Task 4 stores or actual workers must wait for the native Task 3 gate.
- Continue Tasks 4-9 in dependency order once their prerequisites pass. Do not pause between passing tasks for routine confirmations. Record a concrete unavailable/failed gate and continue only work that does not depend on it. Keep M0 incomplete until every required acceptance gate passes.

## Ownership and operating limits

Local Codex becomes the implementation owner when it begins this Windows handoff. Cloud work reviews pushed commits and helps with design/research; do not run simultaneous writers on this branch. Publish each reviewed M0 task and a brief measured status so both sessions can identify the same commit.

Spending remains $0 and all documented resource/storage/AI limits remain fixed. No administrator/OS security/power changes, drive migration, Strata restart/reconfiguration, broker credentials, trading, market-data collection, M1-M6, training or AVO/RSI/DREAM work. M0's existing proposal-only AI qualification is allowed only after the final wrapper limits and recorded budgets are verified. No unattended service is enabled.

Report briefly: completed task, native measurements, exact unresolved gate and next dependency. Engineering completion never implies strategy acceptance.
