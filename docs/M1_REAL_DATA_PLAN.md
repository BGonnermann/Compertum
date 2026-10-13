# Approved M1 real-data verification checklist

Updated 9 October 2026 ET. Owner authorized the read-only $0 increment, existing V20 credentials and historical SIP. Those decisions are resolved.

- [x] Freeze development-only manifests and check storage.
- [x] Verify connector/direct access without exposing secrets or modifying V20.
- [x] Retain original raw/split bodies and complete pagination.
- [x] Verify SIP exact references: 104/104 per adjustment, all four IEX gaps resolved.
- [x] Implement and test strict provider evidence parsing and exact raw-bar split normalization; future splits cannot change earlier output.
- [x] Corroborate supported terms of 11 action records with official sources; preserve missing coverage/timing facts explicitly.
- [x] Independent code review, targeted repairs, source/wheel verification, preservation checks and durable checkpoint.
- [ ] Comprehensive real action/mapping/eligibility coverage and full warmup. The bounded sample does not provide these.
- [ ] Qualified immutable real snapshot and real-provider integration, after the complete input contract is viable.
- [ ] Owner-adopted sealed protocol, all three real baseline horizons, base/stressed costs and reproducibility.
- [ ] Full M1 acceptance and every required deliberate failure case.

Current increment: complete. Full M1: incomplete. The reader returns engineering evidence, not a financially accepted Snapshot. No missing action data are silently treated as zero actions; historical availability remains unverified.

Fresh evidence: [SIP report](../reports/M1_SIP_DATA_EVIDENCE.md), [receipt](../artifacts/m1/sip_data_evidence.json), [action review](../reports/M1_ACTION_EVIDENCE.md), [checkpoint](CURRENT_CHECKPOINT.md). Earlier IEX/connector reports remain unchanged historical evidence. No new spending, orders/account calls, protected prices, training, Strata changes, publishing or deletion.

10October2026 ET: follow-on action evidence checks complete:329 unique actions,32 SPY issuer observations,177 source and122 installed-wheel passes. Real-data qualification remains unresolved after targeted rechecks. Detailed missing fields, source conflict, identity/knowledge limits and next dependency: reports/M1_ACTION_QUALIFICATION.md and docs/CURRENT_CHECKPOINT.md.
