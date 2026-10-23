# Registration verification after cleanup

The owner approved fresh storage admission, registration repair tests, related regressions, and eligible cleanup on 19 October 2026.
This replaces the earlier single-attempt restriction for this verification work. Preserve every consumed attempt and failed result.

- [x] Prepare and review distinct capacity08 files with unchanged limits.
- [x] Review and run capacity09 after correcting historical contract-test verification. Whole job timed out.
- [x] Run the single reviewed capacity10 timing retry with unchanged code and limits. Whole job timed out.
- [x] Remove temporary children from eleven passing source jobs; preserve their parents and evidence.
- [x] Complete reviewed cleanup of four passing installed-package test folders.
- [x] Run capacity11 after cleanup, with unchanged checks and limits.
- [x] Pass full capacity admission. Capacity11 passed in 118.827439 seconds.
- [x] Pass registration tests in tests04. 27 passed; zero failures, errors, or skips. Whole job passed.
- [x] Pass contracts, linked history, and prepared-campaign regressions in tests05. 100 passed; zero failures, errors, or skips.
- [x] Pass campaign-record and development-seal regressions in tests06. 46 passed; zero failures, errors, or skips.
- [x] Remove eligible temporary files after passing jobs. All three cleanups verified; final folder usage measured.
- [x] Review results and update status, report, and project map. Nine pages and all 81 navigation links verified.

Use the existing interpreter, one CPU, 120-second jobs, and 16/12 GiB host memory floors.
Keep capacity at 128 MiB and test jobs at 4 GiB. Keep all folder and category limits unchanged.
Use at most three repair rounds per failure class. Use distinct attempt names for any repaired run.
Stop dependent jobs if storage admission, memory, source identity, or process cleanup fails.
Accept only passing whole-job closures and exact source test results. Record partial results separately.
No actual registration, campaign execution, broker action, security change, service, or publication is included.

Preparation: `.cache/clean-env-m0/Scripts/python.exe -B tools/prepare_registration_completion.py prepare`.
Execution uses preparation11 `run_bounded.py`, capacity11 with kind `capacity`, then fresh tests with kind `ai`.
Prepare each test job with `tools/prepare_registration_completion.py LABEL` after capacity passes.

Capacity08 failed before its census because historical release verification read the revised `tests/test_contracts.py`.
The original archived test matches both historical manifests. The current test has a separate fingerprint in new test jobs.
Capacity09 checks that historical file against its preserved archive. No storage check, limit, or original fingerprint is removed.
Capacity08 exited with zero remaining children in 35.7104693 seconds. Its failed record remains preserved.

Capacity09 confirmed enough storage in its child census, but its parent reached 120 seconds during the final count.
The whole job remains failed. Exit was observed and zero children remained. Product tests did not start.
A proposed metadata reader passed eight preparation checks but was slower across all 31 capped folders.
Its source and comparison evidence remain in `metadata-check01`. No active wrapper uses it.
Capacity10 is one reviewed repeat using the original reader and all unchanged checks.
It also reached 120 seconds during the final count. Its passing child census does not admit product tests.
The next attempt follows reviewed cleanup of wholly passing temporary fixtures, reducing work for every full count.
Capacity11 is the third and final round for this deadline failure class. No deadline or storage limit increases.

All required work is complete. Final source results: 173 passed, zero failed, zero errors, and zero skipped.
All three test jobs passed their complete resource checks. All three temporary test trees were cleaned with evidence preserved.
See `../reports/REGISTRATION_COMPLETION_20261019.md` for counts, measurements, and remaining work outside this scope.
The external map receipt is `registration-completion01-map-review.json` beside the stable project-map inputs.
