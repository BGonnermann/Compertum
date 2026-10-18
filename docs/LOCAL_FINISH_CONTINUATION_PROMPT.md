# Continue bounded evidence preparation

Read docs/CURRENT_CHECKPOINT.md and reports/M5_PIPE_AND_EVIDENCE_PREPARATION.md.
The current isolated pipe client runs inside Windows AppContainer.
Its application identity lacks a matching pipe grant. Windows denies access.
Do not repeat the same pipe launch or change permissions, security context, or saved stops.
The original failed supervisor token was not captured.

The evidence proposal is docs/M5_EVIDENCE_FOLDER_PROPOSAL.json.
Prepare wrapper, census, bounded output writers, and bindings against its explicit ledger.
Preserve all 28 existing folder checks and add the proposed 8 MiB folder check.
Keep the records category at 5 GiB and C: total at 50 GiB.
Keep scratch at 15 GiB, backups at 21 GiB, and D: archive at 200 GiB.
Retain existing evidence paths, hashes, attempt markers, and runtime identities.
Charge actual new records and unused allowance in the census.
Reserve closure space before starting a child.
Get independent review before activation.
Do not activate the folder, run another full scan, or reopen the stopped sequence during preparation.

Keep one heavy job at a time and all original deadlines and resource limits.
Require 16 GiB available host memory before a bounded job. Stop below 12 GiB.
Keep Strata off. Keep spending at zero.
Do not access credentials or take broker, order, or account actions.
Only M0 is accepted.