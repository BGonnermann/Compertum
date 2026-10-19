# Connect reviewed proposals to the existing research runner

19 October 2026. Preparation only. Automatic registration and dispatch remain unfinished.

## Existing connection and proposed interface

The manual bridge saves a review plan. Synthetic campaigns already register all twelve variants before execution.
The history connection associates these records explicitly. It grants no execution authority.

Add a later coordinator-owned operation named `register_reviewed_campaign`.
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

## Execution remains explicit

After successful registration and separate execution approval, use `ResearchController.control` with the existing resume and step operations.
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
