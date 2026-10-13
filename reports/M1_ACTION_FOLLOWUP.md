# M1 action follow-up

10 October 2026 ET. **Evidence checks passed; full M1 remains incomplete.** Product source and project environments are unchanged.

- Added 67 source observations: 32 P&G, 32 NVIDIA and three UnitedHealth.
- Linked 66 more provider dividends, bringing coverage to 272 of 317. The remaining 45 are UnitedHealth (14) and ExxonMobil (31).
- Supplied 71 more missing record/payment dates in separate evidence. Both passes now supply 272 dates. The original provider records still lack 29 record dates, 29 payment dates and 165 CUSIPs after supported fills.
- Linked eight NVIDIA tax-form payment observations and three UnitedHealth partial records. These links do not establish exact cash amounts or complete identity coverage.
- Passed 127 checks in each environment, reproduced the actual output exactly, and completed independent review with no material findings.

## Unresolved evidence

NVIDIA has 22 amount conflicts. Nineteen are compatible with dividing the raw provider amount by four; three would also require rounding. This is a diagnostic observation, not an accepted adjustment rule. Original amounts remain unchanged.

Two UnitedHealth announcements have successful original HTTP bodies. The third, for September 2019, comes from a cached primary-page search extraction; direct access now redirects. Its recorded retrieval timestamp is an approximate research-batch time, not HTTP timing or original publication time. Fourteen older events remain unbound. Secondary sources suggest two more record-date disagreements, which remain research leads.

UnitedHealth's official 2016 annual report confirms common stock listed on NYSE under UNH (PDF page 31, printed page 29). One report does not establish daily broker tradability, provider asset IDs, complete lifecycle coverage or a dated sector table.

Twelve public requests produced nine HTTP 200 responses, one redirect, one denial and one timeout. All responses and failures are retained. Denied endpoints were not retried or authenticated. ExxonMobil's dated releases remain an available route after its public table denied access.

The initial test run passed 126 checks and failed one test whose expectation incorrectly assigned both missing declaration dates to P&G. Raw source rows showed one P&G and one NVIDIA record. The corrected source-backed expectation passed; extraction and acceptance rules were unchanged.

## Next action

Use dated ExxonMobil releases for its 31 unmatched events and raw NVIDIA announcements for amount verification. Preserve the 14 UnitedHealth gaps. Qualify identity, tradability and dated sectors before collecting warmup data and integrating a real Snapshot. Existing credential/SIP approvals remain resolved; protocol adoption is still required before sealing or strategy execution.

Receipt: artifacts/m1/action_followup.json. Data: data/action-followup-20261010-01. Scripts, tests and review: .cache/test-runs/m1-action-followup-20261010-01. Earlier artifacts remain immutable. No spending, deletion, credential use, account/order calls, protected-price requests, training, Strata changes or publication.
