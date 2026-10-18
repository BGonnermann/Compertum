# Evidence folder implementation

Implement the approved 8 MiB proposal without activating storage admission.
Preserve the 28 existing checks and add the proposed folder check.
Charge actual records plus the unused allowance in the census.
Bind each output to a fixed name and limit before writing.
Reserve closure space before other output can consume it.
Refuse excess output and preserve the written prefix as failed evidence.

Use small source tests in a fresh admitted temporary folder.
Run `tests/test_evidence_folder.py` under the existing maintenance job limits.
Use one CPU, 128 MiB, 16 processes, and a 120-second deadline.
Retain the 16 GiB memory start floor and 12 GiB stop floor.
Allow at most three independent review and repair rounds.
Preserve failed test records and report exact counts.

Do not run the full census or activate the proposed folder.
Do not alter permissions, saved stops, runtime identities, or broker state.
Keep Strata off. Preserve all existing folder, category, total, and archive limits.
Refresh the project map after verification.
