# Windows verification handoff

Repository: https://github.com/BrennanCompertum/Compertum

The foundation and Task 3A–3D checkpoints are merged into `main`. The first native run at `68f9643cc591b7a3ab3307f3351fae324b4fd729` failed; see `reports/M0_NATIVE_REPAIRS.md` for the operator summary, repair scope and remaining evidence request. Use the actual published repair commit for a new isolated run after publication. Older branches remain historical checkpoints. Use the actual Git head, not a ZIP's historical local commit. The owner reassigned implementation to this cloud session on 8 October 2026 and authorized reviewed merges. Local code edits are paused; this document describes verification on the home PC.

## Establish the source before changing it

1. Inspect the existing `C:\Users\bgonn\Desktop\Compertum` folder read-only: guidance, Git status and recent commits, existing M0 acceptance report and current source. Its earlier 67 tests belong to the original project. Do not delete, reset, migrate, overwrite or import its runtime state.
2. Fetch the selected private repository through existing local Git authentication. Verify `origin`, the checkpoint branch/head and the tracked files. If the existing folder is already a clean checkout of that branch, it may be used. If its history/source differ or local changes would be overwritten, use an isolated clean checkout or worktree beside it. Do not force unrelated histories together or copy the old implementation over the checkpoint.
3. Read `AGENTS.md`, `docs/CLOUD_HANDOFF.md`, `docs/BUILD_SPEC.md`, `docs/M0_IMPLEMENTATION_PLAN.md` and the stage reports through `reports/M0_TASK3D.md`. The original specification/plan and lock remain preserved. Detailed baseline cloud receipts, wheels and original local history remain in the saved `Compertum_M0_Checkpoint.zip`; they are not tracked in this checkout. That ZIP predates Task 3A.

## Resume M0 on native Windows

- Verify native Task 1 first: current Windows/interpreter capabilities, fresh project environment, locked third-party wheels, actual imports and a second clean reproduction. Keep Python 3.14.7 as the target; do not silently install a replacement interpreter, change the lock or build third-party source. A cloud wheel-resolution preflight is not native installation evidence.
- Rerun the portable source tests and installed-wheel contract/config/runtime checks against the locked clean environment. Record measured results and hashes. Current cloud measurements are in the stage reports. No skip or copied receipt establishes native acceptance.
- The existing environment-verification helper emits `VERIFIED_CLOUD_IMPORTS` and native validation `UNVERIFIED`. Do not rename that output into a native pass. Verify the actual required observations and record new native receipts; any helper adjustment must retain honest environment-specific evidence.
- Candidate ownership, pipe-inspection, private-bootstrap and separate-owner fixtures are available. After native Task 1 is established, run the explicit fixture entry point from a qualified project environment:

```powershell
.\.venv\Scripts\python.exe -B tools\verify_native_ownership.py --suite all --run-fixtures
```

- The entry point uses existing dependencies only and creates small, unique project-local fixture/evidence directories. Without `--run-fixtures` it performs no fixture writes. In Linux it exits 3 with `NATIVE_WINDOWS_UNAVAILABLE`, never a native pass. Read the output's exact counts/status and retain its `result.json`/JUnit/log directory. Any skip or failure keeps the ownership fixture suite unverified. Even a successful fixture suite leaves Task 1, full Task 3 and M0 unverified/incomplete; do not mistake exit 0 for milestone acceptance.
- `--suite all` now includes at least 54 native fixtures: ownership 11, IPC 18, bootstrap 14 and registration 11. `--suite registration` isolates the separate-process cases. Any skipped/failed fixture remains unverified. Trusted bounded helpers use explicit inherited handle lists; no capability enters arguments, environment, metadata or output. Native pending-I/O tests require observed `ERROR_IO_PENDING` and completed cancellation. Injected Python interruption is reported separately from real console Ctrl+C qualification.
- Separate owners now receive worker requests through fresh, request-bound supervisor approval. Remote endpoints deny all operator claims; positive operator admission remains later supervisor/terminal work. Co-located operator inspection retains its documented process-local worker classification boundary. No universal classification of arbitrary same-user processes is claimed. Effectful requests remain disabled. Full Task 3 still needs native qualification and later durable replay integration. Task 4 stores or actual workers must wait for their prerequisites. No production launcher or Job limits are established here. Cloud implementation continues from measured receipts; the PC does not modify source in parallel.
- Continue Tasks 4-9 in dependency order once their prerequisites pass. Do not pause between passing tasks for routine confirmations. Record a concrete unavailable/failed gate and continue only work that does not depend on it. Keep M0 incomplete until every required acceptance gate passes.

## Ownership and operating limits

Cloud source development is the sole implementation writer under the latest owner decision. The home PC runs bounded verification and returns its measured report; local Codex may inspect/run it without making source changes. Do not run simultaneous writers. Every reviewed source stage uses an explicit GitHub commit and a brief measured status.

Spending remains $0 and all documented resource/storage/AI limits remain fixed. No administrator/OS security/power changes, drive migration, Strata restart/reconfiguration, broker credentials, trading, market-data collection, M1-M6, training or AVO/RSI/DREAM work. M0's existing proposal-only AI qualification is allowed only after the final wrapper limits and recorded budgets are verified. No unattended service is enabled.

Report briefly: completed task, native measurements, exact unresolved gate and next dependency. Engineering completion never implies strategy acceptance.

## Native failure follow-up — 8 October 2026 ET

Cloud remains the sole source writer. A remote-control connection does not itself transfer implementation ownership or merge chat state. Local Codex remains the bounded native verifier until an explicit handoff.

The repair candidate bounds malformed-input pytest IDs and launches native fixture helpers directly through the current interpreter's base executable while preserving the selected virtual environment. A new Windows fixture must prove child PID equals the retained process handle's PID, the environment/interpreter match, and a locked third-party import succeeds. Peer checks, pipe permissions and cancellation quarantine are unchanged.

For the next run, use an environment allowlist from the start and omit traceback locals/environment dumps. The operator reported a provider key in an initial traceback; do not copy that key or raw unredacted logs. Key rotation is an owner action, not a reason to inspect authentication stores.

Return a redacted REPORT.md plus the first DACL failure and first cancellation failure traceback/test ID, including the Win32 completion code. Preserve the original failed run. Run ownership first, then bootstrap and registration in separate fresh processes to distinguish primary failures from a quarantined transport. The full suite must also pass eventually; isolated passes are diagnostic only. DACL denial and cancellation remain unresolved, so this repair candidate is not expected to establish M0 acceptance by itself.
