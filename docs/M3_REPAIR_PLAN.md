# M3 repair run plan

23 October 2026. The owner approved this plan for a new, separately labelled M3 attempt.
The plan comes from the previous session's report. This file records it so that later sessions can find it.

## Relation to the blocked attempt

The blocked attempt stays exactly as it is. It is preserved, unchanged, and referenced by the new run.
Do not retry the blocked attempt. Do not reuse its identity, labels, folders, or pinned inputs.
The blocked attempt used tooling `.cache/test-runs/m3-pair-native-20261013-01`.
Its runtime is preserved at `backups/m3-interrupted-runtime-20261014-01/runtime`.
See [the interruption report](../reports/M3_FINAL_INTERRUPTION.md) and [the acceptance map](M3_MASTER_ACCEPTANCE_MAP.md).

The new attempt uses the label `m3-repair-20261023-01`. These folders did not exist when this plan was written:

- Tooling: `.cache/test-runs/m3-repair-native-20261023-01`
- Runtime: `.cache/test-runs/m3-repair-runtime-20261023-01`

## Cause of the block

The owner checked Event Viewer. This session confirmed the same System log entries on 23 October 2026:

| Time on 14 October 2026 | Event | Source |
| --- | --- | --- |
| 00:48:04 | 1074, restart, "Operating System: Service pack (Planned)" | `MoUsoCoreWorker.exe` |
| 00:52:16 | 1074, restart, "Operating System: Upgrade (Planned)" | `TrustedInstaller.exe` |

The audit's last saved signal was at about 00:47. Windows Update restarted the computer about one minute later.
This explains the lost exit receipt. It does not change the recorded BLOCKED result.

Controls for the new run:

- Windows updates are paused until 30 October 2026.
- Sleep and hibernate on mains power are off.
- No restart is pending.
- No other Python process runs. The harness session, LM Studio, and Tundra are closed. Strata stays off.

## The repair run

1. Build a release from the current code. Install it in both environments: editable source and installed package.
2. Run the regression tests, about 600, in each environment. Then qualify both environments.
3. Check storage and prepare the pinned inputs, about 37. One independent reviewer checks them before launch.
4. Run the long chain in its own PowerShell window. The chain must not depend on the agent terminal.
   The chain is not a service or a scheduled task. It runs these stages in order:
   - both 63-unit campaigns
   - all 77 audits
   - one new synthetic Final run, used one time; a restart must refuse a second run
   - the source and installed-package audits of the Final run, with status, pause, resume, and restart checks
   - the three-ridge check

## Limits

- Use synthetic data only. The real 2024 to 2025 vault stays closed.
- Run one heavy job at a time. Check host memory before each job.
- Keep the existing limits: 4 GiB, four CPU threads, and 120 seconds per worker job.
  Keep the 16 GiB launch floor and the 12 GiB stop floor. Do not change thresholds or financial checks.
- M3 is engineering acceptance, not proof of profit.
  The momentum candidates can fail the money gates again. That is an honest result.

## Other owner decisions

- Do not push.
- Leave the 12 records with `Desktop\Vesper` paths unchanged as evidence.
- Leave the 10 unrelated uncommitted files alone.
- If a stage fails, stop and report. Preserve the failed evidence. Do not reset identifiers.

## Owner decisions from 23 October 2026, later the same day

Release source:

- One reviewer checked the dispatch-owner and registration-complete gates. The verdict was `COMMIT_SET_OK`.
- Commit `b3a688cb3ffbe0b2436532e752a308d5b17ac0bd` holds only the gate files: `auditor.py`, `research.py`,
  `simulation/campaign_runs.py`, `campaign_review.py`, `ai/cycle_ownership.py`, and `ai/registration.py`.
- The release is built from that commit, never from the working tree. Other uncommitted work stays in master, untouched.
- `git archive` exports the commit to `.cache/test-runs/m3-repair-release-20261023-01/commit-tree01`, called the clean copy.
  The only added file is the untracked `src/compertum/_native/storage_scan.dll`. The commit pins its SHA-256 in `storage_scan.json`.
- The source lane, the regression tests, and the run tooling import code only from the clean copy.
- For this run, the source environment's editable install (`.cache/clean-env-m0`) points to the clean copy.
  `install-editable01.py restore` puts back the original bytes after the run, pass or fail. It proves that the whole environment matches its first snapshot.

Storage:

- Drive C had 87.37 GiB free. The run needs about 1.8 GiB, and the code keeps 50 GiB free.
- The scratch cap is 13 GiB only in this run's scripts. Product code keeps 12 GiB. The run record states this approval.
- The 13 GiB cap ends when the run ends, pass or fail.
- After the run, scratch stays above 12 GiB. The owner accepts this. The agent proposes a reviewed cleanup and waits for approval.
- The lineage reserve in `m5-lineage-installed-native-20261014-11` stays pinned.

## Progress

- [x] Plan saved and committed.
- [x] Gate files reviewed and committed as `b3a688c`.
- [x] Step 1: release built from `b3a688c` and installed. Wheel SHA-256 `29c884e3684ece0ecba65293863c596523ba4560c7981a64f6c6c929df6fec6e`.
  The source environment points to the clean copy until the restore.
- [ ] Step 2: regressions and environment qualification. **FAILED, stopped.**
  - The installed lane passed 20 of 21 groups (374 tests, 0 failures, 0 skips).
  - Group `installed_negative01` passed 69 tests. Then `tests/test_final_public_control.py::test_public_final_control_idempotence_no_redispatch_and_restart` hung, and the 360 s group deadline ended it.
  - The client waits in `runtime/control.py` `_connect` for the supervisor pipe. The holder process exits normally after 30 s.
  - The same hang occurs with parent commit `5017440`, which has no gates. Thus the gate commit is not the cause.
  - This test last passed on 13 October 2026, before the Windows upgrade restart on 14 October. It has not run since then.
  - Evidence: `.cache/test-runs/m3-repair-regressions-20261023-01/installed/installed_negative01*` and `.cache/test-runs/m3-repair-diagnosis-20261023-01`.
  - The source lane did not run.
- [x] Root cause found and repaired (owner chose option 1).
  - The blocked run's 13 October source passes the same test today, on the same Windows build. Windows is not the cause.
  - Commit `cc96a88` (16 October) gave the client connect wait the 300 s command deadline.
    A stale `supervisor.json` endpoint then blocked `control()` for 300 s.
  - Repair commit `a81c9b4b05d9022f96e01b52a799712c19a6230b`: the client connect wait keeps 5 s, as the resource report states.
    One independent review returned `COMMIT_OK`. Five targeted tests passed in a diagnosis copy.
- [x] Attempt `-01` closed. The source environment was restored, byte-identical (9,975 files). Its evidence stays unchanged.

## Attempt -02

Label `m3-repair-20261023-02`. Folders: `m3-repair-release-20261023-02`, `m3-repair-regressions-20261023-02`,
`m3-repair-native-20261023-02`, and runtime `m3-repair-runtime-20261023-02`.
The scripts are the reviewed `-01` scripts, changed only in folder names, label, and release commit.

- [x] Step 1: release built from `a81c9b4` and installed. Wheel SHA-256 `3664c8bea0697b326b901776d98e5f6422cfc2f9adb12ca598fa1876ad412b2c`.
- [ ] Step 2: regressions and environment qualification.
- [ ] Step 3: storage check, pinned inputs, independent review.
- [ ] Step 4: long chain.
- [ ] Step 3: storage check, pinned inputs, independent review.
- [ ] Step 4: long chain.
