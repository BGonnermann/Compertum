# Test file retention

## Owner decision, 19 October 2026

The owner approved routine cleanup instead of repeated test-storage increases.
This rule replaces blanket retention of disposable test files in earlier plans.
Historical results, failed attempt numbers, and original reports remain unchanged.

## Keep

- Keep test code, configuration, input identities, result XML, logs, source fingerprints, and process exit records.
- Keep real research data, operating databases, original runtime identities, and the real emergency reserve.
- Keep files needed to investigate unresolved failures or reproduce important findings.
- Keep test-run parent folders so deleted temporary files cannot make an old attempt appear unused.

## Remove after verification

Remove generated temporary files from completed, wholly passing test jobs after checking the saved results and dependencies.
This includes synthetic databases and dummy reserves inside disposable test folders.
Do not create full backups of reproducible passing test files merely to delete them.
Keep the commands and test inputs needed to run the tests again under a new attempt number.

For failed jobs, keep failure reports permanently as project evidence.
Keep their temporary files while the failure remains unresolved.
After resolution, record the diagnosis, repair verification, and reproduction inputs before removing disposable files.
Do not infer resolution from file age or an unrelated passing test.

## Routine procedure

1. Check available memory and use one bounded maintenance job at a time.
2. Select exact temporary paths beneath `.cache/test-runs`.
3. Check successful job exit, zero remaining children, and complete passing test results.
4. Check that no active job, unresolved investigation, or future test depends on those temporary files.
5. Preserve result-file hashes and record selected paths, counts, and measured storage charge.
6. Reject linked ancestors. Never follow links during cleanup.
7. Remove only the checked temporary files. Keep each attempt's parent folder and saved results.
8. Verify removal, unchanged result hashes, and the resulting local folder usage.
9. Record partial removal honestly if cleanup stops. Never erase or reuse the cleanup attempt.

The owner approval covers routine cleanup meeting these conditions. Do not request a separate storage increase first.
When storage admission blocks tests, bounded cleanup may reduce existing usage without authorizing tests or clearing operating stops.
Keep cleanup records small and within existing folder, category, and total limits.
Fresh full storage admission remains required before subsequent product tests.
Unclear ownership, missing results, active use, or access denial excludes the affected files from cleanup.
Do not change permissions or relax operating checks to delete them.

## Completion rule

Clean eligible temporary files during test-job completion or before the next admitted test batch.
Use the saved results to decide eligibility. Folder age alone is insufficient.
No scheduled service is required. Keep the 50 GiB total and existing category limits unchanged.

## First cleanup checklist

- [x] Record the owner-approved retention rule and exclusions.
- [x] Check completed history and review-plan test jobs and independent review.
- [x] Remove eligible temporary files and verify preserved evidence.
- [x] Update current status and the project map with measured results.

Scope excludes registration repairs, new product tests, broker actions, and changes to storage limits.
Use at most three repair/review rounds. Stop on unsafe paths, active use, missing evidence, or unsafe memory.
Validation uses a dry run, independent review, exact-path removal checks, and saved evidence hashes.
