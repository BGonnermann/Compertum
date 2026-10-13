# Pair-validation repair

13 October 2026. Native session48305 stopped with exit1 after76 successful audits/reviews. Source and installed campaigns still have63 exact matching outputs, and both aggregate reviews passed. The paired comparison is terminally BLOCKED, reason LAUNCH_FAILED; its native identity was bound but the worker was not resumed. Final was not started. Preserve this runtime and all its identities.

The observed refusal is HEALTH_UNVERIFIED at runtime/jobs.py's final cached-health check after full review validation and startup-image verification. The five-second freshness rule correctly refused execution. The preceding repair refreshed health before that validation; it did not make the validation itself fast enough.

A read-only cProfile diagnostic of the frozen pair measured4.878seconds for current-input validation: nine registration calls, seven current calls, six completed calls, eight source snapshots and four unit-audit collections. Profiling adds overhead; this is not a native launch-time measurement. The diagnostic bypasses only the live-owner assertion to inspect a read-only snapshot and grants no authority or acceptance. Pair registration currently rebuilds each aggregate's validation context immediately after completed() already rebuilt and verified it.

## Checklist

- [x] Preserve the failed command, driver/child logs, signals, database/WAL/SHM snapshot, blocked task history and reservations. Last reservation is ABANDONED; no worker result is claimed.
- [x] Identify repeated validation from source and read-only timing evidence.
- [x] Independently review the minimum correction and evidence-continuity implications. Product review pass1 cleared the two-module correction; an older test fixture was adapted without removing its nine failure cases.
- [x] Add a meaningful regression, make the targeted correction, retain all seal/input/owner/deadline checks and the five-second freshness rule. Four focused cases passed; the corrected pre-repair fixture retained two expected failures and two already-passing seal-refusal cases.
- [ ] Verify changed paths, actual pair-scale timing, negative controls and source/installed consistency. Preserve every failure; no rerun until new evidence supports the approach.
- [ ] Reconcile frozen identities before new native admission; never reset or repin the blocked runtime. Finish the remaining Final/auditor/three-ridge sequence on valid evidence, then M5 dependencies.

Local evidence: .cache/test-runs/m3-pair-validation-repair-20261013-01/failure-state01.json, blocked-snapshot01, profile-validation01.json and profile-validation01.log. Original command/results remain in m3-master-native-20261013-01. No Strata launch, threshold relaxation, scheduled automation or financial acceptance is included.

## Repair verification in progress

Source components passed52/52 and the first native group passed14/14, zero failures/errors/skips; all child exits were observed. These are66 distinct tests on the current two-module repair. The earlier source component attempt retained51pass/1fail because Windows sandbox access denied a named-pipe operation (CreateFileW error5); the authorized native-access run passed all52. The prior562-per-lane receipt covers the preceding frozen release and is not current paired verification of this repair.

The separate read-only old/new workload comparison passed with identical header, request, metadata, record and native-provenance hashes. Baseline samples were3.841/3.709seconds; repaired samples2.061/2.020seconds. Source snapshots fell8to4 and unit-audit collections4to2, with six seal checks retained, including the two late checks. These are unprofiled diagnostic timings, not campaign acceptance. The old-snapshot diagnostic explicitly bypasses live ownership and substitutes only the obsolete package digest after recomputing real runtime identity; those overrides remain confined to its child process.

Fresh source launch-stress probe source_stress02 passed result acceptance. The native final health check occurred3.306042seconds after the real observation; ResumeThread at3.306202seconds. Startup verification took0.000326seconds. The worker exited0, no active processes remained, and all worker/diagnostic child exits were observed. The unchanged five-second rule decided admission. This is a fresh native launch under the diagnostic workload, not the full63-unit pair's current-release acceptance. Receipt: artifacts/m3/pair_validation_launch_stress.json.

Preserved probe source_stress01 also passed launch but failed result acceptance: its unreserved workload report was mistakenly written inside the monitored fixture, causing UNACCOUNTED_GROWTH. The corrected probe writes outside that fixture while remaining inside the admitted outer scratch namespace. Product storage checks were unchanged. One later invocation used an incorrect plan digest and was refused before any process or receipt was created; the verified digest was then used.

Next: finish source/installed regressions and unchanged health-refusal controls, freeze and qualify the repaired release, then prepare fresh full-run identities with a new storage admission. Neither blocked runtime may be resumed, reset or repinned.
