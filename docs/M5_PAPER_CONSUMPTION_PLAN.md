# Durable paper preparation consumption

Continue the authorized offline M5 roadmap. Reuse the existing native execution owner, StateStore, reserve, intent/event tables and external attempt history. No transport, operator route or account authority in this increment. Primary owns implementation; one independent reviewer, at most three repair passes. Scratch64MiB initially; native acceptance separately admits the unchanged actual1GiB reserve.

Keep fake domain records unchanged. Add a strict PAPER_PREPARATION record and inert binding in the existing body/decision columns, distinguished by validated record_type and PAPER_ states. Preserve global256intents/attempts,512events,64KiBrecords and16MiBdatabase caps, and cross-scope intent/client uniqueness. Stable paper client IDs derive from project, alias and intent ID. Only submit/cancel preparations can be consumed; lookups never create a write intent.

Mixed attempt identity v2 is published only after intact v1 evidence and SQLite prefix verification. Preserve all old event bytes, sequence numbers and hashes. Legacy fake events remain v1; paper events use an explicit v2 schema. Missing/partial evidence blocks; no empty-history recreation. External create-only event flush then head publication precede SQLite consumption. A crash burns the attempt or compromises evidence. Receipt remains transport_authorized=False, financial_accepted=False, and never provides an effect permit.

Recovery validates both record kinds, including state/scope consistency. Reconstruct consumed paper preparations from external evidence before admitting new records; expire unconsumed preparations from old owner instances. Fake-only readers reject paper records. Restored pre-schema/pre-attempt snapshots cannot grant a second first consumption. Coordinated replacement of every retained evidence source remains undetectable locally.

Checklist:
- [x] Red tests and strict shared record codec; unchanged legacy compatibility.
- [x] Shared attempt upgrade/append, preparation facade, fake/recovery reader isolation.
- [x] Duplicate/conflicting bindings, expiry, budgets, damaged evidence and old snapshot tests.
- [x] Native crash/restart and retained-backup recovery tests using actual reserve.
- [x] Independent review, matching source/installed package checks, archive/hash receipts and checkpoint.

Next: actual grant/supervision/risk/ownership integration, bounded incident reconciliation and paper-aware recovery closure; then M6 evidence checker. Actual calls remain outside this offline component.

Verification groups are bounded at300seconds each because each combines many native fsync/recovery tests. Product request, storage-scan, peer-health and reserve limits remain unchanged. Independent review closed3/3; native crash and old-backup probes passed. Final package parity verified:1,323matching applicable passes; artifacts/m5/paper_consumption.json.
