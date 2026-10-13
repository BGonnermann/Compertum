# Compertum

A supervised research system with reproducible experiments, bounded AI proposals, independent audits, and controlled paper-trading development.

Updated 13 October 2026. **Working folder: `C:\Users\bgonn\Desktop\Compertum`.** GitHub stores code, configuration, tests, plans and reports for rollback. Credentials, provider data, runtime databases, environments and detailed local evidence stay outside Git.

## Current position

The daily runtime cap is removed: **27 source and 27 installed-package checks passed**. Per-job deadlines and CPU, memory and storage limits remain.

The current two-module validation repair passed **592 distinct matching tests in each source/installed environment**, with zero test failures, errors or skips. Both complete environment qualifications passed with unchanged Python and 38 dependencies. The new release contains 486 frozen files and 190 matching product modules. Separate storage-preflight refusals are preserved and do not count as passing tests.

The preceding M3 run completed63/63 outcomes in each campaign, with all63 mathematical outputs matching exactly and no failed or skipped calculations. Paired responsiveness checks and all76 individual audits and lane reviews passed. The paired comparison then blocked before worker execution because final validation outlasted the five-second health reading. That failure is preserved. The repair removes duplicated validation and retains final seal checks; regression and targeted launch checks now pass. Preparation for a new full run passed native storage checks after preserving two sandbox scan refusals. Independent admission review cleared all37 execution inputs. The repaired source campaign has now completed all63 outcomes in59 native chunks, with zero failed/skipped calculations. The installed-package campaign is running; the paired comparison and remaining audits follow. Final checks have not started. Work stays in master, with one heavy job at a time and memory checks. **Strata stays off.** Complete M3 acceptance remains open. See [the live checkpoint](docs/CURRENT_CHECKPOINT.md) and [required acceptance evidence](docs/M3_MASTER_ACCEPTANCE_MAP.md).

The historical M3 run completed both 63-outcome campaigns with exact mathematical agreement, then stopped after 37 of 77 audits/reviews because cached health had expired. That run remains terminally blocked and preserved. Its earlier combined 819-case component coverage is historical, not fresh coverage of the repaired release. See [the recovery report](reports/M3_INTERRUPTION_RECOVERY.md) and [health repair](docs/M3_REVIEW_HEALTH_REPAIR.md).

| Milestone | Status |
| --- | --- |
| M0: Local foundation and controls | Accepted; preserved acceptance evidence |
| M1: Trustworthy research inputs | Bounded real-data replay verified; full financial input qualification open |
| M2: Strategies and mathematical checks | Synthetic components verified; financial qualification open |
| M3: Protected evaluation and audit | Repaired source campaign63/63; installed campaign running |
| M4: Simulated broker | Fake-broker engineering accepted; 662 matching source/package checks |
| M5: Supervised paper walkthrough | Component verification underway; integration and actual walkthrough pending |
| M6: Daily supervised operation | Evidence structure implemented; **0 of 10 actual supervised market sessions** |

```mermaid
flowchart LR
    m0["M0: accepted"] --> m1["M1: qualification open"]
    m1 --> m2["M2: synthetic checks verified"]
    m2 --> m3["M3: native verification incomplete"]
    m3 --> m4["M4: fake broker accepted"]
    m4 --> m5["M5: integration and walkthrough pending"]
    m5 --> m6["M6: 0 of 10 sessions"]
```

Engineering checks do not establish strategy acceptance or authorize account/order actions. M6 requires actual supervised market sessions.

## Next work

1. Master consolidation published and verified; keep pushing verified checkpoints.
2. Historical recovery is preserved; its failed aggregate cannot resume. Continue the fresh master sequence with memory checks. Strata must not be started.
3. The repaired release passed592 tests per environment and both complete environment qualifications. Verify the admitted fresh full M3 run; preserve both earlier blocked runs.
4. Integrate the prepared M5 retry/opening changes and continue the accepted engineering gates.

[Current checklist](docs/CURRENT_CHECKPOINT.md) | [Build specification](docs/BUILD_SPEC.md) | [Cap removal](reports/DAILY_RUNTIME_CAP_REMOVAL.md) | [M0 acceptance](reports/M0_ACCEPTANCE.md) | [M4 acceptance](reports/M4_ACCEPTANCE.md)

## Checkpoints and rollback

Work in master. Commit and push completed, verified changes at each meaningful checkpoint under the owner's standing authorization. Record unfinished checks explicitly. Preserve commits; never force-push or reset history to make a checkpoint look clean. No scheduled run is needed.

Sibling folders retain historical environments and evidence. Their path-bound runtime records are not relocated or relabeled as master-folder results. Git rollback restores tracked files; runtime/data recovery requires the local backups and receipts. Historical reports may reference local evidence that is intentionally absent from GitHub.
