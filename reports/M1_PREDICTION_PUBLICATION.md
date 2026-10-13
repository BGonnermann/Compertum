# Saved prediction publication verification

9 October 2026 ET. This component is complete. All nine remaining recovery checks passed after the owner approved removal of two old test files. Full M1 and financial acceptance remain incomplete.

Saved synthetic runs now include six trading replays and prediction reports for horizons 1, 5 and 21. The scoring cutoff, input hash, unit identity and output digest stay bound together. Existing six-unit runs retain their previous format.

Workers now enforce their deadline independently of supervisor calls. Late polling accepts an on-time result and rejects a timed-out result even when its exit code is zero. If the deadline monitor cannot start, the suspended child is terminated. Each of these three defects was reproduced before repair and has a passing native regression. Resource limits, dependencies and financial thresholds were unchanged.

| Verification | Result |
| --- | --- |
| Broad source regression | 479 passed, 11 Windows-inapplicable skips; recovery modules checked separately |
| Final source native checks | 17 passed, zero failures/skips |
| Installed-wheel native checks | 17 passed, zero failures/skips |
| Small recovery guard check | 1 passed, zero failures/skips |
| Remaining recovery checks | 9 passed, zero failures/skips on unchanged final source |
| All current source test IDs | 502 accounted for: 491 unique passes and 11 allowed platform skips |
| Source/wheel outputs after prediction-stage pause/resume | All nine files byte-exact |
| Prediction-stage crash/restart | Passed; six prior replay artifacts preserved |
| Environment | Python 3.14.7, 39 matching distributions, identical package hash |
| Independent review | One bounded read-only pass; finding reproduced and fixed |

The broad source run preceded the final monitor-start cleanup repair. All affected native checks were then rerun in both environments, and the remaining recovery checks passed on the same final source. These are reconciled verification phases, not a claim that one unchanged final full suite ran. Both source identities and archives remain available. No required native check was skipped.

## Approved cleanup and storage

The owner approved deleting the two old reserve files only if their tests had completed and passed. Their passing command/JUnit reports were checked. Both original files and both compressed backups were verified by SHA-256 before deletion. Exactly two 1 GiB files were removed, releasing 2 GiB. Their backups, test reports and all other historical files remain.

The final nine tests created two new 1 GiB reserves in a fresh checked namespace. These new files remain. The project still uses the same 5 GiB scratch limit.

A newly generated preflight report accidentally included the entire file inventory, causing a temporary scratch overage of 987,048 bytes after the tests. The exact report was archived and verified, and its scratch copy was replaced with a compact summary. No storage limit changed. The final storage measurement is recorded in the machine receipt; scratch is below 5 GiB with about 8 MiB remaining.

Cleanup proof: [approved cleanup receipt](../backups/verification-reserves-20261009/approved-cleanup.json). Original backup manifest: [manifest](../backups/verification-reserves-20261009/manifest.json).

## Evidence

Initial repair logs, red/green tests, source/wheel identities and output comparisons: `.cache/test-runs/m1-prediction-finish-20261009-02/`.

Fresh recovery checks, all-test reconciliation, preserved prior status and final acceptance reconciliation: `.cache/test-runs/m1-prediction-recovery-20261009-03/`.

Current machine receipt: [prediction_publication.json](../artifacts/m1/prediction_publication.json). The prior interrupted-stage evidence and prior component status are retained.

Development checkout: `C:\Users\bgonn\Desktop\Compertum-development`, branch `local/m0-development`, published base `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781`. Changes are uncommitted and unpublished. The original Compertum checkout, both Git indexes, lock/specification and prior M0/M1 acceptance receipts are unchanged. Spending remains $0. No Strata requests, broker/account access, real-data collection, protected evaluation, training or unattended service was introduced.
