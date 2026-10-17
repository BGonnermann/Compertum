# Read-only Compertum Hub implementation plan

17 October 2026. The owner approved the preview and requested implementation in charcoal and warm white.
The primary agent implements this plan in master. Existing unrelated work stays intact.

## Goal and design

Give the owner one local view of actual project progress, results, missing evidence, and source records.
Use Python's standard library and plain browser files. Add no package dependencies or product imports.
Keep the Hub in `hub/`, outside the installed Compertum package and frozen environments.
Bind only to `127.0.0.1`. Read named public project documents and read-only Git metadata.
Never read credentials, environment files, runtime databases, datasets, private artifacts, or account records.
Serve the existing project-map PDF through one fixed route. Do not expose its containing folder.

## Acceptance checks

- Overview shows the newest checkpoint section, its source, modification time, and current read time.
- Results distinguish source and installed checks. Older results cannot become current totals.
- Missing, unreadable, oversized, or unsupported records show an explicit limitation.
- Work shows observed file changes. It never claims that changed files prove running work or successful tests.
- Milestones use the build specification and explicit checkpoint acceptance statements.
- Records open as plain text, with exact paths and content fingerprints.
- The browser refreshes while visible. Connection failures mark retained information as stale.
- Every page uses charcoal and warm white. Pages work at desktop and narrow widths.
- HTTP writes, foreign hosts, cross-origin requests, path traversal, and unlisted files are refused.
- A manual launcher opens the Hub. It creates no service, task, model, or Compertum runtime.
- Backend tests, real-record checks, browser checks, independent review, and the horizontal PDF refresh pass.

## Files and tasks

- [x] Add `hub/tests/test_hub.py`. First verify that the missing reader and server fail these checks.
- [x] Add `hub/records.py`. Bound record reads and extract current sections with source references.
- [x] Add `hub/server.py` and `hub/start.ps1`. Serve read-only pages and records on loopback.
- [x] Add `hub/static/index.html`, `app.js`, and `style.css`. Build Overview, Work, Results, Map, and Records.
- [x] Test missing records, history isolation, path escapes, read limits, hostile hosts, HTTP writes, and refresh failures.
- [x] Verify actual records and browser behavior. Save browser evidence outside the repository.
- [x] Complete one independent review. Repair supported findings and rerun affected checks.
- [x] Update README and `reports/HUB_VERIFICATION.md`. Refresh and inspect the project-map PDF.
- [x] Commit and push only verified Hub files and reports under the existing synchronization authority.

## Validation and limits

Run `python -B -m unittest discover -s hub/tests -v` with fresh scratch under `.cache/test-runs`.
Use the bundled browser runtime. Add no browser or interpreter installation.
Test data stays below 8 MiB. Browser evidence and PDF output stay outside the repository.
Check host memory before browser and PDF work. Run one substantial check at a time.
Use at most three review and repair rounds. Preserve failed evidence and report unresolved checks honestly.

## Decisions

The owner's approval and explicit build request authorize implementation of the accepted design in this chat.
The Windows line-ending failure was a test expectation error. The viewer preserves the original decoded file text.
The browser used an existing Chromium executable because the bundled library's default revision was absent.
Independent review closed both supported findings. Twenty-three distinct source cases and 33 browser checks passed.
Keep saved observations separate from live execution. The first release does not inspect or control a running research owner.
Refresh saved records every ten seconds while the page is visible. Show file age without inventing verification timestamps.
Use a document catalogue from tracked top-level Markdown files in `docs/` and `reports/`, plus named core records.
Limit each text record to 256 KiB and catalogue entries to 512. Refuse symbolic links and reparse points.
Show unknown counts as unavailable. Do not infer milestone completion from test counts or file presence.
The Hub report is a separate engineering receipt. It does not advance M1 through M6 acceptance.

## Stop conditions

Stop only for unsafe resource headroom, unavailable required tools, unresolved review failures, or missing material authority.
Do not start Strata, change operating gates, clear saved stops, or perform account actions.
