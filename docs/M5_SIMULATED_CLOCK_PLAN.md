# Simulated broker test clock

The owner approved this change on 17 October 2026.
Use a test clock to finish the simulated broker tests without waiting for market hours.
Keep real-broker rules, actual timeouts, evidence, and all existing limits intact.
Keep Strata off. Stop before clearing saved stops or actual broker actions.

## Scope and acceptance

- Keep the clock inside test helpers. Do not change product code or the system clock.
- Advance simulated market time at the same rate as actual elapsed time during each test stage.
- Change the simulated market start time only between stopped stages.
- Keep watchdog clocks, queue warmup, retry delays, process deadlines, and timeout measurements real.
- Bind each clock record to its fixed plan and original test project.
- Preserve the earlier real-clock plans, failed checks, identities, source beginnings, and reserved space.
- Verify refusal outside simulated trading times and expiry after actual elapsed time.
- Complete matching source and installed-package checks and all ten simulated broker stages.
- Check restart recovery, lost replies, cancellation, closing, and native component shutdown.
- Keep simulated results separate from real-clock and actual broker acceptance.
- Finish independent review, preservation, the diagram update, and Git synchronization.

## Limits

Keep scratch at 15 GiB and C: backups at 21 GiB.
Keep C: project storage within 50 GiB and the separate D: archive vault within 200 GiB.
Use the existing admitted test folders. Create no full native project or GiB reserve.
Keep each account and activity history limit at 32.
Require a fresh complete storage check before each native stage.
Run one heavy job at a time.
Require 16 GiB free host memory before starting. Stop below 12 GiB.
Retain 120-second jobs, four CPUs, 4 GiB RAM, and 16 processes.
Keep the 88-second work limit, 17-second cleanup allowance, and 15-second framework allowance.
Keep five-second owner calls and the one-share/$250 test limits.
Keep software versions, locks, financial gates, and all real-broker rules unchanged.

## Work checklist

- [x] Record fresh capacity and preserve the starting state.
- [x] Add clock checks and retain the initial failing result.
- [x] Implement the test clock and verify real timeout clocks remain unchanged.
- [x] Run matching source and installed-package checks.
- [ ] Run and verify all ten bounded simulated broker stages.
- [x] Complete independent review within three review and repair rounds.
- [ ] Close the full sequence with stopped evidence, diagram, and synchronization.

The primary agent owns implementation and verification.
Use one independent reviewer after the implementation is ready.
Retain every failed attempt. Do not reset review counters or test identities.
Stop at a real authority boundary or an exhausted review limit.
The fresh capacity check passed. It retained 86,615,392 bytes of scratch headroom after all recorded holds.
The final source and installed-package helper runs each passed 61 checks, with no failures, errors, skips, or remaining children.
All earlier failed checks remain preserved.
Review round 3 cleared the code, revised plans, and all 689 frozen inputs.
The full broker sequence stopped before its first owner launch because the complete storage check reached its deadline.
The one separate capacity retry also reached its job deadline.
Both jobs observed exit and left zero child processes.
The ten broker test stages remain unrun.
Both complete environment jobs reached their deadlines. Their complete verification remains unaccepted.
Stopped preservation and the final available-evidence audit passed.
Independent review round 3 is closed with no actionable code findings.
Ten broker stages still require a complete fresh storage check.
Prepare a bounded storage-check repair before requesting another capacity attempt.

## Later storage repair - 17 October 2026

The owner approved a targeted repair and one new bounded retry.
Thirteen small maintenance checks passed, with zero failures, errors, or skips.
Independent repair review round 2 cleared the concrete retry.
The retry failed at JOB_DEADLINE after 120.006721 seconds and closed all child processes.
It produced no complete storage result. The ten simulated broker stages remain unrun.
The approved retry is used. No additional full scan is approved.
Preserve the earlier clock review 3 and all failed receipts.
Use docs/M5_STORAGE_TIMEOUT_REPAIR.md for the current repair checklist and stopping point.
