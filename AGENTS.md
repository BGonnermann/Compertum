# Compertum

## Current owner direction — 14 October 2026

- Keep `C:\Users\bgonn\Desktop\Compertum`, the master working folder, and GitHub up to date. The owner clarified that this is a synchronization requirement: an existing valid test need not be restarted solely because its results are written in another folder. Use master for current implementation and avoid unnecessary new desktop checkouts.
- The owner selected `https://github.com/BGonnermann/Compertum` as the private primary repository on 14 October. Use the existing `BGonnermann` GitHub account for future repository work; verify the active account before publication. Master's `origin` points there. The previous repository remains as `legacy-brennan` for reference; do not publish new changes there.
- The owner explicitly authorized keeping the primary GitHub repository current for rollback. Commit and push meaningful verified checkpoints, documenting pending/failed checks. Preserve history; no force-push, destructive reset or scheduled automation.
- The requested local clone is `.cache/checkouts/Compertum-bgonnermann` inside master. It contains Git history and tracked files only. Continue implementation in master; do not copy credentials, environments or path-bound runtime evidence into the clone.
- Older guidance designating `Compertum-development`, preserving master as read-only, prohibiting this publication, or limiting the already approved roadmap engineering to M0 is historical and superseded by later owner instructions.
- Preserve sibling directories and historical runtime identities. Do not relocate/resume a path-bound runtime as if it were created in master. Never erase failed evidence or reset task/attempt IDs to manufacture success.
- The owner approved finishing the existing interrupted M3 test in its original `Compertum-development` runtime/output folders, with master and GitHub kept current. This does not authorize resuming a subsequently blocked test or changing its frozen identities. The fresh master M3 sequence was subsequently closed as BLOCKED after an installed-audit exit receipt was lost. Preserve that terminal history; continue the independent local M5 engineering documented in the checkpoint.
- The owner reported an out-of-memory crash and explicitly prohibited starting Strata again. Do not launch, restart or auto-start Strata or its model server for this work. Preserve its files/configuration. Check host memory before bounded jobs, keep one heavy job at a time, and pause our work if memory headroom becomes unsafe.

## Execution

Read `docs/CURRENT_CHECKPOINT.md`, `docs/BUILD_SPEC.md` v1.1 and the relevant component plan. Work through accepted scope, tests, repair and fresh verification without routine permission stops. Keep a short checklist and exact next action. Update the README when verified status changes.

The primary agent owns implementation and integration. Use one bounded independent reviewer when useful; no parallel writers. Preserve unrelated work and make surgical changes.

## Boundaries

- New spending stays $0. No new account permissions, account/order actions, paid data, administrator elevation, security changes, unattended services or Strata reconfiguration without concrete authority.
- Existing read-only Alpaca permission and the authorized V20 credential-file source persist. Never display, log, copy into the repository, commit or publish secret values. Do not dump authentication stores or environment variables.
- Keep credentials, environments, runtime databases, data, private outputs and local backups/evidence out of Git. Publish code, tests, plans and honest reports only.
- No daily research runtime cap. Retain elapsed accounting, per-job deadlines, CPU/RAM/storage limits, one-heavy-job exclusion and retry limits. The cap-only continuation automation stays paused.
- Preserve the 50 GiB category budget. Test scratch uses fresh checked `.cache/test-runs` namespaces. Do not change interpreter, lock, thresholds or financial gates just to pass checks.

## Evidence

Report exact pass/fail/skip counts and distinguish source, installed-package, simulated, native and historical results. Skips, copied files and diagnostics are not milestone acceptance. The checkpoint separates engineering progress from financial qualification and supervised market sessions.

The original preparation brief is present in master and its hash matches BUILD_SPEC; older missing-brief statements are historical. See `reports/MASTER_CONSOLIDATION.md` for preservation and publication evidence.
