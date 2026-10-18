# Pipe identity and evidence review

## Current observations

The read-only observer ran under the existing bounded launcher on 18 October 2026.
Windows reported version 10.0.26300.
The observer and its immediate parent had matching user, logon, and application identities.
Both ran inside AppContainer, the restricted Windows application environment, at integrity level 4096.
The observer had no separate thread token. Windows returned `ERROR_NO_TOKEN` (1008).
Its effective identity therefore matched its process identity.
`GetPackageFamilyName` returned `APPMODEL_ERROR_NO_PACKAGE` (15700).
This establishes an unpackaged AppContainer process, not an unrestricted desktop process.
The private result retains exact identities and process creation times.
These observations do not identify the original failed supervisor or a future client.
Future execution must read and bind both retained peer identities again.

The bounded observer job passed in 25.735736 seconds, observed exit code 0, and left zero children.
It retained 1 CPU, 128 MiB, 16 processes, and a 120-second deadline.
Memory floors remained 16 GiB before work and 12 GiB during work.
It created zero pipes and made no permission changes.
This was one diagnostic, not a source test or native transport acceptance test.
The previous 42 source passes remain historical results.
Private evidence uses `pipe-identity01-result.json` and `pipe-identity01.closure.json` in `artifacts/m5/local-economics-20261017-01`.

## Pipe name requirements

Production names use `\\.\pipe\compertum-...` in `src/compertum/runtime/_pipes.py`.
Microsoft documents `LOCAL` names for packaged applications and UWP pipe restrictions.
Microsoft also confirms that unpackaged programs can run inside AppContainer.
Therefore, absence of package identity does not prove that all desktop pipe operations are allowed.
The earlier diagnostic created a production-style pipe but failed its client open with error 5.
That record supports creation only. It does not establish communication or the complete launcher policy.

For the proposed isolated experiment, retain the desktop name form to change only the application grant.
Use `\\.\pipe\compertum-policy-4c9002b9d6e14c048c7949ecc069eb74` once, with no name fallback.
This is an experimental choice, not a claim that Windows accepts the connection.
Keep the exact mask `0x00100083`, current user/logon grants, and the observed exact application grant.
Before execution, verify both peer identities again and refuse unexpected changes.
Do not use `LOCAL` as an automatic workaround after failure.

Sources:
- [Microsoft pipe communication](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication).
- [Microsoft CreateNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea).
- [Microsoft AppContainer overview](https://learn.microsoft.com/en-us/windows/msix/msix-container).

## Evidence reconciliation

The named evidence folder contains six files, charged at 81,920 bytes after 4096-byte rounding.
Its directory adds 4096 bytes. Total charged use is 86,016 bytes against 8,388,608 bytes.
The remaining physical allowance is 8,302,592 bytes. This is not uncommitted test space.
Preserve the full 8,261,632-byte forecast and add the existing 81,920 file bytes conservatively.
The directory charge is already included in the forecast.
Total planned charge becomes 8,343,552 bytes, leaving 45,056 bytes.
Keep the proposed 131,072 experiment bytes inside the existing 1,048,576-byte preparation allowance.
Other preparation commitments must fit the remaining 917,504 bytes.
Do not assign old files to that allowance without evidence of their original allocation.
The proposal retains ten stage allocations, ten capacity allocations, review allowance, final closure, and directory charge.
The point-in-time folder observation is not atomic and retained no directory handles.
This report does not activate reservations or establish global storage admission.
The folder check did not scan other project storage or repeat the full census.
Require an exclusive ledger binding and fresh bounded folder check before any later writer.
Unknown preparation commitments must cause refusal, not borrowing from another allowance.

## Next bounded step

Prepare an isolated experiment runner while keeping its native entrypoint disabled.
Bind its exact pipe name, peer observations, access mask, five output limits, and zero retries.
Use query-only identity checks and reject changed identities before pipe creation.
Preserve remote rejection, first-instance protection, non-inherited handles, authentication, and cancellation limits.
Keep five-second operations and one-second cancellation completion.
Obtain independent review of the exact runner and evidence bindings.
Then request explicit approval for one temporary pipe with the added application grant.
Do not create that pipe during preparation.
Stop if fresh global storage admission requires a full scan.
Keep C: at 50 GiB and the separate D: archive at 200 GiB.
Preserve category and folder caps. Keep Strata off.
Do not clear saved stops, change existing permissions, or take broker actions.

Independent review passed for observation only. No blocking safety issue appeared.
The reviewer confirmed the job closure and conservative space arithmetic.
Pipe namespace eligibility and exact remaining preparation commitments remain unverified.
