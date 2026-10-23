# Explicit approved research start

19 October 2026. Source engineering verified. Cleanup waits for other Python processes.

## Change

`Coordinator.start_reviewed_campaign` connects a registered campaign to one first research unit.
The owner must separately approve the registration request, campaign ID, and `START_FIRST_RESEARCH_UNIT` action.
The authenticated decision binds the operator, project, payload, and current owner generation.
The registration request retains the exact plan, prepared input, seal, and output allowance.

Research must already be enabled. The campaign must be paused without attempts or outcomes.
The operation saves a consumed request before dispatch and reuses the existing resume and step operations.
It confirms the saved receipt only after the existing runner reports an active job.
Repeated requests return saved status. A second request cannot start the campaign again.
After restart, fresh authentication can read the original receipt without dispatch.
An uncertain launch remains pending and requires investigation. It cannot retry automatically.
Prelaunch refusal or cancellation returns an unstarted campaign to paused state.

The existing controller retains health, storage, native identity, cancellation, and child cleanup checks.
The twelve variants, fixed 63-unit schedule, resource limits, and transport permissions remain unchanged.
No automatic loop, broker action, service, security change, or Strata process was added or started.

## Fresh verification

| Source job | Passed | Failed | Errors | Skipped | Whole-job seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ai-start-tests04`: start, refusal, cancellation, and restart | 23 | 0 | 0 | 0 | 71.0382125 |
| `ai-start-tests02`: registration and contracts | 80 | 0 | 0 | 0 | 76.7759079 |
| `ai-start-tests03`: campaign records and cleanup errors | 17 | 0 | 0 | 0 | 36.2918838 |
| Final source total | 120 | 0 | 0 | 0 | 184.1060042 |

All three whole jobs passed, observed exit zero, and left zero children.
The earlier `ai-start-tests01` job passed 19 cases in 57.4330873 seconds.
The expanded 23-case group supersedes those cases. They are not added to the final total.

The expected missing-action test recorded zero passes, one failure, zero errors, and zero skips before implementation.
Its whole job exited one in 30.4046159 seconds, with observed exit and zero children.
The original test and preparation sources remain archived beside preparation02.
The earlier contract test remains archived beside preparation03.

`ai-start-capacity01` failed in 1.4870281 seconds because the session sandbox denied an existing test-folder read.
It started no child. The failed receipt remains preserved.
A read-only check outside the sandbox succeeded without permission changes.
The distinct reviewed `ai-start-capacity02` passed in 80.0556955 seconds, with exit zero and zero children.
Later jobs used that receipt and repeated the existing folder checks.

Tests used the existing interpreter, one CPU, 120-second jobs, and 16/12 GiB host memory floors.
Capacity retained 128 MiB; source jobs retained 4 GiB. No storage allowance increased.
Independent review found no blocking implementation issue. Its requested interruption and cancellation cases passed.
The contract test confirms that the new receipt does not enable a transport capability.
The whitespace check passed with Git's Windows carriage-return handling enabled.

## Evidence limits

These are source tests with synthetic fixtures. Successful dispatch and postlaunch receipt failure use a simulated launcher boundary.
The restart case uses two actual Windows owner lifetimes and verifies an increased owner generation.
It stops before worker launch. It is not proof of native research execution.
No fresh installed-package test, actual campaign execution, financial qualification, or supervised market session occurred.
Only M0 remains fully accepted. M3 remains terminally blocked. M6 remains zero of ten actual sessions.

## Cleanup and delivery

The reviewed cleanup helper targets only wholly passing start-test folders.
Its dry run refused because other Python processes were active, including Tundra.
No test files were removed, no unrelated processes were stopped, and no cleanup check was weakened.
The last whole-job count measured 384,028,672 bytes in the unchanged 448 MiB local test allowance.
That measurement leaves 85,733,376 bytes. Small later preparation files are not included in this measurement.
Scratch stays 15 GiB, backups 21 GiB, and total storage 50 GiB.

Result XML, logs, job plans, source fingerprints, and closures are in `artifacts/ai/history-verification-20261019-01`.
Capacity receipts are in `artifacts/m5/simulated-evidence-next-01`.
Preparation files and the cleanup refusal record are in `.cache/test-runs/m5-local-economics-20261017-01/ai-start-preparation03`.
The refreshed map uses the stable external artifact folder from `docs/PROJECT_MAP_REFRESH.md`.
All nine landscape pages passed visual inspection. All 81 navigation links passed checks.
Its separate `ai-start-map-review.json` records the final build, source fingerprints, and visual checks.

This work remains local. No commit or publication was performed.
Next, run the prepared cleanup after other Python work stops.
Native start integration remains a separate verification step with its existing runtime and approval requirements.
