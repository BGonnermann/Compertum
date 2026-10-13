# Native synthetic campaign

149 unique source and 149 installed-package checks passed, with zero failures, errors or skips in accepted runs. The frozen base passed 146 checks per lane; the final owner-error repair passed 25 targeted checks per lane (22 repeated regressions plus 3 new checks). All 63 units per lane below use the final release. This includes 28 native campaign checks (four abrupt owner-crash cases), 16 legacy Windows Job/replay checks and 105 worker/schema/owner/framing checks. Both environments completed the same 63 native units: 27 fits and 36 evaluations, 63 attempts and no failed/skipped units. Every framed output, payload and final scorecard matched exactly.

Recovery covers before fit computation, after publication before commitment, after fit commitment and a resumed evaluation worker entering computation with a saved fit. Orphans remain preserved; committed models never refit; stop survives restart. Admission requires the exact READY-to-RUNNING transition before resume, and duplicate dispatch is refused. Source/wheel runs retained 4 threads, 4 GiB, 120 seconds per unit, 16 MiB outputs, 128 MiB per campaign and 7200 seconds daily Job budget.

Independent review approved after retained red/green repairs. Health controls were represented by explicit fixture doubles; transient exit-code routing used injected receipts. Native process limits, invalid handles, crash exits and artifact equality were exercised directly. This is engineering evidence, not full M2 financial acceptance. Full real-data/protocol qualification remains open.

Receipt: artifacts/m2/native_campaign.json. Next: docs/M3_SYNTHETIC_EVALUATION_PLAN.md, then docs/M4_FAKE_BROKER_ENGINEERING_PLAN.md.
