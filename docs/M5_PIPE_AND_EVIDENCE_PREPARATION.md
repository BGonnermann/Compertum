# Pipe diagnosis and evidence storage preparation

The owner authorized diagnosis and a prepared storage fix on 18 October 2026.
This work does not reopen the stopped simulated sequence.

## Checklist

- Inspect the existing pipe failure and the actual Windows access rules.
- Run bounded isolated diagnostics under the existing maintenance job limits.
- Prepare an evidence storage plan that preserves every existing record and limit.
- Obtain an independent review of the diagnosis and proposed storage plan.
- Record results, limitations, and the next action.

The diagnostic creates temporary local pipes only. It does not start owners or access saved runtime files.
Read the pipe security descriptor. Compare its access rules with the requested rights.
Try individual existing rights to identify the rejected request.
Do not change access rules, tokens, privileges, or the product pipe implementation.
Use one CPU, 128 MiB, 16 processes, and the existing 120-second job deadline.
Keep the host memory start floor at 16 GiB and stop floor at 12 GiB.
Allow at most three review rounds for this preparation task.
Preserve every failed result. Stop before another full scan or simulated broker stage.

## Storage preparation boundary

Keep the risk evidence folder at 16 MiB and the economics evidence folder at 8 MiB.
Keep the C: total at 50 GiB and the D: archive allowance at 200 GiB.
Do not move, remove, rewrite, or compress existing evidence in place.
Measure named evidence folders only. This measurement does not renew complete storage admission.
The candidate is `docs/M5_EVIDENCE_FOLDER_PROPOSAL.json`.
It reserves 8 MiB for future records within the unchanged 5 GiB records category and 50 GiB total.
The forecast requires 8,261,632 bytes. The remaining margin is 126,976 bytes.
This is a proposed allocation. It is not fresh capacity admission.
Preserve all 28 existing folder checks. Add a twenty-ninth check for the proposed folder.
Charge actual records and the unused folder allowance in the complete census.
Do not subtract the new allowance from existing unnamed holds.
Keep the old 16 MiB risk folder and 8 MiB economics folder unchanged.
Bind future outputs explicitly. Keep saved runtime paths and old attempt markers unchanged.
Check available space before writes, during each job, and after child cleanup.
Reserve final closure space before starting a child.
Refuse execution if any folder, category, or total limit fails.
Do not create the proposed folder or activate a replacement launcher during this preparation task.
The candidate needs wrapper and census integration before a separate execution decision.
The existing stopped sequence remains closed.
