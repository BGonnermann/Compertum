# AI proposal translation component

The first roadmap connection now has a source-verified translation component.
It accepts an existing AIProposal and a separate structured selection bound to the exact proposal bytes.
The trusted caller must supply the accepted task, prompt, and ordered input hashes.
The component does not independently authenticate the proposal receipt.

Selections specify review priority among the twelve existing variants.
The complete family, features, targets, model settings, and synthetic data policy remain fixed.
The component returns canonical bytes and content hashes with REVIEW_ONLY authority.
It rejects patches, tool requests, unknown fields, unsupported variants, duplicates, and mismatched identities.
It does not execute prose, access datasets, start models, register trials, or dispatch work.
The existing proposal schema and manual import behavior remain unchanged.

## Verification

The final source run passed 29 tests, with 0 failures, 0 errors, and 0 skips.
The bounded parent passed with exit 0 and zero remaining children.
The run retained one CPU, 128 MiB, 16 processes, and a 120-second deadline.
Host memory floors remained 16 GiB before work and 12 GiB during work.
No installed-package or native integration test ran.

The initial red run recorded one expected collection error because the new module did not exist.
The first implemented run encountered Windows environment-length errors from an oversized generated pytest parameter name.
Explicit short test names repaired the test harness. The product code did not change for that repair.
All earlier results remain under artifacts/m5/local-economics-20261017-01 with ai-translation labels.
Independent code review found no blocking issue.
Independent result review confirmed all five source pins, 29 passes, and closed child processes.
The final parent job took 21.801623 seconds.

## Use and next action

Call compertum.ai.experiment.translate_proposal with proposal bytes, selection bytes, and trusted receipt bindings.
The selection has exactly schema_version, proposal_sha256, and candidate_ids.
Use schema_version 1 and the SHA-256 of the original proposal bytes.
Do not derive experiment settings from free text.

Next, connect this component to accepted manual receipts and persist review plans through the existing bounded artifact writer.
Then link proposals to trial history before adding guarded dispatch.
The entire research loop is not complete. No financial milestone is newly accepted.
Full access remains enabled at the owner's request.
The former request to change this chat's permissions is superseded.
M5 pipe work stays blocked and separate from this component.
Strata stayed off. No full scan, security change, saved-stop change, or broker action ran.
