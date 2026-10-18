# Compertum

## Pipe repair proposal reviewed - 18 October 2026

The proposed repair adds one verified application identity to one temporary test pipe.
Independent review found no blocking design issue. The repair is not applied.
The default pipe rules, runtime source, limits, permissions, and saved stops remain unchanged.
The next step is a disabled isolated helper, pure policy tests, and a fixed evidence ledger.
Creating a pipe with changed access rules requires separate approval.
Pipe-name requirements and native access remain unverified. No new tests or full storage scan ran.
See [the proposal](docs/M5_PIPE_REPAIR_PLAN.md) and [independent review](reports/M5_PIPE_REPAIR_REVIEW.md).
Strata remains off. No broker action ran.


## Full storage check passed - 18 October 2026

One authorized full storage check passed without a retry.
The scan took 71.160717 seconds. The complete job passed in 104.068814 seconds and closed all children.
The check included the new 8 MiB evidence allowance within unchanged category and total limits.
It examined 59,287 directories, 220,813 files, and 4,480 links.
It found zero unknown entries, access barriers, or ledger failures.
This check did not run broker tests or accept a roadmap milestone.
See [the storage report](reports/M5_EVIDENCE_STORAGE_CHECK.md).
Strata remained off. Permissions and saved stops remained unchanged.


## Child output repairs verified - 18 October 2026

Both child programs now use the checked clock-file location.
Child failure records use the existing 16 KiB cleanup allowance and cannot replace existing evidence.
The fresh source run passed 31 checks, with zero failures, errors, or skips.
Independent review found no remaining issue in these two repairs.
The prepared programs remain disabled. The proposed folder remains inactive.
See [the repair report](reports/M5_CHILD_OUTPUT_REPAIR.md).
No full scan, permission change, saved-stop change, or broker action ran. Strata remained off.

## Evidence folder code needs two repairs - 18 October 2026

The new writers enforce file limits and reserve failure records.
Disabled adapters preserve the existing folder checks and add the proposed 8 MiB allowance.
The final source run passed 25 checks, with zero failures, errors, or skips.
Independent review found two remaining child-output integration gaps.
The child helpers still require the old clock path and write one unbounded failure file.
The proposed folder remains inactive. No full storage scan or broker stage ran.
See [the implementation report](reports/M5_EVIDENCE_FOLDER_IMPLEMENTATION.md).
Strata stays off. Existing limits, evidence, permissions, and saved stops remain unchanged.

## Windows pipe restriction identified - 18 October 2026

The isolated test runs inside Windows AppContainer, a restricted application environment.
The pipe grants user access but lacks a matching application grant. Windows rejects the connection.
The final diagnostic completed and closed all children. Two earlier diagnostic failures remain preserved.
No permissions changed. No new broker tests ran.
Nine source helper checks passed, with zero failures, errors, or skips.
An 8 MiB evidence-folder proposal preserves the existing category, total, and folder limits.
The proposal is not active. See [the diagnosis and proposal](reports/M5_PIPE_AND_EVIDENCE_PREPARATION.md).
Strata stays off. Saved stops remain intact. Only M0 is accepted.


## Storage check passed - 18 October 2026

Two full storage checks passed within the unchanged deadlines.
The first simulated broker test failed because Windows refused a local pipe connection (`CreateFileW:5`).
The test result was **0 passed, 1 failed, 0 errors, 0 skipped**. The other nine stages did not run.
The sequence stopped without retry. All child processes closed.
An isolated diagnostic reproduced the error. The cause still needs investigation before a security change or another broker test.
Runtime evidence is preserved. Product file hashes remain unchanged in source and installed locations.
Strata stays off. Saved stops remain intact. Only M0 is accepted.
See [the current report](reports/M5_STORAGE_AND_SIMULATED_RESUMPTION.md) and [checkpoint](docs/CURRENT_CHECKPOINT.md).
The sections below preserve earlier results.

## Prepared storage check repair - 18 October 2026

The parent job uses 13.51 seconds before starting the census.
Startup, the census, and final checks then share less than 106.49 seconds.
The census has a separate 110-second maximum. The old failure did not record its final phase.

Disabled candidates remove repeated archive and file-charge work and add bounded phase records.
The final small set passed **43 source checks**, with zero failures, errors, or skips.
The job closed all children. Fresh byte checks matched 247 product files in each source and installed location.
These checks do not establish full-scan timing or complete environment qualification.

No new full scan or broker stage ran. The active scanner and all limits remain unchanged.
Strata stays off. Saved stops remain intact. Only M0 is accepted.
See [the preparation report](reports/M5_STORAGE_CHECK_PREPARATION.md) and [current checkpoint](docs/CURRENT_CHECKPOINT.md).

## Storage check repair - 17 October 2026

The maintenance repair passed **13 small checks**, with zero failures, errors, or skips.
The wrapper now checks memory and time during storage scans and preserves all existing folder limits.
Independent review cleared one complete capacity retry.
That retry reached `JOB_DEADLINE` after **120.006721 seconds** and closed all child processes.
It produced no complete storage result. All ten full simulated broker stages remain unrun.
The approved retry is used. No additional full scan is approved.
The earlier 61-case source and installed helper results remain historical and were not rerun during this repair.
Saved stops remain unchanged. Strata stays off. Only M0 is accepted.
See [the repair report](reports/M5_STORAGE_TIMEOUT_REPAIR.md) and [current checkpoint](docs/CURRENT_CHECKPOINT.md).

## Simulated broker clock - 17 October 2026

The test helpers can use a saved simulated market time.
Source and installed-package runs each passed **61 checks**, with zero failures, errors, skips, or remaining child processes.
Product source and actual broker rules remain unchanged.
Waits, health checks, watchdog checks, and deadlines still use actual time.

The full broker sequence stopped before its first owner launch.
The complete storage check reached its 110-second deadline. Its single retry reached the 120-second job deadline.
The ten full simulated broker stages remain unrun. A complete fresh storage result is required before they can start.
The earlier requirement to wait for actual market hours does not apply to these simulated tests.
Actual broker actions still require separate approval and retain their original time rules.

Only M0 is accepted. Saved stops remain in place. Strata stays off.
See [the clock report](reports/M5_SIMULATED_CLOCK.md), [the current checkpoint](docs/CURRENT_CHECKPOINT.md), and [the clock plan](docs/M5_SIMULATED_CLOCK_PLAN.md).

## Read-only project Hub - 17 October 2026

Open the local Hub at **[http://127.0.0.1:8767](http://127.0.0.1:8767)** while its terminal is running.
To start it later, open the **Compertum Hub** desktop shortcut or **`hub/Open Compertum Hub.cmd`**.
The shortcut reuses the running Hub. A new Hub keeps a minimized terminal open; restore it and press Ctrl+C to stop.
The PowerShell alternative is `./hub/start.ps1`.

The charcoal and warm-white pages show live agent signals, native project processes, test jobs, original documents, and saved results.
Live activity refreshes every two seconds while visible. Documents refresh every ten seconds. A lost connection marks retained observations stale.
The **Whole loop** page shows 17 stages, registered workers, saved runtime records, and missing reporting sources.
Master, the original development folder, and the approved native test runtime keep separate identities.
Saved running records do not establish current activity. The four new stage reporters say No report received until actual work reports.
Mathematics, qualification, signals, and feedback support measured progress and distinct blocked or completed outcomes.
The Project map page opens the existing horizontal PDF. No model, research runtime, account control, service, or scheduled task starts.

Hub checks passed **91 source cases and 67 main browser checks**, with zero failures, errors, or skips in each final run.
These are Hub checks. They do not change M1 through M6 acceptance or repeat the installed-package fee checks shown below.
See [live activity](docs/HUB_LIVE_ACTIVITY.md), [the four stage reporters](docs/HUB_STAGE_REPORTING.md), and [current verification](reports/HUB_FOUR_STAGE_VERIFICATION.md).
The [initial Hub plan](docs/HUB_PLAN.md) and [initial saved-record verification](reports/HUB_VERIFICATION.md) remain historical records.

## Earlier local risk and controlled dispatch - 17 October 2026

This section preserves the earlier real-clock preparation. The simulated clock report above gives the current test status.

Local implementation and verification are complete. The approved local finish plan still requires its combined native rehearsal.
Source and installed inventories each passed **285 distinct cases**, with zero failures, errors, skips, or remaining children.
Source contains 257 fresh cases and 28 unchanged cases with verified code and imported test files. All installed cases are fresh.
The 247-file package installed offline with unchanged locked tools and dependencies. Both complete environments passed byte verification.
The installed environment passed again after all tests. Earlier failed checks and their original evidence remain preserved.

Current risk, exact consumption, outcome reconciliation, and finite closing are implemented and tested.
Final product source reviews and native preparation review are clear at 3 of 3. Their counters remain closed.
The 29 helper cases belong inside each 285-case inventory. They do not establish full native acceptance.
Ten native stages are prepared. Actual native timing fit and native component halt remain unverified.

Both HISTORY stages must finish before **09:25 New York on Monday, 19 October 2026**.
Fixture buying requires **09:35 or later and strictly before 10:05**. Keep clocks and operation windows unchanged.
The continuing native project is stopped and has a fresh verified preservation archive. No additional project or GiB reserve was created.
Fresh complete storage admission passed. Limits stay 15 GiB scratch, 21 GiB backups, and 50 GiB total. Strata stays off.
Only M0 is accepted. M5 gates 2 through 5 remain open. M6 stays zero of ten actual supervised sessions.
See [the report](reports/M5_LOCAL_RISK_DISPATCH.md), [prepared native commands](docs/M5_NATIVE_REHEARSAL_PLAN.md), and [continuation prompt](docs/LOCAL_FINISH_CONTINUATION_PROMPT.md).

## Earlier native economic continuation - 17 October 2026

The owner approved 15 GiB test scratch and one additional 1072 MiB native folder. Complete storage admission passed.
Backups stay 21 GiB; total storage stays 50 GiB. Both original journals existed before the first account observation.
Source and installed checks each passed 229 distinct cases, with zero failures, errors, or skips.
Each inventory contains 226 in-process cases and three native stages, including shutdown.
Both complete environments passed byte verification. Final economic review is clear at 3 of 3.
The final repairs close source process handles on aborted reads and freeze calculator arguments before callbacks.
The 61 shutdown checks are included in each inventory. All failed attempts and original native identities remain preserved.

The local finish plan remains incomplete. Continue risk, durable dispatch and recovery, and the installed combined rehearsal.
Real owner clocks and operation windows remain required.
Historical inputs must finish before 09:25. Native buying must occur during 09:35–10:05 New York on an eligible exchange day.
The next eligible day is Monday, 19 October. Complete independent implementation and tests before that timing boundary.
M5 gates 2 through 5 remain open. M6 stays zero of ten actual supervised sessions. Only M0 is fully accepted.
See [the current native report](reports/M5_NATIVE_ECONOMICS.md). Strata stays off.

## Earlier economic preparation and approval boundary - 17 October 2026

**Economic preparation is verified. Native qualification and the approved local finish plan remain incomplete.**
Source and installed checks each passed 54 distinct in-process cases, with zero failures, errors, or skips.
Each inventory contains 35 calculation cases and 19 controlled journal cases. No economic native case has passed.
Both complete environment byte checks passed. Independent preparation review 2/3 is clear; final native review 3 remains unused.

The calculation checks linked fees, reversals, cash, and covered asset identity. It grants no source or broker authority.
The test source retains events and acknowledged coverage times across reopening. It rejects files with multiple hard links.
All 232 earlier product files remain unchanged. One unqualified calculation module was added.

The existing native project lacks original fee accruals, payment links, and a complete action calendar.
Its fixed replies cannot prove that missing history. Its first opening and credential slot remain immutable.
Positive native verification needs another project, with its source created before its first account observation.
The approved one-folder allowance is already used. No second folder or reserve has been created.

Active test scratch remains 14 GiB. The measured request is 15 GiB and one additional 1072 MiB native folder.
Backups remain 21 GiB; total storage remains 50 GiB. Preserve all original runtimes, reserves, halts, and failed results.
Next, obtain that specific decision, then require fresh complete capacity admission before native implementation and verification.
Then finish current-input risk, durable dispatch and recovery, and the installed combined local rehearsal.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
Strata stays off. See reports/M5_LOCAL_ECONOMIC_PREPARATION.md for evidence and the exact measured request.

## Earlier posted-fee verification - 17 October 2026

**Posted-fee engineering is locally verified. The approved local finish plan remains incomplete.**
Source and installed inventories each passed 238 distinct cases, with zero failures, errors, or skips.
Each contains 236 in-process cases and two native Windows stages. Both complete environment byte checks passed.
Native stages use real Windows owners and invented local replies.
Final posted-fee review 3/3 is clear. Posted-fee, declared-fee, and infrastructure review rounds are closed.

The calculation preserves original cash and signed USD fee rows. Matching cash does not establish billing or unpaid liabilities.
The new calculation accepts bounded inputs above 64 KiB. The existing parser retains its original limit.
All four native stages passed in the same approved folder. Its original project and allocated reserve remain unchanged.
The stopped runtime has a fresh verified archive. The failed posted-fee attempt also has a complete retained archive.
The test helper now checks proof phases during explicit status calls. Publication acknowledgement remains passive.
The first failure's cause remains unproven. Both older halted runtimes remain preserved and stopped.

The installed test output needed 80 MiB. A fresh complete measurement admitted that hold before installed tests.
Test scratch stays 14 GiB, backups 21 GiB, and total storage 50 GiB. Published program limits remain unchanged.

Next, implement local fixture fee liabilities and action evidence under M5_LOCAL_ECONOMIC_EVIDENCE_PLAN.md.
Its design review 1 is complete. Derive facts from complete original fixture records; do not assume zero liabilities.
Then finish current-input risk, durable dispatch and recovery, and the installed combined local rehearsal.
Actual billing and provider action coverage remain unverified. Financial and actual broker authority remain false.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, master stop, failed evidence, reserves, and terminal M3 history remain preserved. Strata stays off.
See M5_POSTED_FEE_CONTEXT.md for exact results and local evidence paths. Keep Hub results separate from these inventories.

## Earlier declared-fee verification - 17 October 2026

**Declared-fee engineering is locally verified. The approved local finish plan remains incomplete.**
Source and installed inventories each passed 260 distinct cases, with zero failures, errors, or skips.
Each contains 258 in-process cases and two native Windows stages. Both complete environment byte checks passed.
Final fee review 3/3 is clear. All declared-fee and infrastructure review rounds are closed.

The owner approved 14 GiB test scratch for one fresh native folder. Backups remain 21 GiB; the total remains 50 GiB.
Fresh complete capacity admission passed before creation. Published program limits and all 230 package files are unchanged.
The new folder has its own project and fully allocated one GiB reserve. Four separately frozen native stages passed.
They verify original declared inputs, calculator calls, single-use proofs, and no restored freshness after restart.
The stopped successful runtime has a verified 85-file preservation archive. It has no watchdog halt.
Both older failed native attempts and retained halts remain preserved. Never clear or resume those halted folders.

Acceptance covers declared-fee engineering only. Actual billing coverage, account applicability, and unpaid liabilities remain unverified.
Next, implement posted fee observations against original account activity under M5_POSTED_FEES_PLAN.md.
Its measured allocation retains the existing native folder; it creates no additional native reserve.
Then finish liability and action qualification, risk, durable dispatch/recovery, and the installed combined rehearsal.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, master stop, failed fixtures, reserves, and terminal M3 history remain preserved. Strata stays off.
See the declared-fee report and the posted-fee plan for exact evidence and the next bounded step.

## Earlier helper repair and storage pause - 17 October 2026

**The fee test helper is repaired. Native fee qualification remains blocked by a retained storage halt.**
Source and installed inventories each contain 258 distinct passing in-process cases, with zero failures, errors, or skips.
They include 256 unchanged cases and two new storage regression cases. Both refreshed complete environment checks passed.
The repair reserves and publishes the fee reference through checked artifact storage. All 230 product package files are unchanged.

The earlier process inspection condition cleared. A separately recorded attempt then passed startup and published its local account observation.
The watchdog stopped it for `UNACCOUNTED_GROWTH` from a new unreserved reference file. The halt remains intact.
Its complete verified archive retains 403 files. Never clear or resume that stopped runtime.
Both native failed attempts remain failed. No native fee stage is accepted. The first pipe failure's cause remains unproven.

The fresh folder needs 1072 MiB. The current 12 GiB scratch limit cannot admit it; 13 GiB is also insufficient.
The measured 14 GiB proposal leaves 1,037,624,944 scratch bytes. Backups stay 21 GiB, and the total stays 50 GiB.
Owner approval remains pending. No limit has changed, and no fresh folder or reserve has been created.
Infrastructure review 3/3 is clear. Fee final review 3 remains unused. Earlier review counters stay closed.

Next, resolve that specific storage decision and require fresh complete admission before creating the separate native fixture.
Then finish native fee verification, billing and actions, risk, durable dispatch/recovery, and the installed integrated rehearsal.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, master stop, failed fixtures, reserves, and terminal M3 history remain preserved. Strata stays off.
See [the current report](reports/M5_NATIVE_FEE_CONTEXT.md) and [the concrete recovery request](docs/M5_NATIVE_FEE_FIXTURE_RECOVERY_PLAN.md).

## Earlier fee checkpoint - 16 October 2026

## Current fee work and native blocker

16 October 2026. **Declared-fee checks passed in-process; native qualification is blocked.**
Source and installed checks each passed 256 matching distinct in-process cases, with zero failures, errors, or skips.
Both complete environment byte checks passed. Fee reviews 1 and 2 are used; final review 3 remains unused.
The private fee context binds original fills and retained declarations. Actual billed fees and liabilities remain unknown.
The earlier current-cost component retains its separate 53 accepted cases per environment. Do not sum overlapping inventories.

The first source native fee stage failed before account collection: zero passed, one failed, zero errors or skips.
The closed pipe does not establish the child's original exit reason. That first failure's cause remains unproven.
Windows currently denies the required inspection of saved evaluation process ID 31756, including a narrower read.
The existing owner-exit check must refuse reuse. The original failed runtime has a complete verified preservation archive.
No owner identity, exit check, permission, service, or failed result was changed. The blocked runtime must not resume.

A fresh native folder needs 1072 MiB. The measured 12 GiB scratch limit cannot admit that hold.
The prepared request raises scratch to 14 GiB. Backups stay 21 GiB, and the total stays 50 GiB.
This is a pending owner decision. No new native folder or reserve has been created, and no limit has changed.
Finish native verification only after that decision and a fresh complete capacity check.

Fee billing, corporate actions, current-input risk, durable dispatch/recovery, and the installed integrated rehearsal remain open.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, saved stops, failed fixtures, reserves, and terminal M3 history remain preserved. Strata stays off.
No actual broker action occurred. See [the fee report](reports/M5_NATIVE_FEE_CONTEXT.md) and [the recovery request](docs/M5_NATIVE_FEE_FIXTURE_RECOVERY_PLAN.md).

## Earlier current-record cost checkpoint

16 October 2026. **Position costs from current original records are locally verified.**
Source and installed checks each passed 53 matching distinct cases, with zero failures, errors or skips.
Each inventory includes 51 in-process cases and two native Windows stages.
Both final complete environment checks passed. Independent review round 3 is clear; all three rounds are used.

The new private context binds the original account, opening, complete history, portfolio and native activity records.
Supported recorded-fill costs must match. Unsupported histories remain blocked after closing and reopening.
Fees, corporate actions, risk, durable dispatch and the installed integrated rehearsal remain open.
M5 gates 2-5 remain open. M6 remains 0/10 actual supervised sessions. Only M0 is fully accepted.

The final maintenance census passed in 44.6748 seconds under the unchanged 110-second measurement bound.
Its parent Job closed in 48.1994 seconds with zero remaining children.
Scratch has 4,146,112 bytes left after holds. Backups have 924,473,376 bytes left.
Scratch remains 12 GiB, backups 21 GiB and the total 50 GiB.
Production scans retain 30 seconds and their 35-second freshness rule.

The first installed native attempt remains failed. Its original runtime and sidecars have a verified preservation archive.
One existing acknowledgement was recovered without another account request or changed activity identity.
A separate instrumented test passed. Its 4.8145-second acknowledgement has little margin under the unchanged five-second limit.
The original failure's cause remains unproven. Historical failures do not enter passing counts.

Next, bind declared fee calculations to original current fills under the reviewed fee-context plan.
Then qualify fees and actions before risk, durable dispatch and the installed local rehearsal.
The failed fixtures, saved stops, original environment and terminal M3 audit history remain preserved.
No actual broker action occurred. Strata stays off.

See [the exact current cost report](reports/M5_POSITION_COST_CONTEXT.md).

## Resolved storage pause

16 October 2026. **The next accounting increment is blocked at its storage check.** The census stopped after 70.0017 seconds. It counted 99,181 files but produced no complete capacity measurement. Its Job exited 1 with zero remaining children. No position-cost test folder, product test or package build started.

A separate 20-second diagnostic counted 30,218 files. It recorded file-check timing but did not establish one cause. Its Job closed successfully. That diagnostic grants no capacity admission. A busy `bf6` process coincided with the slowdown. Memory remained above the required floors. No other program was stopped.

The original comparison remains verified across 301 matching distinct cases per environment, with zero failures, errors or skips. Both complete byte checks and separate final reviews passed. Its published code checkpoint is `0cae4b5`. Master, GitHub and the requested clone matched that checkpoint. The failed fixture, saved stops, original environment and terminal M3 audit history remain preserved. Strata stays off.

Exact next action: require a measured external-load change, a diagnosed repair or scoped authority for another admission attempt. Then run one instrumented capacity check within the existing bounds. Keep scratch at 12 GiB, backups at 21 GiB and the total at 50 GiB. The prepared retry has not run. M5 gates 2-5 remain open. M6 remains 0/10 actual supervised sessions. Only M0 is fully accepted.

See [the exact blocker](reports/M5_LOCAL_FINISH_BLOCKER.md) and [the bounded follow-up](docs/M5_STORAGE_GATE_FOLLOWUP.md).

## Earlier verified comparison checkpoint

16 October 2026. **The original order and fill comparison is locally verified.** The accepted inventory has 301 matching distinct cases per environment. Failures, errors and skips are zero. It includes 71 calculation cases, 192 compatibility cases, 36 private-context cases and two native Windows stages per environment.

Both complete environment byte checks passed. The calculator and context each completed three independent review rounds. Both final reviews are clear. The isolated closed-database repair passed three focused checks per environment. Valid earlier cases are reused under recorded change comparisons.

The native checks used an invented account opening and local HTTP replies. The passing runtime stayed at its original path after a verified preservation archive. Its project and allocated reserve identities remain unchanged. The failed fixture, master stop, original environment and terminal M3 audit history remain preserved. Strata stays off.

The final census passed. Scratch has 40,286,760 bytes left after recorded holds under its 12 GiB ceiling. Backups have 1,041,917,984 bytes left under 21 GiB. The total stays 50 GiB.

Exact next action: define and freeze the next missing accounting producer. Fee liabilities, corporate actions and full position costs remain unverified. Then continue risk, durable dispatch and the integrated installed rehearsal. M5 gates 2-5 remain open. M6 remains 0/10 actual supervised sessions. Only M0 is fully accepted.

See [exact comparison evidence](reports/M5_OWNERSHIP_COMPARISON.md).

## Earlier native activity checkpoint

16 October 2026. **The native activity producer is locally verified.** Source and installed checks each passed 271 matching cases. Failures, errors and skips are zero. Each inventory includes four native Windows stages and 267 pure or in-process cases. Both complete environment byte checks passed. Final independent code review round 3 is clear; all three rounds are used.

The producer binds the original account context, immutable opening, complete local history and credential identity. Native loopback checks cover collection, lost replies, encrypted publication, restart, cancellation and historical reopening. The account opening is invented test evidence. These checks grant no ownership, economic, risk or broker-write authority.

The owner approved 12 GiB scratch and 21 GiB backups under the unchanged 50 GiB total. The final census passed. Scratch has 141,360,336 bytes left after recorded holds. Backups have 1,074,264,096 bytes left. Both native fixture reserves and the failed fixture's halt remain preserved. The saved master stop, original environment and terminal M3 audit failure remain preserved. Strata stays off.

Exact next action: freeze the ownership and economic reconciliation cases against the immutable opening, complete history and native observations. Then complete risk, durable dispatch/recovery and the integrated local rehearsal in dependency order. M5 requirements 2-5 remain open. M6 remains 0/10 actual supervised sessions.

See [native activity verification](reports/M5_NATIVE_ACTIVITY_PRODUCER.md) and [the current checkpoint](docs/CURRENT_CHECKPOINT.md).

## Earlier activity-parser checkpoint

16 October 2026. **Native retained records and the activity parser boundary are verified.** The combined inventory has 371 matching unique source/installed cases per environment. Failures, errors and skips are zero. It includes 99 new pure activity cases and 272 unchanged component cases. Both latest complete environment byte checks passed. Each dependency completed independent review round 3.

The parser fixes the original query and cursor chain. It preserves exact fill times and keeps missing native, ownership, fee, action and economic evidence blocking. No native activity producer, risk admission or actual dispatch is claimed.

The final census passed in 44.709 seconds. Scratch has 309,710,856 bytes left after a 128 MiB hold. Backups have 1,074,264,096 bytes left under the approved 21 GiB ceiling. Another 1 GiB native fixture exceeds scratch headroom by 764,030,968 bytes. The 11 GiB scratch decision remains pending. The 50 GiB total and emergency reserve remain unchanged.

Exact next action: resolve that allocation, then implement and qualify the private native activity producer. Continue ownership/economics, risk, durable dispatch/recovery and the installed local rehearsal in dependency order. M5 requirements 2-5 remain open. M6 remains 0/10 actual sessions. The saved master stop and terminal M3 audit failure remain preserved. Strata stays off.

See [activity checks and the capacity barrier](reports/M5_ACTIVITY_BOUNDARY.md) and [native record evidence](reports/M5_NATIVE_ATTEMPT_RECORDS.md).

## Earlier native-record checkpoint

16 October 2026. **The native retained-attempt dependency is verified.** Source and installed evidence match across 272 unique cases per environment. There are zero failures, errors or skips in the accepted inventory. Both complete environment byte checks passed. Independent review round 3 is clear.

Native write records remain separate from fake execution and inert preparation. The private reader now includes external attempts after an older database restore. No ownership, economic, risk or dispatch authority is granted.

The owner approved 21 GiB backups under the unchanged 50 GiB total. The complete census passed with 1,074,264,096 bytes of backup headroom. Scratch has 321,240,632 bytes left after a 128 MiB hold. The 11 GiB scratch decision remains pending for another native reserve fixture.

Exact next action: verify the small activity-request and parser boundary. Then qualify the native activity producer and economic evidence. M5 requirements 2-5 remain open. M6 remains 0/10 actual sessions. The saved master stop and terminal M3 audit failure remain preserved. Strata stays off.

See [native records and exact evidence](reports/M5_NATIVE_ATTEMPT_RECORDS.md), [timers and capacity](reports/RESOURCE_TIMERS_AND_STORAGE.md), and [the current checkpoint](docs/CURRENT_CHECKPOINT.md).

## Earlier 16 October reader checkpoint

16 October 2026. **Workload limits are adjusted and the blocked private portfolio reader is verified.** Complete storage scans have 30 seconds and yield to heartbeat work; inventory freshness is 35 seconds. Recovery has a shared 240-second deadline. Authenticated commands allow 300 seconds, with five-second authentication and reply acknowledgement. The current task has 4 GiB temporary space inside a 10 GiB scratch category; the 50 GiB total and 1 GiB emergency reserve remain unchanged.

The reader passed **64 identical source/installed cases**, zero failures/errors/skips, with both final environments byte-verified and independent reader review clear. Installed native three-owner recovery also passed. The full final capacity census passed with 29.567 GiB allocated, including 8.492 GiB scratch, and 187.673 GiB physical disk free. Backups still have only 522,272 bytes of category headroom. Strata remains off; the original installed environment, saved master stop and terminal M3 audit history remain preserved.

See [timers, storage and future capacity](reports/RESOURCE_TIMERS_AND_STORAGE.md), [the reader verification](reports/M5_PRIVATE_PORTFOLIO_CONTEXT.md), and [the current checkpoint](docs/CURRENT_CHECKPOINT.md). M5 requirements 2-5 remain open; M6 remains 0/10 actual sessions.

## Earlier preparation and results

16 October 2026. **The preview resource check is fixed and independently reviewed.
One complete capacity census ran and refused the requested 1 GiB scratch hold.**
The hold exceeds remaining scratch capacity by **1,063,722,952 bytes**. All 31
simulated/pure checks passed, with zero failures, errors or skips. No product
tests ran. The preview was already absent at launch; this work did not stop or
restart it. This repair keeps the reviewed five-second limit. Separate edits
appeared afterward that change the scanner setting to 30 seconds and scratch
to 9 GiB; those edits are outside this review. All evidence and the saved stop
remain preserved. See [the result](reports/PREVIEW_RESOURCE_CAPACITY.md).

A supervised research system with reproducible experiments, bounded AI proposals, independent audits, and controlled paper-trading development.

Updated 15 October 2026. **Working folder: `C:\Users\bgonn\Desktop\Compertum`.** GitHub stores code, configuration, tests, plans and reports for rollback. Credentials, provider data, runtime databases, environments and detailed local evidence stay outside Git.

**Primary repository: [BGonnermann/Compertum](https://github.com/BGonnermann/Compertum)** (private). Future updates use the BGonnermann account. The previous repository remains a historical reference; the full commit history is preserved.

## Historical position before the 16 October resource change

The results and next actions below are preserved history. The dated update above and the current checkpoint supersede their storage limits and reader19 status.

Original intent release18 is verified:393 matching cases per environment, including all106 formerly pending installed cases; final original-release review3 CLEAR. The native storage scanner separately passed43 matching source/package cases,18 C boundary cases, both complete environment checks and three full-master scans within the unchanged five-second/one-CPU/128MiB limits. Times:4.566,4.948,4.930seconds; the last uses the original watchdog volume callback. Final native review6 is CLEAR. Scan headroom is narrow; preserve closed passing scratch before further fixture growth. See [intent verification](reports/M5_NATIVE_INTENTS.md), [native storage evidence](reports/M5_NATIVE_STORAGE.md) and [the current checkpoint](docs/CURRENT_CHECKPOINT.md). Ownership/accounting, risk, durable dispatch/recovery and the local rehearsal remain open. M6 is0/10 actual supervised sessions.

Current storage admission remains blocked after the broader native experiment used rounds10 through12. The aligned private candidate matched two small inventories, then timed out after83,623 files. All23,749 handles closed under the unchanged one-CPU/128MiB/five-second watchdog; no prototype entered the product. Product code is unchanged. Reader19 remains34 private cases, zero executed and no implementation; M5 local gates2 through5 remain open. No failed fixture was removed. See [the measured experiment and unresolved decision](reports/M5_NATIVE_BATCH_EXPERIMENT.md).

15 October 2026. **Storage admission remains blocked; diagnosis and a bounded fix are prepared for review.** The four approved folders remain removed and all backups and prior evidence are preserved. One new read-only five-second profile measured 1.990421 seconds in directory acquisition/first query and 0.677391 seconds in checked closure before timing out. The last complete count, less the 718 removed directories, still leaves a derived 28,620 before later record growth. No current complete inventory or capacity pass is claimed.

The proposed change reuses at most 16 checked-closed buffers in the existing private native walker. It preserves caller-thread reads/callbacks and every current limit and check. Its timing benefit is unproved. The source diff is unapplied; no candidate was compiled, run, installed or promoted. Two in-memory diagnostic record checks passed with zero failures/skips; no product tests ran. Read [the diagnosis](reports/STORAGE_ADMISSION_DIAGNOSIS.md) and [the bounded fix for review](docs/STORAGE_ADMISSION_FIX_REVIEW.md).

All 217 source and 217 installed program files, prior failed receipts, backups, actual coordinator bytes, 1 GiB reserve and watchdog stop remain unchanged. Ordinary work, reader19, Strata and clone updates remain stopped. The twelve earlier scanner experiment rounds and five maintenance reviews stay used; no round-13 candidate or further live admission attempt ran. M5 requirements 2 through 5 remain open; M6 stays zero of ten actual sessions.

Preparation follow-up: the worker is on hold and confirmed that no native Job started. Unapplied integration and regression drafts now select 61 cases per lane. The preservation receipt exists. Complete isolated dependency payloads require at least 345,161,969 bytes, exceeding the 8,388,608-byte scratch ceiling. The executable procedure remains incomplete. See [the three preparation gaps and storage decision](docs/STORAGE_PREPARATION_GAPS.md). No candidate or product test ran.

Historical next action, now superseded: select a storage and installation approach before completing and reviewing the executable procedure. Keep the five-second limit, every saved record, and the worker hold. Do not run another admission check or clear the saved stop.

The owner-approved administrator cleanup has now removed exactly 31 old shortcuts. A separate live check confirmed all 31 target folders are unchanged and all links are absent. No permissions changed. The original failed launches and saved link records remain preserved; all 217 source and installed program files still match. The [cleanup report](docs/FIXTURE_CONSOLIDATION_GATES.md) explains the earlier Windows permission failure and the remaining storage decisions.

Private final input proofs are verified with **277 identical passing cases per source/installed environment**, zero failures/errors/skips, both complete environment checks and final aggregate review CLEAR. Grouped proofs check original account, market and presence evidence after callbacks finish and preserve caller transactions. See [the proof report](reports/M5_INPUT_PROOFS.md). Next: exact native intent and confirmation records.

Account and presence integrity is verified with **222 identical passing cases per source/installed environment**, zero failures/errors/skips, complete environment checks and final review CLEAR2/3. Late validation callbacks cannot hide changed originals or revoked presence; invalid acknowledgements are refused before insertion. See [the integrity report](reports/M5_ACCOUNT_PRESENCE_INTEGRITY.md). Next: exact native intent and confirmation records.

Combined-input integrity is verified with **151 identical passing cases per source/installed environment**, zero failures/errors/skips, complete environment checks and final review CLEAR3/3. Original evidence is rechecked after callbacks; account-health refusal preserves borrowed historical data. See [the integrity report](reports/M5_INPUT_INTEGRITY.md). Account/presence callback repair is now verified above.

Account-only inputs have **306 identical passing cases per source/installed environment**, zero failures/errors/skips, both complete environment checks and verified aggregate evidence. Corrupt opening artifacts and history now refuse permanently while valid nonempty history remains readable. Final independent review3/3 is CLEAR. See [the account-context report](reports/M5_ACCOUNT_CONTEXT.md). Subsequent combined-context repair is described above; account/presence callback repair is verified above.

Native operator presence is verified with **314 identical passing cases per source/installed environment**, zero failures/errors/skips, both complete environment checks and final independent review CLEAR4/4. The repair prevents a refused acknowledgement from being committed by a health-halt callback. Presence expires permanently and grants no broker authority. See [the presence report](reports/M5_NATIVE_PRESENCE.md). Account-only inputs and subsequent integrity repairs are covered above.

The private account/market input context has **255 matching passing cases per source/installed environment**, zero failures/errors/skips, complete environment qualification and verified aggregate evidence. It binds original observations and permanently refuses invalidated contexts. Final independent review3/3 is CLEAR; all order admission remains blocked. See [the input-context report](reports/M5_INPUT_CONTEXT.md).

Durable market-input publication now has **696 matching passing cases in each source/installed environment**, including the full Windows restart/lost-acknowledgement lifecycle. Both complete environments and aggregate verification passed; final independent review3/3 is CLEAR. Original captures survive restart as historical evidence without restoring freshness or trading authority. The next implementation is native paper admission. See [the publication report](reports/M5_MARKET_LINEAGE_PUBLICATION.md) and [admission plan](docs/M5_PAPER_ADMISSION_PLAN.md).

The daily runtime cap is removed: **27 source and 27 installed-package checks passed**. Per-job deadlines and CPU, memory and storage limits remain.

The M3 two-module validation repair passed **592 distinct matching tests in each source/installed environment**, with zero test failures, errors or skips. Both complete environment qualifications passed with unchanged Python and 38 dependencies. That frozen release contains 486 files and 190 matching product modules. Separate storage-preflight refusals are preserved and do not count as passing tests.

M5 collection retries are now integrated and independently reviewed: **521 matching required cases passed per environment**, including real non-sparse 1 GiB reserve creation and reopening. Source results combine 520 checks with explicit unchanged-code continuity and one fresh corrected test; all 521 installed checks ran against the final test release. That verified release has 496 frozen files and 192 product modules. Both complete environments qualified. See [the retry integration report](reports/M5_RETRY_INTEGRATION.md).

M5 opening-baseline integration is also verified and independently reviewed: **221 matching fresh cases passed per environment** (95 opening and 126 compatibility checks). Genuine process restart preserves the original baseline without restoring live authority. A discovered negative-cash diagnostic bug was fixed and all cases rerun. That verified release has 502 frozen files and 194 modules. See [the opening integration report](reports/M5_OPENING_INTEGRATION.md).

The market-owner repair has **394 matching passing tests in both source and installed-package environments**, including the real-process restart scenario, plus 11 source-backed native connection checks. Both complete environments and aggregate evidence verification passed. The fix preserves healthy connections after an acknowledged busy-checkpoint reply; broken connections still close. Earlier failed evidence remains preserved. Subsequent durable-lineage checks are described above; the actual walkthrough remains open. See [the repair report](reports/M5_MARKET_OWNER_REPAIR.md).

The market-input capture foundation has **225 matching passing tests per environment**. It retains one coherent snapshot and reconstructs the original diagnostic from exact bytes. Both complete environments qualified. Subsequent consumption and publication checks build on this foundation. See [the foundation report](reports/M5_MARKET_LINEAGE_FOUNDATION.md).

Original grant consumption and owner-bound capture have **291 matching passing checks per environment**. Consumption commits before collection begins; capture reads its original records from the execution owner. Private encrypted lineage storage/reopening has **243 matching passing checks per environment** and both complete environments qualified. Its final aggregate review3/3 is CLEAR. Durable publication and native recovery are covered by the newer696-case inventory above. See [the encryption report](reports/M5_MARKET_LINEAGE_ENCRYPTION.md) and [consumption report](reports/M5_MARKET_CONSUMPTION.md).

The repaired M3 release completed **63 of 63 calculations in each campaign**, with all 63 source and installed-package outputs matching exactly. Across 120 native chunks, no calculation failed or was skipped. Controls also responded during pending output verification. **All 77 audits/reviews, the Final calculation and its restart checks passed.** The source Final audit passed pause/resume and terminal restart. Four separate three-ridge calculation/audit jobs also passed, with six annual fits and exact source/package outputs. The installed-package audit was interrupted before saving its process-exit receipt and cannot be accepted or retried. M3 remains incomplete. All saved files are preserved, but a failed backup move changed directory identities; the archived runtime cannot resume. See [the interruption report](reports/M3_FINAL_INTERRUPTION.md). Work stays in master, with one heavy job at a time and memory checks. **Strata stays off.** Complete M3 acceptance remains open. See [the live checkpoint](docs/CURRENT_CHECKPOINT.md) and [required acceptance evidence](docs/M3_MASTER_ACCEPTANCE_MAP.md).

Two earlier M3 runs remain terminally blocked and preserved: the development-folder run stopped after 37 reviews, and the preceding master run after 76. Both reached a stale-health refusal before the blocked worker executed. The repairs preserve the five-second health limit and final seal checks. Earlier component coverage remains historical, not fresh coverage of the repaired release. See [the recovery report](reports/M3_INTERRUPTION_RECOVERY.md), [health repair](docs/M3_REVIEW_HEALTH_REPAIR.md) and [pair-validation repair](docs/M3_PAIR_VALIDATION_REPAIR.md).

| Milestone | Status |
| --- | --- |
| M0: Local foundation and controls | Accepted; preserved acceptance evidence |
| M1: Trustworthy research inputs | Bounded real-data replay verified; full financial input qualification open |
| M2: Strategies and mathematical checks | Synthetic components verified; financial qualification open |
| M3: Protected evaluation and audit | Repaired campaigns 63/63 each and exactly matched; 77/77 reviews and Final/restart passed; installed Final audit interrupted, acceptance open |
| M4: Simulated broker | Fake-broker engineering accepted; 662 matching source/package checks |
| M5: Supervised paper walkthrough | Retries, opening baseline and durable lineage checks verified; native admission and actual walkthrough pending |
| M6: Daily supervised operation | Evidence structure implemented; **0 of 10 actual supervised market sessions** |

```mermaid
flowchart LR
    m0["M0: accepted"] --> m1["M1: qualification open"]
    m1 --> m2["M2: synthetic checks verified"]
    m2 --> m3["M3: native verification incomplete"]
    m3 --> m4["M4: fake broker accepted"]
    m4 --> m5["M5: integration and walkthrough pending"]
    m5 --> m6["M6: 0 of 10 sessions"]
```

Engineering checks do not establish strategy acceptance or authorize account/order actions. M6 requires actual supervised market sessions.

## Next work

1. Master consolidation published and verified; keep pushing verified checkpoints.
2. M3 partial closeout and independent checks are verified; the interrupted installed Final audit remains blocked. Strata stays off.
3. M5 retries and opening baseline are verified; original failed evidence remains preserved.
4. Durable lineage, the private input context and native presence are verified and independently reviewed. Account-only inputs passed paired verification and final review. Combined-context integrity is verified; account/presence callback repair is verified; continue exact plans, risk and reconciliation under the admission plan.

[Current checklist](docs/CURRENT_CHECKPOINT.md) | [Build specification](docs/BUILD_SPEC.md) | [Cap removal](reports/DAILY_RUNTIME_CAP_REMOVAL.md) | [M0 acceptance](reports/M0_ACCEPTANCE.md) | [M4 acceptance](reports/M4_ACCEPTANCE.md)

## Checkpoints and rollback

Work in master. Commit and push completed, verified changes at each meaningful checkpoint under the owner's standing authorization. Record unfinished checks explicitly. Preserve commits; never force-push or reset history to make a checkpoint look clean. No scheduled run is needed.

Sibling folders retain historical environments and evidence. Their path-bound runtime records are not relocated or relabeled as master-folder results. Git rollback restores tracked files; runtime/data recovery requires the local backups and receipts. Historical reports may reference local evidence that is intentionally absent from GitHub.

## Storage sharing - 17 October 2026

Storage sharing passed 58 matching source and installed-package checks, with zero failures, errors, or skips per environment.
New recovery sets reuse independently copied bytes for the same unchanged artifact. Sharing survives restore.
Existing evidence, safety checks, and storage limits remain unchanged. No GiB reserve or full native project was created.
See [the remaining test sequence](docs/STORAGE_SHARING_PLAN.md) and [verification scope](reports/STORAGE_SHARING_VERIFICATION.md).
