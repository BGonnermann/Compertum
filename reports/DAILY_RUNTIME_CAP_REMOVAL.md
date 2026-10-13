# Daily research runtime cap removed

12 October 2026 owner correction. The unapproved two-hour daily cap is removed from configuration and both native admission paths. The midnight continuation automation is paused.

Verified: 27 source checks and the same 27 installed-wheel checks passed; zero failures, errors or skips. All 177 Python modules match source, wheel and installation. Real bounded jobs ran with 7,078, 7,200 and 86,400 seconds already charged. Historical charges were retained. Per-job deadlines, CPU/RAM limits, single-job exclusion and strict configuration remain tested. Independent review closed with no material finding.

The exact former 7,200-second configuration field is accepted and ignored for old configurations. Other changes to that field or remaining limits are refused. Source archive and wheel hashes, commands and XML receipts: `artifacts/m3/daily_runtime_cap_removal.json`.

Previous Q campaign results remain preserved under their original release identity. M3 still needs a fresh native pair and Final acceptance. This policy correction is complete; it does not complete M3.

An inactive historical M0 fixture was moved intact to backups: all 128 files (1,076,728,254 bytes) and 28 subdirectories verified. PowerShell changed its root directory identifier. Historical bytes are preserved, but that archived fixture must not be reopened as the original runtime or have its stored identities rewritten. The failed identity check and recovery receipt remain in `.cache/test-runs/m3-fresh-native-20261012-01/`.

The original `Compertum` checkout was preserved.

## Files changed for the cap correction

Application: `src/compertum/runtime/jobs.py` removes both daily allowance gates while retaining accounting; `src/compertum/config.py` retires the setting and handles the exact legacy value; `src/compertum/campaign_review.py` removes the obsolete refusal reason. Configuration: `config/default.toml` removes the daily default. Tests: `tests/test_config.py`, `tests/windows/test_jobs.py`, and `tests/windows/test_campaign_job.py` verify compatibility and genuine work beyond the former allowance. Documentation and receipts record the owner correction. These changes are in `Compertum-development`; the original `Compertum` folder is preserved.

The daily allowance was a project configuration choice, not an Alpaca or OpenAI service limit. Work can run now under each job's existing safeguards. The cap-related automation is inactive.
