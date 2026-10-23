# Approved registration verification

For subsequent cleanup and repair verification, see [the latest report](REGISTRATION_COMPLETION_20261019.md).
The failed attempts and storage measurements below remain historical evidence.

## Result

The approved folder limit is now 448 MiB in distinct preparation07 wrapper and census files.
All other folder limits remain unchanged. Scratch remains 15 GiB, backups 21 GiB, and total storage 50 GiB.
Independent preparation review found no blocking issue before the single capacity07 attempt.

| Attempt | Passed | Failed | Errors | Skipped | Overall job |
| --- | ---: | ---: | ---: | ---: | --- |
| capacity07 | Not a test suite | Not a test suite | Not a test suite | Not a test suite | Passed in 108.189654 seconds |
| registration-tests02 | 62 | 13 | 0 | 0 | Failed; final folder check reached 120.001818 seconds |
| Receipt-only repair | 0 | 0 | 0 | 0 | Not run |
| Campaign and seal regressions | 0 | 0 | 0 | 0 | Not run |

Capacity07 observed exit 0 and zero children. Its complete census took 76.247691 seconds.
It retained 17,757,400 bytes of scratch-category headroom after full commitments.
The source child exited 1. The wrapper observed exit and zero children after its deadline refusal.
The 62 passing cases are results from a failed job, not accepted verification of the repaired implementation.
No installed-package test or actual campaign integration ran. Do not combine this attempt with earlier overlapping counts.

## Failure and prepared repair

All 13 failures reached `domain.validate_record`, which rejected `register_reviewed_campaign` as an unavailable receipt action.
The prepared repair permits this action only during receipt validation. Confirmation rules remain unchanged.
`_CONTROL_ACTIONS`, `M0_CAPABILITIES`, bootstrap rules, transport allowlists, and Windows security settings remain unchanged.
The new contract test checks receipt acceptance, transport denial, and rejection of invalid confirmation.
Independent static review accepted the repair. Neither the repair nor its new test has run.
The earlier restart test checks separate processes and owner generations with orderly cleanup after an injected exception.
It does not establish abrupt process-death recovery.

## Storage stops remaining verification

A bounded folder measurement confirmed 447,995,904 bytes used and 21,766,144 bytes remaining before later preparation files.
Independent review estimated these retained fixture requirements:

| Remaining fixture work | Bytes |
| --- | ---: |
| Thirteen failed registration cases, before successful growth | 9,318,400 |
| Thirty-one development-seal regression fixtures | 14,467,072 |
| Combined minimum | 23,785,472 |
| Minimum shortfall | 2,019,328 |

This estimate excludes successful campaign growth, contract tests, new wrapper files, and directory overhead.
The reviewer proposed a conservative 32 MiB remaining-work allowance. That is a forecast, not authorization.
No second capacity attempt, evidence deletion, evidence move, allowance borrowing, or limit increase occurred.
Full required coverage remains pending. Further tests need a reviewed storage decision and fresh admission.

## Evidence and boundaries

Capacity files use `artifacts/m5/simulated-evidence-next-01/ai-registration-capacity07*`.
Source files use `artifacts/ai/history-verification-20261019-01/ai-registration-tests02*`.
Preparation files use `.cache/test-runs/m5-local-economics-20261017-01/ai-registration-preparation07`.
That folder contains the 84-file preservation manifest and the original `tests02-domain.py` before the new repair.

One CPU, the 4 GiB source-test limit, and 120-second deadlines remain unchanged.
Capacity retains its existing 128 MiB limit. Host memory floors remain 16 GiB before start and 12 GiB while running.
No actual campaign registration, campaign execution, broker action, service, or Strata start occurred.
The session reports restricted workspace access. No access or security setting was changed.
M3 remains terminally blocked. M6 remains zero of ten actual supervised sessions.

Independent final review confirmed the counts, both cleanup receipts, all 84 preservation hashes, and all 37 tests02 source pins.
Recorded host memory remained above both floors. The complete census had zero unknown entries, barriers, or ledger failures.
The historical seal-size source is `ai-history-tests03/pytest` under the same local-economics parent.
Project-map build and inspection results use `ai-registration-map01-review.json` in the external map folder.
No publication occurred.
