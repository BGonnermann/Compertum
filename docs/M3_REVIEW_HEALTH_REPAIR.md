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
- [x] Add scoped authenticated health refresh for review commit and final launch checks. Ordinary cached health checks, public status behavior, failure transitions and deadlines remain unchanged.
- [x] Verify slow healthy preparation, unhealthy/replayed health refusal, final deadline/startup/owner/seal checks and native child closure. Verify ordinary Final completion does not acquire refresh-driven reentrancy.
- [x] Review the repair and run affected source/installed regression checks:344 distinct cases/lane passed. Maximum3 repair/review iterations for this coherent change.
- [ ] Repeat the218 negative/control cases on this repaired release, then verify the exact562 distinct IDs per lane.
- [ ] Freeze a new master release and complete fresh native evidence before synthetic M3 acceptance. Keep the old successful outputs and failed aggregate explicitly historical.

The additional native test runner requires16GiB available physical and commit headroom to start and stops below12GiB. Product worker limits remain4GiB, four CPUs and120seconds; source/package tests remain serial. Test scratch stays in checked master namespaces under the5GiB category limit. No scheduled run is created.

## Current next action

All70 affected native cases passed in source and installed lanes, zero failures/errors/skips and no remaining children. The218 negative/control cases now run serially in session69091 before new master M3 campaign identities. Focused repair checks passed12/12 in both lanes; affected component checks passed262/262 in both lanes, zero failures/errors/skips. All190 installed modules match source. The first component run retained261pass/1fail:an older Supervisor test bypassed initialization and omitted the existing final_audit field; only that fixture was corrected. Product/verification review cleared2/3. Native sequence60053 exited0; combined repair coverage is344 distinct cases per lane. Local native receipt:artifacts/m3/review_health_native_verification.json. The repair changes four product modules and three existing fixture files, adding two test files. The frozen218-case failures and all repair failures remain preserved.

Local verified component receipt:artifacts/m3/review_health_component_verification.json. Source archive bfb503b57e11a9cd3f2c12c09ccc64e92d514fdaad2ae82155b6100f21f1b4e7; wheel8541d802ab8d2317b125814b2dc63e34c43abc734991c9645a5e589648d30a0c. The focused12 checks used the preceding archive; the only later difference is the unrelated Supervisor test fixture, with product and focused inputs unchanged.

Six inactive8October test folders were moved reversibly within master to backups/historical-test-folders-20261013-01. All2,929 file hashes,1,839 directory identities and291 link records matched. No files were deleted; two known failures and four unattributed historical results remain distinct. Absolute links retain their former targets, so these are historical evidence and must be restored to their original paths before any supported reuse. Preservation review cleared2/3. Native storage admission passed4.436seconds after the move, with3,406,212,032 scratch bytes and1,737,862,104 backup bytes. The5GiB scratch and20GiB backup limits are unchanged.
