# Next milestone action: qualify paper-account reads

11 October 2026. This is a prepared scope, not granted account authority. The owner's historical Alpaca data permission remains valid. BUILD_SPEC sections5 and16 require separate paper-account credential/read authority before the actual walkthrough. No account or order API has been called during offline M5 preparation.

First requested scope: use the existing authorized V20 Alpaca credential entries for a bounded, read-only check against https://paper-api.alpaca.markets, with $0 spending. Confirm that the credentials actually belong to the intended paper account. If they do not work there, stop with the retained failure. Do not attempt another account, sign-in, key creation or permission change. Values must remain inside execution-owned credential handling, absent from command lines, logs, exported artifacts and worker environments. OS-protected provisioning and native owner integration are now verified offline; actual credential use still requires this separate scope.

Concrete read packet: account, clock, today's calendar, all positions, and all-status orders from the beginning using25rows/page and at most8pages. Refresh the clock once before final assessment. Maximum13GET requests, fixed paper origin and allowlisted routes, no redirects, 64KiB per reply, bounded request deadlines, no write method or automatic retry. Archive minimal necessary local response provenance without secrets. If the bounded list is incomplete, report incomplete coverage rather than an empty account. Existing orders/positions are preserved and block the clean-account conclusion until explained.

Success establishes actual endpoint/account/read compatibility and a dated account observation only. Current eligible-asset mapping, SIP quote entitlement/freshness, tick size, applicable actions, fees/economic ownership and native health still require qualification. Then prepare an exact one-share opening proposal under the unchanged $250 total exposure cap. Buy, resting buy, cancellation and close each require their own concrete plan authorization under BUILD_SPEC; the read scope grants none of those actions.

Already complete and reviewable:

- Strict inert messages and retained response contracts.
- Bounded account-wide portfolio observations and cursor coverage checks.
- Opening/resting/cancel/close proposals with exact ungranted approval hashes.
- Immutable synthetic walkthrough checker, including fills during recovery/cancellation, terminal-order requirements and final quantity conservation.
- Existing M4 native fake-broker lifecycle and recovery acceptance remains historical separate evidence.

Native read integration is complete and verified offline:746matching source/package passes, actual1GiB Windows process tests, independent review closed3/3. See reports/M5_READ_OWNER.md. Synthetic evidence cannot grant real authority. Finish independent reversible roadmap preparation, then request the scoped read authority for this concrete frozen packet and execute only after that authority is granted. No new owner or second journal is needed.
