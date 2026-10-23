# M3 repair acceptance: attempt m3-repair-20261023-02

23 October 2026. This report reconciles every M3 acceptance requirement with the evidence of repair attempt `-02`.
M3 is engineering acceptance. It is not financial qualification and not proof of profit. Every record has `financial_accepted: false`.

## Result

The M3 engineering sequence passed in full on one release, built from one commit.
Attempt `-02` supplies the installed-package Final audit that the 14 October attempt could not complete. The 14 October attempt stays BLOCKED. It was not repaired or resumed.
All three synthetic momentum candidates failed the money gates. This is an honest result. No gate was changed.

| Item | Value |
| --- | --- |
| Release commit | `a81c9b4b05d9022f96e01b52a799712c19a6230b` |
| Release record | `.cache/test-runs/m3-repair-native-20261023-02/release01.json`, SHA-256 `4083ce9aa79e7a7af2df326b9cd671d1364d227e7bff0b70f06c095bea4647bc` |
| Wheel | SHA-256 `3664c8bea0697b326b901776d98e5f6422cfc2f9adb12ca598fa1876ad412b2c` |
| Execution pins | 37 inputs, SHA-256 `98cb9562a077c231de0b23a42a46ca9a9d3d927a539c0115947267ac1d7886d0` |
| Chain | Started 2026-10-23 12:22:05 EDT. Ended 17:09:18 EDT. Outcome `CHAIN_COMPLETED` |
| Source environment | `SOURCE_ENVIRONMENT_RESTORED_BYTE_IDENTICAL`, 9,975 files |

U = `.cache/test-runs/m3-repair-native-20261023-02`. R = `.cache/test-runs/m3-repair-release-20261023-02`. V = `.cache/test-runs/m3-repair-runtime-20261023-02`.

## Requirement reconciliation

| Requirement | Evidence | Result |
| --- | --- | --- |
| Exact release and source/package origins | `U/release01.json`; `U/campaign01-source-qualification.json`; `U/campaign01-wheel-qualification.json`; `verify-frozen-release.py` | Verified. 711 frozen files and 249 identical modules. The clean copy matches the commit. Both environments returned `ENVIRONMENT_BYTES_VERIFIED`. `uncommitted_files_included` is empty. |
| Affected regression and refusal controls | `U/regressions01.json`, SHA-256 `209dd1b1ac10ae4fa3b4a443ed78b8126b28686bf19e55d6b9219846f4c63b6a` | Verified. Source lane 592 passed. Installed lane 592 passed. 0 failures, 0 errors, 0 skips. 566 required and 26 supporting test IDs. |
| Full paired development campaign | `U/campaign-progress02.jsonl`; `U/pair-outputs01.log` | Verified. `PAIR_OUTPUTS_VERIFIED`: source 63/63, installed 63/63, 63 exact matching payloads, no scan supplements. The log holds one chunk record per unit (126). It does not count accepted chunks, so it is not comparable with the blocked run's 120. |
| Controls remain responsive with pending work | `U/late-prefix02.log` | Verified. `PAIRED_LATE_PREFIX_VERIFIED`. Source: 76 observations, maximum 0.226550 s. Installed: 80 observations, maximum 0.262838 s. Individual sample timestamps were not recorded. |
| Independent development audit and selection | `U/audit-progress01.jsonl`; `U/audit-outputs01.log` | Verified. `ALL77_OUTPUTS_VERIFIED`: 77 tasks, 72 independent unit audits. Paired comparison `EXACT_MATCH`: 63 completed, 0 failed, 0 skipped. |
| Immutable shortlist, one consumed Final | `U/final-freeze01-task.json`; `U/final-prepare01-task.json`; `U/final-batch01-task.json` | Verified. Evaluation `fde3f24c-56fa-5348-bfa9-b18c3120cecd`. Consumption sequence 1 before the batch. One completed native batch. Three momentum candidates. |
| Terminal restart cannot repeat Final | `U/final-restart01-task.json`; `U/final-restart01.json` | Verified. `CLEAN_NATIVE_FINAL_STAGE_VERIFIED`. The journal stayed at sequence 8, and consumption stayed at sequence 1. |
| Independent Final audit and actual controls | `U/final-audit-progress01.jsonl`; five task exports; `U/final-audit-outputs01.log`; audit files below | Verified. `PAIRED_NATIVE_FINAL_AUDITS_AND_RESTARTS_VERIFIED`. Source pause, resume and restart passed. The installed run and restart passed. Exact audit body. The original Final is unchanged. |
| Worst-case three-ridge computation/audit | Four `three-ridge-*02-job.json` receipts; `U/three-ridge-outputs02.log`; `V/three-ridge/*.audit` | Verified. `THREE_RIDGE_PAIRED_NUMERICAL_CHECKS_VERIFIED`. 3 candidates, 6 annual fits, exact producer payloads and independent audits (`VERIFIED_PASS`). Four jobs took 17.865 to 32.716 s and peaked at 563.223 MiB, within the unchanged 120 s and 4 GiB limits. |
| Memory, storage and child closure | 232 command records and 4 job records in U; 42 group command records in the regression folder | Verified. All exited 0 with no timeout, overflow, memory stop or monitoring error, except one. The exception is `storage-admission01`, which refused before any run (see below). |
| Requirement reconciliation and independent review | This report; the independent closeout review | See "Independent review" below. |

## Final candidate results

The Final evaluated three momentum candidates on generated synthetic prices. Status is `SYNTHETIC_ENGINEERING` for all three.
Source: `V/fixture/artifacts/runs/fde3f24c-56fa-5348-bfa9-b18c3120cecd/final/attempt-01.final`.

Fits: 0. The Final has `fits: []`, every fold has `fit: null`, and `ml_contribution_gate` is `NOT_APPLICABLE`. Momentum candidates have no fitted model.

| Candidate | Coverage 2024 (scored/candidate rows) | Coverage 2025 | Annual mean excess | Bootstrap lower bound, annual | Stress annual excess |
| --- | --- | --- | --- | --- | --- |
| `momentum-h01` | 753/3024 | 747/3000 | -0.1576 | -0.1716 | -0.1562 |
| `momentum-h05` | 741/3024 | 735/3000 | -0.0768 | -0.0852 | -0.1352 |
| `momentum-h21` | 693/3024 | 687/3000 | -0.0460 | -0.0591 | -0.0515 |

Bootstrap coverage is `APPROXIMATE_NOT_GUARANTEED`, with 21-session blocks.

| Candidate | Numeric gates failed | Strategy accepted |
| --- | --- | --- |
| `momentum-h01` | annual mean excess, period excess, confidence lower bound, stress excess, Sharpe, completed holding intervals | No |
| `momentum-h05` | annual mean excess, period excess, confidence lower bound, stress excess | No |
| `momentum-h21` | annual mean excess, period excess, confidence lower bound, stress excess | No |

Failure reasons:
- `momentum-h01` had no holding intervals. It never held a position, its volatility was 0 and its Sharpe is `UNDEFINED`.
- All three had negative excess return against the benchmark in both years, and a negative confidence lower bound.
- `momentum-h05` and `momentum-h21` passed the Sharpe gate on synthetic data (68.41 and 54.44). These synthetic values have no financial meaning.

All six external gates remain `UNVERIFIED` for each candidate: data, independent audit, reproducibility, risk, sealed window and timing.

Independent Final audit files, both `VERIFIED_PASS` with matching audit bodies:
- Source: `V/fixture/artifacts/runs/b25a08f4-76a3-5068-9c02-bf58d0e0e1ed/final_audit/attempt-02.audit`. Attempt 01 was the deliberate pause and stays as a partial file.
- Installed: `V/fixture/artifacts/runs/d0a3f9ed-92df-5df9-a17e-ac4052717e06/final_audit/attempt-01.audit`.

## Three-ridge scope and limitations

The three-ridge check is a standalone numerical exercise. It grants no owner or financial authority (`NO_OWNER_ADMISSION_FROM_PURE_COMPUTATION`).
Candidates: `ridge-h01-a001`, `ridge-h05-a010`, `ridge-h21-a100`. The auditor records these synthetic limitations:
`PARTIAL_TRAINING_FROM_2023_NOT_2016`, `THREE_OF_TWELVE_STOCKS`, `SIMULATED_AVAILABILITY` and `ZERO_UNVERIFIED_FEES`.

## Historical test evidence

The current 592-case receipt is authoritative for this release. The map's preserved historical cases are not part of it:
85 math/provenance cases, 4 publication-failure cases and 248 historical Final-auditor cases per lane.
They remain historical evidence only. This report claims no combined historical and current total.

## Deviations and limitations

- Attempt `-01` (commit `b3a688c`) stopped in step 2. The installed lane passed 20 of 21 groups (374 tests). The source lane did not run.
  Group `installed_negative01` timed out with exit 124 after 361.2 s, at its 360 s group deadline.
  Test `test_public_final_control_idempotence_no_redispatch_and_restart` was waiting in `runtime/control.py` `_connect`.
  The cause was commit `cc96a88`, which gave the client connection wait the 300 s command deadline. Commit `a81c9b4` restored the 5 s connection wait.
  Attempt `-01` evidence stays unchanged in the `*-20261023-01` folders.
- `storage-admission01` refused the run with exit 1. Scratch plus reserved growth was 137 MiB over the 13 GiB run cap. It wrote no admission file.
  The owner approved a cleanup under `docs/TEST_RETENTION.md`. One reviewed cleanup removed 42 passing pytest temporary folders (record `.cache/test-runs/m3-repair-cleanup-20261023-01/cleanup01.json`).
  `storage-admission02` then admitted the run at 12.936 GiB.
- The owner approved a 13 GiB scratch cap for this run's scripts only. Product code keeps 12 GiB. The cap ended with the run.
  After the run, scratch measured 13,568,465,416 bytes (12.637 GiB), over the 12 GiB product cap.
  Measurement: `usage_before` in `.cache/test-runs/post-m3-cleanup-20261023-01/cleanup-dryrun01.json`. The owner accepted this. A separate reviewed cleanup follows.
- Startup status probes recorded 158 expected errors before each supervisor accepted connections: 125 at about 5 s and 33 under 1 s.
  The blocked run recorded 212 of the same kinds. The verifiers accept these. The longest successful control reply was 4.470 s.
- Public shutdown/checkpoint of the full runtime is not demonstrated (`public_shutdown_checkpoint_verified: false`). Fixtures close after an authenticated pause.
  Development audits do not claim public review responsiveness. The Final audit stages record it for source pause, source resume and installed run.
- The agent launched the chain in its own PowerShell 7 window at the owner's request, because the owner was away.

## Preserved history

- The 14 October master run stays terminally BLOCKED. It lost the installed audit's exit receipt.
  `reports/M3_FINAL_INTERRUPTION.md` records the cause as unknown at that time.
  On 23 October, the System event log showed Windows Update restarts at 00:48:04 and 00:52:16 on 14 October. See `docs/M3_REPAIR_PLAN.md`, section "Cause of the block".
- The development-folder run (37 reviews) and the preceding master run (76 audits) stay terminally blocked. Neither started the Final.
- No identity was reset or reused. Attempt `-02` used new labels, folders, pair, seal and evaluation identities.

## Open gates

M3 engineering acceptance does not grant financial qualification, paper or live permissions, or supervised market sessions.
Real financial inputs, the vault, M4 economic reconciliation and M5/M6 requirements stay separate gates. Strata stays off.

## Independent review

Round 1 (one independent reviewer): `CHANGES_REQUIRED`. One blocker (candidate fits, coverage and failure reasons missing) and six should-fix items.
The agent checked each finding against the records and revised this report.
Round 2 (same reviewer): `CLOSEOUT_OK`. Every revision matches the records. The report makes no financial overclaim, does not count historical cases toward the 592, and hides no failure.
The reviewer noted that the four synthetic limitations of the three-ridge check also appear in both momentum Final audits.
