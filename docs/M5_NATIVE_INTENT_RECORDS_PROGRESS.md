# Exact native intent records

14 October 2026. Next local engineering dependency after account-only increment14. Implements the existing [native intent contract](M5_NATIVE_INTENT_PROGRESS.md); no account request, order, cancellation or transport authority is granted.

## Checklist

- [x] Independent design audit identified concrete reuse and no missing owner decision.
- [x] Finish account-only14 review and publication (`0bc6758`).
- [x] Reproduce and repair the shared corruption paths in the existing combined context under [integrity repair15](M5_INPUT_INTEGRITY_PROGRESS.md).
- [x] Repair the analogous account-only/presence callback gaps under [the targeted prerequisite](M5_ACCOUNT_PRESENCE_INTEGRITY_PROGRESS.md).
- [ ] Freeze failing tests for exact terms, immutable intent/confirmation and permanent invalidation.
- [ ] Implement the minimal owner component and authenticated routing; verify targeted repairs.
- [ ] Verify identical source/package inventories, complete environments and aggregate evidence; independent final review and publication.
- [ ] Continue ownership/economic/risk readers before consumption or dispatch.

The primary agent writes and integrates. One independent reviewer, at most three review/repair rounds for this increment. Preserve all failed cases and source archives. Native tests use the existing120-second/4-GiB/four-CPU/16-process limits,16/12-GiB host gates,128-MiB namespaces, five-second runtime storage scan and50-GiB category budget. One heavy job; no Strata or scheduled work. Full-reserve routing acceptance requires a separately admitted lifecycle; component routing tests must label simulated capacity.

## Concrete design

Attach a private component to `PaperReadOwner`. Supervisor supplies authenticated request and subject identities to prepare, confirm and inspect. Both native launch/endpoint command lists must match; checkpoint barriers apply; inspect bypasses stored-response caching.

Use separate immutable intent and confirmation records plus irreversible invalidation. Bind exact canonical purpose/terms, project/subject/alias/private-identity hash, credential hash, owner generation/instance/component, original input references and stable binding, original presence ID/hash, owner-measured UTC/monotonic creation and fixed expiry. Return historical duplicate receipts without asserting current validity. Conflict or a second different confirmation cannot rewrite the first.

Keep the actual private input context created at preparation. Confirmation and inspection revalidate that object; recreating it would replace the original and cannot renew evidence. A narrow private presence resolver must preserve the existing revocation behavior. Never use the public presence-status string or fake operator session as proof.

CANCEL uses account-only inputs and exact proposed target identity. Other purposes use their required combined inputs and separate fixture, strategy and close terms. Requested target/quantity remains proposed until ownership/risk readers qualify it. Original account/quote freshness remains30seconds. Pre-start expiry is at most creation+60seconds, original presence expiry and applicable verified window; confirmation never extends it. CLOSE_LONG retains at most12 children/10minutes ending earlier at session close. Fixture terms retain one whole share/$250 exposure; strategy terms retain candidate/version/protocol identity. No timed order exchange is constructed while waiting.

Create schema atomically with version and bounded histories. Check insert counts and exact readbacks. Run all diagnostic/decryption/secrecy/health callbacks before INSERT: those callbacks can commit their own halt on the shared connection. Only durable readbacks and pure identity/age checks follow insertion. Original records, in-memory issued identities and independent invalidation prevent restoration from reviving authority. Restart exposes historical evidence only.

Do not initialize `PaperIntentJournal`, append an attempt guard, modify fake/preparation record identities or dispatch. All outputs keep order admission BLOCKED and transport/financial authority false while required producers are absent.

The increment18 transaction adapter remains private and call-local. Hold `_MUTEX`; reject an existing caller transaction. After all callbacks, retain the original proofs' read-only checks, pure finishes and invalidators locally, consume them normally with grouped `_verify_proofs`, then begin only the adapter's own transaction. After checked INSERT/readback, run all retained durable checks and original native peer checks; complete every owner/store scope exit before pure lifetime/health checks and commit. Roll back before invalidation on failure; clear retained closures unconditionally. Never reset or reuse consumed proof objects, store these closures on an intent, or recreate contexts. The new owner handler must not wrap this final boundary in another owner/store scope whose exit performs later native reads. Return a prebuilt historical receipt, never current transport authority. Tests must cover trigger-induced alias/presence mutation, elapsed post-insert reads and rollback before durable revocation.

## Required evidence

Cover purpose/term validation; subject/account/input/presence substitutions; CANCEL without market; exact confirmation and conflicts; historical duplicates; age/expiry/service-gap boundaries and nonrevival; owner/context restart/replacement; corrupt/partial schema and ignored writes; mutation during callbacks; actual durable health-halt callbacks; private bounded output; zero HTTP/quota/attempt effects; matching native allowlists and uncached inspection. Pin code, tests and helpers before every run. Final review checks the actual paired evidence, not planned counts.

Exact next action: close combined-context integrity15, reproduce/repair the analogous account-only and presence gaps, then activate exact-intent acceptance tests before changing its product code.

Bounded integration audit confirmed owner lifecycle hooks, Supervisor ACTIONS/dispatch/uncached inspection, both native allowlists and domain capability must change together. Presence binds subject/account/credentials/generation but may precede a newer account packet; packet IDs need not match. Apply account-only CANCEL and combined fresh-quote/liquidity inputs for CLOSE_LONG; neither inherits strategy qualification or the09:35 entry window. Proposed targets/quantities remain unqualified until ownership/risk readers exist. Preserve context replacement as permanent invalidation, historical duplicate receipts and zero journal/attempt/HTTP effects. No missing owner decision was found.

Integrity15 and account/presence16 are verified. Latest16 pair:222 cases per environment, zero failures/errors/skips, complete environments and final review2/3 CLEAR. The immediate supporting implementation is the private final-proof interface17, followed by exact native records; ownership/risk and actual actions remain separate downstream gates.

Private final-proof prerequisite17 is verified:277 matching source/package cases, complete environments and final aggregate review CLEAR. Exact record integration must call grouped _verify_proofs(context_proof,presence_proof) after all callbacks and before insertion. Original contexts cannot be recreated at confirmation. Next: freeze exact native record tests and implement the owner component plus authenticated routing.
