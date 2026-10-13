# M4 execution checkpoint

11 October 2026. Local engineering remains authorized; original Compertum and Strata preserved. Scope is deterministic invented accounts, with no HTTP/broker transport, credentials or financial admission.

- [x] Strict immutable USD observation, intent, decision, calendar, strategy-input, plan, authorization and operation-start records.
- [x] Pure strategy risk: buffered cash/remaining buys, no pending-sell credit, exact gross/name/sector and loss limits, prior-session inputs/eligibility, frozen mapping, calendar and session arm pins.
- [x] Separate halted cancellation/long-close checks, exact finite child envelopes, prerequisite cancellations, downsizing, residuals and realized-cap breach refusal.
- [x] Source checks: `.cache/test-runs/m4-execution-contracts-20261011-01/contracts04.xml`:166 passed,0failed/errors/skips. Includes 88 risk/plan checks,27 lightweight-import checks and51 existing domain checks (confirm exact module counts from XML in final receipt).
- [x] Review closed11findings;166matching source/installed checks,0failure/error/skip. Receipt artifacts/m4/risk_contracts.json; report reports/M4_RISK_CONTRACTS.md.
- [ ] Persistent fake broker and execution-owned intent journal; no acceptance/retry/recovery claim yet.
- [ ] Owner-authenticated input/calendar/plan/start pins, health/restart integration and full M4 crash/accounting/recovery matrix.

Review: all11reported findings repaired and closed by independent static review. Failed `plans01` and `review-fixes01` receipts retained; their failures were test fixtures with stale health or omitted filled notional. Product gates were preserved.

Contracts consume independently supplied pins. Valid schemas/booleans do not establish live exclusive ownership, actual journal reservation, source truth or operator authority. Only the future execution owner may authenticate these facts before a simulated effect. M4 is incomplete.

Plan interpretation: a child has an immutable $2000 (or smaller liquidity) maximum notional, plus its separately recorded planned notional.19shares at100 plan1919; repricing110 permits downsizing to18 under the same2000cap. No cap increase occurs. Actual partial fills leave exact residuals; no extra child is added. Authorization reconstructs the source plan and requires its exact snapshot; operation start rechecks the economic snapshot. A refreshed authorization snapshot requires a regenerated plan.

Current resource receipt: `resources01.log`,06:36:08Z: scratch5,356,952,632/5,368,709,120bytes;scan4.392746seconds;RAM8,520,658,944/8,589,934,592required. Full M3 numerical native work remains RAM-blocked. Pure tests run within their normal small process budget. No limit changed.

Exact next action: implement persistent fake-intent lifecycle in the existing execution StateStore, with native owner/generation checks and no transport. Test lost-reply/no-retry, immutable intent conflict, monotonic fill observations and restart disarming using small invented fixtures. Then add the separate persistent fake broker and owner-authenticated operation integration. Check storage before larger fixtures.

## Persistent fake-intent increment in progress

The existing execution StateStore now has a fake-only immutable intent/event journal. It transactionally records SUBMITTING before granting one simulated attempt; restart changes unfinished submissions to UNKNOWN and queued checks to SKIPPED_RESTART. Positive delayed evidence can resolve lost replies, but integrity conflicts latch until a future explicit reconciliation path. Broker evidence is deduplicated once and applied separately to original/cancellation intents. No transport, owner-control route or real reserve/admission capability is connected.

Fresh native receipt `journal-native03.xml`:18passed,0failure/error/skip; includes4actual Windows process exits before attempt, after durable attempt, after separate persisted acceptance, and after local acknowledgment. Each retained0or1acceptance as expected and issued no second attempt. Passing disposable fixtures archived/hash-verified before approved removal. `journal-native02` failed because it tried to replace a still-live same-process owner; preserved, replaced with real process-exit tests without weakening ownership.

Reviewer found and closed cumulative-notional/event-application defects; an explicit conflict-reason path is now latched too. Combined current source suite is running as `journal-source01`; do not claim this later repair verified until its result is read. Next: check combined suite, close narrow review, freeze/build/install and run exact same test IDs. Then implement the full separate deterministic fake broker/driver and execution-owner authority/health/recovery integration. Old-snapshot replay protection and full allocated-reserve recovery remain unverified.

Latest measured resource receipt `resources02`:scratch5,362,294,752/5,368,709,120bytes (about6.1MiB headroom),scan4.9679745seconds,RAM8,491,769,856/8,589,934,592required. Full native numerical jobs remain RAM-blocked. Keep next fixtures small and archive passing copies promptly; preserve all failed evidence.

## Journal component verified; broker component active

Source and installed `journal-source01`/`journal-wheel01`:187matching passes,0failure/error/skip; actual process exits verified. Receipt artifacts/m4/fake_intent_journal.json and report reports/M4_FAKE_INTENT_JOURNAL.md. Journal source is frozen separately from subsequent code. Review closed all fake-journal findings, including explicit conflict latching.

New independent `deterministic_broker.py` persists accepts, fill/cancel events, exact cash/positions, delayed lookup and lost responses. Source `broker03`:10checks pass, including explicit-transaction concurrent-fill and consistent-snapshot regressions. Package verification and driver integration remain. Reviewer closure is pending for its transaction finding. Do not claim fullM4or financial admission.

Exact next action: implement the bounded fake-only dispatch/reconciliation driver, retaining lookup schedule0/2/5/10/20/30seconds and120second incident limit, and connect it to these existing fake journal/broker components. No automatic re-POST; use current pure risk/control checks. Then test joined acceptance/cancel/close flows, source/package equality, and continue the existing owner/watchdog/recovery integration.


## Active joined-driver repairs and resource blocker

The broker transaction review is closed. Joined driver source checks `driver02` passed7/7; `driver03` passed8 and failed1 (test fixture's19-share initial pending buy reached the name cap before the intended unknown-intent assertion). Failed fixtures remain retained; prior passing fixtures were archived, byte-verified and removed under existing approval.

Independent review identified uncertainty not being durably recorded after an acknowledged order's lookup failure, and a late incident inheriting the original submission's expired deadline. Source now classifies read failures as ordinary uncertainty and binding failures as a sticky conflict, saves a new timer for each new incident, preserves it across repeated404/reopen, and permits identical positive evidence to resolve ordinary uncertainty without clearing integrity conflicts. These latest repairs are UNVERIFIED pending resources and regression execution.

`resources03` failed the unchanged5second storage scan at07:01:37Z. RAM8,550,117,376bytes was below8GiB. New test runs paused. Exact next action: identify narrowly scoped cached Compertum package copies matching retained passing wheel evidence, archive/hash-verify the exact paths before approved removal, then run a fresh storage scan. Resume driver regression checks only if resources pass. No limits raised; no failed evidence or active environments removed. After source/package verification, continue owner-authenticated health/authority/recovery integration; fullM4 remains incomplete.


Resource cleanup attempt1:396cached files across four exact Compertum package copies matched retained passing wheels (36/49/54/245checks). Archived to backups/m4-verified-compertum-cache01-20261011.zip, SHA256fb4264b368d250655710a31c7afd7528459153c38169d8a2ec48d9b2bf33e3da; archive and source bytes reverified before exact-path removal. Receipt cache01-cleanup.json. The fresh resources04 scan still exceeded5seconds; RAM8,547,246,080bytes remained below8GiB. Additional narrowly verified duplicates are being inspected; tests remain paused. New real-process-exit regression now covers a late incident's timer surviving restart. No unverified cleanup or native success claimed.


Storage recovered: cache02/cache03 add1,788verified duplicate cache files archived and hash-checked before exact removal. Canonical package receipts and retained wheels remain. resources05 passed at07:14:37Z: scratch5,343,719,408/5,368,709,120bytes, scan4.570974seconds, free226,760,482,816bytes. RAM8,443,330,560/8,589,934,592bytes remains insufficient for full numerical jobs.

Targeted repaired driver/journal native checks driver04:31passed,0failures/errors/skips, including late-incident actual process exit. Combined driver-source01:210passed,0failures/errors/skips. Review closed timing/restart issues but identified another lookup exception class escaping before uncertainty persistence. driver-bound-red01 reproduces2failures/1pass (actual512-call broker limit and injected binding refusal). Catch repaired; full driver-source02 (expected212checks) is running. All prior passing disposable fixtures archived/hash-verified/removed; all failed receipts and fixtures retained. Exact next action: read driver-source02; close narrow review; freeze/build/install and run matching source/package IDs; then proceed with docs/M4_OWNER_INTEGRATION_PLAN.md. No fullM4 acceptance yet.


## Joined broker/driver verified

Source driver-source02 and installed driver-wheel01:212identical passes,0failures/errors/skips; exact130Python files plus schemas/config/lock verified. Independent review closed; report reports/M4_JOINED_FAKE_EXECUTION.md, receipt artifacts/m4/joined_fake_execution.json. Source freeze05d7ba90fdb37d26bab6d6ff9123b3c2322a7a7898426b329a7ade6da0ce643b; wheel2c70449416a48f3a9a101cfa23d1e054fd70f0a6030603ca6b4fab05c5c34c31.

resources06 passes storage(scan4.901963s,scratch5,347,602,856bytes), RAM8,468,549,632below8GiB. No new numerical native admission. Next dependency: append-preserved attempt evidence before execution-owner dispatch; old database snapshots must not regrant a logical submission. Implement bounded fake-only guard using existing native execution ownership and conservative journal patterns, verify old-snapshot/missing/conflicting evidence; then wire authenticated owner authority and health per docs/M4_OWNER_INTEGRATION_PLAN.md. FullM4 remains incomplete; no final handoff at this component checkpoint.


## Append-preserved attempt protection active

New fake_attempt_guard.py stores bounded256attempts/64KiB per event under state/fake-execution-attempts, outside replaceable SQLite snapshots. Original execution-store creation now provisions the guard before any caller can take a snapshot; missing evidence from an existing store cannot be reset. Each simulated attempt persists immutable intent/decision/client identity and a chained head before the database grants it. SQLite mirrors may lag preserved evidence, but cannot contradict or exceed it. Older database rows are reconstructed as UNKNOWN without another effect; missing/partial/conflicting evidence blocks new attempts.

Initial6guard checks passed; actual process-exit matrix expanded from5to7boundaries (before/after preserved head, before SQLcommit). guard-native01:30passes; guard-native02:32passes. Independent review found/reproduced the pre-journal snapshot reset and unbounded Path.iterdir behavior; direct os.scandir now refuses first invalid entry. Primary also reproduced/fixed an already-preserved attempt being mislabeled expired. Red receipts guard-red01,guard-review-red01,guard-review-red02 remain retained. Review now closed, static only.

Current exact action: read guard-source01 (all fake/risk/domain/import plus affected persistence checks); if successful archive passing fixtures, freeze current source, build/install and verify identical tests/package bytes. Then integrate preservation with actual recovery lineage and authenticated execution-owner controls/health. Current new code is NOT package-verified yet. Full native multi-DB restore/default1GiBreserve and fullM4 still unverified. Prior joined fake receipt212remains immutable.


## Storage scan repair and preserved-attempt verification

Guard-source01 passed239checks, zero failures/errors/skips; independent review closed. Source archive c8a989afb91961dbc7e23a23ad063e304dc1bfa628a89b83d14c2e12094368d0 and guard-wheels01 remain preserved. Installed verification was never started: resources07/08 refused the unchanged5second scan. Cache04 archived/hash-verified448 files from3previously verified package copies before exact removal, but did not solve the scan. No failed fixture was removed. Inspection found no substantial passing disposable tree left.

Profile storage-profile01 identified directory opens plus repeated64KiB buffer allocation/copying. Isolated prototype storage-prototype01 scanned83509file/reparse records and2285reparse paths in4.252917seconds, all categories withincaps; this is diagnostic evidence, not product acceptance. Source now reuses the buffer, copies only returned bytes, and carries directory strings until a reparse requires Path resolution. Native opens/attributes/allocation accounting/reparse policy and5second deadline remain mandatory. Added a multi-batch/native/category/reparse regression. This necessary small source repair supersedes the pending guard-source01 package stage; retain it unchanged and freeze a new combined source/wheel after storage checks.

Exact next: run focused native storage checks and a fresh product resource scan, then guard-source02 including all affected storage checks; archive only passing copies, freeze/build/install guard-wheels02 and verify identical IDs. Then continue actual recovery lineage and authenticated execution-owner controls. Full M3 numerical work remainsRAM-gated; fullM4 incomplete.


Preserved fake attempts verified:255matching source/wheel checks, zero failures/errors/skips;131exactPython files. Receipt artifacts/m4/preserved_fake_attempts.json; report reports/M4_PRESERVED_FAKE_ATTEMPTS.md. Storage repair included and independently reviewed; resources09 scans4.560715seconds withcapsunchanged. Full native numerical RAM gate remainsclosed. Next implementation: execution snapshot/manifest lineage and conservative restore/crash integration, then authenticated owner controls and watchdog. FullM4 incomplete.
