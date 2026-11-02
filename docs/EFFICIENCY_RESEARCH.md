# Efficiency research - 2 November 2026

Status: findings, five low-risk changes made, other items for the owner.
Owner request, 2 November 2026: "run a autoresearch cycle for compertum about the effeciency of our system, what tweaks we can do to help smooth it out and other optimizations."
Owner, same day: "yes, implement the low-risk changes when it reports".

A read-only research agent studied the code, the transcripts of 1 November and the test folders. It changed no file.
It started no engine run and made no provider call. It opened no vault data, ledger or database.
Samples: the 12-run GLM real-data batch of 1 November (647 requests, 24 cycles), GEPA run `run-20261101-2a8ab591`, and 609 sandbox jobs.
The earlier report `docs/IMPROVEMENT_RESEARCH.md` covers research quality. This report covers time, cost and friction.

## Main result

Model time is the largest cost. In the GLM batch, request time was 56 minutes over 24 cycles.
Shares of request time: Engineer builds 38.8%, Mathematician specifications 23.1%, Researcher memos 15.4%, Mathematician reviews 14.1%, Director 8.7%.
Sandbox jobs are short on today's markets: p50 0.08 s, p90 0.89 s, maximum 14.6 s.
Storage is the largest operating risk.

## Changes made (low risk, no owner item)

1. Each model call record now keeps the provider's cost in US dollars and the cached prompt tokens, when the reply reports them.
   Forms: OpenRouter `usage.cost` and `usage.prompt_tokens_details.cached_tokens`; DeepSeek `usage.prompt_cache_hit_tokens`.
   Bad values (not a number, negative, over $1,000, true or false) are dropped. File: `src/compertum/ai/models.py` (`usage_counts`).
   Reason: for the GLM batch, token counts at list prices gave $0.080, but the balance fell by $0.27 to $0.28.
2. New read-only tool `tools/run_cost.py [RUN_ID]`. It adds up calls, minutes, tokens, the cached share and the cost per role from a run's transcript.
   Older transcripts hold no cost. The tool then shows "no cost reported".
3. `tools/run_tests.py` adds `--durations=25`, unless the caller gives a `--durations` value. Every lane output now names its 25 slowest steps.
4. The whole suite collects again. Three native test files had the same base names as files in `tests/`, so collection stopped with 3 errors.
   They are now `tests/windows/test_native_fake_resume.py`, `test_native_incident_alert.py` and `test_native_operation_progression.py`.
   Importlib import mode was not used, because many tests import other test modules by name.
5. Four test files stop their local HTTP test server faster (`poll_interval` 0.01 s instead of 0.5 s), as four other test files already did:
   `tests/test_ai_models_interface.py`, `test_harness_agent.py`, `test_harness_model.py`, `test_pull_bars.py`.
   Measured: `test_ai_models_interface.py`, `test_run_cost_tool.py` and `test_run_tests_tool.py` together went from 24.18 s to 5.37 s (100 tests).
   The harness lane took 11.35 s (143 tests), against 13.30 s in `.cache/test-runs/harness-simplify-20261102-01/harness-lane.txt`.
6. `.gitignore` ignores the generated `config/models-route-*.toml` candidates of `tools/route_search.py`.

Not changed, because another session had uncommitted edits in the file: `tests/test_engine_roles.py` has the same 0.5 s server stop.
Not changed, because they are product tests or product helpers with recorded fingerprints: `tests/helpers/paper_*_supervisor.py`, `tests/helpers/fixture_rehearsal_source.py`, `tests/test_ai_strata_contract.py`.

## Items for the owner

1. Storage, scratch category. 32 dummy reserve files of 1 GiB each (`execution-reserve.bin`) hold about 32 GiB of the 38.78 GiB used in `.cache/test-runs`. The cap is 50 GiB.
   - 21 of them are in `e8-windows-01` (28 October). That folder has no `output.txt` and no `retention.json`, and no document names it.
   - The others are in milestone evidence folders, and nine reports or plans name some of them. The `native-shared` folders may serve later native tests.
     Two M3 runtime folders hold one reserve each. M3 closed as BLOCKED, so those stay.
   - `e8-windows-01` is the Windows lane of 27 October: 209 passed, 126 failed, 5 errors. Its failures are unresolved and preserved.
   - Done, 2 November 2026, owner decision "Delete fillers only (Recommended)": 22 zero-filled 1 GiB files were removed, 21 from `e8-windows-01` and 1 from `total200-targeted-20261024-230045`.
     All other files stay. Free disk went from 61.06 GiB to 83.06 GiB. Record: `.cache/test-runs/cleanup-records/cleanup-20261102-080744-reserves.json`.
   - The other 10 large reserves stay. Live `native-shared` runtimes need theirs. The plans pin the lineage reserve. M3 history and the known `full-monitor-repair` failure stay.
2. Storage scan time. Each start walks the project. Measured: 15.4 s of the 30 s `storage_scan_seconds` deadline, 349,461 files, 71% under `.cache/test-runs`.
   The gap between two practice runs was 21 to 22 s. Cleaning the small files of passed old jobs could cut the scan to about 5 s (estimate).
   The large file counts are in `m5-local-economics` (36k files) and `native-accounting` (24k files). Both are evidence folders, so the owner decides.
3. Backups category: 20.41 GiB of 21.0 GiB. 16 GiB are 1 GiB reserves inside backed-up fixtures, and 9 more are 320 MiB reserves in `historical-test-folders-20261013-01` and `-02`.
   Checked 2 November 2026, nothing removed. These backups exist to keep the fixtures byte for byte, and the reports record that the bytes are unchanged:
   `reports/M5_MARKET_OWNER_PROGRESS.md`, `M5_RETRY_INTEGRATION.md`, `M5_OPENING_INTEGRATION.md`, `docs/M3_REPAIR_PLAN.md` and `M3_PAIR_VALIDATION_REPAIR.md`.
   Of the 16, 9 hold passed fixtures, 6 hold failed fixtures, and 1 is the interrupted M3 runtime.
   A sparse file does not help: `storage.py` charges each file at the larger of its length and its allocation.
   Options for the owner: keep everything and raise the backups limit, or allow removal from the passed fixtures only (9 GiB), which ends their byte-for-byte record.
   Done, 2 November 2026. Owner: "raise backup to 100GB and put them in the D drive." The ceiling is 100 GiB, and 67 backup folders (20.39 GiB) moved to `D:\Compertum\backups`. No reserve was removed.
4. Engineer task: 92% of 210 builds spent their first request on reading `/main.py` or `/spec.md`, which the task could show directly.
   Estimate: about 10% fewer requests per cycle. It changes what the firm sees, so it is a hand edit of the firm. That edit needs the bench exam, and the bench is off.
5. Mathematician review in a practice cycle: 14 to 15% of request time, and the result is only recorded. `review: off` already exists. Section 19 and the sealed `cycle.py` name the review.
6. Director approval: 594 of 600 memos approved, 11% of requests. Section 19 names the step.
7. Parallel practice batches: practice accepts one manifest, so a 12-market batch ran in sequence for 35 minutes. The `run_together` path could run them together in about 5 to 8 minutes (estimate).
   It needs the owner's OK for concurrent runs. The client has no retry for HTTP 429 replies, so rate limits would become step faults.
8. French data and the 120 s sandbox deadline (item 13 of `docs/IMPROVEMENT_RESEARCH.md`): the sandbox has no numpy or pandas.
   Code that re-reads all rows for each session took 18.5 s on 12,824 rows. Code with `statistics` per session took about 79 to 100 s for the VALIDATION period. The current p90 job could reach about 90 s on French data (estimate).
   Facts in the Engineer task (row counts, 120 s, standard library only) need the owner's OK under the no-steering rule. A longer deadline changes the sealed `execution.py`.
9. `library_multi` speed: `choose()` took 26.8 s for 75 settings on a generated 49 by 20,518 panel. Computing weights only to the end of TRAIN and the benchmark metrics once per window could save about 25%.
   Another session is changing that file now. A numpy rewrite would change float sums and the `score_sha256` checks, so it is an owner item.
10. Request time limits: 300 s and 600 s, against a longest GLM request of 127.8 s. AGENTS.md says to retain job deadlines, so the limits stay unchanged.
11. One HTTPS connection and one event loop per request (`models.py`, `_request`). Estimated cost 50 to 150 ms per request, 1 to 3% of cycle time. Low value.

## Not worth doing now

- Retries for HTTP 429 and 5xx replies: 1.15% of 25,243 requests did not complete. Reconsider with item 7.
- Prompt order for provider caches: system prompts are small, and Engineer conversations already keep a stable prefix.
- Data handoff to the sandbox: about 18 ms per job.
- Harness start: importing `compertum.harness.cli` takes 0.256 s.

## Not checked

The AppContainer start cost, `ledger.summary()` per cycle, the history and French loaders (they read vault rows), the engine lane durations,
and provider cache hits (item 1 of the changes now records them).
