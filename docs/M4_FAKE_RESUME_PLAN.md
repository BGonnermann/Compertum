# Explicit fake resume

Approved local roadmap continuation, 11 October 2026. Implement after the economic component has fresh source/package/native evidence. One writer and one bounded independent reviewer; at most three evidence-backed review/repair passes. No broker transport, credentials, live data, strategy arming or changed limits.

- [ ] Add only `resume` to the existing authenticated `fake_operator` path. Public command contains no caller-supplied readiness, observation or time.
- [ ] Check exact request deduplication first. Build a fresh owner observation using the independent opening ledger; run current control-health and regular-session checks. Unknown intentions, foreign/unexplained economics, missing evidence, stale health/supervision and reserve failure refuse.
- [ ] Recheck current owner/session/profile and freshness before one atomic write of halted=false, armed=false, admission=DISARMED, cleared approval and the bounded receipt. Resume never renews supervision, clears health/compromise flags or dispatches an effect. Exact write/readback failure rolls back.
- [ ] Advance the existing validated plan epoch exactly once. Old plans/receipts remain inspectable but cannot approve/start/dispatch. Replaying a prior resume after halt, expiry, replacement session or restart returns only the original receipt and changes no authority.
- [ ] Focused source tests, ignored-write and time-change regressions; final bounded review. Fresh exact source/wheel verification and real public reconnect/lost reply/restart/barrier checks with actual reserve and child-origin evidence.

Reuse ExecutionAuthority, FakeObservationOwner.read, control_health and the current plan context. Observation helpers run before the write transaction; revalidate before commit. Supervisor already authenticates the command and managed_owner blocks mutation during a checkpoint barrier. A sticky health fault requires restored healthy owners; resume cannot erase it. Final economic/M4 and financial acceptance remain separate.

Exact next action after economic receipt: add the failing healthy-resume/replay/old-plan tests in a fresh admitted scratch namespace, then the smallest owner transition.
