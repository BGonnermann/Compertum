# Current Compertum checkpoint

12 October 2026, evening. Active checkout: `Compertum-development`. Original `Compertum` remains preserved. The owner explicitly removed the proposed daily two-hour research runtime cap. Do not wait for midnight or re-enable that cap. The continuation automation `continue-compertum-roadmap` is PAUSED.

## Active task

- [x] Remove both daily-cap admission checks and the default setting. Keep historical elapsed-time accounting and all per-job/resource/financial controls.
- [x] Preserve exact legacy configs by ignoring their retired 7200-second field; other settings remain strict.
- [x] Reproduce the former cap with four failing regressions, then pass 27 focused source/native checks. Native jobs run with 7078, 7200 and 86400 seconds already charged and retain those rows unchanged.
- [x] Independent change review, iteration 1/3, has no material findings.
- [x] Build and install the cap-free local wheel. Prior Q source archive and wheel hashes verified intact.
- [x] The same 27 checks passed against the installed wheel, zero failures/errors/skips.
- [x] All 177 Python modules match source/wheel/installation. Frozen 452-file source archive and final receipt: `artifacts/m3/daily_runtime_cap_removal.json`.
- [ ] Prepare and execute the next valid M3 native verification using new runtime identities and unchanged data content.

## Continuation and evidence

N=`.cache/test-runs/m3-fresh-native-20261012-01`; P=`.cache/test-runs/m3-fresh-runtime-20261012-01`.

The cap removal changes the package identity. The old Q campaign has 63/63 source and 63/63 installed outcomes, exact mathematical payloads, and 61/77 audits. These results and all historical time charges remain preserved as Q evidence; they cannot be mixed with the new runtime or counted as fresh cap-free release results. Do not execute the obsolete `Run-Audits05.ps1` against the modified source. Existing seal and worker identity checks require a new clean pair with new run/seal/audit/Final IDs. No identity check was relaxed.

A fresh runtime fixture needs a checked storage plan. An inactive historical M0 fixture was moved to `backups/archived-test-runs-20261012/m0-recovery-final-20261009-01`. All 128 file hashes/sizes and 28 subdirectories match. PowerShell changed its root directory ID; preserve original PREPARED receipt and recovery02, do not rewrite state IDs or reopen it as the original runtime. This preserves historical evidence and releases 1,076,728,254 scratch bytes without changing project total. Fresh storage admission remains required.

Source tests: `N/daily-cap-green02.xml`, 27 passed, zero failures/errors/skips; wrapper111.924seconds. Old-cap reproduction: `N/daily-cap-red01.xml`, four expected failures. Package build/install receipts: `N/daily-cap-wheel-build01-command.json` and `N/daily-cap-wheel-install01-command.json`. Change plan: `docs/DAILY_RUNTIME_CAP_REMOVAL.md`. Pre-change files: `N/daily-cap-before01.zip`.

Storage preparation preserved 413 passing test roots in a byte-verified archive before removing duplicate loose files; 65 failed-case files remained unchanged. Earlier storage-scan refusal is retained. A helper accidentally saved the full storage inventory into N; its unchanged oversized receipt was relocated to P with a hash/location receipt. Corrected admission03 passed with a 4.521second scan and unchanged limits. All diagnostic failures remain recorded.

## Remaining roadmap

After valid M3 campaign/audit/Final receipts: integrate only the recorded Final-auditor delta, excluding test bootstrap/schema copies; verify actual generated Final, worst-case three-ridge fixture, native source/package parity, controls and recovery. Then apply only collection retry R and paper opening S deltas, preserving the cap removal. Continue `docs/M5_MARKET_OWNER_PLAN.md`, then M6 engineering.

Staged T remains44files/480current historical small passes; R520 staged passes; S81small passes. They are not integrated native acceptance. M0 accepted. M1 real engineering sample13symbols/43scored sessions/six exact replays verified; all14UNH gaps resolved. Full financial input qualification remains open. M2 synthetic components verified. M4 fake-broker engineering accepted. M6 actual supervised sessions remain0/10. Actual account/order authority and supervision remain separate.

Prior detailed checkpoint: `docs/history/CURRENT_CHECKPOINT_20261012_2040.md`. User amendment supersedes its daily-budget wait and automatic scheduling instructions.

Exact next action: integrate reviewed Final auditor T before the fresh native pair, preserving cap removal. No contract requires a completed Final merely to integrate the auditor; Final completion is required only at audit registration. Then freeze the coherent release, admit fresh namespaces and execute M3 verification.

T integration: 42 reviewed files applied (24 source, 18 tests); jobs.py merged preserving both removed cap gates; all other cap edits and original test bootstrap/schema unchanged. Source verification plan includes 480 staged/legacy cases plus 27 cap/native regressions. U=`.cache/test-runs/m3-final-native-20261012-01` (96MiB), V=`.cache/test-runs/m3-final-runtime-20261012-01` (1GiB+384MiB); fresh admission passed. Old P reservation closed to new tests and unused capacity released; no old files changed. Exact next action: run integrated-source verification, repair evidence-backed failures, then build/freeze the combined release.

Merged-source verification: 507 passed, zero failures/errors/skips, 207.590 pytest seconds. Independent integration review CLEAR1/3. Native startup/campaign-boundary/independent-auditor compatibility extension is running as session44490, U/source-native02. Await this result before wheel freeze; do not launch concurrent native suites.

Combined release: source 545/545 passed (507 integration +38 actual native compatibility), zero failures/errors/skips. Source/archive/wheel/installation pin 190identical Python modules,483frozen source/config/test files; U/release01.json. Installed545checks running session87728 under540-second test wrapper; product Job deadlines unchanged. Source/wheel environment manifests prepared and hash-pinned; no new campaign fixture or numerical run yet. Current next action: await installed run, verify exact545test IDs and source continuity, then preflight/prepare fresh pair and use reviewed U/Run-Campaigns01.ps1.
