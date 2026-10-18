# Storage check timeout repair

The owner approved this repair and one bounded capacity retry on 17 October 2026.
This approval replaces the earlier instruction to request another storage attempt.

## Scope

Fix repeated storage monitoring work without changing product storage admission.
Keep each sample fresh. Keep every existing folder limit and error check.
Check host memory and the actual job deadline during each storage sample.
Preserve the original deadline start and every failed receipt.
Use one independent reviewer within three review and repair rounds for this repair.
Keep all earlier review counters closed.

## Acceptance and stopping points

- [x] Reproduce the repeated work with small folder fixtures.
- [x] Verify folder counts, overlapping limits, links, growth, errors, and deadline interruption.
- [x] Complete independent review before the one full capacity retry.
- [x] Execute the one approved capacity retry within the existing limits.
- [ ] After that retry passes, finish the ten existing simulated broker stages and review.
- [ ] Finish complete environment checks, preservation, the project diagram, and Git synchronization.

If the retry fails, preserve the failure and stop dependent broker test stages.
Stop after the first failed broker test stage or a later failed capacity check.
Do not create another full test project or reserve.
Keep Strata off. Do not clear saved stops or take actual broker actions.

Keep the 110-second census deadline and 120-second job deadline.
Keep the census at one CPU and 128 MiB.
Keep test jobs within four CPUs, 4 GiB, and 16 processes.
Require 16 GiB available host memory before each job. Stop below 12 GiB.
Keep one heavy job at a time and all existing call and cleanup deadlines.
Keep C: storage at 50 GiB, test scratch at 15 GiB, and backups at 21 GiB.
Keep the separate D: archive vault at 200 GiB.
Keep all frozen test identities, software versions, financial rules, and evidence.

## Current evidence

The first census reached its 110-second deadline during traversal.
It recorded 161,721 metadata calls and 72.167656 seconds inside those calls.
The parent job repeated overlapping folder scans while the census ran.
The parent checked its deadline only after each complete scan.
The retry receipt has host memory sample gaps of 44.16 and 40.53 seconds.
These observations support a targeted repair to the maintenance wrapper.
They do not prove that the repaired full census fits its deadline.

## Retry result

The final small fixture run passed 13 cases, with zero failures, errors, or skips.
Its wrapper passed in 29.628102 seconds and left zero child processes.
Independent review round 2 cleared the exact retry and its one-use launch record.
The full retry failed at JOB_DEADLINE after 120.006721 seconds.
The job observed exit and closed all child processes.
It saved no complete census result or partial traversal counts.
The agent did not start any simulated broker stage.

The maximum interval between host memory samples was 0.669146 seconds.
The minimum observed available host memory was 33.908875 GiB.
These observations verify improved deadline and memory monitoring.
They do not establish complete storage admission or full census timing fit.

The one retry is used. No additional full scan is approved.
Exact next action: prepare a separate bounded proposal to reduce full census work.
Keep dependent tests stopped until fresh complete storage admission qualifies.
