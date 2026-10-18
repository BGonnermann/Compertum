# Disabled pipe policy helper

The helper in `tools/prepare_pipe_policy.py` prepares text for review only.
It cannot create pipes, query Windows tokens, or change permissions.
Its command entrypoint always stops with `PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED`.
Production runtime files remain unchanged.

## Verified behavior

The source run passed 42 checks, with 0 failures, 0 errors, and 0 skips, in 0.322 seconds.
Its bounded parent passed in 26.744591 seconds, observed exit code 0, and left zero children.
Source hashes remained unchanged during the run.
The job retained 1 CPU, 128 MiB, 16 processes, and its 120-second deadline.
Host memory retained the 16 GiB start floor and 12 GiB stop floor.

The helper retains the existing user and logon grants and adds only the supplied exact application identity.
The candidate mask remains `0x00100083`.
It rejects broad identities, altered masks, malformed identifiers, and changed process or effective-token observations.
It requires an explicit pipe namespace and a restricted name suffix.
Every result states that permission, native identity, and launcher namespace verification remain absent.
Synthetic observations cannot establish real Windows identity or authorization.
The source tests compare the candidate against the unchanged production descriptor.
No installed-package, native transport, or broker test ran.

## Evidence allocation

`docs/M5_PIPE_EXPERIMENT_OUTPUTS.json` names five proposed output files.
Their allowances total 128 KiB, including a 64 KiB closure record.
This is a proposed suballocation of the existing 1 MiB preparation allowance inside the 8 MiB evidence folder.
It adds no folder, category, or total allowance. It reserves no space yet.
A separate read-only comparison confirmed that the JSON ledger matches the helper exactly.
Actual files and all other preparation commitments must be reconciled before reservation.
Do not add 128 KiB on top of the existing 1 MiB forecast.
Existing failed evidence remains preserved.

Private test evidence uses `pipe-policy-tests01` under `artifacts/m5/local-economics-20261017-01`.
The source hashes, XML results, and parent closure remain there.

## Review and next step

Independent code review found no blocking issue in this preparation-only helper.
Independent evidence review confirmed the counts, parent closure, unchanged source hashes, and matching output ledger.
The reviewer performed read-only inspection and ran no jobs.
The next step is read-only observation of the intended process identity and the launcher’s pipe-name requirements.
Reconcile the proposed output allocation before presenting a specific permission request.
Any permission experiment must remain separately approved, isolated, bounded, and limited to zero retries.
No full storage scan, permission change, saved-stop change, or broker action ran. Strata remained off.
Only M0 remains fully accepted.
