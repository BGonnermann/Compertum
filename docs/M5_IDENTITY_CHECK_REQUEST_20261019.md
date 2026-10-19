# One query-only Windows identity check

19 October 2026. Prepared request. No new identity check or security change has run.

## Current state

This session reports workspace-write access and automatic approval review.
The older plan expected workspace-write access with user approval review.
These settings differ. Neither setting proves a Windows AppContainer identity.
AppContainer is Windows application isolation. The prior experiment requires its exact pinned identity.
Folder read access succeeded without permission changes. That result does not verify the pipe identity.

## Exact proposed scope

Approve one bounded query-only observation in the current restricted session, with zero retries.
Do not change the session permissions or Windows security settings.
Read the process token, effective token, and retained immediate parent through the existing `IdentityReader` checks.
Compare the observed user, logon, application, and integrity identities with the existing reviewed pins.
Require AppContainer membership and integrity level 4096.
Save match results and hashes. Do not publish raw identities or authentication data.
Stop on any mismatch, missing identity, unreadable token, or administrator setup request.
Do not replace pinned identities or switch to unrestricted execution.

## Fixed limits and evidence

Use the existing project Python 3.14.7 and one CPU, 128 MiB, 16 processes, and 120 seconds.
Require 16 GiB host memory before starting. Stop below 12 GiB.
Use the fresh label `pipe-identity-check02` under `artifacts/ai/history-verification-20261019-01`.
Keep that folder's checked 2 MiB allowance. This request proposes no additional allowance.
Reserve the following exact files before launch.

| File | Maximum bytes |
| --- | ---: |
| pipe-identity-check02.job.json | 8192 |
| pipe-identity-check02-source-pins.json | 8192 |
| pipe-identity-check02-result.json | 16384 |
| pipe-identity-check02-stdout.log | 8192 |
| pipe-identity-check02-stderr.log | 8192 |
| pipe-identity-check02.closure.json | 65536 |

The complete proposed reservation is 114688 bytes. It is inactive until explicit approval and a successful capacity check.
Use `docs/M5_PIPE_EXPERIMENT_BINDINGS.json` for the unchanged identity and interpreter hashes.
The private observation is `artifacts/m5/local-economics-20261017-01/pipe-identity01-result.json`.
Use `tools/pipe_experiment_identity.py` for the existing query-only reader.
Bind the observer and launcher sources to the approved request before execution.
Check actual remaining capacity before reserving files. Preserve every prior attempt.
Require observed process exit and zero remaining children.

## Approval boundary

The day plan authorizes preparing this request. It does not authorize executing this new identity attempt.
The existing launch-context plan requires explicit authority for the distinct check.
This request creates no pipe, changes no grant, retries no experiment, and takes no broker action.
A passing identity check permits preparation of a separate pipe request only.
Any later pipe grant or production integration needs its own reviewed, exact approval.
