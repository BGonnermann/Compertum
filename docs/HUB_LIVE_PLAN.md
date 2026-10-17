# Live Hub activity and whole-loop tracking

17 October 2026. The owner requested activity as it happens and a whole-loop page.
This extends the approved Hub. The primary agent implements and verifies the change in master.

## Scope and acceptance

- [x] Read current local Codex session events for this project, including test and file-change tools.
- [x] Observe native Windows project processes by their actual working directory and creation identity.
- [x] Keep running, finished, interrupted, stale, and unavailable observations separate.
- [x] Display only fixed activity labels, identities, timestamps, stages, and observed exit codes.
- [x] Never expose prompts, model reasoning, command bodies, credentials, tool output, or other projects.
- [x] Refresh activity every two seconds while visible. Keep document refresh separate and mark connection loss immediately.
- [x] Add a horizontal whole-loop page with current activities, stage details, connections, and missing reporting links.
- [x] Provide a small local stage-reporting wrapper for trusted future jobs. It does not grant execution or account authority.
- [x] Verify event parsing, native process detection, expired observations, partial records, HTTP access, and browser transitions.
- [x] Complete one independent review within three bounded passes.
- [ ] Refresh the horizontal PDF and synchronize the approved private repository and clone.

## Design and bounds

Use separate `/api/live` and saved-document endpoints. The browser reads live activity every two seconds.
The observer reads only recent session files whose metadata identifies this exact project root.
It exports sanitized activity events, never raw transcripts or tool arguments. Unsupported records do not establish success.
Native process identity includes process ID and creation time. A vanished process means its outcome is unknown.
Pending agent tools and actual process observations are separate sources. Neither grants milestone acceptance.
An agent without a recent signal is stale. A missing completion receipt never becomes a passing result.

The whole loop covers data, proposals, experiments, mathematics, development audit, protected evaluation,
independent audit, qualification, owner authorization, signals, risk, intentions, paper execution, reconciliation, reports, and feedback.
The page marks missing operational reporting explicitly. Engineering tests use a separate lane.
Trusted jobs can publish bounded stage observations through a manual wrapper outside the repository.
The Hub remains a reader. It never starts a research owner, changes a gate, or sends an account request.

Use Python's standard library and existing browser tools. Add no dependency or model installation.
Limit discovery, session reads, record sizes, native candidates, retained events, and observation age.
Use fresh `.cache/test-runs` fixtures and external browser/PDF evidence. Preserve unrelated work and failed native history.
Check host memory before substantial checks. Use at most three review/repair rounds.
Run `python -B -m unittest discover -s hub/tests -v` and the browser checks.
Stop only for missing material authority, unsafe resources, or an unresolved required verification.
