# Storage check diagnosis and prepared repair

The owner requested preparation and independent review on 18 October 2026.
The owner prohibited another full storage scan.
This work prepares disabled source copies. It does not restore storage admission.

## What the evidence establishes

The parent job gives all work 120 seconds.
Its first folder count took 13.512762 seconds before the child started.
Child startup, the census, and final parent checks shared less than 106.487238 seconds.
The child starts its separate 110-second timer after imports and its first cost-seal check.
The child cannot receive that complete maximum interval inside this parent attempt.
A faster child could still finish. The 110-second limit is not a required duration.

The parent completed seven folder counts in 95.960012 wall seconds.
Six overlapped the child and took 82.447250 wall seconds.
These measurements do not establish processor use or equivalent time lost by the child.
Parent counts lasted 12.855914 to 14.444755 seconds each.
The final count also shares the original 120-second deadline.

The failed retry ended at JOB_DEADLINE after 120.006721 seconds.
It closed every child process but saved no child result or phase record.
The evidence cannot identify the last child phase or determine which parent count was active.
The wrapper also postponed saving the child exit code until after its final count.
Thus, the old record cannot distinguish every possible child outcome.

An earlier child failure recorded 161,721 observations and 72.167656 seconds inside observation calls.
Those calls include memory checks, file opening, metadata, stream checks, closure, and scheduling delays.
The evidence does not isolate one Windows call or prove one complete cause for the slowdown.
Earlier successful censuses used the same native traversal and observation code.
Their historical durations do not establish current timing fit.

## Prepared changes

The generator checks the exact original source hashes before preparing either copy.
Both copies refuse execution before imports or file writes.
The active wrapper, active profiles, and prior census remain unchanged.
No activation file or new full-scan plan was created.

- The census builds one ZIP name set inside each open archive.
- The census computes each observed file charge once, including every named stream.
- The parent saves the child exit code before final checks.
- Both programs save bounded phase records with common timestamps and original timer start points.
- The parent retains an unfinished count marker and completed count durations, including processor time.
- Routine parent log records occur at most once per five seconds.
- Boundary records remain explicit. Actual parent counts retain their two-second sampling interval.
- Each log permits at most 64 records and 64 KiB within the existing records budget.
- Log writes and closure check the original deadline. Late closure cannot retain success.
- Partial records always state incomplete status and cannot establish storage admission.

Fresh native observations, checked handle closure, both verification passes, and all 28 folder limits remain intact.
The child still uses one CPU, 128 MiB, and its original 110-second timer.
The enclosing job retains its original 120-second timer and host memory checks.
C: remains 50 GiB, scratch remains 15 GiB, and backups remain 21 GiB.
The separate D: archive vault remains 200 GiB.
Financial checks, saved stops, software versions, and runtime identities remain unchanged.

The helpers are tools/storage_check_diagnostics.py and tools/prepare_storage_check.py.
The disabled private copies are run_jobs07_prepared.py and capacity_census_clock04_prepared.py.
They remain under artifacts/m5/risk-dispatch-20261017-01.
The public helper tests do not require private artifacts.
Private source checks compare the disabled copies with the retained originals.

## Verification and preserved failures

The initial missing-helper check recorded zero passes, one expected failure, zero errors, and zero skips.
The first implemented set passed 36 source cases, with zero failures, errors, or skips.
Its wrapper passed in 29.539363 seconds and closed every child process.

Independent review round 1 required changes.
It found late log closure, excessive routine logging, and a late preservation-phase label.
It also required common-clock timestamps.
The agent corrected those findings and separated public tests from private source checks.
Round 1 source copies and the exact initial failing test source remain preserved.

The next fixture log recorded 43 passes, zero failures, zero errors, and zero skips.
Its preservation verifier tried to read the 1 GiB reserve into the 128 MiB job.
That operation raised MemoryError.
Its result name also collided with the existing review record.
The wrapper failed in 30.210958 seconds and closed every child process.
The original review record, failed closure, test log, and exception log remain preserved.
Those 43 passes do not establish successful preservation verification.

The receipt repair uses a separate result name and reads hash inputs in 1 MiB parts.
The final set passed 43 source cases, with zero failures, errors, or skips.
It contains 22 public helper cases, eight private source checks, and 13 existing namespace cases.
The wrapper passed in 44.699596 seconds and closed every child process.
Its peak job memory was 25,452,544 bytes.
The verifier checked 24 preserved evidence pins and 247 product files in each source and installed location.
It also checked 135 original file byte hashes and the unchanged attempt guard sequence of zero.
It opened no original database connection.
These file checks do not qualify the complete environments or repeat installed-package tests.
Independent review round 2 returned READY_FOR_OWNER_REVIEW for preparation only.
Both review rounds are closed within the three-round bound.
No actionable code finding remains. This verdict grants no execution clearance.
The four small-fixture jobs contain two passing jobs and two failed jobs.
All four observed exit and closed every child process.
The final 43-case inventory includes overlapping earlier cases. Do not add the earlier totals to it.
No installed-package test, full environment qualification, full census, or broker stage ran in this preparation.
Earlier 61-case source and installed-package clock results remain historical.

## Evidence and next action

Private evidence remains in artifacts/m5/local-economics-20261017-01 and artifacts/m5/risk-dispatch-20261017-01.
The preparation plan is docs/M5_STORAGE_CHECK_PREPARATION.md.
The failed full retry remains storage-timeout-capacity-retry01.closure.json.
The original single retry remains used. This work adds no full-scan allowance.

| Final item | SHA-256 |
| --- | --- |
| Diagnostic helper | b073c3d45e9d5b8d290a9f455c11b8b21c116e2da47e55dcccc66a3abfd8581e |
| Candidate generator | 513be95a30eb7946b8025021d25e717342e4dc6f7caff6736a2c12eed3ca1401 |
| Public helper tests | dc8fa6256eb739e715254ba52b89a621132d784cbd79bc4177ff724d0c299011 |
| Disabled wrapper | e5954799943234b7b38860204e52d7dadadbfcb2ef4d61e514967c7a24e7ff57 |
| Disabled census | 9b647bac98da51b09dcbb2b1ec7502711648814f35158ddab59f4962abfb03e7 |
| Fixture receipt | 11a1de29a7e622cbc1a627292ee0a9538ce39b43beb9e892de1e5049ace8ef6d |
| Wrapper closure | 5b3e7a2d526b90c362ab5950d5845bc5e27d413de0c13f06691a7a6ceec45020 |

A separate execution decision is required before activating either candidate or running a complete census.
That future census must satisfy all original checks and close within the unchanged parent deadline.
Only then can dependent simulated broker stages satisfy their storage prerequisite.
Keep Strata off. Do not clear saved stops or take broker actions.
