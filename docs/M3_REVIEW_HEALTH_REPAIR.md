# M3 review health repair

13 October 2026. Authorized supporting repair in the master folder. Strata stays off. No account, order, protected-data or spending authority is added.

## Evidence and scope

The frozen release completed both63-outcome campaigns with exact mathematical agreement and37 of77 audits/reviews. Source aggregate task8d72907c-5f3e-575a-80e9-942342886ac1 failed HEALTH_UNVERIFIED before native admission. Its recorded attempt is BLOCKED/LAUNCH_FAILED; its unused output reservation is ABANDONED. The state/history and SQLite/WAL snapshot are preserved in the master recovery evidence namespace. This task cannot resume under existing rules. A new code release must use new campaign identities and independent evidence; never reset or repin this failed run.

Repeated synchronous dependency validation prevents the Supervisor loop from updating its cached health. The commit check refuses health older than five seconds. Inspection also found more validation after that check, before ResumeThread. The failed driver took13.77seconds overall; this does not measure individual preparation phases. Mutual peer health separately latches failure after15seconds, so a late refresh cannot repair an interval that already crossed that limit.

## Checklist and acceptance

- [x] Preserve failed aggregate, inspect current state and close the original runner. No native phase after the source aggregate is accepted.
- [x] Review frozen regression coverage:545 historical and93 fresh master cases cover601 distinct IDs per environment. The existing218 negative/control IDs are absent from both sets.
- [x] Archive and verify two passing master basetemps before removing their copies. Failed fixtures remain untouched. Native storage admission passed1.85seconds afterward.
- [x] Run the exact218 cases serially in source and installed modes against the unchanged frozen release; source03 and installed01 each passed218 with zero failures/errors/skips and identical IDs. Frozen483 inputs and190 modules matched. Fresh master coverage is311 distinct cases/lane; combined historical/current coverage819/lane.
- [x] Reproduce stale health before editing product source:source_red01 failed HEALTH_UNVERIFIED at commit after real5.2second preparation delay; native descendants all exited.
- [ ] Add scoped authenticated health refresh for review commit and final launch checks. Ordinary cached health checks, public status behavior, failure transitions and deadlines remain unchanged.
- [ ] Verify slow healthy preparation, unhealthy/replayed health refusal, final deadline/startup/owner/seal checks and native child closure. Verify ordinary Final completion does not acquire refresh-driven reentrancy.
- [ ] Review the repair and run affected source/installed regression checks. Maximum3 repair/review iterations for this coherent change.
- [ ] Freeze a new master release and complete fresh native evidence before synthetic M3 acceptance. Keep the old successful outputs and failed aggregate explicitly historical.

The additional native test runner requires16GiB available physical and commit headroom to start and stops below12GiB. Product worker limits remain4GiB, four CPUs and120seconds; source/package tests remain serial. Test scratch stays in checked master namespaces under the5GiB category limit. No scheduled run is created.

## Current next action

Inspect source_green01's10 focused tests, complete independent product review, then build and check the installed package and affected regressions. The repair touches Coordinator, Supervisor wiring, CampaignReviewController and the native job launch checks, plus two fixture stubs. Source01 of the218-case set was interrupted by a SQLite WAL inventory race; source02 produced217pass/1fail because restricted IPC denied the child connection. Native IPC runs source03 and installed01 passed. All earlier failures remain preserved.
