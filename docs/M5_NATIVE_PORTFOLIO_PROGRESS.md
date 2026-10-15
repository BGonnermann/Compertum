# Native ownership and economic observations

14 October2026. Next accepted local engineering dependency after exact intents18. Implementation has not started. No actual account request, broker write, financial qualification or order authority is included.

## Checklist

- [x] Independent bounded design audit: existing opening/account/history readers support a small read-only increment; no missing owner decision.
- [ ] Finish paired verification, final review and publication of18 before changing frozen product inputs.
- [ ] Define a private reader over the intent's original retained input context and immutable opening/history references; freeze precise regression cases.
- [ ] Implement, repair, verify matching source/package cases and complete environments, then review and publish.
- [ ] Continue the separately defined actual-write history, risk and consumption dependencies; unknown producers remain blocking.

The primary agent owns implementation; one independent reviewer and at most three review/repair rounds. Preserve all failures and source bytes. Use existing job/memory/storage/deadline limits, one heavy job and fresh checked scratch. Do not start Strata, schedule work or widen broker/account authority.

## Smallest useful contract

Return private, read-only ownership/economic observations derived from the existing execution owner. Preserve the exact context retained by the native intent: constructing another account context would replace it. Validate the first opening through `paper_opening._original`, current account evidence through the existing context and history through `paper_account_binding._history`/`require_attempt_guard`. Do not instantiate journals: their constructors can initialize/recover records.

Bind complete relevant journal rows as well as the guard head. Unconsumed CHECKED/PAPER_PREPARED rows are deliberately outside attempted-record matching; the guard hash alone cannot prove an unchanged full journal. Bound/canonicalize the snapshot, classify fake/preparation/unknown records and recheck original rows before final clocks. Finish artifact/decryption/scanning callbacks before grouped original proofs and pure age/object checks. Preserve caller transactions, permanent refusal and borrowed market resources.

An empty schema created after a context was captured still changes its original history binding; it must invalidate that context. The positive empty-schema case needs a fresh qualified account packet/context, while the first opening remains unchanged. Include fake session rows in classification rather than relying only on the existing history.empty flag. Successful diagnostics must have no database effects; failure handling must retain the existing proof components' required invalidation behavior and must never commit a caller transaction.

The first positive observation means only: authenticated clean first opening, verified empty local history, complete supported current account observations, zero observed positions/orders and cash within the existing inclusive$0.01 tolerance. Never replace opening cash with a newer balance. Keep order admission BLOCKED, authority false and actual_flat=None. Missing, blocked or legacy opening remains explicit; malformed or corrupt originals refuse.

Nonempty native history cannot yet be reconciled. Actual-write records, authenticated order/fill/event coverage, fees/actions/settlement explanations and sleeve-capital history are missing producers. Fake economic records and a cmp- client-ID prefix establish no native ownership. Submission-list pagination is not fill/event coverage.

## Acceptance inventory to freeze

- Clean zero history before/after empty schema creation; original opening identity and classification.
- Inclusive±$0.01 cash tolerance, larger differences and decimal-context independence.
- Fake, inert preparation, unconsumed and unknown histories; complete row/head binding.
- Duplicate, foreign and unsupported current positions/orders; no ownership inferred from names/prefixes.
- Late artifact, row or head changes; expiry, owner/context replacement, restart, credentials and health; restoration cannot revive a refused context.
- Private bounded output; no database changes, journal initialization, network or quota effects; original intent context remains intact.

API direction from the follow-up audit: a private `_portfolio_context(context)` factory accepts only the genuine current account-only or combined input context. It borrows that exact object, retaining owner/slot/generation/binding checks; its close releases only its own references. Intent integration later passes the retained `_issued[intent_id][1]` context. No new public control is needed. A confirmed account-only context with zero observations is the positive fixture; CANCEL remains a nonempty/unattributed-target case. Operator-intent confirmation is a later independent admission gate, so read-only portfolio diagnostics may precede it. Compose portfolio durable checks with the original input proof while preserving its original pure lifetime/health tail and single-use identity; do not validate a proof and then perform later portfolio I/O. The exact private composition mechanism still needs focused design/tests before implementation.

Exact next action: complete18's393-case paired closeout, inspect actual storage headroom, then freeze this reader's API and tests against the current source. This plan is engineering preparation, not verified implementation or milestone acceptance.

## Reviewed proof composition

Keep the composition private to this module and decorate the original unused `_FinalProof` returned by the borrowed context. Retain its object identity, owner, captured database/lease/health/peer, single-use state and original closures. Under `_MUTEX`, reject a pending captured-connection transaction before calling the borrowed context's proof-preparation method. Complete artifact/decryption, arithmetic, canonicalization and secrecy callbacks before assigning decorated fields; preparation failure must leave no usable partial proof or retained sensitive closures.

The decorated durable check validates wrapper/context identity, runs the original check, rechecks the complete pinned portfolio/history snapshot with nondecrypting callback-free reads, then checks wrapper identity again. Its pure finish validates wrapper objects and calls the original finish last. Its invalidator closes the wrapper and reliably invokes the original invalidator; ordinary wrapper close releases only its own references. Never reset `_used`, validate the original proof before decoration, retain a completed proof, or reconstruct an underlying context.

`diagnostic()` consumes through existing `_verify_proofs` under `_MUTEX`, without an outer owner/store scope that could perform native reads after final clocks. A transaction opened after preparation remains open and unchanged; verification leaves the proof unused, matching existing semantics, even if `owner.db` was replaced. Grouping portfolio with presence still uses exactly two proofs.

Freeze decisive probes for original proof/resource identity and duplicate/reuse refusal; late opening/unconsumed-row mutation without guard-head change; expiry during last journal reads or scope exit; captured-connection transaction preservation; borrowed-resource lifetime and absence of I/O after final clocks. Independent read-only composition audit found this narrower approach suitable; no new proof framework is needed.

Factory qualification also requires the execution owner's database to be its current store connection. Retain that exact connection on the wrapper for pending-transaction checks even after owner-field replacement. Diagnostics expose reference hashes, counts and explicit observation statuses; raw account identifiers, credentials, cash balances and journal bodies remain private. A matching opening cash observation does not clear the separate ownership, economic-coverage, fee/action, risk or consumption requirements. Classify fake-session-only history as nonempty local evidence even though the older account-history helper excludes that table from its `empty` flag.


Current dependency:increment18 has393 source and287 installed passing cases, with106 installed cases blocked by production storage admission. Reader implementation has not begun. The owner approved continuation through full ownership/accounting and integrated local rehearsal; this empty-opening reader alone will not close gate2. Preserve the seven pending18 groups and resolve infrastructure admission before starting native verification.
