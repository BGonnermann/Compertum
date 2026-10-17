# Restore native fee verification in a fresh test folder

16 October 2026. This is a prepared storage request. It is not permission to create or start another native runtime.

## Current blocker

The first fee native stage failed before account collection. It passed zero tests and failed one test.
Its Job closed with zero remaining children. The parent recorded a closed pipe, Windows error 109.
The child's original exit reason was not retained. The exact cause of that first failure remains unproven.

The recorded evaluation owner uses process ID 31756. Windows currently lists `svchost` in session 0 at that ID.
Both the normal process read and a narrower query returned access denied, Windows error 5.
The existing owner exit check must refuse when it cannot establish the previous process's identity or exit.
The import-only helper diagnostic passed without starting an owner or making an account request.

The original runtime remains at its original path. Its failed state has a verified full preservation archive.
Its project identity and allocated one GiB reserve remain unchanged. No saved identity or failed result was reset.
Do not stop the Windows service, change permissions, bypass the exit check, or restart the blocked runtime.

## Requested storage decision

Increase the approved local scratch ceiling from 12 GiB to 14 GiB.
Keep backups at 21 GiB and the aggregate budget at 50 GiB.
Keep every existing deadline, memory floor, CPU limit, financial gate, and allocated reserve.

The complete capacity measurement passed in 45.8714 seconds. Its parent closed in 53.8328 seconds with zero children.
The measurement leaves 14,539,184 scratch bytes after existing holds.

The proposed fresh fixture needs these bounded allocations:

| Allocation | Limit | Purpose |
| --- | ---: | --- |
| New scratch namespace | 1072 MiB | A fully allocated 1024 MiB reserve and 48 MiB for runtime growth |
| Separate backup namespace | 64 MiB | Preservation of the new runtime if needed |
| Separate record namespace | 8 MiB | Frozen stages, logs, and verification receipts |

Under the current scratch cap, the new hold is short by 1,109,534,288 bytes.
A 13 GiB ceiling is still short by 35,792,464 bytes.
A 14 GiB ceiling leaves 1,037,949,360 bytes after the proposed hold.
The projected aggregate charge is 37,205,247,776 bytes, below the unchanged 53,687,091,200-byte total.
The proposed backup hold leaves 689,592,352 bytes under 21 GiB.
The remaining scratch capacity is not authority to run unmeasured jobs.

## Procedure after explicit approval

1. Record the owner decision and the revised local scratch ceiling.
2. Run a fresh complete capacity check for the three proposed allocations.
3. Create `.cache/test-runs/native-fee-fresh-20261016-01/native-shared` as a new runtime.
4. Copy only the required tracked configuration and schemas.
5. Create a new project identity and a fully allocated one GiB reserve.
6. Provision only invented test credentials and local HTTP replies.
7. Record the new project, reserve, path, configuration, and original stop state before testing.
8. Freeze two native stages for source and the same two stages for the installed package.
9. Verify original fee inputs, adapter and calculator calls, single-use proofs, and refusal after restart.
10. Finish complete environment checks and the unused final fee review, round 3.
11. Refresh the reports and the nine-page project map. Synchronize the verified checkpoint and requested clone.
12. Continue the approved accounting, risk, durable dispatch, recovery, and installed local rehearsal plan.

The primary agent owns implementation. One bounded reviewer may inspect the procedure.
Each ordinary Job retains 120 seconds, four CPUs, 4 GiB RAM, and 16 processes.
Host start and stop floors remain 16 GiB and 12 GiB. Run one heavy job at a time.
No fixture folder, reserve, or native owner has been created under this proposal.

## Current evidence and acceptance limits

All 256 distinct source in-process cases passed with zero failures, errors, or skips.
The offline Windows package has 230 matching package files. The 256 matching installed checks remain pending at preparation.
The failed native stage is not acceptance evidence. No native fee stage has passed.
Fee reviews 1 and 2 are used. Final fee review 3 remains unused. Earlier component counters stay closed.

The current wheel hash is `bfec2f5f3a9d5c4a8bb377ffbc654409d454eea7f85f311d1afc3e2b79d1d59a`.
The source archive hash is `a012ebf2b2b9f2e5b5594e7a9c70b2111e397f56371248668e3ec79ab3bc757d`.

Private receipts remain in `artifacts/m5/native-fee-context-20261016-01`.
The complete projection is `fee-capacity04-result.json`.
The failed runtime archive is recorded in `fee-failed-native01-preservation-result.json`.
The process checks are `fee-prior-owners01-result.json` and `fee-prior-limited-query01-result.json`.

## Independent checks completed after preparation

Both source and installed in-process inventories now passed the same 256 distinct cases, with zero failures, errors, or skips.
Both complete environment byte checks passed. Native fee qualification and final fee review 3 remain open.
Final census 05 passed in 45.4573 seconds. Its parent closed in 54.6959 seconds with zero remaining children.
The scratch and backup projections above remain unchanged. Additional verification records raise the projected aggregate to 37,209,644,976 bytes.
That remains below 50 GiB. The owner decision remains pending. No limit has changed and no fresh fixture exists.

M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions.
Only M0 is fully accepted. The terminal M3 audit, failed fixtures, original environment, and saved stops remain preserved.
Actual broker actions remain outside this local scope. Strata stays off.
