# Durable paper opening baseline

12 October 2026. Bounded local M5 continuation under the owner's autonomous roadmap instruction. Reuse the existing execution owner, account attestation, state table and encrypted read evidence. Actual account permission and concrete order plans remain separate.

Purpose: preserve the first confirmed clean paper-account observation so later reads cannot silently replace starting cash or adopt foreign activity. This is a pretrade baseline. It does not settle post-trade fills, fees, actions or economic NAV and does not clear the complete reconciliation gate.

Design under bounded independent review:

- Couple the opening reference to the first alias confirmation in the existing SQLite transaction. Reference the exact proposal, first packet, published manifest, private identity and credential digests, confirmation time and verified zero-attempt history. No plaintext cash, private UUID, new file journal or copied raw response.
- Record a blocked opening when the first confirmation has unexplained positions/orders, nonzero or invalid local history, blocked account or invalid cash. Account identity can still be attested. A later empty read never silently replaces that reference.
- A missing opening for an existing confirmed alias is legacy/unverified, not a fresh baseline. Missing or corrupt artifacts, guards or publication records remain errors; no read initializes or repairs them.
- A private reader derives starting cash from the original encrypted artifact, verifies its exact durable links, and separately checks fresh current confirmed context. Current account/credentials, empty holdings/orders and zero local history must match; cash differences over $0.01 require explanation under the unchanged build specification. A tolerated one-cent difference never changes starting cash.
- Historical verification after restart preserves provenance only. Every use that needs current qualification must recheck native owner, health/reserve, current confirmation, original observation age and credentials, including after artifact validation. No cache restores freshness, arms or permission.
- Keep existing blocked preflight and public identity behavior. New diagnostic outputs remain bounded and redacted. There is no new transport, caller-supplied cash, trusted origin flag, operator grant, or order effect.

Material assumption: an unexplained initial account observation is terminal for this automatic clean-opening path. Resolving it requires a later explicit reconciliation increment; this component must not invent a fresh baseline after the unexplained state disappears.

Checklist:

- [x] Close design review, maximum three passes.
- [x] Admit separate staging from frozen retry R, preserving active Q and R archives.
- [ ] Write failing tests, then smallest implementation and targeted repair.
- [ ] Test first confirmation atomicity; exact repeated confirmation; corrupt/missing opening/guard/publication; cash thresholds; foreign holdings/orders; changed account/credentials; stale context during verification; interruption and restart; privacy and fake-broker compatibility.
- [ ] Independent code review, maximum three passes per review scope; retain every failure.
- [ ] After M3 ends, integrate verified dependencies and run applicable current-source/installed-package tests, exact replays and native Windows checks in fresh admitted namespaces.

Verification boundary: pure/in-memory tests may run while M3 is active. Further native filesystem/process/network fixture suites are serialized with M3 because concurrent test directories caused two final storage scan timeouts. No required check is dropped. Native loopback or injected PAPER_TLS tests never prove actual account acceptance. No new spending, actual requests, credentials, publication or unrelated environment changes.

Exact next action: resolve the independent design review, then stage the source under an admitted bounded namespace. Do not edit the active source/package before M3 campaign, audits and Final complete.

Design review CLOSED on pass2. Recovery safeguard: new opening creation requires the original execution database and no active-generation pointer, generations directory, restore-operation.json, restore-*.jsonl or aborted-pointer-*.json marker. Inspect only bounded direct state entries and fail closed on unreadable/unexpected types. Recheck inside the confirmation transaction. Normal owner process generation increments alone do not block. Existing restored pins can supply historical provenance only until fresh current confirmation is verified. No attempt-guard advancement or new recovery schema.

Staging admitted at04:51:57UTC: .cache/test-runs/m5-paper-opening-staging-20261012-01,8MiB,462 files copied exactly from frozen retry R archive. All452activeQ files unchanged. Storage scan4.516seconds, all outstanding M3/retry envelopes reserved; RAM46,423,343,104bytes. Pure/in-memory work only while M3 runs. Detailed admission.json retained in that namespace.


Staged code review CLOSED2/3 at 2026-10-12T05:06:54.868715+00:00. Final pure/in-memory run81passed/0failed/error/skip. Retained original failures: missing module; alias compatibility; two fixture-unpack errors and zero-history schema transition; hostile Decimal context2failures; secret-reflection2failures. Repairs preserve64character alias contract, compare zero guard evidence across empty schema initialization, use explicit bounded Decimal context, and scan exact pinned credentials before opening-reference writes and on reads. Native fixtures prepared, not run; positive origin/health in policy tests explicitly injected. Staged archive 0e075259e267c09bb0018001e0d91e420e105190534a1efee6397701b5e908ce; active Q and prior retry R byte-for-byte unchanged. Next action remains finish M3 then dependency integration/native and source/package verification.
