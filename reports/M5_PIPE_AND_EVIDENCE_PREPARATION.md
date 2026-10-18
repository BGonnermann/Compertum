# Windows pipe diagnosis and evidence storage proposal

## Result

Windows rejects the isolated pipe client because its AppContainer identity lacks a matching grant.
AppContainer is Windows' restricted application environment.
The pipe grants the user and logon identities. It does not grant the application identity or either capability identity.
The final diagnostic confirms AppContainer, restrictions, and low integrity level 4096.
It also confirms that the effective user matches the intended operator.
The applied access rules match the intended rules.
Windows `AccessCheck` denies the exact `0x00100083` request. The actual open also fails with `CreateFileW:5`.
Zero entries in the restricted-group list did not exclude AppContainer restrictions.

Microsoft requires both user/group access and AppContainer access for this kind of protected resource.
See [Microsoft's AppContainer access model](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer).
The diagnostic demonstrates this restriction in the current environment.
It does not establish whether additional restrictions would remain after a permission change.
No permission change or alternate security context was tested.
The original failed supervisor token was not captured. Its exact token cannot be reconstructed from these later observations.

## Fresh observations

The final diagnostic made seven isolated client-open observations. All seven returned access denied.
These are diagnostic observations, not seven failed broker tests.
The final diagnostic job passed in 50.778809 seconds. It closed all child processes.
Earlier diagnostic jobs 01 and 02 also completed. Diagnostic jobs 03 and 04 failed.
Job 03 saved no child result. Its failed parent closure remains preserved.
Job 04 saved its partial result and the one-byte token-field decoding error.
Frozen native version 05 reads that field as a byte and saves partial results on failure.
The revised public decoder accepts one-byte and four-byte results, records the length, and rejects other lengths.
The revised decoder has not received another native run.
The first diagnostic compared security strings literally. Windows removed leading zeros from the access mask.
Its false comparison did not establish different access rules. Later comparisons normalize those leading zeros.

Private results remain under `artifacts/m5/local-economics-20261017-01/pipe-rights-diagnostic*.json`.
Parent closures remain under `artifacts/m5/risk-dispatch-20261017-01/pipe-rights-diagnostic*.closure.json`.
Frozen diagnostic sources 02 through 05 remain in the economics evidence folder.
Version 01 was not separately frozen before editing. Its job plan and result remain available.
Do not treat that first result as a reproducible source-pinned qualification.

Nine source helper checks passed, with zero failures, errors, or skips.
They check token-field decoding and allocation arithmetic. They do not qualify pipe transport or activate storage integration.
No complete source suite or installed-package broker test ran during this task.
The earlier simulated result remains historical: 0 passed, 1 failed, 0 errors, and 0 skipped.
Nine later stages remain unrun. Only M0 is accepted.

## Evidence folder proposal

The existing risk evidence folder has a 16 MiB limit. The next history forecast requires 524,288 bytes.
The initial targeted count found 16,498,688 bytes used, leaving 278,528 bytes.
New diagnostic records consume more space. That initial count is not current admission.
The observed blocker is the folder allowance. This task did not establish fresh total-capacity admission.

The machine-readable candidate is `docs/M5_EVIDENCE_FOLDER_PROPOSAL.json`.
It proposes an 8 MiB folder for future evidence within the existing 5 GiB records category and 50 GiB total.
Its forecast totals 8,261,632 bytes, including preparation, ten stage outputs, ten capacity outputs, review, closure, and the directory.
The remaining margin is 126,976 bytes.
Keep every existing folder, limit, file, hash reference, and failed-attempt marker.
Add the proposed folder to all checks. Charge its actual use and unused allowance in the full census.
Do not reuse unnamed existing holds or count D: as runtime storage.

This is a reviewed allocation proposal, not an activated storage repair.
Wrapper, census, and output-binding integration remain necessary before execution.
A fresh complete capacity check must establish that the added allowance fits the unchanged category and total limits.
No new full scan, folder activation, evidence relocation, or simulated sequence ran.

## Boundaries

Strata remains off. No permissions, saved stops, runtime identities, or broker actions changed.
The pipe diagnosis is sufficient to stop blind retries in the current security context.
Do not broaden access rules or change security context without separate authority.
The stopped simulated sequence remains closed.
