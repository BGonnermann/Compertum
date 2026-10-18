# Evidence folder implementation review

Status: INCOMPLETE. The proposed folder remains inactive.

The owner authorized implementation, small tests, and independent review on 18 October 2026.
The owner prohibited a full storage scan, permission changes, saved-stop changes, and broker actions.

## Implemented code

`tools/evidence_folder.py` reserves file allowances before writes and preserves existing files.
It rounds file charges to 4096 bytes and reserves closure space.
Parent and child writers share one ledger with separate writable names.
It rejects excess output, changed files, removed files, and unsafe folder entries.
Failure and closure records have a separate five-second recording deadline after execution stops.
This deadline does not extend child execution.

`tools/evidence_capture.py` copies child output through bounded streams.
An output failure terminates the child and fails verification.
The enclosing Windows Job must still close descendants.
The source tests use fake child streams. They do not qualify Windows pipe transport.

`tools/prepare_evidence_candidates.py` creates disabled wrapper, census, stage, fixture, and admission adapters.
The wrapper preserves 28 folder checks and adds the proposed folder.
The census counts actual records plus the unused 8 MiB allowance.
It does not reduce other reserved allowances.
The stage output map preserves original plan bindings and provides matching receipt names.
Clock files consume 4096 bytes each from the existing 1 MiB preparation allowance.
Every generated program stops before imports or execution.
The original programs, plans, attempt markers, and evidence remain unchanged.

## Verification

The first source run passed 19 checks, with zero failures, errors, or skips.
Its parent job passed in 82.075567 seconds and closed all children.
The second parent job reached JOB_DEADLINE at 120.001286 seconds and closed all children.
Its test XML records 24 passed, zero failed, zero errors, and zero skipped in 6.844 seconds.
The parent timeout makes that overall run failed. Its failed closure remains preserved.
The final source run passed 25 checks, with zero failures, errors, or skips, in 8.719 seconds.
Its parent job passed in 83.511019 seconds and closed all children.
The source hash check confirmed unchanged inputs during that final run.
These results cover helper behavior and disabled source generation, not complete simulated broker operation.

Private evidence is under `artifacts/m5/local-economics-20261017-01`.
The labels are `evidence-implementation-tests01`, `evidence-implementation-tests02`, and `evidence-implementation-tests03`.
The generated sources are in `evidence-candidates01` under that folder.

## Independent review

One independent reviewer completed three review rounds.
Earlier findings led to repairs for shared ownership, timeout recording, removed files, input paths, output names, and admission checks.
The third round found two remaining integration blockers.

- The supervisor and execution helper still require the clock file beside the original plan.
- The execution helper still writes an unbounded failure file beside that plan.

The original helper files are `tests/helpers/paper_fixture_rehearsal_supervisor.py` and `tests/helpers/paper_fixture_rehearsal_execution.py`.
The disabled candidates cannot pass a complete simulated stage until these output paths have reviewed adapters.
The three-round implementation review limit is reached. Do not treat passing helper tests as acceptance.

## Next action

Prepare disabled adapters for both child helpers.
Bind their clock input and failure output to the same fixed evidence ledger.
Preserve plan hashes, clock validation, runtime identities, and all operating limits.
Test those adapters with harmless fixtures and obtain independent review before considering activation.
A separate full storage check remains required before the proposed folder becomes active.
No new full scan, permission change, saved-stop change, or broker action occurred. Strata remained off.
