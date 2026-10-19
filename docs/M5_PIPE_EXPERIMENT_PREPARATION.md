# Isolated pipe experiment preparation

## Scope and acceptance

Prepare a disabled two-process experiment for the exact temporary pipe in the identity review.
Keep production code, Windows permissions, saved stops, and broker state unchanged.
Keep Strata off. Do not run a full storage scan.
Allow three independent review and repair rounds for this preparation.

- [x] Bind the exact pipe name, identity evidence, rights, and output files.
- [x] Reconcile the full preparation allowance and existing evidence.
- [x] Prepare query-only identity checks and the disabled native runner.
- [x] Verify refusal paths and bounded output behavior with source tests.
- [x] Obtain an independent review and resolve blocking findings.
- [x] Update the checkpoint and README. Include this status in the final project-map verification.
- [x] Prepare the exact permission request and list remaining execution prerequisites.

Use the existing maintenance wrapper for source tests.
Keep one CPU, 128 MiB, 16 processes, and the 120-second job deadline.
Keep the 16 GiB starting memory floor and 12 GiB stop floor.
Use fresh test directories under the existing checked scratch allocation.
Preserve every failed test result. Do not reuse test labels.

## Experiment boundary

The candidate uses two temporary processes under the existing restricted launcher.
The server retains the suspended client process before creating the pipe.
Both ends check the actual peer process and creation time.
Both ends query their effective token and require the reviewed user, logon, application, and integrity identities.
Historical process IDs never authorize a future process.

The exact pipe name is `\\.\pipe\compertum-policy-4c9002b9d6e14c048c7949ecc069eb74`.
This desktop name is a fixed experimental choice. Launcher support remains unverified.
No fallback name, security context, access mask, or transport is permitted.

The sole proposed permission change adds `(A;;0x00100083;;;<observed application SID>)` to this new pipe's protected access list.
The existing user and logon grants remain unchanged.
The application identity comes from the pinned private observation, then receives fresh checks before pipe creation.
The runner records hashes and match results. It does not publish identity strings or authentication material.

The command entrypoint refuses execution before importing Windows code.
Preparation does not activate an output reservation or grant native execution authority.
After approval, activation requires a reviewed copy, fresh resource admission, and exact source and evidence bindings.
If fresh admission requires a full scan, stop for that separate authority.

## Native evidence limits

One pipe, one client, one exchange, and zero retries are proposed.
Pipe operations retain five-second deadlines and one-second cancellation completion.
The first failure stops the experiment and preserves its evidence.
Success would establish only the observed communication and cancellation behavior.
Wrong-token, remote-client, and server-instance denial tests remain unverified unless separately exercised.
No security fixture, extra identity, or remote connection is part of this permission request.

Final source verification passed 132 checks, with zero failures, errors, or skips.
Independent review round 3 accepted disabled preparation. All review rounds are closed.
See `reports/M5_PIPE_EXPERIMENT_PREPARATION.md` for exact results and the proposed permission change.
Exact next action: present the temporary-pipe permission request. Fresh complete capacity evidence remains a separate execution prerequisite.
