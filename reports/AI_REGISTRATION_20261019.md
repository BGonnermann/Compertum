# Reviewed campaign registration

For subsequent cleanup and repair verification, see [the latest report](REGISTRATION_COMPLETION_20261019.md).
The results and remaining-work statements below are historical.

Later verification is recorded in [the approved-storage report](AI_REGISTRATION_VERIFICATION_20261019.md).
Capacity07 passed at 448 MiB. Tests02 failed, and the receipt-only repair remains untested.
The earlier implementation and failure history below remain preserved.

## Implementation complete; revised tests blocked

The accepted scope is local implementation and bounded synthetic tests. Actual registration and execution remain separately gated.
The pre-existing AGENTS.md edit remains untouched.

`Coordinator.register_reviewed_campaign` now uses the existing saved campaign owner and seal integration.
The operation binds the task, plan, prepared input, campaign, seal, output allowance, operator, request, and owner generation.
It commits a pending control record before campaign creation. It returns a paused campaign after publishing the history link.
Identical requests reuse the original campaign. Conflicting requests fail.
Recovery preserves the original approval record. A new owner requires a fresh authenticated request with unchanged operator and inputs.
Incomplete registration blocks resume and unit preparation. Completed registration checks the published plan and link again before dispatch.
These checks preserve the existing cooperative verification of campaign results.
No command was added to a worker or operator transport allowlist. The operation remains an owner-facing interface.
Registration does not resume research, create a unit attempt, or grant execution permission.

The first test run exposed a receipt-format error. Storage manifests contain a task field that control-receipt artifacts do not accept.
The repair projects the four required artifact fields. Independent review also prompted restart and dispatch-evidence repairs.
Independent static review round 3 found no remaining blocking issue. Revised code has not passed fresh tests.

## Preserved preparation failures

`ai-registration-capacity01` failed before child creation with `EVIDENCE_FILE_LIMIT`.
Its 4,490-byte job exceeded the 4,096-byte capacity-job allowance.
The wrapper reported 0.01301579998107627 seconds and zero remaining children. It could not reserve its closure.
The original job and generated wrapper remain unchanged. The command output and this report retain the failure.

`ai-registration-capacity02` failed on the historical `development_seals.py` source hash before the complete census.
Its closure records exit 1, observed exit, zero remaining children, and 30.96673570002895 seconds.
The child result records `FIRST_GATE_FAILED_STOP`. No test ran.

The distinct third preparation checks historical source against the existing hash-pinned release archive.
It retains exact historical hashes and all original resource checks. Current test jobs pin current source separately.
The capacity job now binds only capacity inputs and enforces its original 4,096-byte allowance before writing.

Independent preparation review found two test-runner issues. Both are repaired before test-job creation.
The prepared-campaign test and its imported fixtures now have source pins.
The second test label no longer substitutes an unrelated historical test for registration tests.

## Evidence

Capacity evidence is under `artifacts/m5/simulated-evidence-next-01/ai-registration-capacity*`.
Source evidence will use `artifacts/ai/history-verification-20261019-01/ai-registration-*` within its existing 2 MiB allowance.
At preparation time, no source test had run. Results below replace that initial count.

## Final observed test and resource results

| Attempt | Passed | Failed | Errors | Skipped | Meaning |
| --- | ---: | ---: | ---: | ---: | --- |
| ai-registration-red01 | 0 | 1 | 0 | 0 | Expected missing-operation failure |
| ai-registration-tests01 | 62 | 7 | 0 | 0 | Source results retained; overall job failed its storage check |
| Revised implementation | 0 | 0 | 0 | 0 | Not run; storage approval required |

Do not combine overlapping test attempts. The failed source job does not establish accepted verification.
It measured 404,942,848 bytes against a 402,653,184-byte test-folder limit.
The guard stopped it with `ECONOMIC_SOURCE_LIMIT` after 89.32298910000827 seconds.
It observed process exit and zero remaining children.
Five original source files were preserved before repair in the bounded AI evidence folder.
The preservation receipt is `registration-source-preservation.closure.json`.

Capacity attempts 03, 04, and 05 each had a passing census child but failed the overall 120-second deadline.
Their closure times were 120.00183570000809, 120.00025079998886, and 120.00170590000926 seconds.
Each observed exit and zero remaining children. None admitted tests.
Attempt 05 retained a quoting defect that left the old polling interval active.
Attempt 06 corrected the capacity-only interval and passed in 103.97474750003312 seconds.
It observed exit 0 and zero remaining children. Test jobs retained their previous polling interval.
Its admission preceded the later test-folder overrun and cannot authorize further tests now.

The evidence uses synthetic fixtures with native Windows ownership and bounded child jobs.
No revised installed-package check, accepted native campaign integration, actual campaign registration, or execution ran.
M6 remains zero of ten actual supervised sessions. Historical results remain separate.

## Remaining roadmap

| Item | Current evidence | Remaining prerequisite |
| --- | --- | --- |
| AI reviewed registration | Implemented and statically reviewed; first test run failed | Approve the exact folder allowance, obtain fresh admission, then verify repairs |
| M1 real inputs | Existing qualification plan retains a rejected input contract | External action coverage, historical eligibility, and knowledge-time evidence |
| M2 campaign components | Existing fixed twelve-variant, 63-unit runner remains in use | Revised registration tests and separate actual registration/execution approval |
| M3 | Terminal master BLOCKED history remains unchanged | No retry is authorized; missing installed-audit exit proof cannot be manufactured |
| M4 | Original development receipt records 662 source and 662 installed passes, with zero failures, errors, or skips | Retain historical scope; no new M4 acceptance run is needed for this registration change |
| M5 | Prepared query-only identity request remains available | Explicit identity-check authority, then separately reviewed native integration and broker plans |
| M6 | Manifest and calendar foundation exists | Trusted M5 supervision, order, ledger, restore, and AI-off records, plus ten actual sessions |

No additional ready implementation was identified within the current component plans.
The original M4 receipt was found read-only at `C:/Users/bgonn/Desktop/Compertum-development/artifacts/m4/acceptance.json`.
Its SHA-256 is `8ec695e3e8ee1b1ff4d0f3e86317d51f6eaeedd6db3243f2af037d0d67d141b9`.
Its acceptance state is `VERIFIED_ENGINEERING_MILESTONE`, with review `CLOSED_PASS_3_OF_3`.
This resolves the older plan's unchecked acceptance-map item as historical work. It is not fresh master verification.
Automatic dispatch, feedback, and revision remain later scope in `AI_RUNNER_CONNECTION_PLAN.md`.
The project-map rebuild and publication remain pending fresh verification and resource admission.
No commit or push occurred. Strata and its model server were absent from the process-name check.
No service, security change, broker action, or new spending occurred.

The smallest required decision is in `docs/AI_REGISTRATION_STORAGE_REQUEST.md`.
It proposes 448 MiB for this test folder within unchanged category and total budgets.
