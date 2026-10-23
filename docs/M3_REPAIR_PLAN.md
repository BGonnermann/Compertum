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

## Progress

- [x] Plan saved and committed.
- [ ] Step 1: release built and installed.
- [ ] Step 2: regressions and environment qualification.
- [ ] Step 3: storage check, pinned inputs, independent review.
- [ ] Step 4: long chain.
