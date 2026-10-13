# Remove the daily research runtime cap

12 October 2026. Owner instruction: "You can remove that I never OK'd that."

The daily two-hour research-job limit was a proposed spec allocation, not an owner-approved restriction. Remove it from active documentation, defaults and runtime admission. Keep elapsed-time accounting, per-job deadlines, CPU/RAM/storage limits, single-job exclusion, retries and all financial authority unchanged. Existing time charges and frozen test evidence must remain intact. The midnight continuation automation has been paused.

Acceptance checklist:
- [x] Historical daily charges no longer refuse campaign preflight or native launch.
- [x] Defaults no longer advertise a daily CPU-job cap; exact old configuration remains readable without imposing it.
- [x] Native tests prove jobs still observe deadlines, memory/thread limits, single-job exclusion and charge accounting.
- [x] Source/package behavior agrees for the new release; independent review closes material findings.
- [x] Checkpoint and tracker record the new policy and honest continuation requirements.

Verification: focused configuration checks, native jobs/campaign tests including charges above 7200 seconds, remaining resource and sealed-runtime regressions, then source/package comparison. Use fresh checked scratch under the existing runtime namespace; no limit increases. Up to three repair/review iterations for this change.

The Q campaign is bound to its previous runtime identity. Its completed 63+63 units and 61 audits remain historical evidence. Removing the cap changes package identity; do not falsify pins or mix the new runtime into that unfinished fixed run. The next complete native pair needs fresh IDs and a checked storage plan. Reuse unchanged data content, not old identity-bearing envelopes.

Pre-change files are preserved in `.cache/test-runs/m3-fresh-native-20261012-01/daily-cap-before01.zip`.

Completion: 54 passes total, exact 177-module source/package identity, no failures/errors/skips. See `reports/DAILY_RUNTIME_CAP_REMOVAL.md` and `artifacts/m3/daily_runtime_cap_removal.json`. Fresh M3 verification remains separate.
