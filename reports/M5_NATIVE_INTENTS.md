# Native proposed intents and confirmations: partial checkpoint

Exact proposed actions and separate confirmations are implemented. They retain original account/input objects, operator presence, terms and expiry. Conflicting requests refuse, duplicate requests return historical receipts, and changed or expired evidence permanently invalidates dependent confirmations. Order admission remains BLOCKED; no broker dispatch, actual-write authority or financial qualification is added.

## Verified and pending

| Evidence | Result |
| --- | --- |
| Source |393 passed,0 failed,0 errors,0 skipped;39 closed jobs |
| Installed package |287 passed,0 failed,0 errors,0 skipped;32 closed jobs |
| New intent/confirmation cases | All116 passed in both environments |
| Required compatibility cases | Source277 passed; installed171 passed and106 pending |
| Build and environments | Offline build/install and both complete qualifications passed; unchanged Python and38 dependencies |
| Inputs |557 frozen files,213 product modules; exact source/package bytes verified |
| Partial evidence audit | VERIFIED bindings and preservation,896 pins; no production admission or full acceptance |

The partial audit is `artifacts/m5/native_intents_partial_storage_blocked.json`, SHA `dcc2e45b9263b582bd4473ec5d75ee0c4732742a93f66f3740d0a955abc45edf`. Maximum completed current job:76.324seconds; peak aggregate Job memory:214.887MiB. Current120-second,4GiB,fourCPU,16process,128MiB namespace and16/12GiB host floors remain unchanged. Build preparation retained its stricter64MiB namespace.

The seven pending installed groups contain34 account/input-context cases,13 opening cases and59 presence cases. Their exact IDs remain in `groups-final18d.json` and `installed-continuation18d.json` under `.cache/test-runs/m5-native-intent-20261014-18`. The287 completed installed cases retain their original receipts and IDs. No completed case was rerun to change its result.

## Corrected defects and preserved failures

Initial implementation stopped with58 passes and2 failures because a presence read learned a trigger-written reason before rollback. Review1 also found ambiguous schema/duplicate reads, an unbound SQL confirmation ID and malformed caller terms invalidating stored state. Seven probes reproduced6 failures and1 passing control. Repairs enforce exact schema and unique reads, bind SQL/body identity, validate caller terms before stored-state invalidation and learn durable revocation outside transactions. Implementation review2 is CLEAR. All116 repaired new cases then passed in each environment.

The original109-case red inventory included one incorrect Windows-path expectation. That failure and its corrected routing run remain. All23 preliminary native jobs, failed/mixed roots and five original source archives are retained. No failed evidence was removed.

Three installed groups were refused by the unchanged five-second production storage scan before any test process or fixture existed. After the second refusal, six successful disposable build stages were archived and byte-verified before exact cleanup. After the third, a read-only profile identified directory cost; two fully passed historical component pytest roots were archived under a12MiB hard allocation bound. Their5,854 files,2,872 directories,80 links and49,730,477 logical bytes were verified before removal. Their original218-case-per-environment reports remain, and their failed companion runs were untouched. These historical checks are preservation evidence, not fresh increment18 test counts. Maintenance review2/3 is CLEAR; its missing-import-pin finding and correction are preserved.

The subsequent three production scans still refused. No further test was launched. A separate instrumented offline profile completed in8.902seconds and found104,546 files; it is diagnostic only and its timing includes instrumentation overhead. Available category space was163,941,696 bytes scratch and5,695,520 bytes backups. Neither the five-second admission limit nor category limits were raised. The profiler's initial extended-path error was corrected in a new retained helper; both results remain.

## Remaining gate

Increment18 is incomplete. Full393/393 paired verification, final aggregate acceptance and the integrated local rehearsal have not passed. Scoped independent review1 returned CLEAR_FOR_PARTIAL_PUBLICATION. The partial checkpoint was published as 1b63360b1ebd6e440ae99b436e78bf4b768aa4ad; master, primary GitHub and the requested clone matched cleanly. The local receipt is artifacts/m5/native_intents_partial_published.json. This does not satisfy full acceptance. Resolve storage admission with changed evidence before another native job. Preserve frozen inputs and completed receipts; if production code changes, qualify the new identity and affected checks.

Tests use native Windows stores, leases and DPAPI with invented account origins, clocks and reserve capacity. Managed-owner routing startup is simulated. No full-reserve lifecycle or actual broker session is claimed by this component. Strata was not started.

The approved continuation is full ownership/accounting, risk/admission, durable dispatch/recovery and one integrated local Windows rehearsal. The empty-opening reader is only a prerequisite. Actual paper orders, cancellations and closes require later scoped owner approval. M3's lost installed-audit receipt remains terminally blocked, M5 acceptance remains open and M6 remains0/10 actual supervised sessions. See [the checkpoint](../docs/CURRENT_CHECKPOINT.md) and [finish gates](../docs/M5_PAPER_ADMISSION_PLAN.md).
