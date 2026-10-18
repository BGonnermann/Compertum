# Simulated broker test clock

## Current result

The owner approved a test clock on 17 October 2026.
Source and installed-package runs each passed 61 checks, with zero failures, errors, skips, or remaining child processes.
The ten full simulated broker stages remain unrun.
The first complete storage check reached `CENSUS_110_SECOND_DEADLINE` after 110.002 seconds.
Its job closed after 138.800 seconds with zero remaining child processes.
The single retry reached `JOB_DEADLINE` after 120.393 seconds.
That job also observed exit and closed all child processes.
Neither attempt produced a complete storage result.
Neither attempt started a broker test owner or created a clock frame.
The complete source environment check reached `JOB_DEADLINE` after 121.060 seconds.
The complete installed environment check reached `JOB_DEADLINE` after 143.510 seconds.
Both jobs observed exit and left zero child processes.
The installed child wrote an `ENVIRONMENT_BYTES_VERIFIED` receipt.
Its full job failed, so complete installed environment verification is not accepted.
The source job has no completed byte-verification receipt.
Earlier complete environment passes remain historical results.
Stopped preservation passed its complete job in 117.298 seconds, with zero remaining child processes.
The archive retains 135 files and 197 entries. It uses 12,374,240 bytes.
Archive verification found no changed original file.
The final evidence audit passed in 114.556 seconds, with zero remaining child processes.
It confirmed the original project, unchanged attempt guard, and unchanged account and activity histories.
Independent review round 3 is closed. No actionable code findings remain.
The review accepts the clock helpers and preparation. It does not accept the unrun broker stages.
This report does not accept M5 or authorize an actual broker action.

## Change

`tests/helpers/fixture_market_clock.py` supplies market timestamps inside test helpers.
Each stage starts at a fixed simulated market time on 19 October 2026.
The clock advances at the same rate as actual elapsed time.
Each clock record expires after 120 actual seconds.
Its hash binds the original project and the exact saved test plan.
The helpers restore the original timestamp functions when their clock scope ends.

The source server and test execution owner use the same clock record.
The controller keeps the existing trading-window checks and completion margins.
The controller changes the simulated start time only between stopped stages.
Product source, system time, actual broker rules, and the existing installed package remain unchanged.

Health checks, watchdog checks, queue warmup, retry delays, and all deadlines use actual time.
The queue still requires its actual 60-second warmup.
Jobs retain four CPUs, 4 GiB RAM, 16 processes, and a 120-second deadline.
The controller retains 88 seconds for work, 17 seconds for cleanup, and 15 seconds for the test framework.
Owner calls remain limited to five seconds.

## Verification evidence

Private receipts remain in `artifacts/m5/risk-dispatch-20261017-01`.
The matching final helper runs are `test-clock-green04-source` and `test-clock-green04-installed`.
Each inventory contains 31 clock checks, one separate-process cleanup check, and 29 existing helper checks.
The runs check plan identity, clock expiry, trading-window refusal, actual timeout clocks, and cleanup after failure.
The installed run imports the existing installed product, with the same fixed test inventory.
Each passing helper run checked the 247 product files before and after testing.
That product check does not replace complete environment verification.

The independent reviewer found two clock cleanup defects during rounds 1 and 2.
One module copied its reply timestamp function before the test replaced the source function.
Another module could copy the simulated function during its first import.
Separate failing checks reproduced both defects before repair.
Round 3 found no further code or preparation issue.
The reviewer verified all 689 frozen inputs and all ten revised plans.
Round 3 independently verified the final available evidence and recorded the remaining blockers.
Earlier product review counters remain closed.

The first missing-interface run failed 19 checks.
The plan-binding run passed 21 checks and failed nine checks before repair.
The copied timestamp regression failed one check before repair.
One source run passed 58 checks and failed one local connection check with `WinError 10013`.
The network sandbox caused that connection refusal.
The authorized runs outside that sandbox passed the matching local connection checks.
The first cleanup regression had a child import setup error.
Its corrected run reproduced the cleanup defect before repair.
All failed receipts remain in place.
Earlier 35-case and 60-case passes remain historical and overlap the current 61-case inventory.
The earlier 285-case component inventories are separate historical results.
Do not add overlapping inventories together.

## Fixed full sequence

`simclock02-plans.json` records the ten revised plans.
The earlier `simclock01` plans remain preserved and unrun.
The original real-clock plans also remain preserved and unrun.

The sequence runs source and installed history collection first.
These stages run the actual Windows owner programs with invented local replies.
It then checks buying, lost replies, restart with holdings, resting orders, exact cancellation, and closing in each environment.
The closing test uses one child order.
It does not establish a full-process close with multiple children.
Each stage requires its own fresh complete storage result and observed process closure.
The sequence stopped at its first failed capacity check.
The single separate capacity retry also failed.
The original stage records and test plans remain unchanged.
The prepared retry launcher was not used.

Use only `.cache/test-runs/native-economic-fresh-20261017-01/native-shared`.
Its project identity remains `266b470c104c6b122e2db6d48a7c5946037235feae781ce2a808bda5010f4e39`.
The plan starts with 11 account packets and nine activity records per owner.
Successful execution would end with 29 account packets and 27 activity records per owner.
Each history limit remains 32.
Successful execution would advance the external attempt guard from zero to eight without a reset.
The final audit verified that the guard remains zero.
Both owners still have 11 account packets and nine activity records.

## Limits and stopping point

Scratch stays within 15 GiB. C: backups stay within 21 GiB. C: project storage stays within 50 GiB.
The separate D: archive vault stays within 200 GiB.
The vault does not increase runtime or scratch capacity.
The tests use the existing admitted folders and allocated reserve.
No new full project or GiB reserve is permitted.
Only one heavy job can run at a time.
Jobs require 16 GiB free host memory before starting and stop below 12 GiB.
The one-share and $250 fixture limits remain unchanged.
New spending remains zero.

Keep Strata off.
Preserve original sources, identities, openings, saved stops, failed attempts, and original receipts.
Stop before clearing a saved stop or performing an actual broker action.
Only M0 is accepted.
M5 requirements 2 through 5 remain open.
M6 remains zero of ten actual supervised sessions.

## Next permitted preparation

Investigate the complete storage check without starting a broker test owner.
Preserve both failed capacity jobs and every original plan.
Keep complete directory coverage, allocation checks, archive checks, and saved-stop checks.
Keep the 110-second census deadline and 120-second job deadline.
Keep the one-CPU and 128 MiB capacity-job limits.
Retain the completed clock review counter and all earlier component review counters.
Prepare a bounded storage-check repair and its independent review before requesting another capacity attempt.
Do not infer storage admission from a partial count or an earlier passing receipt.
The prepared `capacity_census_clock03_candidate.py` reads the preserved helper mapping once before its loop.
The candidate remains unexecuted. Its effect on elapsed time is unknown.
