# Connect reviewed proposals to the existing research runner

## Supervised cycle preparation - 19 October 2026

The owner approved the complete cycle design and implementation plan.
Its independent record layer now passes 21 source tests and 53 contract regressions.
Authenticated cycle control and exclusive dispatch ownership now have source checks.
The final job passed 25 cases, including 21 record cases and four control cases.
Continuation and native acceptance remain unfinished. Receipt capacity blocks further source verification.
Native acceptance also awaits cleanup and a verified current environment pair.
See [the cycle progress report](../reports/SUPERVISED_RESEARCH_CYCLE_20261019.md).

The earlier registration account follows unchanged.

19 October 2026. The owner-facing registration operation and receipt repair passed fresh source verification.
All 173 required cases passed, with zero failures, errors, or skips. All three whole jobs passed.
Routine cleanup enabled fresh capacity admission within unchanged limits. Actual execution and automatic dispatch remain unfinished.
See [the current report](../reports/REGISTRATION_COMPLETION_20261019.md).

## Existing connection and proposed interface

The manual bridge saves a review plan. Synthetic campaigns already register all twelve variants before execution.
The history connection associates these records explicitly. It grants no execution authority.

The coordinator-owned operation is named `register_reviewed_campaign`.
Its inputs are the task ID, saved plan hash, request ID, new campaign ID, and checked prepared campaign artifact.
The operator must approve those exact inputs and the output allowance before registration.
Keep this approval separate from proposal acceptance and from any permission to execute.

Reuse `development_seals.create_prepared_campaign` with the existing `SavedRuns` owner and development-seal integration.
Validate the prepared artifact with `read_prepared` and preserve its existing seal and environment checks.
Do not invent a second campaign producer or accept executable proposal text.
Register every variant, persist the proposal link, and return a paused campaign.
The current plan's priorities remain review information. They cannot reduce the registered family or change its fixed schedule.

## Interrupted registration

Bind the request ID to the complete input hashes before registration.
An identical request returns the same campaign. A conflicting request fails.
Use the existing durable coordinator ownership and control records.
If a crash occurs after campaign registration, recovery completes the missing history link only.
Never start the campaign, generate a replacement ID, or abandon its history during recovery.
If evidence changed or storage failed, retain the incomplete registration and block dispatch.

The implemented operation retains the original authenticated control binding across owner generations.
Recovery requires fresh authentication for the current generation with the same operator, request ID, and approved inputs.
The original generation and approval hash remain unchanged in the durable record.
Before dispatch, bounded plan and link checks run alongside the existing campaign verification.
No transport command or automatic registration call has been enabled.

## Execution remains explicit

The owner-facing `Coordinator.start_reviewed_campaign` operation accepts a separate authenticated execution decision.
Its payload names `registration_request_id`, `run_id`, and approval `START_FIRST_RESEARCH_UNIT`.
The registration request binds the saved plan, prepared input, seal, and output allowance.
The decision binds that payload, operator, project, and current owner generation.
Research must already be running. The campaign must be paused with no attempts or outcomes.
The operation saves a consumed request before queueing the existing resume and step operations.
It starts one first unit. Completion polling stays with the existing controller.
Repeated requests return the saved receipt. A second request cannot start the same campaign.
After interruption, a fresh authenticated decision can read the original receipt without restarting work.
An uncertain pending receipt requires investigation. The action provides no automatic retry or recovery dispatch.
The controller confirms the receipt only after the existing runner reports an active job.
Prelaunch refusals leave the campaign paused. Failed receipts and uncertain launch effects remain recorded.
No transport command or automatic execution loop is enabled.

Preserve health checks, recovery checks, one-job admission, native identity checks, cancellation, and final child cleanup.
Keep the existing four-CPU maximum, 4 GiB worker limit, 120-second unit deadline, and saved-run output limits.
The same history view reads resulting attempts and checked results. It does not launch work.
Feedback, automatic revision, financial selection, and broker operations require later scope.

## Required checks before later implementation completes

- Verify duplicate requests and reject changed plan, campaign, seal, environment, or artifact bindings.
- Interrupt registration before and after campaign persistence. Recover without duplicate campaigns or execution.
- Reject unapproved execution, paused research, failed health checks, insufficient capacity, and pending recovery.
- Verify all twelve variants and the fixed schedule remain unchanged.
- Verify failed jobs and missing results remain visible through linked history.
- Record source and native integration evidence separately. Missing native proof remains unverified.
