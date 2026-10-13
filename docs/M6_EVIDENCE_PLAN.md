# M6 immutable evidence preparation

Scope: offline preparation under the existing autonomous roadmap authority. Requirements remain in M6_EVIDENCE_REQUIREMENTS.md; no actual account calls or milestone acceptance.

1. [x] Verify bounded canonical manifest and complete transitive artifact closure: exact IDs, bytes, hashes, sizes, identity bindings, roots, counts and sequence ranges. Reject missing, extra, conflicting or malformed evidence.
2. [x] Verify session chronology and a ten-session XNYS window against the installed calendar, with holiday, early-close and daylight-saving cases. Reject future/incomplete, duplicate or skipped sessions. Preserve legitimate no-order sessions.
3. [x] Prove all provenance labels, including an untrusted actual-paper claim, yield zero verified actual sessions. Explicitly retain missing native semantic verification and the two unresolved acceptance predicates.
4. [x] Independent bounded review, repairs and paired source/installed-package checks; save source, wheel and exact replay receipts.
5. [ ] Connect native semantic readers after M5 produces the actual supervision/order/ledger/restore/AI-off records. Derive coverage and reconciliation from those records. Do not invent a second producer or accept caller-provided healthy/complete flags.

The current increment implements items 1-4, the reusable manifest/closure/calendar foundation. Item 5 depends on the remaining M5 owner integration. Opaque payloads are hash-bound but their business meaning is explicitly UNVERIFIED. A structurally complete packet can never establish an actual supervised day, recovery operation, AI-off exercise or financial acceptance.

Bounds: one canonical JSON manifest and each artifact at most 64 KiB; at most 128 artifacts per session (8 MiB), graph depth at most 16; exactly ten entries per window, processed one session at a time. These are engineering parser bounds, not operating-day acceptance thresholds. Reuse existing strict JSON, immutable bytes and XNYS calendar. No extra database, owner, transport, scheduler or dependency.

Manifest freezes project/account alias/private-context digest, session ID/date/operating interval, calendar package version, code/lock/config digests, preceding session reference, and all required input/supervision/order/ledger/incident/closing roots. Recovery and AI-off roots may be absent but stay unverified. Root payload counts and pages are structural assertions; they do not prove that a producer omitted no events. Actual qualification remains unavailable until trusted producers and semantic readers exist.

Verification: 231 matching passes per environment, three exact replay cases and independent review CLOSED 3/3. artifacts/m6/session_evidence.json. Native semantic readers remain pending.
