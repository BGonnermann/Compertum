# Disabled communication experiment prepared

18 October 2026. Preparation is complete. Native execution remains disabled.
Independent review round 3 found no blocking preparation defect.
This review does not establish Windows communication or security acceptance.

## Prepared files

`tools/prepare_pipe_experiment.py` binds the exact name, identity evidence, rights, limits, and preparation allocations.
`tools/pipe_experiment_identity.py` contains query-only process and effective-token checks.
`tools/pipe_experiment_native.py` contains the disabled two-process experiment.
Its first executable statement refuses execution before imports or Windows calls.
`tools/prepare_pipe_launcher.py` prepares a disabled copy of the existing bounded launcher.
`tools/pipe_experiment_evidence.py` checks commands, source hashes, output names, old evidence, and future capacity records.
`docs/M5_PIPE_EXPERIMENT_BINDINGS.json` pins the reviewed source and private identity evidence without publishing identity strings.

The launcher permits only the existing interpreter and the exact activation copy, import paths, and scratch folder.
The activation copy may differ only by removing the explicit execution guard after approval.
Unknown plan fields, fixture overrides, changed identities, changed files, and extra outputs cause refusal.
The native runner retains both process handles and verifies peer process IDs and creation times.
Each process checks its effective identity before exchanging data.
The client owns the reserved log. Client access failures retain the Windows operation and error number.
The server retains child exit codes and saves bounded failure records when execution deadlines expire.
Authentication bytes never enter the saved outputs.

## Source verification

| Run | Passed | Failed | Errors | Skipped | Parent result | Parent elapsed |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| `pipe-runner-tests01` | 111 | 0 | 0 | 0 | PASSED | 30.673117 seconds |
| `pipe-runner-tests02` | 130 | 1 | 0 | 0 | FAILED | 16.203179 seconds |
| `pipe-runner-tests03` | 132 | 0 | 0 | 0 | PASSED | 15.966749 seconds |

The second run found a missing constant in a fake test environment. The corrected test passed in the final run.
All three runs observed process exit and zero remaining children. Their evidence remains preserved.
The final run checked the preparation, original policy helper, and existing bounded evidence writer.
It also used fake adapters to verify deadline records and client `CreateFileW:5` records.
These fake checks made no Windows pipe calls.
The final source hashes remained unchanged during testing.
The final job retained one CPU, 128 MiB, 16 processes, and a 120-second deadline.
Starting and running host memory floors remained 16 GiB and 12 GiB.
The three bounded jobs used 62.843045 seconds in total. These are overlapping verification inventories, not cumulative acceptance counts.
No installed-package, actual pipe, broker, or full storage test ran.

## Independent review

Round 1 required exact launch-command binding and reliable failure records.
Round 2 accepted those repairs and required saved client error evidence.
Round 3 accepted the repaired preparation and verified all 16 source pins and the interpreter hash.
It also verified the disabled launcher, private permission request, final test counts, and process closure.
The reviewer ran no jobs and changed no files.
All three review rounds are closed.

## Evidence commitments

The six existing files still match the observed sizes and hashes.
Their conservative file charge is 81,920 bytes. The full original forecast remains 8,261,632 bytes.
The combined commitment is 8,343,552 bytes within the 8 MiB folder, leaving 45,056 bytes.

The existing 1 MiB preparation allowance now has these proposed assignments:

| Assignment | Bytes |
| --- | ---: |
| Five experiment files | 131,072 |
| One separately authorized capacity check | 262,144 |
| Remaining preparation hold | 655,360 |

The remaining hold stays reserved. Unknown files cause refusal.
No allocation is added above the original forecast. No live reservation was activated.
The capacity allocation has nine exact names. Uncreated optional files must be marked absent, not fabricated.
The result, measurement, job plan, and closure records are mandatory.
No new full scan is authorized by this preparation.

## Exact permission request

Create one temporary pipe named `\\.\pipe\compertum-policy-4c9002b9d6e14c048c7949ecc069eb74`.
Add one allow entry for the exact observed application identity to that new pipe's protected access list.
The added entry is `(A;;0x00100083;;;<observed application SID>)`.
The SID is the Windows identity identifier bound by the private request and public manifest hash.

The exact rights are `FILE_READ_DATA`, `FILE_WRITE_DATA`, `FILE_READ_ATTRIBUTES`, and `SYNCHRONIZE`.
They permit reading, writing, reading attributes, and waiting for pipe operations.
The current user and logon grants remain unchanged.
No existing object permissions, application profile, security label, or production pipe would change.
The experiment retains remote rejection, first-instance protection, and non-inherited handles.
It permits one client, one exchange, a cancellation check, and zero retries.
Its limits remain five seconds per pipe operation and one second for cancellation completion.

The complete before-and-after access rules are in the private file:
`artifacts/m5/local-economics-20261017-01/pipe-isolated01-permission-review.json`.
The disabled launcher is `pipe-launcher-prepared01.py` in the same folder.

## Execution prerequisites and next action

Ask the owner to approve only the exact temporary-pipe permission change described above.
AGENTS.md requires explicit authority for security changes. The permission proposal does not grant that authority.
Native execution also requires fresh complete storage evidence and a verified producer-recorded completion timestamp.
The historical storage result has no such timestamp. Its time must not be inferred, changed, or reused.
A new full scan needs separate authority and reviewed capacity bindings before execution.
The runner refuses missing, stale, incomplete, or changed capacity evidence.
The fixed desktop pipe name remains an experimental choice. Launcher compatibility remains unverified.
Wrong-token, remote-client, and server-instance denial behavior remain unverified native cases.
No additional security test fixtures are included in this request.

Keep the failed broker sequence closed, saved stops intact, and Strata off.
M5 remains incomplete. M6 remains zero of ten actual supervised sessions.
The horizontal project map records this preparation status and the remaining approval and storage requirements.
