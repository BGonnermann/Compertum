# Child output repairs

The two child-output issues are repaired in disabled test adapters.
The proposed evidence folder remains inactive.

Both child programs now check the clock path through `tools/evidence_child.py`.
This check verifies the original plan hash and frozen output mapping.
The fixture launches the prepared supervisor, which launches the prepared execution helper.
The original helpers, plans, runtime identities, clock checks, and startup verification remain unchanged.

Child failure records use the existing 16 KiB `NAME-cleanup.json` allowance.
The writer refuses to replace an existing file.
If details exceed the allowance, the writer saves an explicit failure record without claiming complete details.
The writer retains the five-second failure-record deadline.
No folder, category, total, or archive limit increased.

## Verification

The fresh source run passed 31 checks, with zero failures, errors, or skips, in 0.992 seconds.
Its parent job passed in 39.185811 seconds and closed all children.
Its source hashes remained unchanged during verification.
Tests checked matching clock paths, changed-input rejection, exclusive failure writes, oversized failure details, and disabled entrypoints.
The existing writer, capture, accounting, admission-adapter, and collection checks also passed.
One independent reviewer found no remaining issue in these two repairs.
The reviewer performed read-only inspection and did not run tests.
These results do not qualify installed-package behavior, Windows pipe access, or complete simulated broker operation.

Private evidence uses `evidence-implementation-tests04` under `artifacts/m5/local-economics-20261017-01`.
Prepared copies are in `evidence-candidates02` under that folder.
Earlier failed and passing evidence remains preserved.

## Boundary

All generated entrypoints retain their unconditional stop.
The proposed evidence folder was not created or activated.
No full storage scan, permission change, saved-stop change, or broker action ran.
Strata remained off. Only M0 remains fully accepted.
Fresh full storage admission and the separate Windows pipe restriction remain outside this repair task.
