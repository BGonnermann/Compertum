# Read-only Compertum Hub verification

17 October 2026. The owner approved the design and requested charcoal and warm white.
The Hub reads the actual master working folder. It runs separately from the Compertum package.

## Verified interface

- Overview reads only the newest checkpoint section. Historical sections remain available in the original record.
- Current work shows recorded next actions and current source-file changes from read-only Git commands.
- Results keeps source and installed counts separate. Unknown counts show as unavailable.
- Project map reads milestone requirements from BUILD_SPEC and opens the fixed horizontal PDF.
- Source records searches tracked top-level Markdown documents and opens the original text with its SHA-256 content fingerprint.
- The browser refreshes records every ten seconds while visible. Failed refreshes mark retained information stale.
- Source text cannot execute as page markup. HTTP writes, foreign hosts, cross-origin reads, and unlisted paths are refused.

The actual first connection found 302 named or tracked project records, seven milestone rows, and the existing PDF.
It read 260 source and 260 installed cases from the newest fee checkpoint. These were not rerun by the Hub.
The screen correctly showed only M0 fully accepted, M6 at zero of ten actual sessions, and the research runtime as not observed.
Catalogue size can change after new documents are committed. It is not a progress measure.

## Fresh checks

| Check | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Hub source contract and actual local HTTP checks | 23 | 0 | 0 | 0 |
| Real browser and browser-only failure checks | 33 | 0 | 0 | 0 |
| Independent review rerun of Hub source checks | 23 | 0 | 0 | 0 |

The independent rerun repeats the same 23 cases. Do not add it to the distinct source count.
Hub source tests use Python's standard library on Windows. They do not install the Hub or run Compertum's native lifecycle suite.
Browser checks use the bundled Playwright library and the existing Chromium executable. No browser, dependency, or interpreter was installed.
Browser checks verified all five pages, actual file fingerprints, separate counts, the PDF, automatic refresh, failure recovery, and safe text display.
Each page fit at 390 and 320 pixels, including the expanded Results excerpt.
Desktop and narrow screenshots were opened and inspected. The page uses charcoal and warm white.

Independent review found two issues. The Results excerpt could widen a narrow screen; its text now wraps.
Git output was limited after collection; reads now stop at one MiB plus one detection byte.
Both fixes passed fresh checks. The final independent review found no remaining material issue.
A first-line summary test also prevents the checkpoint's whole paragraph from becoming a large page heading.

Initial expected missing-feature failures and the failed browser attempts remain separate from accepted results.
The first browser launch lacked the expected browser revision. Verification then used an existing Chromium executable.
The next attempt exposed whitespace in the summary comparison. A stronger first-line check and reader repair resolved it.

Browser evidence is local and excluded from Git:
`C:\Users\bgonn\.codex\visualizations\2026\10\17\01a14a69-85c1-7252-8eb9-f7ddce9f50a3\hub-checks-final`.
Its `browser-results.json` records all 33 accepted checks. Earlier attempt folders retain their failure receipts.

## Access and resource limits

The server binds only to `127.0.0.1:8767`. The standard launcher opens the default browser.
It runs in the user's terminal. It creates no Windows service, scheduled task, automatic startup, or model process.
Press Ctrl+C in that terminal to stop it. It does not stop Compertum or other work.

The reader permits named core records and at most 512 tracked top-level Markdown documents in `docs/` and `reports/`.
Each text read is limited to 256 KiB. Changed, missing, invalid, unreadable, and oversized records have explicit states.
Symbolic links, Windows reparse points, private paths, and traversal requests are refused.
The PDF route serves one named file, at most 16 MiB. It does not expose the containing artifact folder.
Git commands disable optional writes, have a three-second deadline, and discard standard error output.
One request runs at a time. Browser requests have an eight-second deadline; idle client connections have a three-second limit.

Before work, the host had 42.12 GiB free memory and 166.86 GiB free disk space.
The standalone Hub used the existing Python 3.14.7. Its observed working set after browser checks was 30.29 MiB.
Checks used fresh small folders under `.cache/test-runs/compertum-hub-20261017`; no native reserve was created.
Browser evidence and generated PDFs remain outside the repository. No storage category or operating limit changed.
The original model setup, credentials, runtime databases, saved stops, native fixtures, and unrelated M5 files were not used by the Hub.
Strata stayed off. No account call or financial action occurred.

## Project-map refresh

The existing map now includes the read-only Hub and its source references. Research and financial gates remain unchanged.
The generator's reviewed-source list includes the Hub reader, server, browser files, plan, and report.
All nine landscape pages were generated, rendered, and inspected. Verification found 81 navigation links and 90 source notes.
The full-project page identifies the Hub's read-only connection. The roadmap retains the unfinished research-loop connections.
The stable PDF path remains the one recorded in `docs/PROJECT_MAP_REFRESH.md` and served by the Hub.
The original map, roadmap, generator, review manifest, and PDF were copied to a separate local preservation folder before editing.

## Repository synchronization

Implementation checkpoint `cad2de8ab070db2b0a6e8358bc1db5a121e189f4` was pushed to the approved private `BGonnermann/Compertum` repository.
The active account was verified as `BGonnermann`. The remote main head matched the local checkpoint after publication.
Only Hub files, this plan and report, and the README belong to this change. Unrelated M5 work remains outside its commit.
Nine pre-existing modified or untracked source and instruction files matched their initial SHA-256 fingerprints after the build.
The complete Hub change passed the staged whitespace check. Existing unrelated line-ending warnings were left untouched.
This report accompanies the subsequent verification checkpoint and the browser check that also works after files are committed.
