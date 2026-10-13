# M4 owner-health checkpoint

11 October 2026. D=.cache/test-runs/m4-owner-health-20261011-01; E=.cache/test-runs/m4-owner-full-reserve-20261011-01.

- [x] Prior recovery:313 matching source/package passes; reports/M4_FAKE_EXECUTION_RECOVERY.md.
- [x] Verified old passing reserve/archive duplicate removed only after exclusive/hash checks. C/passed-reserve-cleanup01.json. Scratch3.90GiB/5GiB before new full-size test; global caps unchanged.
- [x] Mutual health implemented through existing supervisor-bound channels, exact peer native identity, sequence/timestamp freshness, 15second timeout, cumulative clock drift and sticky disarm. Actual reserve/SQLite durability checks.
- [x] Six review regressions reproduced then repaired: clock drift, numeric identity substitution, out-of-order timestamp, two negative acknowledgment cases and missing initial execution heartbeat. review-green02:26passes.
- [x] Initial native actual1GiB reserve/expiry/disarmed restart passed(native-source01); archived/hash-verified before removal. Original source predates final review repairs, so final repeat remains required.
- [x] Full Supervisor relay/execution exit passed(supervisor-exit-source01); archived/hash-verified before removal.
- [ ] Full Supervisor watchdog-exit source run started(watchdog-exit-source01); inspect final receipt then archive only on pass.
- [ ] Added first-missing-peer native test, small-reserve rejection, SQLite downgrade and lightweight import checks; final affected suite and independent closure pending.
- [ ] Freeze/build/install; repeat identical small checks and three separate full-reserve scenarios, cleaning only passed copies between allocations. Fresh capacity admission before each actual allocation.
- [ ] Persist owner session/operator/plan/start/progression controls, remaining M4 integration, native final numerical work if resources permit. M5 needs concrete account/order authority; M6 needs elapsed supervised sessions.

Exact next action: inspect watchdog-exit-source01, run new affected source regressions, close narrow reviewer findings, freeze the resulting source. No financial or fullM4 acceptance claim. Failed fixtures retained; original checkout untouched.

Final update: artifacts/m4/native_mutual_health.json is VERIFIED_COMPONENT.221 matching passes/environment,3non-Windows-only skips,0failures/errors;133exactinstalledPythonfiles. Full-size expiry and both peer-exit scenarios pass in both environments. Independent review closed and source frozen330files. All passing1GiB allocations archived/hash-verified and removed; no failure evidence deleted. D/health-proof01 succeeds. Exact next action: persist execution-owner session/operator authority and route fake-only controls; then integrate immutable plans/starts and bounded progression. FullM4 remains open.

Next implementation contract: docs/M4_OPERATOR_CONTROL_PLAN.md. Latest D/resources01 scan4.373613s, scratch4,198,012,440bytes; availableRAM8,597,458,944 briefly above8GiBfloor by7,524,352bytes. This observation does not admit a numerical job; launch must recheck the unchanged floor.
