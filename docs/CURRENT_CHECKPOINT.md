# Current Compertum checkpoint

13 October 2026. All new work stays in `C:\Users\bgonn\Desktop\Compertum`. Strata and its model server must stay off. Keep one heavy job active, require 16 GiB free physical/commit headroom to start, and stop below 12 GiB. Worker limits remain 4 GiB, four CPU threads and 120 seconds.

## Checklist

- [x] Consolidate master, preserve original files/history and publish rollback checkpoints. Details: [consolidation report](../reports/MASTER_CONSOLIDATION.md).
- [x] Preserve the historical M3 run: both 63-outcome campaigns matched, but only 37 of 77 audits/reviews completed. Its source aggregate is terminally BLOCKED after a health refusal. Never resume or repin it. Details: [recovery report](../reports/M3_INTERRUPTION_RECOVERY.md).
- [x] Reproduce and repair stale review health. Verify 562 distinct matching tests in each source/installed lane, zero failures/errors/skips, with no remaining test children. Preserve failed runs. Details: [repair record](M3_REVIEW_HEALTH_REPAIR.md).
- [x] Qualify both complete environments with unchanged Python and 38 dependencies. Freeze 485 release files and 190 matching source/installed modules. Preserve the old M0 environment, original cache files and corrected SciPy assessment.
- [x] Prepare fresh master runtime identities and an actual nonsparse 1 GiB reserve. Independent admission review cleared 2/3 against all 37 bound inputs.
- [ ] Complete the fresh paired 63-outcome campaigns, exact output comparison, all 77 audits/reviews, generated Final, independent Final audits/restarts and three-ridge exercise. Active terminal session: **48305**. The fresh source campaign completed63/63 outcomes in58 chunks, zero failed/skipped; installed-package execution is next in the same running sequence. Local receipt: artifacts/m3/master_source_campaign.json.
- [ ] Reconcile acceptance with saved evidence, obtain independent closeout review and publish verified status.
- [ ] Integrate only the mapped 28 M5 retry/opening files, preserving newer Final/health work. Verify source/installed and native checks before implementing the existing market-owner plan.

## Exact next action

Monitor session48305. It runs `Run-MasterCampaigns01.ps1` and, only after success, `Run-RemainingM3-Memory01.ps1`. Both are fresh-only: do not rerun over existing labels. On any failure preserve command/result/state and diagnose before further execution. Keep product, tests, environments and bound helpers frozen while the sequence runs.

Tooling: `.cache/test-runs/m3-master-native-20261013-01` (U). Runtime: `.cache/test-runs/m3-master-runtime-20261013-01` (V). Current progress: `U/campaign-progress02.jsonl`, then `U/remaining-sequence01.jsonl`. See [native plan](M3_MASTER_NATIVE_PLAN.md) for exact commands and pins and [acceptance map](M3_MASTER_ACCEPTANCE_MAP.md) for required evidence.

- New pair SHA: `52a50e72480e35faaabae4b1ec332c4561ab863cd0cb1dd4b0aa5e3bc56857a7`.
- Execution manifest SHA: `5892bd9eab5dd6edf194b03153db6748470067519daae84dfaf2621eddb9533f`.
- Current regression receipt: `artifacts/m3/review_health_complete_regressions.json` (562 distinct IDs per lane).
- Source qualification: `U/env-source-qualify03`; installed qualification: `U/env-wheel-qualify01`.
- Latest published commit before this update: `a5e888057c762a8a6759de332044c5f4ebd4fe31`.

## Roadmap and remaining authority

M0 accepted. M1 bounded real-data replay verified; full financial input qualification open. M2 synthetic components verified. M3 fresh native closeout is running; full acceptance is not claimed. M4 fake-broker engineering accepted. M5 local integration and actual walkthrough remain. M6 has **0 of 10 actual supervised market sessions**.

The 28-file M5 integration map is preserved read-only at `C:\Users\bgonn\Desktop\Compertum-development\.cache\test-runs\m3-final-native-20261012-01\next-integration-map01.json`. After it passes, continue [the market-owner plan](M5_MARKET_OWNER_PLAN.md). Do not overwrite master with a whole historical archive. A fresh read-only review verified all28 before/after hashes and both archives, with no health/Final overlap. R requires521 cases per lane (the actual-reserve case is still pending); S requires94, including13 native cases not yet run. Exact compatibility groups are saved in artifacts/m5/master_integration_readiness.json.

Current authority includes local engineering and meaningful verified GitHub checkpoints. It does not include new spending, account/order actions, new permissions, admin changes, protected real-data evaluation or a scheduled service. No new automation is needed. Secrets, datasets, runtime databases, detailed local evidence and backups stay out of Git.

Historical runtime identities, failed receipts and backups remain preserved. The old run's 819-case combined coverage is historical; do not relabel it as fresh current-release coverage or add overlapping counts. Detailed preservation records remain under `artifacts/m3`, `.cache/test-runs/m3-interruption-recovery-20261013-01` and `backups`.
