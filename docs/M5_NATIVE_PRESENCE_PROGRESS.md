# Native operator presence

14 October 2026. Next bounded dependency after increment12. Implement native presence first, then exact intent/confirmation; these are separate dependencies within the existing admission scope. No order start, dispatch, strategy arm, cancellation or closing is enabled by presence.

## Contract

Attach a private presence component to `PaperReadOwner`, using its existing execution store, exclusive lease, reserve and mutual health. Add one authenticated `paper_presence` control route. The supervisor supplies subject and request identity from its native decision, never caller payload; worker routes remain denied. Inspect/status bypass coordinator response caching and recheck current records. The existing managed-owner checkpoint barrier applies.

An acknowledgement names an already published, currently confirmed account packet and its original manifest. Resolve private identity, alias and credential envelope from original records, with current native provenance and health. It needs no market quote or strategy arm. Persist a bounded, separately versioned immutable presence record plus checked request binding/readback. Bind project, subject, account alias, private identity hash, credential hash, execution generation/instance, private component lifetime, original packet/confirmation, original wall/monotonic times and fixed five-minute expiry. Never publish credentials or private account IDs. Presence is an observation of the authenticated operator, not permission for any broker action.

The initial acknowledgement requires an actual recorded confirmation and fresh native account observation; a proposed/unconfirmed packet cannot qualify. Later inspection verifies the original records and current identity/credential/owner binding without requiring the original30-second observation to remain fresh. Ordinary same-account packet replacement preserves presence when those bindings remain unchanged. Fresh account reconciliation remains a separate future action gate. Holdings, orders, negative cash, a closed market, ordinary HALTED/DISARMED admission, or an absent market producer do not by themselves deny presence. Lost mutual health or a retained health halt still denies it. Do not require an empty deficiency list or clean opening.

Identical duplicate acknowledgements return the original receipt without extending its lifetime; a conflicting subject or payload refuses. Inspection reports current validity separately from the immutable acknowledgement. Expiry at300seconds, reverse clocks, cumulative disagreement over5seconds, service gaps over15seconds, lost health, component replacement, restart, account identity or credentials changing permanently invalidate that receipt. A later acknowledgement must use a new identity and never revives an older receipt. Preserve records through restart. Do not clear retained health halts. Keep the current presence distinct from future disjoint fixture/strategy/cancel/close intent confirmation.

Acknowledgement receipts always describe historical recording and never claim current validity, including coordinator replay after expiry/restart. A separate uncached inspection is the only current validity response. Add explicit replay-after-expiry/restart, same-account packet replacement, holdings/orders and market-closed cases. Independent design review supports this presence-only scope with these distinctions; it makes no implementation or test claim.

Acceptance: authenticated routing and worker denial; original confirmed account provenance; no market prerequisite; no broker requests/attempts/quota consumption; same-request replay and conflicts; exact expiry boundary; clock reversal/gap/drift and no revival; health/credential/alias/owner replacement; historical inspection after restart; corrupt/partial schema, malformed records and ignored writes; failed transactions do not create partial receipts; late expiry/invalidation while verifying; bounded redacted results; uncached public status. Component fixtures explicitly label invented account origins/clocks and simulated reserve capacity. Full-reserve native routing acceptance requires separate storage admission.

Use existing120second/4GiB/fourCPU/16process jobs,16/12GiB host gates, five-second storage scan and50GiB category budget. One heavy job and one independent reviewer, at most three evidence-led review/repair iterations. Freeze exact original source/test inputs before every run; retain failed artifacts. Verify matching source/package inventories, full environment identities and aggregate receipts before publishing. Stop only for a genuine resource/authority blocker or the iteration/execution limit; continue independent accepted work when possible.

## Checklist

- [ ] Finish and publish increment12 first; do not mutate its frozen source during checks.
- [ ] Finalize native presence records/API and exact initial cases; reproduce missing behavior.
- [ ] Implement presence with checked persistence, authentication and lifetime invalidation.
- [ ] Verify source/package compatibility and real native routing where storage permits; review and publish.
- [ ] Continue exact immutable intent/confirmation and its account-only cancellation input dependency.

Exact next action: complete increment12 aggregate/final review/publication, then freeze native presence acceptance tests. This file records a design, not implemented behavior or milestone acceptance.
