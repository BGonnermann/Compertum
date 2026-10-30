# Current Compertum checkpoint

## Harness 0.6.4 resize-safe echo and side-pane watching - 29 October 2026

The owner reported two problems with a screenshot: finished boxes broke apart after a terminal resize, and `/watch` blocked typing.
Cause of the first: each finished box stayed in the scrollback at the old width. Windows Terminal re-wraps such lines on resize.
Fix: after Enter, the box is erased and a one-line echo, `› task`, stays. Ctrl+C and Ctrl+Z also erase the box. Only the live box is drawn as a box.
Second: inside Windows Terminal, `/watch` now runs `wt -w 0 split-pane -V` with `python -m compertum.harness.pane`, then moves focus back left.
The pane is read-only. It reads the run record and log, or the research store in read-only mode. A new `read_card` in `runs.py` avoids `RunManager`,
which would arm deadline timers and could set the kill switch. Run IDs are checked before they reach the `wt` command. Outside Windows Terminal, `/watch` is unchanged.

Verification, source, product environment: harness unit lane and the console native tests, 122 passed, 0 failed, 0 skipped.
An earlier attempt failed 3 editor tests, which pinned the old box that stayed after Enter; they now check the echo on an emulated screen.
A live smoke test ran the pane viewer for 4 seconds in a hidden console on `run-20261029-d783224d`: no error, and it showed the run and its cycles.
Not checked: a real Windows Terminal split pane. The two sandbox native tests were not run, because the bench-4 baseline was running.
Files: `.cache/test-runs/harness-pane-20261029-192604`. The project map was not refreshed; this change affects only the console display.

Exact next action: the owner restarts `compertum-harness`, resizes the window after a task, and types `/watch` to check the side pane.

## Harness 0.6.3 calmer display - 29 October 2026

The owner asked for more space, cleaner text and some color: "my eyes go everywhere". Most output was plain white with no gaps.
Changed, in `src/compertum/harness/display.py`, `editor.py` and `cli.py`:
- Palette from the project map: orange for tool marks, the box title, the selected command and `RUNNING`; warm grey for detail; green and red for results.
- One blank line between the task box, thinking, each tool step, the answer, the result line and each command result. Never two.
- The result line is now `✓ done  ·  2 steps  ·  0:31`. Errors start with `✗`.
- Run cards align their keys. `/help` shows descriptions in grey. Thinking is faint italic.
- Colors are added only when a line is written, so the box's width checks still measure plain text.
Scripts and logs keep the earlier plain output. A rendered before-and-after preview was checked during the work.

Verification, source, product environment: harness unit lane and the console native tests, 119 passed, 0 failed, 0 skipped.
That is 115 unit tests, 2 console native tests and 2 run-detach native tests. One earlier attempt failed 1 test, which pinned the old diff colors;
the test now pins the new palette. The two sandbox native tests were not run, because the bench-4 baseline was running.
Files: `.cache/test-runs/harness-style-20261029-190426`.
The project map was not refreshed. This change affects only how text looks, so its footer still names harness 0.6.2.

Exact next action: the owner restarts `compertum-harness` and checks the colors and spacing in Windows Terminal.

## Harness 0.6.2 engine runs outlive the terminal tab - 29 October 2026

The owner asked what is next for the harness and approved the first open item: runs that the harness started probably ended when the tab closed.
Cause: the run process shared the harness console, so a closed console could end it.
Fix, in `src/compertum/harness/runs.py`: `/run`, `/gepa` and `/bench` start the run in its own hidden console (`CREATE_NO_WINDOW`).
The run also leaves the console's job object (`CREATE_BREAKAWAY_FROM_JOB`). If the job forbids that, the harness starts the run without leaving the job.
`/test` runs keep the old start, because only an open console enforces a test deadline. Engine runs have their own hour limit.
Recovery after a restart and `/stop` through the kill switch are unchanged.

New native test `tests/windows/test_harness_run_detach.py`: a parent in a job starts one run the new way and one the old way.
The new run has its own console. It survives the closed job if the job allows leaving. The old run shares the console and ends with the job.
This is a simulation with a job object and a hidden console. The owner's real Windows Terminal tab close is not yet checked.

Verification, source, product environment: harness unit lane and the console native tests, 117 passed, 0 failed, 0 skipped.
That is 113 unit tests, 2 console native tests and 2 new native tests. The new native test then passed 3 more times.
The two sandbox native tests were not run, because the bench-4 baseline was running. This change does not touch the sandbox.
Files: `.cache/test-runs/harness-detach-20261029-184815`. Free memory was 42.4 GiB before the tests.

The project map was refreshed: footer and owner node show harness 0.6.2. 9 pages, 81 internal links with 0 broken; page 1 was inspected.
Git refused the repository because `CodexSandboxOffline` owns `.git`. The owner added a `safe.directory` entry for this folder.

Exact next action: the owner starts a short engine run from the harness, closes the tab, reopens the harness and checks `/runs`.

## Markets calibrated: 4,096 sessions, bench-4 - 29 October 2026

The owner asked whether about 1,000 cycles and several GEPA runs changed nothing. The record says yes: 39 run summaries,
about 1,160 trials, 0 candidates passed the gate and the Auditor, and no GEPA candidate was applied.
Cause found with bench-3: on 500-session markets even the exact planted rule fails the gate. So no cycle could reach the top levels,
and GEPA got almost the same score for every candidate. The owner chose to calibrate the markets first: "Okay let's do step one first."

Built:
- `tools/calibrate_markets.py`: no model call, no sandbox, 528 markets in 9 seconds, calibration seeds 5000 to 5007.
  At 500 sessions the planted rule passed the gate on 7 of 64 patterned markets (192 trials). At 2,000 sessions all strong patterns passed on every seed,
  also at 1,200 trials. At 4,096 sessions weak patterns passed on 4 to 7 of 8 seeds. Simple rules on empty markets passed 1 of 144 checks at 192 trials, 0 at 1,200.
  Output: `.cache/test-runs/calibration-20261029/calibration.json`.
- `bench.CALIBRATED_SESSIONS` is 4,096. Practice and GEPA synthetic markets use it by default (`--sessions` still overrides). Real markets keep 500.
- `bench-4`: bench-3's layout on seeds 127 to 142 at 4,096 sessions, regime starts scaled to 2048, 1638 and 2457.
  The planted rule passes its gate (192 trials) on 8 of 10 patterned markets. It fails on weak reversal seeds 133 and 134. No empty market passes,
  and no simple rule passes on its empty markets. `tools\practice.ps1 -BenchSet bench-4` selects it.
- bench-1, bench-2, bench-3 and holdout-1 are unchanged (bench-3 is now pinned by digest too).
- Defect found by the engine lane: a 4,096-session practice run refused with `EVENT_INVALID`, because the market fingerprint used the 64 KiB event encoder.
  The fingerprint now uses the same encoding without the cap. Earlier markets keep the same fingerprint, so their lessons history stays linked.
  A practice market at 4,096 sessions is a new market, so it starts with an empty lessons table.

Verification, source, simulated markets: engine lane, all engine files with `test_ai_models_interface.py`, `test_run_tests_tool.py` and
`test_clean_test_runs.py`: 312 passed, 0 failed, 0 skipped, 8 pandas warnings. Product lane, the same files: 247 passed, 0 failed, 7 skipped.
The first engine lane failed 1 test (`test_practice_run_as_a_separate_process`, the refusal above); its files are in `.cache/test-runs/calibrated-markets-engine-20261029-171654`.

Committed as `b9b5f05`. The project map was refreshed: 9 pages, 81 internal links with 0 broken; pages 1 and 2 were inspected.

Open:
- Holdout-1 has 500 sessions, so it is not calibrated. A calibrated holdout set is needed before the next holdout use.
- Real markets have the same limit: 500 sessions give 150 VALIDATION sessions. That is part of the real-market work.
- Step 2 is the owner's decision: count trials for the whole history, as now, or per research question or market.

Cleanup, owner OK on 29 October 2026 ("go ahead with the cleanup"): the `tmp` folders of the six resolved failed test jobs of 29 October were removed
with the test runner's link-safe functions: 5,570 files, 232.8 MiB. Each job keeps `output.txt` and `retention.json`.
Record: `.cache/test-runs/cleanup-records/resolved-failures-20261029-183410.json`. The 40 engine sandbox folders were already empty.

Bench-4 flash baseline `run-20261029-3c88c5bb` started at 18:34 EDT on the owner's yes, through `tools\start_run.ps1` (process 19096, 4 cycles per market,
2,400 requests). It runs into the 21:00 to 00:00 EDT peak. Record: `.cache/test-runs/practice-bench-20261029-183426-record.json`.

Stopped by the owner at 18:57 EDT ("just stop deepseek") through the stop file, which was removed after the END row: `KILL_SWITCH`, 6 cycles,
138 requests, 23.6 minutes. Verdict `INCOMPLETE: a market has no finished cycle` (6 of 16 markets had a cycle). Patterns found 1 of the 6 markets reached; false discoveries 0.
- seed 127 (momentum 5, 0.004): level 10; 3 candidates passed the bench gate; found by 2, best capture 0.560.
- seed 128 (momentum 5, 0.004): level 10; 1 candidate passed the bench gate; best capture 0.381, below the found mark of 0.5.
- seed 129: level 7. seed 130: level 6. seed 131 (weak): level 7. seed 132 (weak): level 2.
These are the first level-10 cycles in the project: on calibrated markets an audited candidate passed the bench gate.
The real gate, with the global count of 1,183 trials and the recorded trial variance, still gave these candidates a deflated Sharpe of 0.
The recorded variance mixes trials from 500-session markets, so step 2 (how trials are counted) now decides whether any practice candidate can be promoted.

Flint small test `run-20261029-d783224d` (owner-started 19:00 EDT, `flint@q4_k_m` in LM Studio, bench-4, 1 cycle per market): `MEASURED`, `CYCLE_LIMIT`,
16 cycles, 316 requests, 48.3 minutes, 7 step faults, 31 candidates, $0. Patterns found 2 of 10; false discoveries 0 of 6; mean level 5.88.
Level 10 on seeds 127 (momentum, capture 0.777) and 130 (reversal, 0.532): one candidate each passed the bench gate. Level 9 on seed 132 and 8 on seed 129.
Levels 1 and 2 on seeds 128, 135 and 140 (nothing built). Median generation speed 63 tokens per second, 173k output tokens.
Not comparable with the stopped DeepSeek run (6 cycles). Both models reached level 10 on seed 127. The comparison needs equal runs.
Record: `.cache/test-runs/practice-bench-20261029-190000-record.json`.

Owner questions of 29 October, answered from public sources (no change made): the best local model for the firm is Qwen3.6-35B-A3B;
its Unsloth UD-IQ3_XXS build (13.2 GB, 91.2% top-1 agreement with the full model) fits the 16 GB card; UD-Q3_K_M (16.6 GB, 93.0%) and
UD-Q4_K_S (20.9 GB, 94.8%) need offload. Mainline llama.cpp now has a MoE expert cache (`--moe-cache-mib`) and MTP speculative decoding for Qwen3.6;
LM Studio's engine lags both. Parallel slots give no throughput on one local MoE model. Proposed, not done: replace LM Studio with the official
`llama-server` Windows CUDA build as a child process of `toolspractice.ps1`. That changes the AGENTS.md server rule and waits for the owner's explicit OK.

Owner decision, 29 October 2026, 20:10 EDT: "nvm, im just going to keep flint." No model download, no engine switch, no rule change.
The model findings stay recorded here and in docs/ENGINE_PLAN.md ("Finding local models"); `tools/find_models.py` lists GGUF models from the Hub on demand.

Exact next action: the owner starts the bench-4 Flint baseline (4 cycles per market, $0): `tools\start_run.ps1 -Mode bench -BenchSet bench-4 -CyclesPerMarket 4 -Requests 2400 -Note "bench-4 Flint baseline"`.
Then the weekend GEPA run on Flint in the off-peak block from Friday 06:00 EDT. Open: step 2, how trials are counted, before any promotion is possible.

## GEPA gets its own markets, a split and no history; the Director sees outcomes in words - 29 October 2026

Owner direction, 29 October 2026: fix the workflow flaws found after the seventh GEPA run, and review the workflow.
Principle agreed the same day: free exploration, strict measurement. No prompt tells a role which ideas to pursue or avoid.
The gate, the trial count, the Auditor, the vault and the empty markets decide what is believed. GEPA is the optimizer, never the scorer.

Built:
- GEPA markets (`practice.py`): 24 generated markets on seeds 200 to 223 (`GEPA_SEEDS`, 200 to 299, reserved for GEPA; a practice run refuses them).
  16 training markets, which GEPA reflects on, and 8 validation markets, which rank candidates. Each set cycles through eight patterns:
  momentum 5, momentum 10, reversal 3, reversal 5 at strength 0.004; momentum 5 and reversal 3 at 0.002; two with no pattern.
  Before this, GEPA learned and selected on the same four markets, one of which (seed 12) was also the practice market.
- GEPA cycles have purpose `gepa` (`ledger.py`, `cycle.py`, `gepa_run.py`): no history in (blank summary), nothing out (no lessons, no recent list), no agenda step.
  Every candidate is measured under the same conditions, and practice runs no longer change what GEPA cycles see. A GEPA cycle may still promote and queue a strategy.
  `run_bounded` refuses purpose `gepa`. The START row records `validation_markets`. `MAX_MARKETS` is 24, `MINIBATCH` is 4, `SPEED_WEIGHT` is 0.004.
- The Director's lessons table (`levels.py`) shows each idea's best outcome as a sentence, without the level number or the `best_level` field.
  The seventh GEPA run had 12 idea titles with the literal word "level-7".
- `config/engine_prompts/director.md` (applied after the practice run, because the engine reads the prompt files every cycle) no longer says
  "build on partial successes", "level 7 or higher" or "level 6 or lower". It says the table holds outcomes in words and a repeated idea must say what changed.

Results of GEPA runs 1 to 7 are not comparable with later runs. The next GEPA run is the first on this design.
Bench results from this point use the new Director prompt, so they are not comparable on prompts with the bench-1 baselines of 26 October.

Practice run `run-20261029-7514150d` (20 cycles, `deepseek-flash`, old Director prompt): `CYCLE_LIMIT`, 504 requests, 92.9 minutes, 0 faults.
Levels: 18 cycles at 7 and 2 at 5, mean 6.80. 57 candidates: 37 `REJECTED_DEFLATED`, 20 `REJECTED`. Of 60 ideas, 27 were "brakes" and 2 were reversal.
The last cycle saw 40 lessons rows. The run used the old prompt and the old lessons table.

Storage cleanup, owner OK on 29 October 2026 ("OK for storage cleanup", then "yes" for the three old suite folders): `tools/clean_test_runs.py` removed
102,620 files and 56,467 folders (3.3 GB) in 55 seconds from 38 engine sandbox folders and `e8-full-product-03`, `e8-full-product-02` and
`scratch50-full-20261024-224412`. Each target keeps its top folder. The record is under `.cache/test-runs/cleanup-records/`.
`.cache/test-runs` went from 148,299 to 100,672 folders. `tools\practice.ps1` now runs the sandbox cleanup after every run that exits 0.
The tool refuses while an engine run is open, below 8 GiB free, for the economics fixture folder, and skips a folder with a link that points outside it.

Final verification, source, simulated markets, after the Director prompt change:
- Engine lane, all engine files with `test_ai_models_interface.py`, `test_run_tests_tool.py` and `test_clean_test_runs.py`: 306 passed, 0 failed, 0 skipped, 8 pandas warnings.
- Product lane, the same files: 242 passed, 0 failed, 7 skipped (engine libraries absent).
- One earlier attempt of each lane failed one test, `test_bad_bench_options_are_refused_before_the_lease[options11]`: it expected a GEPA run to refuse
  `--seed 875` under the old offset scheme. GEPA no longer reads `--seed`; the case now checks that a practice run refuses GEPA seed 200.
  Those two job folders keep their working files under `.cache/test-runs/engine-lane-gepa-split-20261029-101600` and `engine-files-product-gepa-split-20261029-101856`.

Committed as `c825b71`. The project map was refreshed for the GEPA design: 9 pages, 81 internal links with 0 broken; pages 1 and 2 were inspected.
The bench-2 flash baseline, `run-20261029-1bab0fc4`, started at 10:25 EDT (4 cycles per market, 600 requests, new Director prompt), inside off-peak.

Owner decisions after the workflow review, 29 October 2026:
- Practice runs should use real markets and fake markets. Built now: `tools\practice.ps1 -Seed N` (run mode only) picks the fake market, so runs can
  rotate through seeds outside the reserved ranges (bench 100 to 199 and 900 to 999, GEPA 200 to 299). Real markets wait for a fresh data pull and trials per source.
- GEPA weekend runs should be faster. Plan, not built: run several cycles at once (model latency dominates; the sandbox part is seconds and keeps one job at a time).
- Runs must survive a closed window. Built: `tools\start_run.ps1 <practice.ps1 arguments>` starts the run as its own process through the Windows
  process service, outside the caller's job, with console output in `.cache/test-runs/practice-detached-<stamp>.log`. The owner still starts each run;
  nothing repeats or schedules. Tested against the live bench-2 lease: the detached process ran, logged `{"refused": "OWNER_BUSY"}` and exited;
  bench-2 was unaffected. The first attempt quoted parameter names, so practice.ps1 read them as text; fixed. `-Show` prints the command line without starting.
- Hand edits to prompts should take the same bench check as GEPA candidates (proposed; the old prompts survive as candidate 0 of `run-20261029-65d4d5c4`).

Bench-2 flash baseline, `run-20261029-1bab0fc4` (committed prompts with the new Director prompt, bench-2, 4 cycles per market): verdict `MEASURED`,
`CYCLE_LIMIT`, 20 cycles, 562 requests, 92 minutes, 2 step faults, 59 candidates. Patterns found 1 of 3; false discoveries 0 of 2 empty markets; mean level 6.10.
- seed 106 (momentum 5, noise 0.006 then 0.02): levels 6, 5, 6, 5; no candidate beat buy-and-hold.
- seed 107 (reversal 3, drift +0.002 then -0.002): levels 7, 5, 7, 7; 7 of 12 beat buy-and-hold, 6 audited, found in 2 cycles, best capture 0.665.
- seed 108 (momentum 5 then reversal 3): levels 5, 5, 6, 6; no candidate beat buy-and-hold.
- seed 109 (changing noise, no pattern): levels 7, 6, 7, 7; 3 beat buy-and-hold by luck, none passed the gate.
- seed 110 (no pattern): levels 7, 7, 6, 5; 2 beat buy-and-hold by luck, none passed the gate.
Reading: the firm finds a reversal rule even when the drift flips, and finds no momentum rule when the noise or the pattern changes halfway.
This is the first bench-2 run, so there is no earlier bench-2 result to compare with. It is not comparable with the bench-1 flash baseline of
26 October (2 of 3, mean 7.15): different markets and a different Director prompt. The sandbox cleanup ran after the run: 799 files and 137 folders removed.

Bench-3 flash baseline, `run-20261029-5fa9cd3c` (new Director prompt, 4 cycles per market, started 11:58 EDT through `tools\start_run.ps1`):
verdict `MEASURED`, `CYCLE_LIMIT`, 64 cycles, 1,675 requests, 291 minutes, 191 candidates. Patterns found 6 of 10; false discoveries 0 of 6; mean level 6.22.
Record: `.cache/test-runs/practice-bench-20261029-115804-record.json`.
- Momentum 5 at 0.004: seed 111 not found (best capture 0.313), seed 112 found by 4 candidates (1.106).
- Reversal 3 at 0.004: seed 113 not found (no candidate beat buy-and-hold), seed 114 found by 1 candidate (0.536).
- Momentum 5 at 0.002: seed 115 found by 5 candidates (1.369), seed 116 not found (no candidate beat buy-and-hold).
- Reversal 3 at 0.002: seed 117 found by 4 candidates (2.448), seed 118 by 1 (0.502).
- Changing regimes: seed 119 not found (0.379), seed 120 found by 2 candidates (0.988).
- Empty markets 121 to 126: 0 passed the bench gate. Seed 124 had 4 audited candidates that beat buy-and-hold by luck, seed 126 had 2 (levels 8 and 8).
No candidate on any market passed the bench gate. The planted reference rule did not pass it either (best reference bench deflated Sharpe 0.823, seed 111).
So on 500-session markets the bench measures "found" through capture only, and level 10 is out of reach even for the true rule.
Capture is noisy where buy-and-hold has a negative Sharpe: the ratio passed 1 on four markets.
The two seeds of one pattern disagreed on four of five patterns, so one seed per pattern says little. Bench-3's 2 seeds per pattern were the right choice.
12 build steps ended with `AI_RESPONSE_TRUNCATED` (11 Engineer, 1 Mathematician) and 2 with `AI_TOOL_EXECUTION_DENIED`; each cycle went on.
Comparison, all `deepseek-flash` at 4 cycles per market: bench-1 (26 October, old prompt) 2 of 3, mean 7.15; bench-2 1 of 3, mean 6.10; bench-3 6 of 10, mean 6.22.
The sets have different markets, so the numbers rank nothing. False discoveries were 0 in all three. Bench-3 is the baseline for the next prompt changes.

Parallel GEPA cycles, built on 29 October 2026 (owner: weekend GEPA runs "should not take that long if we optimize it"):
- `PromptAdapter.evaluate` (`gepa_run.py`) runs the markets of a batch at the same time, up to `PARALLEL_CYCLES` (4), each cycle in its own thread and context.
  Cycle indices are given before the cycles start, so records stay in batch order. The cycle limit cuts a batch to the cycles still allowed, records them, then stops.
  A stopped cycle is recorded with its code, and the batch's other cycles finish before the code stops GEPA.
- `ModelClient` (`models.py`): the budget check and the request count are one locked step, so concurrent calls never pass the limit, and the ledger row and
  transcript line are written under a second lock. Every call row carries `cycle_id` from a context variable that `run_cycle` sets (`CYCLE` in `models.py`).
  LangGraph copies the context into its worker threads, so role calls made inside an agent keep their cycle. Reflection calls carry no cycle.
- `EngineerSandbox` (`execution.py`): one lock around the sandbox job, because the sandbox has one fixed profile. Model calls overlap; sandbox runs queue.
- The cycle's speed measure counts only the rows of its own cycle.
Expected effect: a 10,000-request GEPA run in about 9 hours instead of 36, because a cycle is mostly waiting for the model.
Product lane, `test_engine_gepa.py` and `test_ai_models_interface.py`: 94 passed, 0 failed, 0 skipped.
The first engine lane after bench-3 failed 3 tests, 305 passed (evidence kept in `.cache/test-runs/parallel-gepa-engine-20261029-165013`).
Cause: `run_cycle` set the cycle tag and never reset it, so calls after a cycle in the same thread carried that cycle's tag.
`run_cycle` now sets the tag for its own run only and restores the earlier value when the cycle ends.
Final verification, source, simulated markets: engine lane, all engine files with `test_ai_models_interface.py`, `test_run_tests_tool.py` and
`test_clean_test_runs.py`: 308 passed, 0 failed, 0 skipped, 8 pandas warnings. Product lane, the same files: 244 passed, 0 failed, 7 skipped (engine libraries absent).
The parallel speed is not measured yet. The first weekend GEPA run measures it.
Committed as `823493c`. The project map was refreshed for parallel cycles and bench-3: 9 pages, 81 internal links with 0 broken; pages 1 and 2 were inspected.
Bench and practice runs (`run_bounded`) still run one cycle at a time.

Recommended, not applied: the Engineer's cap in `config/models-deepseek.toml` is 8,192 output tokens. In the 11 cut-off Engineer replies,
reasoning used 2,991 to 7,531 of them. Raising the cap to 16,384, the engine maximum, waits for the owner because it changes the bench-3 conditions.

Exact next action: the owner decides on the Engineer cap and the hand-edit bench check. Then the first weekend GEPA run, off-peak, through `tools\start_run.ps1`.

## Seventh GEPA run stopped; bench-3 and GEPA scoring verified - 29 October 2026

The owner stopped the seventh GEPA run on 29 October 2026 at 08:26 EDT ("ok lets stop the GEPA cycle").
`run-20261029-65d4d5c4` ended with `KILL_SWITCH` after 2,543 requests and 9 hours 18 minutes. Its last cycle, 427, was cut off.
It evaluated 124 cycles and 27 prompt sets, with 31 proposals across all eight parts. It used the old score.
The committed prompts scored a mean level of 6.21 over 52 cycles. Candidate 9 scored 6.62 over 21 cycles.
The recorded best, candidate 11, has only two cycles, both level 7. Six other candidates tie with it.
None of these gaps is outside the noise. No candidate is applied. Files: `state/engine/prompts/run-20261029-65d4d5c4/`.
Assessment: GEPA learns and selects on the same four practice markets, with one noisy cycle per market.
The proposed next design uses about 24 generated practice markets: 16 to learn from and 8 to select with. It is not built.

Final verification, source, simulated markets:
- Product lane, `test_engine_bench.py`, `test_engine_practice.py` and `test_engine_gepa.py`: 60 passed, 0 failed, 0 skipped.
- Engine lane, `test_engine_gepa_run.py`, `test_engine_bench_run.py` and `test_engine_practice_run.py`: 21 passed, 0 failed, 0 skipped.
- Engine lane, all engine files with `test_ai_models_interface.py` and `test_run_tests_tool.py`: 299 passed, 0 failed, 0 skipped, 8 pandas deprecation warnings.
- Product lane, the same files: 236 passed, 0 failed, 7 skipped (engine libraries absent in that environment).

The project map was refreshed for bench-3 and the GEPA score: 9 pages, 91 function groups, 503 source files, 81 internal links with 0 broken.
All nine renders were inspected. The map footer still names harness 0.5.7; the harness entries above are newer.

The owner's practice run (20 cycles, `deepseek-flash`, 600 requests) was first refused with `STORAGE_SCAN_DEADLINE`, before any request.
`.cache/test-runs` holds 148,299 folders, and the storage scan limit is 30 seconds. Only 930 folders were new since the last passing scan.
The retry passed the scan and started `run-20261029-7514150d` at about 08:40 EDT. Routine cleanup of old passing test folders is the next storage step.

Exact next action: report `run-20261029-7514150d`. Then the bench-2 and bench-3 flash baselines, unless the owner changes the order.

## Harness 0.6.1 run watching - 29 October 2026

The owner typed `/watch` during the seventh GEPA run and saw nothing. That run was started outside the harness with `tools\practice.ps1`.
`/watch` knew only harness-started runs. It now opens a picker of runs, running ones first, including such engine runs.
Engine runs are read from `state/research.sqlite` in read-only mode. Enter opens a live view that refreshes every 2 seconds.
It shows status, cycles, requests, elapsed time and the last six cycles. Esc, Enter or q returns, and the last snapshot stays.
Watching never changes or stops a run. `/runs` also lists engine runs. A preview read the live run `run-20261029-65d4d5c4`.

The product-environment harness lane passed 112 tests, zero failed and zero skipped.
The two console native tests passed. The two sandbox native tests were not run, because they start a sandbox job during the GEPA run.
This change does not touch the sandbox or run starts.

## Harness 0.6.0 bug fixes - 29 October 2026

The owner found that typing `/`, moving to `/runs` and pressing Enter did nothing useful. Enter sent the typed `/`.
Enter now runs the highlighted command and shows it in the box. A command that needs details gets its template first.
An independent bug hunt then found 17 confirmed bugs and 5 suspected issues. The fixes cover:
- Multi-line paste, which sent each line as a separate task. A real-console native test now confirms one task.
- Esc, Ctrl+A, Ctrl+E, Ctrl+Backspace, emoji, and Ctrl+Z, which quit even with text in the box.
- Run notes with apostrophes, Windows paths, upper-case commands, and raw Python errors for placeholders and missing details.
- Ctrl+C during a slash command, which quit the harness. `/model` names in any case, and a warning for unknown model IDs.
- Raw JSON results in the terminal. Scripted input still gets JSON. `/sessions` now shows dates and first tasks.
- Empty session files at each start. A session file now starts with its first task. A full session now ends the task cleanly.
- A kill switch that the harness set and never removed, which blocked every later engine run. Other STOP files now give a clear message.
- Run cards whose elapsed time kept growing, `/watch` choosing an older run, and recovery dropping the newest records.
- Run processes that could read console keys, bare `/test` that skipped two files, Tab after a space, and a stale tab title.
Not fixed: closing the Windows Terminal tab probably ends harness-started runs. Wide characters can misalign the box.
Keys typed ahead while the harness is busy can count as a paste. Up and Down have no prompt history.
Another session changed `src/compertum/ai/engine/bench.py`, `tests/test_engine_bench.py` and `tools/practice.ps1` during this work.
Those changes were left untouched and uncommitted.

The product-environment harness lane passed 108 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.

## GEPA scores with a fixed trial count - 29 October 2026

Problem found in the seventh GEPA run: 67 of its first 104 cycles were exactly level 7, and none was higher.
Levels 7 to 9 used the deflated Sharpe with the ledger's global trial count, 828 at that time and growing.
So GEPA could not tell a strategy that found the pattern from one that was lucky. Later candidates also faced a stricter test than earlier ones.
The owner agreed to the fix on 29 October 2026.

The change, in `src/compertum/ai/engine/gepa_run.py`:
- GEPA levels use the fixed count `GEPA_TRIALS`, which equals `bench.BENCH_TRIALS` (60), through `bench.bench_level`.
- On a practice market with no pattern, levels above 6 count as 6. A false discovery makes the cycle level 0, below building nothing, even if another candidate is honest.
- A candidate with a false discovery is never `best_index` while a clean candidate exists. `result.json` counts false discoveries per candidate.
- The feedback shows the fixed-count deflated Sharpe, says when a market has no pattern, and names a false discovery as such. The START row records `score_trials`.
- `practice_market` now records the market's `kind`. Real-market manifests have no `kind`, so they get no cap.
The real gate, the Auditor, the queue and the Director's lessons table are unchanged.
Example from the tests: the exact planted rule on a momentum market was level 7 under the global count, and is level 8 now.

Results are not comparable with GEPA runs 1 to 7. The seventh run keeps the old score, because its process loaded the old code.
One independent review found no blocking defect and five findings. Three were fixed with tests before the final runs:
a reckless prompt could outrank an honest one through the mean over markets (10, 10, 10, 3 against 8, 8, 8, 6);
the feedback called a false discovery an Auditor failure; and building nothing ranked below a false discovery. A test now covers how evaluation sets the cap.
Recorded, not changed: 60 fixed trials is fewer than a long run really tries, so GEPA levels compare candidates and are not evidence of an edge.
Final product lane: `test_engine_gepa.py`, `test_engine_lessons.py` and `test_engine_preflight.py` passed 43, failed 0, skipped 1 (no `langchain_core` in this environment).
Final engine lane: the same files passed 44, failed 0, skipped 0.
`tests/test_engine_practice.py`, `tests/test_engine_bench.py` and `tests/test_engine_gepa_run.py` wait until the engine run ends.
The code comments added earlier for bench-3 were removed on the owner's request: "Can you comment less or not at all in the codebase?"

## Bench-3 written; seventh GEPA run running - 28 October 2026 (local time)

The owner asked for bench-3, a larger bench, and a bench-2 baseline. GEPA must stay the optimizer only, never the scorer.
`bench-3` in `src/compertum/ai/engine/bench.py` has 16 markets, seeds 111 to 126, assigned in order:
- Four markets at the normal strength 0.004: momentum window 5 twice, reversal window 3 twice.
- Four markets at the weak strength 0.002 (`WEAK_STRENGTH`), with the same patterns and windows.
- Two regime markets: momentum to reversal, and reversal with changing noise.
- Six markets with no pattern: three plain, two with changing noise, one with a steady drift of 0.001. No drift turns negative.
The planted rule beats buy-and-hold on all ten patterned markets and on no empty market. It passes the bench-local gate (192 trials) on none.
`bench-1`, `bench-2` and `holdout-1` hash exactly as before. `tools\practice.ps1 -BenchSet bench-3` selects the new set.
Three new tests are in `tests/test_engine_bench.py`. They have not run yet: the test runner refuses that file while an engine run is open.

The owner said "yes start GEPA run 6 on flash". I started it from a superseded next action, so its note says "GEPA run 6".
It is the seventh GEPA run, `run-20261029-65d4d5c4`. The real GEPA run 6 ended on 27 October (see the entry of that date).
Limits: 1,000 cycles, 10,000 requests, `deepseek-flash`. Start: 45.9 GiB free memory, 86.1 GiB free on C:, research store 25.0 MiB.
An earlier one-cycle practice run, `run-20261029-c9270586`, was stopped on the owner's request after 1 request (`KILL_SWITCH`).

Progress on 29 October at 05:50 EDT: 94 cycles and 1,839 requests in 6 hours 42 minutes, about 4.3 minutes and 20 requests per cycle.
1,804 calls completed, 32 were cut off at the output cap (recorded as step faults), and 3 were refused. Free memory was 42.1 GiB.
At this pace the request limit is reached around noon EDT on Friday 30 October. The owner chose to let the run finish ("keep it going").

Exact next action: after `run-20261029-65d4d5c4` ends, run `tests/test_engine_bench.py` and `tests/test_engine_practice.py` in the product lane, and `tests/test_engine_gepa_run.py` in the engine lane.
Then run the bench-2 flash baseline: `tools\practice.ps1 -Models deepseek -Model deepseek-flash -Mode bench -BenchSet bench-2 -CyclesPerMarket 4 -Requests 600 -Note "bench-2 flash baseline"`.
Then, with the owner's yes of 28 October, the bench-3 flash baseline: `tools\practice.ps1 -Models deepseek -Model deepseek-flash -Mode bench -BenchSet bench-3 -CyclesPerMarket 4 -Requests 2000 -Note "bench-3 flash baseline"`.
Then compare bench-2 and bench-3 with the bench-1 flash baselines, and report the seventh GEPA run.

Owner direction, 28 October 2026: time DeepSeek runs to the off-peak hours, which are half price.
Third-party sources give peak as 01:00–04:00 and 06:00–10:00 UTC, Monday to Friday. The owner gave the same hours in Eastern time.
Off-peak in EST from 1 November: Monday to Thursday 05:00–20:00 and 23:00–01:00, and Friday 05:00 to Sunday 20:00. Before 1 November, add one hour.
Before each DeepSeek run, compare its expected length with these windows. Put long GEPA runs in the weekend block.
Timing means choosing when the owner's run starts. No scheduled task or service starts runs without the owner's explicit authority.

## Harness 0.5.8 picker keeps known models - 29 October 2026

The owner reported that `deepseek-flash` no longer appeared in the `/model` picker.
A model-list request showed that DeepSeek still offers `deepseek-flash` and `deepseek-v4-pro`.
The picker listed only each file's default, the active model and IDs listed in the open console.
After the owner switched to Kimi and then `deepseek-v4-pro`, the file default, flash dropped out.

The harness now keeps every used or listed model ID in `state/harness/models-known.json`, outside Git.
A fresh `/models NAME` listing replaces that file's IDs. The owner's file was filled from today's lists:
two DeepSeek IDs and six Kimi IDs. The model-list requests sent no task and used no quota.

The product-environment harness lane passed 99 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.

## Harness 0.5.7 readiness fixes - 29 October 2026

The owner asked what to fix before regular use and approved four items.
1. `/run`, `/gepa` and `/bench` now refuse while a Kimi model is selected. Kimi Code subscriptions are interactive-only.
   The engine also still sends temperature 0, which Kimi `k3.1-pro` refuses. The message says to choose DeepSeek or local first.
2. Tasks now default to 100 steps and 60 minutes, the highest the harness allows. The earlier default was 30 steps and 15 minutes.
   `/limits` shows the limits. `/limits STEPS MINUTES` changes them for the open console and for `/new` and `/resume` there.
3. Any unexpected error, such as a failed disk write, now ends a task with an error outcome. A failed session save shows a note.
4. The project-map PDF was refreshed under `docs/PROJECT_MAP_REFRESH.md`. The map last showed harness 0.3.3.
   Since then, only harness files and the `AGENTS.md` bash exception changed. The owner node now shows the model picker,
   saved choice, Kimi engine-run refusal and `/limits`. The tools node now shows search and the host `bash` exception,
   with engine code still sandboxed. The status footer and roadmap scope show harness 0.5.7 with 98 unit and 4 native tests.
   The rebuilt PDF has nine pages, 91 function groups and 502 source files. All nine renders were inspected.
   All 81 internal links reach existing pages, and all 91 source notes are present.

The product-environment harness lane passed 98 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.

## Harness 0.5.6 Kimi subscription works - 29 October 2026

The owner created a Kimi Code Console key from the membership subscription and set `KIMI_API_KEY`.
Kimi Code keys draw on the membership quota, not pay-as-you-go billing, according to Kimi's documentation.
The configured overseas address `https://api.kimi.ai/coding/v1` and model `k3.1-pro` match that documentation.
Kimi's community guidelines limit subscriptions to interactive use. Harness chat is interactive. Engine runs are batch work.
The owner was told to select DeepSeek before `/gepa`, `/bench` or `/run`.

The first Kimi task failed with HTTP 400. The harness discarded the server's reason.
A model-list request confirmed the key: Kimi listed six model IDs, including `k3.1-pro`.
One short diagnostic request then showed the reason: "invalid temperature: only 1 is allowed for this model".
The harness sent temperature 0 on every request. It now sends no temperature, so each provider uses its default.
A refused request now shows the server's short reason after the HTTP status.
A second short request returned `OK` in 4.2 seconds with 129 tokens. Live Kimi authentication and a reply are now verified.
The engine still sends temperature 0. Kimi engine runs would fail, and Kimi's terms do not permit them on a subscription.

The product-environment harness lane passed 95 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.

Exact next action: the owner sends the task again with `k3.1-pro` selected.

## Harness 0.5.3 model picker - 29 October 2026

The owner typed `/model` and pressed Enter. The harness printed a JSON listing and offered no way to choose.
The command menu also stayed on screen above the answer.

Plain `/model` in the interactive console now opens an arrow-key picker below the box.
Up and Down move. Enter selects and saves the choice. Esc keeps the current model.
The picker lists `deepseek-v4-pro`, `deepseek-flash`, `k3.1-pro` and `flint@q4_k_m` on this host, plus IDs cached by `/models`.
It marks the current model and shows `KIMI_API_KEY not set` beside Kimi. It sends no model request.
Scripted input keeps the JSON listing. Enter now erases the command menu rows below the box.

The product-environment harness lane passed 94 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.

Exact next action: the owner restarts `compertum-harness`, types `/model`, presses Enter, and picks a model with the arrow keys.

Owner follow-up, harness 0.5.5: the owner selected Kimi and sent a task. The console printed only `Error: AI_CREDENTIAL_UNAVAILABLE`.
The cause is expected: `KIMI_API_KEY` is not set. The missing key now ends the task as a normal error outcome.
It names the variable and says to set it or choose another model with `/model`.
The product-environment harness lane passed 94 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.
Exact next action: the owner sets the user variable `KIMI_API_KEY` from a Kimi Code Console key, or picks a DeepSeek model.

Owner follow-up, harness 0.5.4: the owner checked the picker and asked for no second box. The picker is now plain text:
a heading line, a blank line and the list. It hides the text cursor and erases itself after Enter or Esc, so only the result line stays.
The product-environment harness lane passed 94 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.

## Harness 0.5.2 model choice repair - 29 October 2026

The owner reported that the harness seemed stuck on `deepseek-flash`. `/model` switching worked inside one console.
Three causes made it feel stuck. The global `compertum-harness.cmd` passed `--models deepseek --model deepseek-flash` at every start.
The choice was not saved, so a restart or `/resume` returned to flash. Tab on `/model` inserted `/model [NAME] [MODEL_ID]`,
and Enter then reported an unknown model file. A check also found that `KIMI_API_KEY` is not set, so Kimi requests would fail.
Only the presence of the variable was checked; no value was read.

The harness now saves each `/model` choice in `state/harness/model.json` and uses it at the next start and resume.
Start options still override it for one start. A saved choice that no longer loads falls back to `local` with a note.
The box title shows the active model, for example `Compertum · deepseek-flash`. Selecting a model whose key is missing shows a warning.
Tab leaves out optional bracket parts. A bracket sent by mistake gets an example of the correct form.
The wrapper `C:\Users\bgonn\AppData\Local\Programs\Compertum\compertum-harness.cmd`, outside the repository, no longer forces a model.
The saved choice was set to `deepseek deepseek-flash`, so the next start matches the previous default.
A first scripted rewrite of the wrapper damaged its paths for about one minute. The Write tool then restored it, and `--help` ran.

The code commit `caa7305` went out before its document update, because a failed document script did not stop the commit.
This follow-up commit adds the documents and the version 0.5.2.

The product-environment harness lane passed 91 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.
A scripted check before the fix switched to Kimi and `deepseek-v4-pro` without a request. It created one empty session, which was deleted.

Exact next action: the owner restarts `compertum-harness`, types `/model deepseek deepseek-v4-pro`, restarts and confirms the box title.
To use Kimi, the owner sets the user variable `KIMI_API_KEY` from a Kimi Code Console key.

## Harness 0.5.1 secret-check repair - 29 October 2026

The owner's next task ended after 17 steps and 11 minutes with `AI_SENSITIVE_INPUT_DENIED`.
The model had read `src/compertum/harness/packets.py`. Its rule text contains `_authtoken`, which matches the new token rule.
The `read` tool checked only the shared rule, so the file entered the conversation. The request check uses both rules and refused it.
The refused text stayed in the conversation, so every later request and a resume would also fail.

Every tool result now passes the request check's rules before it joins the conversation. Matching lines are hidden.
A resumed session is cleaned the same way. A new task that looks like it holds a secret is refused before it is added.
Sandbox `run` output now hides matching lines, as bash output does. The owner's session `session-20261029-015658-5dcfd758`
failed the request check before cleaning and passes after it: 38 messages, 76 KiB. No request was sent during this check.

The product-environment harness lane passed 88 tests, zero failed and zero skipped. The native lane passed four tests, zero failed and zero skipped.

Exact next action: the owner restarts `compertum-harness` and uses `/resume session-20261029-015658-5dcfd758` to continue the task.

## Harness 0.5.0 bash, search and 512 KiB conversations - 28 October 2026

The owner's first real task ended with `EVENT_INVALID` after three file reads. The model also had to guess file names.
`EVENT_INVALID` came from the reused 64 KiB event-store record limit. Three reads of 469 to 634 lines filled it.
The owner chose tools like the pi agent and a 512 KiB conversation limit. The owner chose a full host shell over safer options.

The harness now has six tools: read, write, edit, search, bash and sandbox run.
`search` finds regular-expression matches with file and line numbers. It skips Git-ignored files and protected folders.
`bash` runs Git Bash on the host. `AGENTS.md` records this owner exception; engine and strategy code still runs only in the sandbox.
The shell receives no key variables. Output lines that match common secret formats are hidden. This is a safeguard, not a boundary.
Each command runs in a Job object, so background processes end with it. Ctrl+C works. Bash waits while an owner run holds the job slot.
The conversation limit is 512 KiB. A note appears at 80 percent. A full conversation reports `CONVERSATION_FULL` with the size and `/new`.

An independent review found no blockers and eight should-fix items. All eight are fixed and tested.
They covered provider key names, background processes, Ctrl+C, the job slot, the decoded secret scan, searches for words such as password,
a parent repository that ignores the workspace, and common token formats. A later check found that one new secret rule backtracked on long text.
The rule now starts at the keyword with bounded repeats. A 600 KB worst case takes 0.33 seconds.
The fake model server in `tests/test_harness_model.py` now reads each request body. Unread data caused the intermittent `WinError 10053`.
Eight repeated model-test runs then passed.

The product-environment harness lane passed 86 tests, zero failed and zero skipped, in two consecutive runs.
The native lane passed four tests, zero failed and zero skipped.

Exact next action: the owner restarts `compertum-harness` and repeats the task that failed. The model should now search and list folders.
The physical Windows Terminal checks from 0.3.4 onward remain pending. No provider, GEPA, benchmark or engine run occurred.

## Harness 0.4.0 activity display - 28 October 2026

The owner asked for coloured code changes and a working indicator like Codex or Claude Code. The owner approved three display upgrades.
Tool steps now show as short lines, such as `● Edit src/x.py` and `● Run main.py --fast`, instead of raw JSON arguments.
Edits and writes show a coloured diff with line numbers. New files show their first lines. Run results show the exit code and the last output lines.
The diff is display only. The model still receives the same short tool result.
A spinner shows the step and elapsed time while the model or a tool works. It disappears before the next output.
The Windows Terminal tab shows a busy ring and the title `Compertum · working`. The tab returns to idle after each task, after an error and at exit.
Scripts, logs and consoles without virtual-terminal mode keep the plain lines.

An independent review found one blocker. Writing an empty file, such as `__init__.py`, crashed the display and left a tool call without a reply.
It also found four should-fix items: diffs that could run for minutes, raw terminal controls from model or program text,
a full read of a large file before the size check, and a busy tab after errors. All five are fixed and have regression tests.
Diffs now match only the changed region. A region over 40,000 line pairs shows a summary; the slowest allowed case took 0.08 seconds.
Display failures now fall back to a plain summary and never reach the task. Minor items for line endings, empty files, widths and spinner erasure are fixed.

The product-environment harness lane passed 71 tests, zero failed and zero skipped.
The native lane passed four tests, zero failed and zero skipped. A new native test reads a real console screen after a spinner step.
It found only the answer row. With the erase step removed, the same check showed the spinner text on the screen.

Exact next action: the owner restarts `compertum-harness` and gives a task that edits a file. The owner then checks the spinner, the diff and the tab ring.
The physical Windows Terminal checks for 0.3.4 to 0.4.0 remain pending. No provider, GEPA, benchmark or engine run occurred.

## Harness 0.3.5 command menu spacing - 28 October 2026

The owner reported that the slash-command menu looked cramped. Commands, descriptions and the example all started at one indent.
The menu now indents commands under the input text. Each command shows its description in one aligned column.
The column stays fixed while the list scrolls. One footer row shows the hidden counts, for example `↑ 3 more   ↓ 10 more`.
Blank rows separate the box, the list and the example. Narrow terminals show the selected description above the example.
At the owner's request, the menu shows six commands before it scrolls instead of four.

The product-environment harness lane passed 57 tests, zero failed and zero skipped. The native lane passed three tests, zero failed and zero skipped.
The screen-emulator test passed with the new layout.

Exact next action: the owner restarts `compertum-harness` and types `/` to check the menu in Windows Terminal.
The physical rendering checks for 0.3.4 and 0.3.5 remain pending. No provider, GEPA, benchmark or engine run occurred.

## Harness 0.3.4 composer rendering pass - 28 October 2026

The owner approved four rendering changes after the 0.3.3 resize repair. The design is in `docs/superpowers/specs/2026-10-28-harness-rendering-design.md`.
The composer now waits for Windows console key and resize events. It no longer polls the keyboard every 50 milliseconds.
A 500-millisecond safety wake still repairs a missed resize. Unchanged frames write nothing.
Each frame is one write inside synchronized-output markers. Terminals without that mode ignore the markers.
A stable frame rewrites only its changed rows. A width change, a height change or a taller frame still uses the full reflow-safe redraw.
The composer restores the console input mode on exit, including after Ctrl+C and Ctrl+Z. It falls back to keyboard polling without console input.
Completion now also accepts plain session and run lists. This fixes a Tab crash that only the editor's default arguments could reach.

The product-environment harness lane passed 55 tests, zero failed and zero skipped.
A new screen-emulator test drives 1,850 keys through typing, menu movement and widening. It checks the screen after every frame.
Three deliberately broken patch versions each failed that test.
The native lane passed three tests, zero failed and zero skipped. The new native test sends real key and resize records to a hidden console.
It confirms the event reader, the input mode during reads and the restored mode. A forced fallback and a wrong mode mask each failed it.
An independent review found no blockers. It found one should-fix item: modified keys now acted as plain keys. That item and five minor items are fixed.
Two minor items remain. Repeated keys after Enter in one console record are lost; Windows Terminal sends single records.
The screen test does not model narrowing reflow. String assertions still cover the narrowing redraw.

Exact next action: the owner restarts `compertum-harness` in Windows Terminal. The owner then types, moves through the command menu and resizes quickly.
The physical rendering result remains unverified until that check. No provider, GEPA, benchmark or engine run occurred.

## Harness 0.3.3 composer resize repair - 28 October 2026

The owner reported leftover borders after moving Windows Terminal. The composer erased from the cursor column and assumed one row above it.
It also waited for a key before detecting a new terminal width. These choices left stale content after console reflow.

The composer now polls for input and terminal changes. It finds the previous frame start after reflow and erases from the line start.
Unchanged frames produce no output. The product-environment harness lane passed 48 tests, zero failed and zero skipped.
The native AppContainer lane passed two tests, zero failed and zero skipped. No provider or engine run occurred.

Exact next action: the owner restarts `compertum-harness` and resizes Windows Terminal with empty input and an open command menu.
The physical console result remains unverified until that check. Unit streams cannot emulate Windows Terminal reflow.

## Harness 0.3.2 model selection and interactive composer - 28 October 2026

The owner can change models without restarting the harness. `/model` shows configured model files without a request.
`/model NAME` selects a file's default. `/model NAME MODEL_ID` selects an exact model. `/model MODEL_ID` uses the active file.
`/models [NAME]` lists IDs without a completion or selection change. Tab completes model-file names and cached model IDs.
Selection preserves the conversation and changes future engine-run defaults. Failed selection leaves the active model unchanged.
The composer width now follows the terminal only. Long input scrolls horizontally without widening the box.
Up/Down scrolls through four visible commands. The selected command shows a description and example. Tab inserts the selection.
The change also fixes `/run` practice mapping and removes the invalid `-Cycles` option from `/bench` commands.

The product-environment harness lane passed 46 tests, zero failed and zero skipped. The native lane passed two tests, zero failed and zero skipped.
One earlier full-lane run had a transient `WinError 10053` in an existing model test. That test passed alone and in the final full lane.
An independent review found a client-switch test gap and small hardening items. The fixes passed a second review with no blockers.
A separate menu review found no blockers. Registry, wrap-around and changing-row cursor checks were added.
A scripted master check selected `kimi` and `k3.1-pro` with the same session. It sent no model-list or completion request.
The owner's physical Windows Terminal check and live Kimi authentication remain unverified.

Exact next action: the owner starts `compertum-harness`, types `/model kimi`, and checks `/status`.
The owner can then use `/models kimi` after setting `KIMI_API_KEY`. No GEPA, benchmark, holdout or provider run occurred during this work.

## Kimi K3.1 Pro provider configuration - 28 October 2026

The owner authorized Kimi Code as a remote provider. `config/providers.toml` names the overseas coding endpoint and `KIMI_API_KEY`.
`config/models-kimi.toml` selects the official model ID `k3.1-pro` for all four roles. Each role has 16,384 output tokens and 600 seconds.
The configuration contains no API key. Membership quota and rate limits apply. Kimi results need a separate bench baseline.

The targeted product-environment lane passed 80 tests, zero failed and zero skipped.
A scripted harness start selected `k3.1-pro` and exited cleanly. It sent no model-list or completion request.
Live Kimi authentication and a model reply remain unverified. The owner must create `KIMI_API_KEY` from a Kimi Code Console key.

Exact next action: the owner starts `compertum-harness --models kimi --model k3.1-pro` in a new terminal after setting the key.
Both options are needed because the global wrapper's defaults are DeepSeek and `deepseek-flash`.
No GEPA, benchmark, holdout or provider run occurred during this configuration work.

## Harness 0.2 interactive composer and live smoke - 27 October 2026

The global `compertum-harness` command opens master from any folder with DeepSeek flash. The product `compertum` CLI is unchanged.
The interactive composer draws a box and shows matching slash commands. Tab inserts editable run templates and completes session or run identifiers.
The editor supports backspace, delete, arrows, Home, End and Ctrl+Z. Scripted input keeps the plain prompt.
The owner completed a live DeepSeek task. It read `config/gepa_goal.md`, wrote `harness_smoke.py` and ran it in the sandbox with exit code 0.
The owner-started `/test` command also completed with 24 passed and a `COMPLETED` run card.

The final UX unit lane passed 34 tests, zero failed and zero skipped. The native lane passed two tests, zero failed and zero skipped.
An independent review found cursor-row, key-code and command-matching defects. The fixes passed a second review with no blockers.
The owner's real interactive Windows Terminal check remains pending. Unit streams cannot emulate a physical console cursor.

Exact next action: the owner checks the box and Tab completion interactively. Publish the verified UX checkpoint with that limitation recorded.
No new GEPA optimization or holdout run occurred.

## Evaluation hardening and minimum harness verification - 27 October 2026

The evaluation hardening work is implemented. Candidate 4 from GEPA run 6 remains unapplied.
GEPA run 6 stopped because two `gepa-reflect-tool` calls exhausted token caps. It did not hit the research database cap.
The baseline found one of three patterns with mean level 7.00. Candidate 4 found two of three with mean level 7.20.
Both runs recorded zero false discoveries. One comparison is insufficient, and candidate 4 had more build and audit failures.

Bench and holdout reports now persist in returned state and durable END rows. `python -m compertum.ai.engine.compare` compares saved reports.
`bench-2` adds deterministic momentum, reversal, regime-change and noise markets with negative controls. `bench-1` and `holdout-1` are unchanged.
Real-market manifests rebuild chronological development markets from retained `BarEvidence`. Bench and holdout reject these manifests.
Real-provider practice and GEPA transcripts default to `training_allowed: false`. Bench and holdout transcripts can never enable training.
The original Alpaca evidence files were not found. Only retained-format fixtures verify the adapter. No actual Alpaca practice run has occurred.

Post-review targeted lanes passed 186 product-environment tests and 271 engine-environment tests, with zero failures and zero skips.
The final engine lane also passed 271 tests, zero failed and zero skipped. It reported eight pandas deprecation warnings.

The full top-level product lane recorded 7,225 passed, 14 failed, 18 skipped and 14 errors in 1 hour 30 minutes.
All 28 failures and errors came from four fixture files that need the approved fixture root. The new harness tests were not in that collection.
All 12 economic-fixture files then passed in that root: 113 passed, zero failed and zero skipped.
The distinct main and economic-fixture lanes therefore have 7,338 passed, zero unresolved failures and 18 skips.

The minimum terminal harness is implemented under `src/compertum/harness` and documented in `docs/HARNESS_PLAN.md`.
Its product-environment unit lane passed 24 tests, zero failed and zero skipped. An independent re-review found no blockers.
The final native harness lane passed two tests, zero failed and zero skipped. It covered real AppContainer execution and process recovery.
No live provider conversation or harness-started engine run has occurred.
The separate Windows lane recorded 209 passed, 126 failed and 5 errors in 29 minutes 32 seconds.
Many failures share `BOOTSTRAP_DENIED` from the existing 64-worker identity limit. These failures are not harness acceptance results.

The project map was rebuilt with nine pages, 91 function groups and 498 source files. All nine renders were inspected.
The final PDF has no broken internal links.

Exact next action: commit and push separate evaluation and harness checkpoints with the Windows failures preserved.
Do not start another GEPA optimization or use the holdout during this work.

## M3 engineering accepted; engine stages E1 to E7 complete; owner-started Flint practice run next - 24 October 2026

Repair attempt `m3-repair-20261023-02` (release commit `a81c9b4b05d9022f96e01b52a799712c19a6230b`) passed every M3 engineering requirement.
Source lane 592 passed, installed lane 592 passed, zero failures, errors or skips. Campaigns 63/63 per lane with 63 exact payloads. All 77 audits verified.
One consumed Final, terminal restart refusal, paired native Final audits with pause, resume and restart, and the three-ridge check verified.
All three momentum candidates failed the money gates. Every record has `financial_accepted: false`. The 14 October attempt stays terminally BLOCKED.
Independent closeout review: `CLOSEOUT_OK` in round 2. Evidence: [the acceptance report](../reports/M3_REPAIR_ACCEPTANCE.md) and [the repair plan](M3_REPAIR_PLAN.md).

The 19 October registration and cycle work is committed as `3310653` after 253 source tests passed today (zero failures, errors or skips) and one independent review.
Storage limits: on 24 October 2026 the owner raised the scratch ceiling from 12 GiB to 50 GiB and the project total from 50 GiB to 200 GiB, because the data will grow (see the investigation entry below). Measured scratch that day: 12.546 GiB.
The project-map PDF was refreshed twice on 23 October 2026 and seven times on 24 October 2026, last after the Flint practice runs: nine pages, 91 source notes and 472 source files, pages 1 and 2 inspected at full size.
Known follow-up: a research cycle in BLOCKED or AWAITING_OWNER_REVIEW has no release path yet.

Engine stage E1 is complete and owner-approved on 23 October 2026: `src/compertum/ai/models.py`, `config/models.toml` and `tests/test_ai_models_interface.py`.
Source lane: 34 new tests passed, 58 with the related adapter tests, zero failed, zero skipped. One independent review, two rounds, verdict `E1_OK`; the final should-fix is applied and tested.
Limitation: the installed-package `.venv` holds the M3 release wheel, which predates this module. E1 is verified in the source lane only until a new wheel build.
Limitation: the 40-request and 8-task daily caps in `manual.py` do not apply to the new client. Its only limit is the per-client request limit until stage E5.

Engine stage E2 is complete and owner-decided on 23 October 2026: `src/compertum/runtime/sandbox.py` and `tests/test_engine_sandbox.py`.
Two review rounds (round 1 `CHANGES_REQUIRED`: one blocker, seven should-fixes, five notes; round 2: one should-fix, then `E2_OK` on the code). The AppContainer denies reads and writes outside the job folder, reads of an earlier job folder, external network, child processes, memory above the limit and time past the deadline.
First run, source lane, native Windows: 19 passed, 1 failed, 0 skipped. The failed test was the loopback escape. On this host (Windows 11 10.0.26300) a capability-less AppContainer reaches a loopback listener. No firewall rule or administrator-free setting restores the block.
The owner chose option 1: loopback reach is a documented limitation on this host. The gate now has ten controls; loopback is recorded as an observation with every verification, never gated. After the decision: 20 passed, 0 failed, 0 skipped.
Limitation: code in a sandbox job can reach the model server the owner starts for a run, outside the ledger. Stage E3 must add the compensating connection check with Auditor freeze. See "Loopback finding" in [the engine plan](ENGINE_PLAN.md).

Engine stage E3 is complete; the owner gave the OK on 24 October 2026 (commit `38af592`): `src/compertum/ai/engine/` (roles, cycle, execution, ledger, market), `config/engine_prompts/`, the tool-call extension of `src/compertum/ai/models.py`, the loopback watcher and two new controls in `src/compertum/runtime/sandbox.py`, and `hold_job_slot` in `src/compertum/runtime/jobs.py`.
The four roles run as Deep Agents over one ledgered loopback model path in the separate environment `.cache/engine-env` (system Python 3.14). One supervised cycle on a synthetic market runs end to end: Director picks, Researcher memos, Director decisions, Mathematician specifications, Engineer code built and run in the AppContainer sandbox, Validator score, Archivist rows for every step. Engineer code that reaches loopback froze the engine in the test on this host.
Engine environment lane: 12 passed, 0 failed, 0 skipped. Product lane: sandbox 25 passed, model interface 39 passed, engine module 1 skipped (no Deep Agents there). Review round 1 `CHANGES_REQUIRED` with no blocker, six should-fixes and five notes, all applied; round 2 `E3_OK` with two notes.
Full product suite in `.cache/clean-env-m0` on 24 October 2026: 7162 passed, 3 failed, 12 skipped in 1 h 56 min. The engine lane was rerun on the final code afterwards: 12 passed.
The three failures are not from E3; E3 changes no module that these tests import.
Resolved on 24 October 2026 (owner investigation, see the entry after this list): failures 2 and 3 were stale tests, failure 1 followed the owner's new scratch limit.
1. `tests/test_backup_capacity_amendment.py::test_backup_amendment_preserves_all_other_storage_limits` expects scratch 10 GiB; `config/default.toml` has held 12 GiB since 16 October 2026. The owner decides whether the test follows the config.
2. `tests/test_fake_economic_recovery.py::test_opening_change_after_staged_hash_refuses_publication` expects the refusal during `STAGING_EXECUTION` but the restore now refuses during `STAGING_COORDINATOR`. It fails alone too. The test last changed on 13 October 2026; `src/compertum/recovery.py` changed on 16 and 17 October 2026. A direct comparison against the committed code was not possible: the runtime identity pins reject a package loaded from another path.
3. `tests/test_final_transaction.py::test_empty_shortlist_completes_once_with_committed_evidence_and_no_prices` fails only in suite order because an earlier test leaves `compertum.modeling.generated_final` imported. It passes alone.
Evidence for the three failures is in `.cache/test-runs/e3-full-suite01-failed-evidence` (pytest output and the failed tests' folders). Mistake recorded: the suite's basetemp was placed inside `.cache/test-runs/m5-local-economics-20261017-01`, whose owner-approved cap is 448 MiB, and grew to 2.8 GiB during the run. The passing files were removed after the results were recorded; the folder is back under its cap at about 285 MiB. Future full runs use a fresh folder directly under `.cache/test-runs`; only the eight economic-fixture test files need the capped folder.
Limitation: the Validator adapter scores the synthetic market only; the connection to the real walk-forward Validator is stage E6 work. No bounded run, kill switch or request maximum yet (E5).

Engine stage E4 is complete; the owner gave the OK on 24 October 2026 (commit `3d0fe22`): `src/compertum/ai/engine/deflation.py` (deflated Sharpe ratio with the total trial count, gate `DSR >= 0.95`, section 10 family size `max(12, trials)`), `src/compertum/ai/engine/vault.py` (candidate queue as insert-only events, sealed vault batches with an owner note, the look counted before any vault row is read, no repeat evaluation), four insert-only tables in `engine/ledger.py`, `split_market_tiers` and `deflation_inputs` in `engine/market.py`, and the cycle records one trial per candidate before any run.
Product lane: `tests/test_engine_validator.py` 9 passed, 0 failed, 0 skipped (hand-calculated cases; expected values computed separately with `statistics.NormalDist`); `tests/test_engine_sandbox.py` and `tests/test_ai_models_interface.py` 64 passed. Engine environment lane: `tests/test_engine_roles.py` 12 passed with the E4 integration. The full suite was not rerun: no module outside `src/compertum/ai/engine` changed since the 24 October run.
Independent review round 1: `E4_OK` with one should-fix (the vault read order was not enforceable by the module) and seven notes. The should-fix and six notes are applied: the vault is read through a callable only after the checks pass, the gate compares the unrounded value, the batch open is one transaction, admission checks the deflation record's numbers, a malformed queue row refuses, and the test asserts the read order. One note (add the E4 modules and the store database to the sandbox probe targets) is deferred to E6. After the fixes: product lane 9 passed; engine environment lane 21 passed (roles and validator files). The reviewer recomputed every hand value and matched to better than 1e-8.
Limits: `auditor_passed` is an input to queue admission; the engine does not call the Auditor yet (E6). The sealed protocols still hold family size 12; a grown family in a sealed protocol is an owner-reviewed change to a fixed part. Running frozen candidate code on vault data in the sandbox is E6 wiring.

Engine stage E5 is complete; the owner gave the OK on 24 October 2026 (commit `a88770f`) and set the first hard maximum, `request_hard_maximum = 450`, the same day: `config/engine.toml` (owner-only hard maximum for AI requests per run), `src/compertum/ai/engine/limits.py` (settings loader, run limits, the run gate for the kill switch, the hour limit and freezes, the daily summary), `run.py` (one bounded run: START row, cycles until the first limit, END row with the reason), `control.py` (owner commands: list, clear-freeze, close-run), a `gate` hook before every request in `src/compertum/ai/models.py`, run rows in the ledger, and the gate before every cycle step.
Product lane after the review fixes: `tests/test_engine_limits.py` 7 passed, 0 failed, 0 skipped; with `tests/test_engine_validator.py` and `tests/test_ai_models_interface.py` 57 passed, and `tests/test_engine_run.py` 1 skipped there (no Deep Agents); `tests/test_engine_sandbox.py` 24 passed. Engine environment lane: `tests/test_engine_roles.py`, `test_engine_validator.py`, `test_engine_run.py` and `test_engine_limits.py` 35 passed, 0 failed, 0 skipped. The full suite was not rerun: outside `src/compertum/ai` the only change is the optional gate parameter of the model client, covered by its own test file.
Independent review round 1: `CHANGES_REQUIRED` with one blocker, three should-fixes and eight notes. The blocker: the run process holds the coordinator owner lease, so no owner command could set the pause state of a standalone run; the only kill switch was killing the process. Fixed with the owner stop file read by the gate before every request and step. The should-fixes (a direct client-gate test, a tight hour-limit test, JSON with exit 2 for every owner-command refusal) and six notes (secret check on the approval note, engine built before the START row, and four design statements) are applied; two notes were documentation placeholders, now filled.
Engine stage E6 is complete; the owner gave the OK on 24 October 2026 (commit `2e25352`) and confirmed the Auditor split: `src/compertum/ai/engine/audit.py` (the engine Auditor: trial counted, candidate list before any run, score recomputed from the signals, deflation record consistent, no loopback or denied access, then a frozen-code rerun that must reproduce the signals and three reruns with the last 1, 4 and 8 validation rows perturbed that must leave earlier positions unchanged, which catches lookahead into the return column; integrity failure freezes `AUDITOR_FAILED`, a candidate defect rejects `REJECTED_AUDIT`), `promotion.py` (promoted code as a versioned template under `state/engine/promoted` with a manifest; the Validator's vault rerun inside a sealed look), forbidden-access freeze `FIXED_PART_ACCESS` in `engine/execution.py`, the request-count invariant `REQUEST_LIMIT_EXCEEDED`, and probe targets covering the rules, the fixed configuration, the judge code and the store.
Acceptance: a bounded run with scripted roles on a synthetic market (seed 12, 500 sessions, planted momentum 0.004) finds the planted pattern: beats baseline, deflation PASS, Auditor `VERIFIED_PASS`, queued, promoted; a vault batch with the owner's note is the only way a vault job runs; a write to `AGENTS.md` from the sandbox leaves the file unchanged and freezes the engine; a non-reproducible candidate is rejected without a freeze; an Auditor integrity failure freezes.
Product lane: `tests/test_engine_audit.py` 5 passed, 0 failed, 0 skipped (hand-calculated Validator fixture included); every engine-related product file together (`test_engine_audit.py`, `test_engine_validator.py`, `test_engine_limits.py`, `test_ai_models_interface.py`, `test_engine_sandbox.py`) 86 passed, with the three Deep Agents files skipped there. Engine environment lane: the six engine test files (`test_engine_acceptance.py` 5, `test_engine_roles.py` 12, `test_engine_run.py` 7, `test_engine_validator.py` 9, `test_engine_limits.py` 7, `test_engine_audit.py` 5) 45 passed, 0 failed, 0 skipped. The full suite was not rerun: no module outside `src/compertum/ai/engine` changed.
Independent review round 1: `CHANGES_REQUIRED` with one blocker, eight should-fixes and seven notes. The blocker: the job reads `validation.csv` with every session's return, and the score pays position t with return t+1, so code that reads tomorrow's return scores perfectly, reproduces exactly and would have been promoted. Fixed: the Auditor reruns the frozen code three times with the last 1, 4 and 8 validation rows perturbed; positions before the perturbed tail must not move; a hand-written lookahead candidate is rejected in the acceptance test. Also applied: reruns and promotion use the code as submitted (kept in the launch record), a rerun refusal is a candidate defect, the E3 test writes into a temporary project (two stray folders in master's `state/engine` from today's tests were removed), the daily summary reports queued, audit-rejected and frozen candidates, the forbidden-access limits are stated (a benign `PermissionError` is a false freeze the owner clears; a caught exception hides an attempt; the AppContainer is the boundary), a deterministic non-reproducible fixture, any failure inside a vault look consumes the look, four more probe targets, order assertions, promotion before queue admission, vault data tier files deleted after scoring. The owner confirmed the Auditor split on 24 October 2026 (an integrity failure freezes the engine; a candidate defect rejects the candidate).
Kill switch: the run holds the coordinator owner lease, so `research pause` cannot reach a standalone run's store (found in review). The owner stops a run by creating the file `state/engine/STOP` inside the project; the gate reads it before every request and every step, the run ends with reason `KILL_SWITCH`, and the file blocks the next run until the owner removes it. A request in flight ends within its timeout (120 s default), a sandbox job within 120 s. The owner command is a module entry point, not a `compertum.cli` subcommand, and reports a busy owner as JSON with exit 2. The Auditor is not called inside a run yet (E6).

M0 and M3 engineering are accepted. Financial qualification, paper permission and M6 (zero of ten actual sessions) stay open. Strata stays off.
The owner's practice-run command exists: `python -m compertum.ai.engine.practice --project . models | run --cycles N --requests R --note TEXT` (`src/compertum/ai/engine/practice.py`). It refuses below 16 GiB free host memory before taking any lease, lists server model IDs without a completion, takes the coordinator owner lease for one bounded run, verifies the sandbox with the sixteen probe targets, sets the research state to RUNNING for the run and back afterwards, and prints the record as JSON. Product lane `tests/test_engine_practice.py` 4 passed; engine environment lane `tests/test_engine_practice_run.py` 1 passed (a full run as a separate process against the scripted server, with the stop-file refusal).
Engine stage E7 is complete; the owner gave the OK on 24 October 2026 (commit `6c14f6c`): `src/compertum/ai/engine/gepa_run.py` (GEPA improves the four role prompts in memory inside a bounded run; one supervised cycle per evaluation on TRAIN and VALIDATION; the score is deterministic from the outcome, 1.0 for a queued strategy down to 0.0 for none; reflection through the E1 client with bounded records and an injection warning; the owner's cycle limit is a hard bound; candidates written to `state/engine/prompts/<run id>/` with a result record; the run never writes into `config/`), `prompts.py` (the prompt loader without any engine library), the `gepa` and `apply-prompts` subcommands of the practice command, and the in-memory transcript of a cycle for reflection.
Product lane after the review fixes: `tests/test_engine_gepa.py` 6 passed and `tests/test_engine_practice.py` 5 passed, 0 failed, 0 skipped; every engine-related product file together 97 passed, with the five Deep Agents files skipped there. Engine environment lane: the ten engine test files (`test_engine_gepa_run.py` 2, `test_engine_gepa.py` 6, `test_engine_roles.py` 12, `test_engine_run.py` 7, `test_engine_acceptance.py` 5, `test_engine_practice_run.py` 1, `test_engine_practice.py` 5, `test_engine_validator.py` 9, `test_engine_limits.py` 7, `test_engine_audit.py` 5) 59 passed, 0 failed, 0 skipped. The full suite was not rerun: no module outside `src/compertum/ai/engine` changed.
Independent review round 1: `CHANGES_REQUIRED` with one blocker, five should-fixes and four notes. The blocker: the owner's `gepa` command read two keys that sit one level deeper in the result and crashed after every run, after the lease was released and before the record was printed; no test covered that path. Fixed, with a product-lane test of the `gepa` path. Also applied: a refusal inside a reflection call is kept and re-raised at the next evaluation (GEPA swallows exceptions from the proposer); an audit rejection now scores 0.3, below an honest losing strategy, so the score never rewards a prompt for reaching the Auditor by cheating; GEPA's best candidate is mapped by hash to the folder index the owner applies; the reflection minibatch equals the market count; a proposal returns only changed roles; the transcript is bounded in bytes; records are passed whole.
All seven engine stages are accepted. No run against a real model has happened yet; every engine result so far is from scripted roles on synthetic markets.
Practice-run preparation on 24 October 2026 (owner present): the owner decided to drop Harness2 from consideration; the harness-improvement path is Deep Agents plus GEPA, both native Windows and already in the engine environment. The owner chose Flint Q6_K for the first run. The model file (`flint-Q6_K.gguf`, 30.5 GiB, 49 layers, 256 experts with 6 routed and 2 shared per token) is served by LM Studio, installed on this host under the name Bionic, with the expert weights forced onto the CPU (the part of Strata's method that carries over), 16384 context, one prediction slot, Q8_0 KV cache, reasoning budget 512 because the engine client allows 2048 output tokens and 120 seconds per request, and a repaired chat template (the shipped template holds a `\x00` escape that Bionic's Jinja parser rejects; the filter was removed in Bionic's template editor, the model file is unchanged). After loading: 3.2 GB GPU memory in use, 19.1 GiB host memory free. `config/models.toml` now names `flint@q6_k` for all four roles.
Two refusals on the first start, both from 8 October runtime files in master's `state/`, neither from the engine: `OWNER_UNVERIFIED` because `state/locks/coordinator.lock` (8 October, empty) had no metadata file, which the current ownership code treats as unverifiable; moved to `state/locks-stale-20261008/`. Then `STORE_IDENTITY_MISMATCH` because `state/research.sqlite` was the 8 October manual-AI-day store (39 requests that day, older schema without the identity table, pre-rename project identity); with the owner's OK it was moved with its sidecar files to `state/legacy-20261008/`, nothing deleted. The engine then created a fresh store with the current identity; `control list` reports no freezes, no open runs, zero trials. The other 8 October files (`execution-reserve.*`, `runtime/`, `watchdog/`, the three other empty locks) are untouched.
Practice run 1 (`run-20261024-ee1bd303`, the first run against a real model): 21 requests, 46 seconds, `STOPPED_ENGINE_STEP_LIMIT`, no candidate. Flint answered the Director in 20 seconds with valid JSON (about 33 tokens per second). Two harness faults found and fixed with tests, see "Practice run with Flint" in [the engine plan](ENGINE_PLAN.md): the idea tasks carried no market description (fixed: `market_brief` in every pick, memo, specification and agenda task), and the text roles were Deep Agents with file tools over an empty store, which the model searched until the step limit (fixed: Director, Researcher and Mathematician are one completion without tools; the Engineer agent stops after three identical tool-call rounds). Engine environment lane 60 passed; product lane 97 passed. Memory with Flint Q6_K loaded sat between 15.6 and 19.1 GiB free, around the 16 GiB floor.
Practice run 2 (`run-20261024-e4a06f91`, fixed harness): 10 requests, 3.2 minutes, `STOPPED_AVAILABLE_RAM_FLOOR`. The Director picked three market hypotheses, the Researcher wrote three memos, the Director approved all three, the Mathematician wrote three specifications, each reply in 14 to 26 seconds; the first Engineer build refused on the memory floor with Q6_K loaded. Owner direction the same day: a model-reply fault is recorded and the cycle goes on (`STEP_FAULTS` in `cycle.py`, faults in the END record, the run record and the summary); run-level refusals still stop the cycle. Live view tool `tools/engine_tail.py` (read-only). Engine environment lane 61 passed; product lane 97 passed.
Practice run 3 (`run-20261024-813e5403`, Q6_K with memory freed by the owner, 17.3 GiB free at start): 1 request, 22 seconds, cycle completed with no hypotheses because the Director's JSON held one glitched token and the strict parser refused it. Fix: one bounded retry for a JSON-answer step that shows the model its parse failure; no repair of model text. Engine environment lane 62 passed.
Practice run 4 (`run-20261024-4af7cb8d`): stopped on the memory floor because the model file still named Q6_K while Q4_K_M was loaded, and the server loaded Q6_K on demand beside it (my mistake; `config/models.toml` now names `flint@q4_k_m`; on-demand loading set off in Bionic's settings file with the owner's OK, effective at the next app start). The owner chose Q4_K_M after the arithmetic: Q6_K at 32.7 GB is the same byte size as the Qwen model that crashed Strata, and leaves no room above the 16 GiB floor on this 63 GiB host.
Practice run 5 (`run-20261024-813baa6f`, Q4_K_M): 40 requests, 3.7 minutes, cycle `COMPLETED`, the first to reach the sandbox. One Engineer candidate wrote, fixed and ran a program that produced `signals.csv` with 150 rows, then hunted for the file in its store until the repeat guard stopped it, and the harness discarded the completed run. Fixed with tests: a build fault after a completed run keeps the signals and scores them; the Engineer starts from a starter program; `run_job` tells the model the signals are accepted. Engine environment lane 63 passed; product lane 97 passed. See "Practice run with Flint" in [the engine plan](ENGINE_PLAN.md).
Practice run 6 (`run-20261024-ed962295`, Q4_K_M): 38 requests, 3.9 minutes, cycle `COMPLETED`. The first candidate through the whole path: built from the starter, run to signals, reviewed, scored `REJECTED` (long on all 150 sessions, Sharpe 1.058 against buy-and-hold 1.063), deflation recorded. The other candidate searched its one-file store with `glob` and `grep` for twenty rounds until the step limit; fix: the Engineer's file tools are `read_file`, `write_file` and `edit_file` only.
Practice run 7: stopped by the kill switch after 6 requests, as designed. On-demand model loading is off in Bionic (the app reads its own copy of the server settings; both copies now say off; verified by a probe). Practice run 8 (`run-20261024-be58bee0`): 26 requests, 4.8 minutes, the first clean cycle with no faults: three candidates built in four model calls each and scored; two did not beat buy-and-hold; the third did (Sharpe 1.415 against 1.063, 67 position changes) and the deflation gate rejected it at DSR 0.31 over 10 trials. The engine works end to end against a real model; no candidate has passed the gate yet, which is the expected result for a handful of random ideas on a synthetic market.
GEPA run 1 (`run-20261024-06c3d7c4`): 8 evaluation cycles on two markets, 112 requests, 23 minutes, `GEPA_COMPLETE`. One proposal (a longer Director prompt) scored below the committed prompts (mean 0.2 against 0.3); best is the committed set, nothing applied. The owner-run wrapper `tools/practice.ps1` exists (owner OK the same day); practice run 9 (`run-20261024-ea13e6ca`, 17 requests, `COMPLETED`, one candidate rejected at DSR 0.13 over 22 trials) ran through it: memory check, listing check, run, record, model unloaded. Day total: nine practice runs, one GEPA run, cycles 1 to 17, 22 trials, eight harness fixes with tests; no candidate has passed the deflation gate.
Practice run 10 (`run-20261025-9c940f96`, 8 cycles, 156 requests, 23.7 minutes, no candidate past the gate) and GEPA run 2 (`run-20261025-675a3639`, stopped by the kill switch after 52 requests) exposed a fault of mine: from practice run 6 to GEPA run 2 the Engineer's task ended with the literal text of a template instead of the specification (a missing `f` prefix in the run 5 fix; the test only checked for a heading). Practice runs 6 to 10, GEPA run 1 and GEPA run 2 say nothing reliable about Flint as an Engineer; their records stay as history. Fixed with content-checking tests: one task builder with the specification, a TRAIN sample (no validation row) and `/spec.md`; `/spec.md` is not submitted with the code; a read-only streak stops with `ENGINE_NO_PROGRESS`. Engine environment lane 66 passed; product lane 97 passed. Details in "Practice run 10 and GEPA run 2" in [the engine plan](ENGINE_PLAN.md).
Harness plan written on 25 October 2026 (plan only; the owner said not to start now): [the harness plan](HARNESS_PLAN.md). Owner direction the same day: a Compertum variant of Vesper core (the owner's separate project, `Desktop harness`, 709 lines), copied into Compertum, in the style of the pi harness: four plain tools (read, write, edit, run), no permission prompts, the barrier is the section 19 sandbox, not a prompt. Four small stages: the variant without a model with a preflight check, the four tools, a wider GEPA surface, real data. The owner still starts every run.
Practice run 11 (`run-20261025-cedbea93`, the first run with a working Engineer task): 6 of 8 cycles, 116 requests, 28 minutes, stopped on the memory floor (free memory fell from 27.8 to 15.3 GiB during the run; cause not confirmed, the model server had 4 prediction slots). The Engineer wrote 17 programs and made 22 runs; no candidate passed the deflation gate (best deflated Sharpe 0.35, 47 trials counted). Fixed with tests: the Engineer run limit now counts per candidate, not per cycle. The wrapper loads the model with one prediction slot and records memory every 30 seconds. Engine environment lane 67 passed; product lane 97 passed. Details under "Practice run 11" in [the engine plan](ENGINE_PLAN.md).
Practice run 12 (`run-20261025-1b11893a`, one model slot): all 8 cycles, 151 requests, 33 minutes, no memory stop; every Engineer build produced signals; no candidate passed the gate (best 0.36, 61 trials). Its memory file shows the model server itself growing about 10 GiB per hour; the likely cause is Bionic's 32 context checkpoints per slot.
The approved GEPA information changes are built and reviewed (round 1 `CHANGES_REQUIRED`, all applied): the ten-level score, explaining feedback with repeated ideas, four varied markets (`market.py` generator only, existing markets byte-identical). Levels 7 to 9 need an Auditor pass, which today happens only at the 0.95 gate, so an unaudited strategy that beats buy-and-hold stays at level 6. Engine environment lane 70 passed; product lane 100 passed. Details under "Practice run 12" and "Built on 25 October 2026" in [the engine plan](ENGINE_PLAN.md).
Owner OK on 25 October 2026: Flint Q4_K_M's saved Bionic settings now hold `llm.load.llama.contextCheckpoints` 4 (was the default 32); backup `flint-Q4_K_M.gguf.json.backup-20261025` next to the file. A load test confirmed the model server starts with `--ctx-checkpoints 4` and `--parallel 1`. Whether this stops the memory growth is shown by the next run's memory file.
The Director's lessons table is built and reviewed (owner request, 25 October 2026; round 1 `CHANGES_REQUIRED`, all three should-fixes applied): code builds one row per idea tried on the same market from the END records, with tries and the best of the ten levels, and no Validator numbers or model reasons. Cycles now record a market fingerprint; older cycles are left out. Product lane 108 passed, 5 skipped; engine environment lane 83 passed. One earlier engine-lane run had an unexplained `NO_SIGNALS` failure in `test_engine_practice_run.py` that did not repeat. Details under "the Director's lessons table" in [the engine plan](ENGINE_PLAN.md). Held in a git stash during the baseline and restored by the other session on the owner's decision (25 October 2026: "let it run with the lessons table"). Baseline runs 13 and 14 ran without the table; run 15 runs with it. Run 14 cycles 65 and 66 read the two new Director prompt lines while the table did not exist yet, and run 14 cycle 64 had one sandbox job refused with `SANDBOX_PROFILE_EXISTS` while the lessons session ran engine tests; those three cycles are reported separately. At the restore only the non-sandbox product tests ran (88 passed); the engine environment lane and `tests/test_engine_practice.py` wait until the baseline ends, because they use the live sandbox profile.
Superseded next action (kept as history): the owner's 50-cycle baseline of the current prompts, as three runs because the hard maximum of 450 requests allows about 23 cycles per run (the owner keeps the maximum): runs 13 and 14 with 17 cycles, run 15 with 16, each with a 440-request limit, chained with `&&`. The wrapper unloads the model between runs, which also resets the model server's memory. Then I grade every cycle with the ten levels as the baseline for GEPA run 3. Owner decision the same day: the Auditor checks every candidate that beats buy-and-hold, at the gate or below it. Built and reviewed (round 1 `CHANGES_REQUIRED`, applied: a rounding case that would have frozen the engine on an honest FAIL, and two missing tests). Only a candidate that passes the gate and the Auditor is promoted or queued. Levels 7 to 9 now apply to audited honest strategies. Engine environment lane 75 passed; product lane 101 passed. The baseline runs after this commit, so the baseline and GEPA run 3 use the same rules.
The owner stopped the baseline on 25 October 2026, local time ("can we stop it for now?"; run IDs carry the UTC date). Run 13 (`run-20261025-ff76da95`): 17 cycles, 292 requests, `CYCLE_LIMIT`. Run 14 (`run-20261026-ca206b02`): 16 cycles, 137 requests, `KILL_SWITCH`, cycle 76 cut off. Run 15 did not start. 28 cycles are clean; 96 trials are counted. The model is unloaded and nothing runs.
The owner then agreed a new order with a second agent's plan: engine tests, a preflight check, a fixed bench and holdout, a bench baseline, GEPA run 3. Steps 1 to 3 need no model and are done:
1. Engine tests after the lessons table: engine environment lane 122 passed, 0 failed, 0 skipped.
2. The preflight content check (commit `4d1d64a`): before the lease and any request, every role task of every market is built from sample values and checked for unfilled placeholders, broken escapes, missing values, size and validation rows. A failure refuses the run with `ENGINE_PREFLIGHT_FAILED` and a list of problems.
3. The fixed bench and the holdout (`src/compertum/ai/engine/bench.py`): separate seed sets; evaluation cycles see no history and teach nothing (no lessons, no recent list, no GEPA feedback); holdout uses are counted before the first cycle and retire after 5; a bench-local measure with a fixed trial count that does not drift; a reference rule per patterned market; a false discovery on either empty market makes the verdict `BROKEN`. Finding: the exact planted rule passes the 0.95 gate on only 2 of 6 patterned markets with 150 validation sessions, so "found" uses half of the reference's Sharpe advantage instead. One independent review found seven defects, all fixed with tests; the two most serious could have let holdout markets reach learning cycles (reserved seeds and fingerprint checks now prevent it), and evaluation candidates no longer enter the queue. Engine environment lane 160 passed, 0 failed, 0 skipped; product lane 145 passed, 0 failed, 7 skipped. Details under "the fixed bench and the holdout" in [the engine plan](ENGINE_PLAN.md).
Project map refreshed on 25 October 2026 after this work, with the earlier unapplied lessons-table update folded in: nine pages, 91 source notes, 481 source files; pages 1 to 3 inspected after rendering.
The first bench start, 25 October 2026 at 22:25 local time, refused with `STORAGE_SCAN_DEADLINE` before any run row, request or trial. The storage scan covers about 333,000 files and took 18.2 seconds with the model unloaded, against the 30-second limit; with Flint just loaded it took longer. The limit is unchanged. With the owner's OK ("Ok, clean it.") and under `docs/TEST_RETENTION.md`, the basetemp of the 24 October full-suite run (`.cache/test-runs/total200-full-20261024-230548`) was emptied: 52,729 files, 33,960 folders and 1,572 symbolic links, all pointing inside the folder and removed as links. The output file is kept with an unchanged hash; the record is `.cache/test-runs/test-retention-20261025-total200.json`. After cleanup: 280,654 files, scan 13.7 to 14.1 seconds.
Bench baseline 1 (`run-20261026-84433f03`) ran 15 full cycles, 3 per market, and was stopped by the owner's stop file: verdict `MEASURED`, patterns found 3 of 3 (best capture 0.79, 0.66 and 0.74), false discoveries 0, mean bench level 6.44, 293 requests, 63.4 minutes. Details and the table are under "Bench baseline 1" in [the engine plan](ENGINE_PLAN.md). Built during and after it (commit `4960ca5`): real refusal codes with `finish_reason` and token counts in every model-call record, the review length limit, the owner's lower memory floor (8 GiB), and a runner guard against sandbox tests during a run. Engine environment lane 162 passed, product lane 166 passed and 7 skipped.
Speed work on 26 October 2026 (details in [the after-bench plan](MATHEMATICIAN_PLAN.md), "V1 results"): Flint's expert offload ratio is 0.6 (68.1 tok/s against 48.2 at 1; GPU 12.3 of 15.9 GiB); flash attention on, 8 threads and batch sizes 2048/1024 are set; the GEPA speed tie-breaker (V2) is built and tested; the memory floor is 8 GiB.
GEPA run 3 (`run-20261026-64268b35`, 26 October 2026): 22 cycles, 387 requests, 59 minutes, stopped at its cycle limit. Candidate 2 (a longer Researcher prompt) had the best mean level, 5.0 against 4.4 for the current prompts, over 8 cycles each. That gap is within noise: levels vary by 2 to 3 between repeats on one market. Candidate 3 was never scored.
Holdout use 1 of 5 (`run-20261026-2708cd89`), candidate 2: 20 cycles, 4 per market, 401 requests, 59 minutes. Verdict `MEASURED`: patterns found 2 of 3 (momentum 5, capture 0.539; momentum 10, capture 0.950; reversal 3 not found, no audited candidate), false discoveries 0, mean level 5.85. This is a pass/fail check on new markets, not a comparison: bench baseline 1 used other seeds, 3 cycles per market and older code. Candidate 2 is not applied. Owner decision: holdout-1 rests for several days.
An independent read-only review after the holdout found nine defects; all are fixed with tests (details in [the after-bench plan](MATHEMATICIAN_PLAN.md), "V2 revised"). The two most serious: the test runner's during-run guard could be bypassed and failed open on a ledger error (now an allow-list that fails closed and follows a restored generation), and a reply cut off inside a tool call was recorded as a tool fault without its token counts (now `AI_RESPONSE_TRUNCATED` with counts). Also: GEPA's best candidate is now ranked by exact mean level first; speed is output tokens per candidate built, which extra calls cannot game; `run_gepa` refuses bench and holdout markets itself; candidate files must match their recorded hashes; the found rule uses the unrounded capture; `practice.ps1` passes both `-Cycles` and `-Hours` and checks the server status line exactly. Engine environment, all engine files plus the model interface and runner: 235 passed, 0 failed, 0 skipped. Product environment, the same files: 178 passed, 0 failed, 7 skipped.
Model providers (owner standard, 26 October 2026: the engine must run on any local model, API key or sign-in, because the PC is also a work machine). Step 1 is built: the owner lists remote providers in `config/providers.toml` (address and the name of the user environment variable that holds the key); `--models NAME` (`-Models NAME` in `tools\practice.ps1`) picks `config/models-NAME.toml`, and `local` stays `config/models.toml` (Flint). Loopback rules are unchanged; a remote address must match a listed provider exactly over HTTPS; the key goes only into the Authorization header and never into a record; a missing key refuses before the request counts. The owner picks the model at run time without editing files: `-Model ID` sets one model for every role for that run, and `-Pick` shows a menu of model files and of the models that provider lists now (LM Studio's downloaded models for local). The provider file names the key's variable with `key_variable`; a value that is not a variable name, such as a pasted key, is refused as `PROVIDER_KEY_IN_FILE` without echoing it. The first provider is DeepSeek, authorized by the owner on 26 October 2026 with no spending limit (`config/models-deepseek.toml`, default model `deepseek-v4-pro`; the service also lists `deepseek-flash`; the key check passed with a model list and no completion). DeepSeek results are not comparable with Flint results and need their own bench baseline. Every evaluation run's START row now records the hashes of the committed prompts too. Planned, not built: step 2, adapters for APIs that are not Chat Completions compatible; step 3, sign-in through official command-line tools.
Noise run 1 (`run-20261026-bb362839`, committed prompts on Flint, bench-1, 4 cycles per market): 20 cycles, 428 requests, 58 minutes. Verdict `MEASURED`: patterns found 2 of 3 (momentum 5, best capture 1.897; momentum 10, 1.147; reversal 3 not found, no audited candidate), false discoveries 0, mean level 6.35. The committed prompts also missed the reversal pattern, so candidate 2's reversal miss on the holdout was not caused by its prompt.
DeepSeek v4-pro bench baseline 1 (`run-20261026-a43450fb`) was stopped by the owner's stop file after 13 cycles and 76 requests, on my advice. It measured nothing about the model: `deepseek-v4-pro` thinks before it answers, and all 18 Mathematician "specify" replies used the whole 2048-token cap on thinking (`AI_RESPONSE_TRUNCATED`), so no candidate was built and the Engineer was never called. Fix: a model file may set `max_tokens` (up to 16384) and `seconds` (up to 600) per role; they replace the engine's default of 2048 tokens and 120 seconds for that model only. `config/models-deepseek.toml` sets 8192 and 300; Flint's file sets neither and is unchanged. Replies, thinking text included, may be up to 256 KiB. Engine environment: 257 passed, 0 failed, 0 skipped; product environment: 200 passed, 0 failed, 7 skipped. The DeepSeek baselines run again after this fix.
DeepSeek v4-pro cap check (`run-20261026-c593d049`, bench-1, 1 cycle per market): 5 cycles, 106 requests, 34 minutes. The whole chain ran on DeepSeek: model check with the key, Director, Researcher, Mathematician, Engineer in the sandbox, scoring, gate and Auditor. 11 candidates built, 6 audited, patterns found 2 of 3, false discoveries 0, mean level 7.80 (one cycle per market, so not a baseline). The Mathematician used 6653 to 7773 thinking tokens per review and one of the first three was still cut off at 8192, so its cap in `config/models-deepseek.toml` is now 16384 tokens and 600 seconds; the other roles keep 8192 and 300.
DeepSeek flash cap check (`run-20261026-a5167a2c`, 1 cycle per market): 5 cycles, 133 requests, 21 minutes, 0 cut-off replies, 15 candidates, 5 audited, patterns found 1 of 3, false discoveries 0, mean level 7.40. The whole chain ran on flash too. Owner's cost figures: about $0.14 for the flash cycles and $0.54 for all v4-pro cycles so far. Flash used about 27 requests per cycle, so a 20-cycle bench run did not fit in 450: the owner raised `request_hard_maximum` in `config/engine.toml` from 450 to 600 on 26 October 2026. Next: full DeepSeek baselines at 4 cycles per market with `-Requests 600`, one model after the other.
DeepSeek bench baselines, committed prompts, bench-1, 4 cycles per market, 26 October 2026. Both verdicts `MEASURED`, both stopped at their cycle limit.
- v4-pro (`run-20261026-b2a7be11`): 20 cycles, 503 requests, 168 minutes. Patterns found 2 of 3 (momentum 5: 3 candidates at capture 0.5 or more, best 1.000; momentum 10: 9, best 1.043; reversal 3: 0, best 0.414), false discoveries 0, mean level 7.65, 58 candidates.
- flash (`run-20261026-d0267a4a`): 20 cycles, 538 requests, 86 minutes. Patterns found 2 of 3 (momentum 5: 2, best 0.807; momentum 10: 5, best 0.991; reversal 3: 0, best 0.185), false discoveries 0, mean level 7.15, 59 candidates. No flash candidate passed the bench gate.
- For comparison, Flint noise run 1 (same settings): 2 of 3, false discoveries 0, mean level 6.35, 43 candidates, 58 minutes. All three models missed the reversal pattern.
- On the two markets with no pattern, 17 v4-pro, 13 flash and 7 Flint candidates beat buy-and-hold and passed the Auditor; the deflation gate rejected all of them.
- Output tokens by role (v4-pro / flash): Mathematician 566,400 (69%) / 560,514 (64%), at 56.9 / 26.6 seconds per call. Cut-off replies: v4-pro Mathematician 2 at 16384, Engineer 1 at 8192; flash Engineer 2 at 8192.
- One run per model, so the level gaps are not yet shown to be larger than noise. On Flint, levels vary by 2 to 3 between repeats on one market.
Owner direction, 26 October 2026: no separate Mathematician tool; tell GEPA what the firm wants, then run it on flash. Built: the optional goal file `config/gepa_goal.md`, owned by the owner and read only by the engine. Every reflection call receives it as "THE OWNER'S GOAL". It steers the proposals only; the score stays the level from the Validator's numbers. The START row records its hash. GEPA still rewrites all four roles in turn. Engine environment (GEPA, GEPA run, practice, bench files): 46 passed, 0 failed, 0 skipped; product environment: 44 passed, 0 failed, 1 skipped.
Owner direction, later on 26 October 2026: "USE GEPA to improve the firm." GEPA now also changes the firm's routing, a fifth component next to the four prompts: `config/engine_prompts/routing.md`. Code reads only four keys with fixed values, so a proposal chooses routes and adds no code. `review`: off (no Mathematician code review; saves its tokens), advice (the review is recorded only, the route used until now), or rebuild (the Engineer builds once more from its code and the review; the last completed run is scored and audited as before). `specify_sees_hypothesis`, `engineer_sees_memo` and `researcher_sees_lessons` (yes or no) send one more input to that role. The committed file holds the old routes, so committed runs and the baselines stay comparable. Every cycle END row records its routing. GEPA candidates write and apply `routing.md` with the prompts; a candidate from before this change is measured with the committed routing. The judge, the Auditor, the deflation gate and the ledger are unchanged; the review never sees a score, so a rebuild cannot select on validation results. Engine environment, all engine files plus the model interface and runner: 260 passed, 0 failed, 0 skipped. Product environment, the same files: 202 passed, 0 failed, 7 skipped.
Owner direction, 26 October 2026: "No GEPA limits. Let it just run and find and fix stuff." The owner raised `request_hard_maximum` in `config/engine.toml` from 600 to 10000, the highest value the E1 client accepts. GEPA now keeps up to 1000 candidates (was 64). Engine environment: 260 passed, 0 failed, 0 skipped; product environment: 202 passed, 0 failed, 7 skipped.
GEPA run 4 (`run-20261026-7b63a782`, flash, no limits) was stopped on the owner's request after 3 cycles and 78 requests, before any GEPA proposal, so that more of the firm could be handed to GEPA. The stop file was created at 19:28 EDT; the process then exited during a Mathematician call (status FAILED_UNEXPECTED, cause not recorded) without an END row. The agent closed the run with `control close-run` and a note (reason OWNER_CLOSED).
The firm's slots, 26 October 2026 (owner: "USE GEPA to improve the firm", "No GEPA limits"). GEPA now rewrites eight parts in turn: the four role prompts and four slots in `config/engine_prompts/` (`prompts.py`). Code reads each slot in one fixed way, and the referee (judge, Auditor, deflation gate, ledger, limits) is never a slot.
- `routing.md`: the earlier routes, plus `director_sees_tool`, `researcher_sees_tool` and `specify_sees_tool`. The committed file sends the tool's report to the Mathematician.
- `settings.md`: hypotheses per cycle (1 to 3), retries (0 to 2), Engineer runs per candidate (2 to 5), and per role an output cap (model, 1024 to 16384) and a temperature (0 to 1). A chosen cap replaces the model file's cap for that role (`override_tokens` in the E1 client). The committed file holds the earlier values.
- `tool.py`: GEPA's analysis program. Each cycle that routes its report runs it once in the sandbox, with train.csv and a validation.csv that holds the header only. Its run is filed under `<cycle id>-tool`, so the Auditor's checks of a candidate see only that candidate's runs; a denied access or a loopback connection still freezes the engine. A failed tool gives the roles no report, and GEPA reads why it failed. The seed tool reports, on the training rows only, the correlation of past window sums with the next return at windows 1 to 20, and the mean next return after streaks. On a practice market with a planted 3-day reversal it shows t values of about -3 to -4.
- `starter.py`: the Engineer's starter program, unchanged in the committed file. GEPA may rewrite it; it runs only in the sandbox, as the Engineer's code.
- Each slot is reflected on by the model of its closest role (routing and settings: Director; tool: Mathematician; starter: Engineer). Candidates write and apply all eight files. A candidate from before a slot existed is measured with the committed slot.
- The committed firm now differs from the one the baselines measured: the Mathematician receives the seed tool's report. A GEPA result is compared with the flash baseline as "the old firm"; a new flash baseline measures the new committed firm if needed.
Step S3 is built (docs/MATHEMATICIAN_PLAN.md): every sent model request is saved in full to `state/engine/transcripts/<run id>.jsonl` (messages, reply, tool calls, the thinking text of a thinking model), for bounded runs and GEPA runs, GEPA's reflection calls included. Deviation from the plan, on purpose: bench and holdout requests are saved too, for analysis, and every such line carries `training_allowed: false`; a dataset builder must keep only `training_allowed: true` lines. Every text passed the client's secret check before it was sent or accepted. One run's file stops at 2 GiB; later lines are counted as skipped. The END row reports lines, bytes, skipped lines and failures. Not built: a stop based on the records storage category.
Tests: engine environment, all engine files plus the model interface and runner: 266 passed, 0 failed, 0 skipped. Product environment, the same files: 206 passed, 0 failed, 7 skipped. One end-to-end GEPA test on scripted roles runs 40 real cycles and rewrites all eight parts; the rewritten tool and starter run in the sandbox.
GEPA run 5 (`run-20261027-523c00f4`, flash, all slots) failed after 4 cycles and 105 requests: `sqlite3.OperationalError: database or disk is full` in `record_cycle`. The disk had 115 GB free. The research store `state/research.sqlite` had reached its 16 MiB cap (16,773,120 bytes), mostly engine records: about 36 KB per cycle. The END row was written (FAILED_UNEXPECTED).
Owner decision, 26 October 2026: raise the research store cap to 256 MiB. Built: `STORE_BYTES` in `persistence.py` (research store 256 MiB; the evaluation and execution stores keep 16 MiB). The checkpoint limit follows the largest cap. A recovery set now sizes the research store's snapshot from its current size plus 64 KiB (`snapshot_bound`), and the supervisor reserves that size, the two other caps and 16 MiB for messages (was a fixed 64 MiB). Snapshots go to the backups category (21 GiB budget, unchanged); a full recovery set of a 256 MiB research store reserves about 304 MiB there. A separate engine database stays possible later, if the engine's records approach the new cap. New test: a 20 MiB research store opens and checkpoints.
Superseded next action (kept as history; GEPA run 6 ran on 27 October): the owner starts GEPA run 6 on flash: `tools\practice.ps1 -Models deepseek -Model deepseek-flash -Mode gepa -Cycles 1000 -Requests 10000 -Note "GEPA run 6, flash, all slots, 256 MiB store"`. Then the best candidate is measured on bench-1 with flash and compared with the flash baseline. Watch the reversal market.
Next build (owner agreed, 26 October 2026): the sandboxed harness. Each harness version that GEPA writes runs as a copy of the firm inside the sandbox; its model calls go through a gate outside the sandbox that holds the key and counts requests; the referee stays outside. Then GEPA may rewrite the harness logic itself. Never slots: keys, providers, the request maximum, the stop file, the memory check, the sandbox, and the referee.
Superseded next action (kept as history): the owner starts GEPA run 4 on flash: `tools\practice.ps1 -Models deepseek -Model deepseek-flash -Mode gepa -Cycles 1000 -Requests 10000 -Note "GEPA run 4, flash, no limits"`.
Superseded next action (kept as history): bench noise runs before any more GEPA (owner decision, 26 October 2026). The owner runs the current prompts on bench-1 two or three times, then candidate 2 the same number of times, with the same settings: `tools\practice.ps1 -Mode bench -CyclesPerMarket 4 -Requests 450 -Note "noise run 1, current prompts"` and `tools\practice.ps1 -Mode bench -CyclesPerMarket 4 -Requests 450 -PromptsRun run-20261026-64268b35 -PromptsCandidate 2 -Note "candidate 2 bench run 1"`. From the spread, size the cycles per candidate for the next GEPA run, and check whether capture is a steadier score than the level. The request limit stays 450.
Superseded next action (kept as history), in order:
Done on 26 October 2026: steps 1 to 3 below. Results: the three load settings kept (prompt reading +82%), XMP at 6000 MT/s kept (prompt reading +12%, generation unchanged at about 67 tok/s). Step 4, GEPA run 3, is next.
1. The owner's one-cycle check of the three new load settings, before the restart: `tools\practice.ps1 -Cycles 1 -Requests 40 -Note "speed settings check"`. Measure generation speed with Bionic's server log (the `eval time` lines; compare with 68.1 tok/s) and GPU and RAM use with the wrapper's memory record (`gpu_used_gib` column).
2. The owner restarts the PC and enables the RAM's EXPO profile (the DDR5-6000 kit ran at 5000 MT/s). Then a second one-cycle check measures EXPO alone.
3. If a check is slower, undo that change from the backups `flint-Q4_K_M.gguf.json.backup-20261026-before-fa-threads-batch` and `flint-Q4_K_M.gguf.json.backup-20261026-before-offload`, next to Flint's settings file under `C:\Users\bgonn\.lmstudio\apps\bionic\.internal\user-concrete-model-default-config\lmstudio-community\flint-GGUF\`.
4. GEPA run 3: `tools\practice.ps1 -Mode gepa -Cycles 22 -Requests 450 -Note "GEPA run 3"`, then one holdout check of its best prompt set before any prompt is applied.
Superseded: step V1 of the after-bench plan, moving some of Flint's expert layers to the GPU, with the owner's OK; then GEPA run 3 with the speed tie-breaker. Superseded: the owner starts the bench baseline of the committed prompts, `tools\practice.ps1 -Mode bench -Requests 450 -Note "bench baseline 1"` (20 cycles, about 85 minutes with Flint loaded). Then GEPA run 3, then one holdout check of its best candidate with `-Mode holdout -PromptsRun <run id> -PromptsCandidate <n>` before any prompt is applied. Open for later: count trials per data source before the real-data stage, because practice and bench trials raise the real gate. After the bench baseline: [the Mathematician plan](MATHEMATICIAN_PLAN.md) (plan only; a power check, a train-only data summary, then train-chosen parameters with declared trials, each measured alone on the bench). Also for later: [the native scanner plan](NATIVE_SCANNER_PLAN.md) (plan only; a profile shows 93,749 directory opens take about 10.5 of 15.2 seconds, so cleanup of test folders comes first and a native walker would save about 30 percent).
Owner investigation of the three recorded full-suite failures, 24 October 2026. None was a product defect.
1. Backup capacity test: it stated scratch 10 GiB. The owner raised the scratch ceiling to 50 GiB the same day ("increase storage to 50 GiB") and then the project total to 200 GiB ("overall the project can use 200 GiB"; the other categories are unchanged); the test and `tests/test_config.py` now state both. The scratch default lives in `src/compertum/config.py` (the hard ceiling `CAPS` in `storage.py` derives from it) and in `config/default.toml`; frozen configs with the retired 5 GiB or 12 GiB limits still load and read as the new default (new tests). Measured before the change: scratch 12.546 GiB, over its 12 GiB ceiling, which blocked storage admission; backups 20.413 GiB; records 1.247 GiB; total 34.207 GiB of 50 GiB; C: free 126.9 GiB (50 GiB must stay free). Effect and limits to know: the total is a single value, `total_bytes` in `src/compertum/config.py` and `config/default.toml`; `TOTAL_CAP` in `storage.py` reads it, and the six guards in `storage.py`, `recovery.py` and `watchdog.py` that held a literal 50 GiB total now read `TOTAL_CAP`. The separate rule "50 GiB must stay free on the volume" is unchanged. Three things bound growth now: (1) the category ceilings sum to 96 GiB (data 15, models 5, scratch 50, records 5, backups 21), so they bind before the 200 GiB total; the data category is still capped at 15 GiB; (2) C: had 126.9 GiB free, so the free-space minimum allows about 77 GiB of growth today; (3) the total of 200 GiB binds only after the categories are raised. The owner decides whether to raise data or backups next. Frozen configs with the retired 50 GiB total or the retired scratch limits still load (new tests).
2. Fake economic recovery test: the restore order changed on 17 October 2026 (commit `22e41ad`, the coordinator snapshot is taken last on purpose, comment at `recovery.py:123`). The phase history of the failing run reads PREPARING, STAGING_EVALUATION, STAGING_EXECUTION, STAGING_COORDINATOR. The test now asserts the last staging phase, the staging order and that READY and PUBLISHED never appear. Commit `63e6ab9`.
3. Final transaction test: other test files import the generated numerical module during collection, so under the whole suite it is always loaded. Reproduced by running `tests/test_generated_final.py` first (the old test fails). The test now removes the module and its package attribute before the run, restores them afterwards, and still fails if the empty-selection path imports the module. Commit `63e6ab9`.
Full product suite after the storage change, 24 to 25 October 2026, `.cache/clean-env-m0` (source lane, simulated fixtures; no native, installed-package or financial result):
- Main lane, 14 failed, 7092 passed, 16 skipped, 14 errors in 1 h 28 min. All 28 failures and errors are in four test files that use the economic fixture (`test_fixture_source_journal`, `test_fixture_closing_source_write`, `test_fixture_order_rejection`, `test_fixture_order_source_binding`), error `CONTROLLED_FIXTURE_SOURCE_UNVERIFIED`: the fixture admits paths only under `m5-local-economics-20261017-01`. Not caused by the storage change.
- The same four files in that folder: 29 passed, 0 failed. The eight files listed in the fixture helper in that folder: 84 passed (13, 19, 19, 6, 10, 2, 4, 11), 0 failed.
- Distinct totals: 7204 passed, 0 failed, 16 skipped. The 16 skips are the five Deep Agents engine files (skipped in this lane, they pass in the engine lane) and 11 older skips. Earlier run: 7162 passed, 12 skipped.
- The first attempt stopped at collection (`tests/windows` has files with the same names as top-level files); it ran no tests. Output and basetemp: `.cache/test-runs/total200-full-20261024-230548*`.
- Measured storage after the run: scratch 16.62 GiB, records 1.25 GiB, backups 20.41 GiB, total 38.28 GiB; C: free 122.8 GiB.
Strata removed on 24 October 2026 on the owner's decision: `D:\Strata` (66.9 GiB, of which 65.6 GiB model files), `C:\Users\bgonn\strata` (1.1 GiB source clone) and `AppData\Roaming\Strata` were deleted after a read-only check (no running process, no scheduled task, no service, no links pointing outside the folders). D: free space rose from 554 to 621 GiB. The GitHub fork `BGonnermann/Strata` was kept. Compertum's adapter module, schemas and the accepted M0 and M3 records that mention Strata are unchanged. `AGENTS.md` now says Strata is removed and the start floor is 16 GiB. Then `gepa --cycles 12 --requests 200 --note "GEPA run 1"`. I read the printed records and the daily summaries under `state/engine/` and record the results here. The two unexplained suite failures above stay recorded until the owner asks for an investigation.

Earlier entries below retain their original evidence and dates.

## Cycle control source checks passed; complete cycle blocked - 19 October 2026

Authenticated control and exclusive dispatch ownership are implemented in the working tree.
Stop releases ownership atomically. Pending cleanup blocks dispatch across controller reconstruction.
Waiting pause, stop, and shutdown preserve unrelated workers after ownership release.
Independent review found no remaining blocker in this control scope.

Final source results: 25 passed, zero failed, zero errors, and zero skipped.
The job took 47.851189 seconds, observed exit zero, and left zero children.
It checked 21 record cases and four control cases, including twelve approval-refusal variants in one unchanged fixture.
All 57 current input hashes and 141 historical evidence hashes match.
Earlier control jobs omitted the generated runner from their input hashes. The final job pins both runner and wrapper.
Successful first-launch behavior remains simulated. Native acceptance and full-cycle continuation remain unverified.

The receipt folder uses 2,043,904 of 2,097,152 bytes. Its next 98,304-byte reservation is short by 45,056 bytes.
Smaller diagnostic outputs preserve the complete 65,536-byte exit-record allowance. No prior receipt was changed.
The test namespace uses 425,820,160 of 469,762,048 bytes. Native and preparation holds remain short by 94,470,144 bytes.
Cleanup again refused active Python work before selecting or removing files. Existing limits and process checks remain unchanged.

The accepted cycle remains incomplete: continuation, audited packet, actual assessment, revised proposal, and native acceptance are outstanding.
The current source/wheel environment pair also remains unverified. No spending, publication, service, or Strata start occurred.
Only M0 remains accepted. M3 remains terminally blocked. M6 remains zero of ten actual sessions.
Next action: Reclaim eligible temporary test files when process checks permit; receipt capacity must also admit further verification.
See [the report](../reports/SUPERVISED_RESEARCH_CYCLE_20261019.md) and [execution checklist](SUPERVISED_RESEARCH_CYCLE_WORK.md).

Earlier entries below retain their original evidence and dates.

## Cycle records verified; native acceptance not admitted - 19 October 2026

The approved supervised cycle remains unfinished. Its bounded record layer passed fresh source verification.
Final counts: 74 passed, zero failed, zero errors, and zero skipped. The job observed exit zero and left zero children.
Of these, 21 test cycle records and 53 test existing contracts.
Independent review defects were reproduced and repaired before this final suite.
Authenticated cycle control, dispatch ownership, continued execution, feedback, and revised-proposal import remain pending.
No actual cycle, numerical worker, installed-package check, assessment, or revised proposal was produced.

The latest test namespace charge is 393,261,056 bytes. Its unchanged 448 MiB limit leaves 76,500,992 bytes.
The native and preparation holds require 138,412,032 bytes. Cleanup still refuses active unrelated Python work.
The history evidence folder also cannot fit the proposed full 1 MiB receipt hold.
A matching current source/wheel environment pair remains a native prerequisite.
No limits changed. No unrelated process was stopped. Strata remains off.
Only M0 remains accepted. M3 remains terminally blocked. M6 remains zero of ten actual sessions.
See [the progress report](../reports/SUPERVISED_RESEARCH_CYCLE_20261019.md) and [execution checklist](SUPERVISED_RESEARCH_CYCLE_WORK.md).

Earlier entries below retain their original evidence and dates.

## Explicit research start verified in source - 19 October 2026

The coordinator now accepts separate approval to start one first unit of a registered campaign.
It saves the request before dispatch. Duplicate requests and owner restarts cannot repeat the start.
Prelaunch refusal leaves the campaign paused. Existing runner checks and transport permissions remain unchanged.
Fresh final source results: 120 passed, zero failed, zero errors, and zero skipped.
All three final whole jobs passed, observed exit zero, and left zero children.
The distinct capacity02 check passed outside the session sandbox without permission changes.
Successful dispatch tests use simulation. The owner restart test uses real Windows owner lifetimes before worker launch.
No actual campaign execution or installed-package verification occurred. Native start integration remains unverified.
Cleanup waits for other Python processes, including Tundra. Test files and all receipts remain preserved.
No limits changed. No broker action, service, security change, Strata start, commit, or publication occurred.
Only M0 remains accepted. M3 remains terminally blocked. M6 remains zero of ten actual sessions.
See [the start report](../reports/AI_START_VERIFICATION_20261019.md).

Earlier entries below retain their original evidence and dates.

## Registration repair verified after cleanup - 19 October 2026

Fresh source verification passed: 173 passed, zero failed, zero errors, and zero skipped.
Registration contributed 27 cases; contracts, history, and prepared campaigns contributed 100; campaign records and seals contributed 46.
All three whole jobs passed, with observed exit zero and no remaining children.
Capacity11 passed in 118.827439 seconds after routine cleanup. Earlier failed capacity attempts remain preserved.
Cleanup removed 140.2 MiB of old passing test files and all three new test groups' temporary files.
All 2,778 historical cleanup evidence hashes matched. All 120 prior verification hashes and all 41 current input hashes match.
The local test folder now uses 326,844,416 bytes, leaving 142,917,632 bytes within its unchanged 448 MiB allowance.
The cleaned installed-test parent uses 71,270,400 bytes. Its installed environment remains unchanged.
Scratch remains 15 GiB, backups 21 GiB, and total storage 50 GiB.
The saved-receipt repair preserves transport denial. No actual registration, campaign execution, or new installed-package verification occurred.
Next, define the separate connection from approved registration to research execution. Automatic dispatch, feedback, and revision remain unfinished.
Only M0 remains fully accepted. M3 remains terminally blocked. M6 remains zero of ten actual supervised sessions.
See [the completion report](../reports/REGISTRATION_COMPLETION_20261019.md).

Earlier entries below retain their original evidence and dates.

## Routine test cleanup verified - 19 October 2026

The owner approved `TEST_RETENTION.md`, replacing blanket retention for verified disposable test files.
The first cleanup removed 2,365 entries from two completed jobs' temporary trees.
All 114 external evidence files remain byte-identical. Both attempt parent folders remain.
Failed registration files, source snapshots, preparation files, and real runtime state remain unchanged.
Net storage charge fell by 33,308,672 bytes. Local folder usage is now 414,769,152 bytes.
The unchanged 448 MiB folder allowance has 54,992,896 bytes available.
Scratch remains 15 GiB, backups 21 GiB, and total storage 50 GiB.
The cleanup completed in 39.6957291 seconds after a successful dry run and independent review.
No new product tests ran: zero passed, failed, errors, or skipped.
Fresh complete admission and registration repair verification remain pending.
Next, admit the pending tests within existing limits. Use routine cleanup instead of another storage increase.
See [the cleanup report](../reports/TEST_RETENTION_20261019.md).

Earlier entries below retain their original evidence and dates.

## Approved storage passed; registration verification remains blocked - 19 October 2026

The owner approved only the local-economics test folder increase from 384 MiB to 448 MiB.
Distinct preparation07 files passed independent review. All other folder, category, and total limits remain unchanged.
The single capacity07 job passed in 108.189654 seconds, with exit 0 and zero remaining children.

The revised source run recorded 62 passes, 13 failures, zero errors, and zero skips.
All failures reached the receipt validator, which rejected the registration action as unavailable.
The overall job also reached its 120-second deadline during its final folder check.
Exit was observed and zero children remained. All evidence and consumed attempts remain preserved.

A receipt-only repair is prepared and independently reviewed, but remains untested.
It keeps transport capability checks unchanged. No actual campaign registration or execution occurred.
Remaining required tests exceed available folder space by at least 2,019,328 bytes before successful registration growth.
Further tests require a reviewed storage decision and fresh admission. No additional limit change or capacity retry occurred.
Project-map build and inspection results use the external `ai-registration-map01-review.json` receipt.

One CPU, the 4 GiB test limit, 120-second deadlines, and 16/12 GiB host memory floors remain unchanged.
Strata stayed off. This session reports restricted access; no security setting changed.
M3 remains terminally blocked. M6 remains zero of ten actual supervised sessions.
See [the verification report](../reports/AI_REGISTRATION_VERIFICATION_20261019.md).

Earlier entries below retain their original evidence and dates.

## Reviewed registration implemented; verification blocked - 19 October 2026

The coordinator now registers reviewed campaigns through the existing campaign owner and seal integration.
Registration retains exact approval bindings, twelve variants, the fixed schedule, and paused state.
Recovery preserves the original request and campaign. Registration grants no execution permission.
Independent static review round 3 is clear. Revised implementation remains untested.

The first source run recorded 62 passes, seven failures, zero errors, and zero skips.
Its overall job failed because retained test files exceeded the 384 MiB folder allowance by 2,289,664 bytes.
The guard observed exit and zero remaining children. Every failed attempt and five original source files remain preserved.
Receipt-format, restart-recovery, and dispatch-evidence repairs are prepared but need fresh verification.

The proposed folder allowance is 448 MiB within unchanged 15 GiB scratch and 50 GiB total budgets.
No allowance change has been applied. Approval and fresh complete capacity admission are required before further tests.
The horizontal map rebuild and publication remain pending. The previous PDF does not show this new blocked state.
Only M0 is fully accepted. M3 remains terminally blocked. M6 remains zero of ten actual sessions.
Strata stayed off. No actual campaign registration, execution, broker action, or service ran.

See [the report](../reports/AI_REGISTRATION_20261019.md), [checklist](AI_REGISTRATION_WORK_CHECKLIST.md),
and [exact storage request](AI_REGISTRATION_STORAGE_REQUEST.md).

## Linked research history verified - 19 October 2026

The new explicit link connects a saved review plan to one existing synthetic campaign.
Identical repeated links are safe. Conflicting links cannot replace retained evidence.
The read-only view checks proposal, plan, campaign, seal, and published result evidence.
It retains all twelve variants, attempts, failures, skipped dependencies, and pending results.
Historical seal checks preserve recorded identities. Execution still refuses a changed current identity.
All 121 source cases passed, with zero failures, errors, or skips. Independent review round 3 is clear.
The source job passed in 117.677234 seconds, observed exit 0, and left zero children.
Fresh capacity admission passed in 114.402827 seconds. Earlier failed and intentional failing tests remain preserved.
Source verification used native Windows ownership and bounded jobs. No installed-package or broker integration check ran.
The starting checkpoint was published as 94e772b. Final publication and map receipts appear in today's report and local final receipt.
Runner registration is prepared in AI_RUNNER_CONNECTION_PLAN.md. Automatic dispatch, feedback, and revision remain unfinished.
The exact query-only request is M5_IDENTITY_CHECK_REQUEST_20261019.md. Its distinct attempt still needs explicit authority.
Only M0 is fully accepted. M3 remains terminally blocked. M6 remains zero of ten actual sessions.
Strata stayed off. No security change, broker action, or service ran.
See [today's report](../reports/DAY_PROGRESS_20261019.md).

Earlier entries below retain their original evidence and dates.

## Saved review plans verified in source - 19 October 2026

The new storage attempt passed in 116.543130 seconds. No permission change was needed.
All 58 source tests passed, with zero failures, errors, or skips. Independent review round 3 is clear.
Both successful jobs observed exit 0 and left zero children. All failed attempts remain preserved.
The saved review-plan connection now has source verification. Registration and automatic dispatch remain unfinished.
The nine-page project map is refreshed and checked. Paper operation and financial qualification remain blocked.
Only M0 is fully accepted. M6 remains zero of ten actual supervised sessions. Strata stays off.
See [the verified source report](../reports/AI_REVIEW_VERIFICATION_20261019.md).

Earlier entries below retain their original evidence and dates.

## Capacity access failure blocks verification - 19 October 2026

The single prepared capacity attempt failed in its initial folder count.
Windows denied access to `.cache/test-runs/m5-posted-fees-20261017-01/posted-source2-part29`.
The job took 1.588822599966079 seconds, started no child, and left zero children.
Its failed closure remains preserved. No full census, source test, or retry ran.
The five relocated evidence files match their saved sizes and hashes.

Three preparation repairs passed independent static review and remain untested.
They preserve existing test folders, check preparation folders, and mark wrapper exceptions as failures.
The consumed generated wrapper and job remain unchanged.
The saved review-plan component still has no passing revised test result.
Fresh source counts are 0 passed, 0 failed, 0 errors, and 0 skipped because tests did not run.

This turn uses a restricted workspace context. Earlier Full access statements are historical.
No permission change, broker action, publication, or PDF-generation job ran. Strata stayed off.
The PDF refresh is blocked and the old PDF is not current for this result.
M6 remains zero of ten actual supervised sessions. That requirement cannot finish by tomorrow.
Next, resolve folder read access and obtain authority for a distinct, reviewed capacity attempt.
Do not reopen consumed attempts or change security rules without the required authority.
See [the batch report](../reports/AUTONOMOUS_BATCH_20261019.md) and [pending diagram changes](PROJECT_MAP_PENDING_20261019.md).

The sections below preserve earlier states.

## Saved review plans implemented; verification blocked - 18 October 2026

The accepted-proposal connection is implemented but has no passing test result yet.
The expected failing test recorded 0 passes, 1 failure, 0 errors, and 0 skips before implementation.
The test wrapper wrote its final result without reserving space first.
The evidence folder exceeds its 8 MiB limit by 12,288 bytes. All evidence remains intact.
Further jobs are stopped. A reviewed evidence allocation must precede fresh tests and the diagram refresh.
Full access remains enabled, and Strata stays off.
See [the report](../reports/AI_REVIEW_PLAN_STORAGE.md) for the implementation, review, and remaining checks.


## AI proposal translation verified - 18 October 2026

The roadmap now has a proposal-to-settings translation component for review only.
Source tests passed 29 cases, with zero failures, errors, or skips. Independent code review found no blocking issue.
It keeps all twelve variants and fixed synthetic settings. Registration and automatic dispatch remain unfinished.
Full access stays enabled. The earlier permission-change proposal is superseded by owner direction.
M5 pipe work remains blocked. No security change, full scan, saved-stop change, or broker action ran.
Strata stayed off. See [the component report](../reports/AI_EXPERIMENT_TRANSLATION.md).
Next, connect accepted manual receipts to bounded saved review plans and proposal history.


## Launch-context correction reviewed - 18 October 2026

The failed pipe attempt inherited this chat's Full access context. Its launcher did not remove an AppContainer identity.
Saved Codex defaults specify workspace-write, but this chat's recorded permission profile disables sandboxing.
The smallest proposed fix changes only this chat to Ask for approval, then checks the exact pinned identities first.
Independent review accepted that proposal. Thirteen artifact and configuration checks passed, with zero failures or skips.
No permission changed. No new native check, full scan, or experiment ran.
A setting change alone does not prove that the earlier identity returns.
The prepared approval covers the session change and one bounded query-only identity check, with zero retries.
It excludes pipe creation, access grants, production changes, and broker actions. Strata stays off.
See [the diagnosis and review](../reports/M5_PIPE_LAUNCH_CONTEXT_REVIEW.md) and [the exact approval](M5_PIPE_LAUNCH_CONTEXT_PLAN.md).

## Approved pipe attempt stopped at identity check - 18 October 2026

The fresh storage check passed. The single pipe attempt failed with `APPCONTAINER_REQUIRED`.
The launched process lacked the required Windows isolation identity.
The runner stopped before creating its client or pipe. No pipe permission changed.
Storage passed in 88.753094 seconds. The pipe job stopped in 19.795012 seconds.
Both jobs observed child exit and left zero children. No retries ran.
All six older evidence files and all 16 prepared source bindings remain unchanged.
Paper trading and unattended production work remain blocked. Only M0 remains accepted.
The approved attempt is consumed. A new launch context and attempt require review and explicit authority.
No production change or broker action ran. Strata stayed off.
See [the execution report](../reports/M5_PIPE_EXPERIMENT_EXECUTION.md).

## Disabled communication experiment prepared - 18 October 2026

The two-process experiment is prepared and remains disabled.
Final source verification passed 132 checks, with zero failures, errors, or skips.
Its bounded job passed in 15.966749 seconds, observed exit 0, and left zero children.
Independent review round 3 accepted preparation with no blocking finding.
The earlier failed fake-test run remains preserved.
The exact temporary-pipe request adds only the observed application identity with access mask 0x00100083.
The five experiment files use 128 KiB inside the existing preparation allowance.
Full conservative commitments leave 45,056 bytes in the proposed evidence folder.
Security approval and fresh complete storage evidence remain required before native execution.
No pipe, permission change, full scan, saved-stop change, or broker action ran. Strata stayed off.
See [the preparation report](../reports/M5_PIPE_EXPERIMENT_PREPARATION.md).

## Pipe identity observed - 18 October 2026

The observer and parent share an unpackaged AppContainer identity at integrity level 4096.
The bounded observation passed in 25.735736 seconds, with exit 0 and zero remaining children.
No pipe was created. Windows pipe access and launcher namespace eligibility remain unverified.
The evidence folder uses 86,016 charged bytes. Conservative full commitments leave 45,056 bytes.
Independent review accepted observation only. No new source or broker tests ran.
Next, prepare the disabled experiment runner and resolve its namespace choice and exact evidence bindings before requesting permission.
See [the identity review](../reports/M5_PIPE_IDENTITY_REVIEW.md).
Strata stayed off. No permissions, saved stops, or broker state changed.



## Disabled pipe helper verified - 18 October 2026

The pipe helper now prepares review text and always refuses native execution.
All 42 source checks passed, with 0 failures, 0 errors, and 0 skips.
Its bounded job passed in 26.744591 seconds and left zero children.
Independent code review found no blocking issue. Windows pipe access remains unverified.
The proposed five-file output ledger totals 128 KiB within the existing preparation allowance.
It is not an active storage reservation or permission grant.
See [the helper report](../reports/M5_PIPE_POLICY_HELPER.md).
No full storage scan, permission change, saved-stop change, or broker action ran. Strata remained off.


## Pipe repair proposal reviewed - 18 October 2026

The proposed repair adds one verified application identity to one temporary test pipe.
Independent review found no blocking design issue. The repair is not applied.
The default pipe rules, runtime source, limits, permissions, and saved stops remain unchanged.
The next step is a disabled isolated helper, pure policy tests, and a fixed evidence ledger.
Creating a pipe with changed access rules requires separate approval.
Pipe-name requirements and native access remain unverified. No new tests or full storage scan ran.
See [the proposal](M5_PIPE_REPAIR_PLAN.md) and [independent review](../reports/M5_PIPE_REPAIR_REVIEW.md).
Strata remains off. No broker action ran.


## Full storage check passed - 18 October 2026

One authorized full storage check passed without a retry.
The scan took 71.160717 seconds. The complete job passed in 104.068814 seconds and closed all children.
The check included the new 8 MiB evidence allowance within unchanged category and total limits.
It examined 59,287 directories, 220,813 files, and 4,480 links.
It found zero unknown entries, access barriers, or ledger failures.
This check did not run broker tests or accept a roadmap milestone.
See [the storage report](../reports/M5_EVIDENCE_STORAGE_CHECK.md).
Strata remained off. Permissions and saved stops remained unchanged.


## Child output repairs verified - 18 October 2026

Both child programs now use the checked clock-file location.
Child failure records use the existing 16 KiB cleanup allowance and cannot replace existing evidence.
The fresh source run passed 31 checks, with zero failures, errors, or skips.
Independent review found no remaining issue in these two repairs.
The prepared programs remain disabled. The proposed folder remains inactive.
See [the repair report](../reports/M5_CHILD_OUTPUT_REPAIR.md).
No full scan, permission change, saved-stop change, or broker action ran. Strata remained off.

## Evidence folder code needs two repairs - 18 October 2026

The new writers enforce file limits and reserve failure records.
Disabled adapters preserve the existing folder checks and add the proposed 8 MiB allowance.
The final source run passed 25 checks, with zero failures, errors, or skips.
Independent review found two remaining child-output integration gaps.
The child helpers still require the old clock path and write one unbounded failure file.
The proposed folder remains inactive. No full storage scan or broker stage ran.
See [the implementation report](../reports/M5_EVIDENCE_FOLDER_IMPLEMENTATION.md).
Strata stays off. Existing limits, evidence, permissions, and saved stops remain unchanged.

## Windows pipe restriction identified - 18 October 2026

The isolated diagnostic runs inside Windows AppContainer, a restricted application environment.
The pipe grants the user and logon identities, but lacks a matching application or capability grant.
Windows AccessCheck and the actual client open both deny access.
The final diagnostic completed in 50.778809 seconds and closed all children.
Earlier diagnostic jobs 03 and 04 failed. Their evidence remains preserved.
Nine source helper checks passed, with zero failures, errors, or skips.
No permission change, alternate security context, full scan, or broker stage ran.
The original failed supervisor token was not captured. These observations establish the current isolated restriction.

A prepared allocation proposal adds an 8 MiB evidence folder within the unchanged 5 GiB records category and 50 GiB total.
Its forecast is 8,261,632 bytes. It preserves all existing folder caps and evidence.
The proposal is not active. Wrapper, census, output bindings, and fresh capacity admission remain prerequisites.
Independent preparation review round 3 closed without remaining findings. See reports/M5_PIPE_PREPARATION_REVIEW.md.
The stopped sequence remains closed. Keep Strata off and saved stops intact. Only M0 is accepted.
See reports/M5_PIPE_AND_EVIDENCE_PREPARATION.md and docs/M5_EVIDENCE_FOLDER_PROPOSAL.json.


## Storage passed; simulated startup failed - 18 October 2026

The owner requested autonomous local progress. The agent ran the reviewed storage check and then the existing simulated sequence.
Two full storage checks passed in 104.739527 and 101.633859 seconds, within unchanged limits.
Independent review cleared the storage package and completed result.
The source history test reported zero passes, one failure, zero errors, and zero skips.
Windows refused the supervisor's local pipe connection with `NATIVE_CALL_FAILED:CreateFileW:5`.
The first managed worker did not start. The remaining nine stages did not run.
The sequence stopped without retry. All child processes closed.
An isolated diagnostic reproduced the access denial without starting owners or changing permissions.
Its process token had zero restricted SIDs. The complete cause remains unproven.

Stopped preservation verified 133 files and 195 entries. The attempt guard remains at zero.
The final named audit matched 61 frozen inputs and 247 source and 247 installed product files.
These hash checks do not qualify the complete environments.
One incorrectly prepared audit failed. A separate corrected audit passed. Both records remain preserved.
The earlier 43-case source and 61-case helper results remain historical.

Exact next action: identify the Windows access check that rejects the isolated pipe client.
Independent result review round 2 verified the stopped result. Both launcher review rounds are closed.
The latest diagnostic closure left 385,024 bytes in the record folder. The next history forecast needs 524,288 bytes.
Both access diagnosis and a reviewed evidence-storage plan are prerequisites for another broker stage.
Do not restart the failed sequence, relax permissions, or clear saved stops.
Keep all storage, deadline, memory, processor, retry, and financial limits unchanged.
Keep Strata off. Only M0 is accepted. No actual broker action occurred.
See reports/M5_STORAGE_AND_SIMULATED_RESUMPTION.md for results and evidence.
The sections below retain earlier states and do not replace this current status.

## Storage check preparation - 18 October 2026

The owner requested diagnosis, a bounded candidate, and independent review without another full scan.
The parent spends 13.512762 seconds on its initial folder count before child startup.
Less than 106.487238 seconds remain for startup, a census capped at 110 seconds, and final parent checks.
Repeated parent counts also overlap the child. The last failure did not save its final child phase.
These facts explain the restricted time budget. They do not isolate every cause of the slowdown.

Separate disabled candidates remove repeated ZIP membership work and repeated file-charge sums.
They add bounded phase records, retain original timer start points, and save child exit before final checks.
The active wrapper, census, product files, profiles, and limits remain unchanged.
Both prepared programs refuse execution before imports or writes.

The final preparation set passed 43 source cases, with zero failures, errors, or skips.
Its wrapper passed in 44.699596 seconds and closed every child process.
Fresh byte checks matched 247 product files in each source and installed location.
The verifier matched 24 old evidence pins and 135 original file hashes. The attempt guard remains at zero.
No original database connection, installed-package test, complete environment check, full census, or broker stage ran.

The initial missing-helper failure and the later verifier failure remain preserved.
One fixture verifier exceeded its job memory while reading the reserve. Its result name also collided with an existing review record.
A separately named repair passed with 1 MiB hash reads and unchanged resource limits.
Independent preparation review round 2 cleared the corrected candidate for owner review.
Both review rounds are closed. The review grants no full-scan or broker-stage execution.

Storage admission remains blocked. The earlier full retry remains used.
Exact next action: review the disabled candidate before a separate full-scan execution decision.
Keep Strata off. Do not clear saved stops or take broker actions.
See reports/M5_STORAGE_CHECK_PREPARATION.md and docs/M5_STORAGE_CHECK_PREPARATION.md.

## Storage check timeout repair - 17 October 2026

The owner approved a targeted repair and one new bounded capacity retry.
This instruction replaces the earlier instruction to request another capacity attempt.
The one approved full retry is now used. Storage admission remains blocked.

The maintenance wrapper now shares each fresh file observation across overlapping capped folders.
It keeps all 28 folder limits and explicit current metadata checks.
It checks host memory and the original job deadline during each scan and after the final scan.
Product storage admission, software versions, test identities, and financial rules remain unchanged.

Thirteen final small fixture checks passed, with zero failures, errors, or skips.
Their final wrapper passed in 29.628102 seconds and left zero child processes.
It also checked actual name spelling for file and directory calls.
The first wrapper reached 120.000295 seconds and closed all child processes.
Both the helper code and sandbox context changed between those attempts.
The timing difference does not identify one cause by itself.

Independent repair review round 2 cleared the concrete retry.
The full retry reached JOB_DEADLINE after 120.006721 seconds and closed all child processes.
It produced no complete census result or saved partial traversal counts.
Host memory checks had a maximum interval of 0.669146 seconds.
The minimum observed available host memory was 33.908875 GiB.
All ten simulated broker stages remain unrun. No new complete environment check ran.
The agent stopped dependent stages and preserved the failed retry.
No additional full scan is approved.
Exact next action: prepare a separate bounded proposal to reduce full census work.
Keep Strata off. Do not clear saved stops or take actual broker actions.
See reports/M5_STORAGE_TIMEOUT_REPAIR.md and docs/M5_STORAGE_TIMEOUT_REPAIR.md for evidence, the checklist, and unchanged limits.

## Simulated broker clock - 17 October 2026

The owner approved a test clock for the simulated broker.
This instruction replaces the earlier requirement to wait for actual market times for these simulated tests.
Keep real-broker rules, actual timeouts, evidence, storage limits, and saved stops unchanged. Keep Strata off.

The final source and installed-package helper checks each passed 61 cases, with zero failures, errors, or skips.
Both runs closed all child processes. All earlier failed checks remain preserved.
The clock changes only market timestamp functions inside test helpers. Product files remain unchanged.
Independent review round 3 cleared the code, all ten revised plans, and all 689 frozen inputs.
The first full storage check reached CENSUS_110_SECOND_DEADLINE before completion. No broker test owner started.
The one capacity retry also reached JOB_DEADLINE. Both failed jobs closed all child processes. No further retry is planned.
The ten full simulated broker stages remain unrun. Actual broker authority remains false.
Both fresh complete environment checks also reached JOB_DEADLINE. Both observed exit and closed all child processes.
The passing helper runs verified 247 product files in each environment. Complete environment verification remains incomplete.
Stopped preservation passed with 135 files, 197 entries, and zero changed original files.
The final evidence audit passed. It verified guard sequence zero and unchanged 11/9 histories per owner.
Independent review round 3 is closed with no actionable code findings. It does not accept the unrun broker stages.

Use docs/M5_SIMULATED_CLOCK_PLAN.md for acceptance, limits, and the current work checklist.
Preserve the earlier real-clock plans and results as historical evidence.
Only M0 is complete and accepted. M5 and its actual broker requirements remain incomplete.

## Local risk and controlled dispatch - 17 October 2026

Local implementation and verification are complete. The approved local finish plan remains blocked on the combined native rehearsal.
Source and installed inventories each passed 285 distinct cases, with zero failures, errors, skips, or remaining children.
The source total contains 257 fresh cases and 28 unchanged cases with verified code and imported test files.
All 285 installed cases are fresh. Both complete environments passed byte verification; the installed environment passed again after testing.
The frozen package contains 247 files. It installed offline with unchanged locked tools and dependencies.

Current risk, exact consumption, original-source outcome reconciliation, and the finite closing parent are implemented.
All final product source reviews and native preparation review are clear at 3 of 3. Keep their counters closed.
The 29 helper cases are included in each inventory. Earlier failed checks, scripts, and original receipts remain preserved.
Ten native stages and ten preceding capacity jobs are frozen. Ten current-date checks refused before starting owners.
No positive combined native stage has run. Actual native timing fit and native component halt remain unverified.

Use `.cache/test-runs/native-economic-fresh-20261017-01/native-shared` only.
Its project identity remains `266b470c104c6b122e2db6d48a7c5946037235feae781ce2a808bda5010f4e39`.
The first opening, original sources, source beginnings, credential slot, and allocated reserve remain intact.
A fresh stopped archive passed verification. The external attempt guard remains at zero; the order source still contains only its original beginning.
There are 11 account records and nine activity records per owner. The planned sequence ends at 29 and 27, within separate limits of 32.

Both HISTORY stages must finish before 09:25 New York on Monday, 19 October 2026.
Buying requires 09:35 or later and strictly before 10:05. Do not substitute clocks or create an automatic delayed launch.
Then verify restart with holdings and open orders, exact cancellation, resolved outcomes, bounded closing, and native component halt.
Finish flat and disarmed, verify complete environments, and preserve the stopped project again.

Fresh complete storage admission passed. Scratch has 87,127,968 bytes left after all recorded holds.
Backups have 488,257,568 bytes left. Limits remain 15 GiB scratch, 21 GiB backups, and 50 GiB total.
No additional full native project or GiB reserve was created. Strata stays off.
Only M0 is accepted. M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions.
See reports/M5_LOCAL_RISK_DISPATCH.md, docs/M5_NATIVE_REHEARSAL_PLAN.md, and docs/LOCAL_FINISH_CONTINUATION_PROMPT.md.

## Earlier native economic continuation - 17 October 2026

The owner approved 15 GiB test scratch and one additional 1072 MiB native folder.
Fresh complete storage admission passed. Backups stay 21 GiB; total storage stays 50 GiB.
Both original journals existed before the new project's first account observation. All earlier identities and evidence remain preserved.

Source and installed economic checks each passed 229 distinct cases, with zero failures, errors, or skips.
Each inventory contains 226 in-process cases and three native stages, including shutdown.
They check original source qualification, changed-source refusal, and restart without restored freshness.
Both complete environments passed byte verification. The frozen package contains 238 product files.
Economic final review is clear at 3 of 3. Its two findings were reproduced and repaired without resetting the counter.
The repairs close source process handles on terminal reads and freeze calculator arguments before callbacks.
Gate 2 remains open for future controlled order history and its remaining integration.

The native run exposed a shutdown defect in the recent backup-sharing change.
The repair passed 61 matching source and installed checks and independent shutdown review 1.
Both failed native attempts have verified archives. The continuing native project is stopped without a retained watchdog halt.

Next, finish economic verification, risk, durable dispatch and recovery, and the installed combined rehearsal.
The accepted plan retains real owner clocks and operation windows.
Historical inputs must finish before 09:25. Native buying requires 09:35â€“10:05 New York on an eligible exchange day.
The next eligible day is Monday, 19 October.
Complete independent code and tests before stopping for that external timing condition.
M5 gates 2 through 5 remain open. M6 stays zero of ten actual supervised sessions. Only M0 is fully accepted.
See reports/M5_NATIVE_ECONOMICS.md. Strata stays off.

## Storage sharing - 17 October 2026

Storage sharing passed 58 matching source and installed-package checks, with zero failures, errors, or skips in each inventory.
The installed run reused existing dependencies and verified its frozen package bytes before and after tests.
This is component verification. It does not accept a full isolated environment, a GiB reserve, or native economic qualification.

New recovery sets share independently copied bytes for the same unchanged artifact identity and hash.
Sharing records precede coordinator snapshots, so reuse survives restoration of the first set.
Different identities keep separate paths. Snapshots, manifests, original evidence, failures, reserves, halts, and storage checks remain intact.
This task changed no limits and created no full native project or GiB reserve.

Another task had already activated its separately approved 15 GiB test profile and created the economic project.
Use that existing project only where original history, identity, storage admission, and process closure permit sharing.
Plan economics, risk, dispatch, supported recovery, and installed rehearsal as one compatible sequence.
Keep destructive or incompatible cases separate. Do not raise limits to run them.
See docs/STORAGE_SHARING_PLAN.md and reports/STORAGE_SHARING_VERIFICATION.md for the exact scope and next action.
Historical checkpoint sections below retain their original status and approvals. Strata stays off.

## Earlier economic preparation and approval boundary - 17 October 2026

**Economic preparation is verified. Native qualification and the approved local finish plan remain incomplete.**
Source and installed checks each passed 54 distinct in-process cases, with zero failures, errors, or skips.
Each inventory contains 35 calculation cases and 19 controlled journal cases. No economic native case has passed.
Both complete environment byte checks passed. Independent preparation review 2/3 is clear; final native review 3 remains unused.

The calculation checks linked fees, reversals, cash, and covered asset identity. It grants no source or broker authority.
The test source retains events and acknowledged coverage times across reopening. It rejects files with multiple hard links.
All 232 earlier product files remain unchanged. One unqualified calculation module was added.

The existing native project lacks original fee accruals, payment links, and a complete action calendar.
Its fixed replies cannot prove that missing history. Its first opening and credential slot remain immutable.
Positive native verification needs another project, with its source created before its first account observation.
The approved one-folder allowance is already used. No second folder or reserve has been created.

Active test scratch remains 14 GiB. The measured request is 15 GiB and one additional 1072 MiB native folder.
Backups remain 21 GiB; total storage remains 50 GiB. Preserve all original runtimes, reserves, halts, and failed results.
Next, obtain that specific decision, then require fresh complete capacity admission before native implementation and verification.
Then finish current-input risk, durable dispatch and recovery, and the installed combined local rehearsal.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
Strata stays off. See reports/M5_LOCAL_ECONOMIC_PREPARATION.md for evidence and the exact measured request.

## Earlier posted-fee verification - 17 October 2026

**Posted-fee engineering is locally verified. The approved local finish plan remains incomplete.**
Source and installed inventories each passed 238 distinct cases, with zero failures, errors, or skips.
Each contains 236 in-process cases and two native Windows stages. Both complete environment byte checks passed.
Native stages use real Windows owners and invented local replies.
Final posted-fee review 3/3 is clear. Posted-fee, declared-fee, and infrastructure review rounds are closed.

The calculation preserves original cash and signed USD fee rows. Matching cash does not establish billing or unpaid liabilities.
The new calculation accepts bounded inputs above 64 KiB. The existing parser retains its original limit.
All four native stages passed in the same approved folder. Its original project and allocated reserve remain unchanged.
The stopped runtime has a fresh verified archive. The failed posted-fee attempt also has a complete retained archive.
The test helper now checks proof phases during explicit status calls. Publication acknowledgement remains passive.
The first failure's cause remains unproven. Both older halted runtimes remain preserved and stopped.

The installed test output needed 80 MiB. A fresh complete measurement admitted that hold before installed tests.
Test scratch stays 14 GiB, backups 21 GiB, and total storage 50 GiB. Published program limits remain unchanged.

Next, implement local fixture fee liabilities and action evidence under M5_LOCAL_ECONOMIC_EVIDENCE_PLAN.md.
Its design review 1 is complete. Derive facts from complete original fixture records; do not assume zero liabilities.
Then finish current-input risk, durable dispatch and recovery, and the installed combined local rehearsal.
Actual billing and provider action coverage remain unverified. Financial and actual broker authority remain false.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, master stop, failed evidence, reserves, and terminal M3 history remain preserved. Strata stays off.
See M5_POSTED_FEE_CONTEXT.md for exact results and local evidence paths. Keep Hub results separate from these inventories.

## Earlier declared-fee verification - 17 October 2026

**Declared-fee engineering is locally verified. The approved local finish plan remains incomplete.**
Source and installed inventories each passed 260 distinct cases, with zero failures, errors, or skips.
Each contains 258 in-process cases and two native Windows stages. Both complete environment byte checks passed.
Final fee review 3/3 is clear. All declared-fee and infrastructure review rounds are closed.

The owner approved 14 GiB test scratch for one fresh native folder. Backups remain 21 GiB; the total remains 50 GiB.
Fresh complete capacity admission passed before creation. Published program limits and all 230 package files are unchanged.
The new folder has its own project and fully allocated one GiB reserve. Four separately frozen native stages passed.
They verify original declared inputs, calculator calls, single-use proofs, and no restored freshness after restart.
The stopped successful runtime has a verified 85-file preservation archive. It has no watchdog halt.
Both older failed native attempts and retained halts remain preserved. Never clear or resume those halted folders.

Acceptance covers declared-fee engineering only. Actual billing coverage, account applicability, and unpaid liabilities remain unverified.
Next, implement posted fee observations against original account activity under M5_POSTED_FEES_PLAN.md.
Its measured allocation retains the existing native folder; it creates no additional native reserve.
Then finish liability and action qualification, risk, durable dispatch/recovery, and the installed combined rehearsal.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, master stop, failed fixtures, reserves, and terminal M3 history remain preserved. Strata stays off.
See the declared-fee report and the posted-fee plan for exact evidence and the next bounded step.

## Earlier helper repair and storage pause - 17 October 2026

**The fee test helper is repaired. Native fee qualification remains blocked by a retained storage halt.**
Source and installed inventories each contain 258 distinct passing in-process cases, with zero failures, errors, or skips.
They include 256 unchanged cases and two new storage regression cases. Both refreshed complete environment checks passed.
The repair reserves and publishes the fee reference through checked artifact storage. All 230 product package files are unchanged.

The earlier process inspection condition cleared. A separately recorded attempt then passed startup and published its local account observation.
The watchdog stopped it for `UNACCOUNTED_GROWTH` from a new unreserved reference file. The halt remains intact.
Its complete verified archive retains 403 files. Never clear or resume that stopped runtime.
Both native failed attempts remain failed. No native fee stage is accepted. The first pipe failure's cause remains unproven.

The fresh folder needs 1072 MiB. The current 12 GiB scratch limit cannot admit it; 13 GiB is also insufficient.
The measured 14 GiB proposal leaves 1,037,624,944 scratch bytes. Backups stay 21 GiB, and the total stays 50 GiB.
Owner approval remains pending. No limit has changed, and no fresh folder or reserve has been created.
Infrastructure review 3/3 is clear. Fee final review 3 remains unused. Earlier review counters stay closed.

Next, resolve that specific storage decision and require fresh complete admission before creating the separate native fixture.
Then finish native fee verification, billing and actions, risk, durable dispatch/recovery, and the installed integrated rehearsal.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, master stop, failed fixtures, reserves, and terminal M3 history remain preserved. Strata stays off.
See [the current report](../reports/M5_NATIVE_FEE_CONTEXT.md) and [the concrete recovery request](M5_NATIVE_FEE_FIXTURE_RECOVERY_PLAN.md).

## Earlier fee checkpoint - 16 October 2026

## Current fee work and native blocker

16 October 2026. **Declared-fee checks passed in-process; native qualification is blocked.**
Source and installed checks each passed 256 matching distinct in-process cases, with zero failures, errors, or skips.
Both complete environment byte checks passed. Fee reviews 1 and 2 are used; final review 3 remains unused.
The private fee context binds original fills and retained declarations. Actual billed fees and liabilities remain unknown.
The earlier current-cost component retains its separate 53 accepted cases per environment. Do not sum overlapping inventories.

The first source native fee stage failed before account collection: zero passed, one failed, zero errors or skips.
The closed pipe does not establish the child's original exit reason. That first failure's cause remains unproven.
Windows currently denies the required inspection of saved evaluation process ID 31756, including a narrower read.
The existing owner-exit check must refuse reuse. The original failed runtime has a complete verified preservation archive.
No owner identity, exit check, permission, service, or failed result was changed. The blocked runtime must not resume.

A fresh native folder needs 1072 MiB. The measured 12 GiB scratch limit cannot admit that hold.
The prepared request raises scratch to 14 GiB. Backups stay 21 GiB, and the total stays 50 GiB.
This is a pending owner decision. No new native folder or reserve has been created, and no limit has changed.
Finish native verification only after that decision and a fresh complete capacity check.

Fee billing, corporate actions, current-input risk, durable dispatch/recovery, and the installed integrated rehearsal remain open.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
The original environment, saved stops, failed fixtures, reserves, and terminal M3 history remain preserved. Strata stays off.
No actual broker action occurred. See [the fee report](../reports/M5_NATIVE_FEE_CONTEXT.md) and [the recovery request](M5_NATIVE_FEE_FIXTURE_RECOVERY_PLAN.md).

## Earlier current-record cost checkpoint

14 October 2026. Work resumed. **The M3 Final passed, but its installed-package independent audit lost its exit receipt. It cannot be accepted or retried.** The cause of the interruption is unknown. No current test process was found. Use supported closure only, preserve the failed attempt and continue genuinely independent work. Master and GitHub remain the working/published checkpoints. **Do not start Strata.**

## Active checkpoint

16 October 2026. **Position costs from current original records are locally verified.**
Source and installed checks each passed 53 matching distinct cases, with zero failures, errors or skips.
Each inventory includes 51 in-process cases and two native Windows stages.
Both final complete environment checks passed. Independent review round 3 is clear; all three rounds are used.

The new private context binds the original account, opening, complete history, portfolio and native activity records.
Supported recorded-fill costs must match. Unsupported histories remain blocked after closing and reopening.
Fees, corporate actions, risk, durable dispatch and the installed integrated rehearsal remain open.
M5 gates 2-5 remain open. M6 remains 0/10 actual supervised sessions. Only M0 is fully accepted.

The final maintenance census passed in 44.6748 seconds under the unchanged 110-second measurement bound.
Its parent Job closed in 48.1994 seconds with zero remaining children.
Scratch has 4,146,112 bytes left after holds. Backups have 924,473,376 bytes left.
Scratch remains 12 GiB, backups 21 GiB and the total 50 GiB.
Production scans retain 30 seconds and their 35-second freshness rule.

The first installed native attempt remains failed. Its original runtime and sidecars have a verified preservation archive.
One existing acknowledgement was recovered without another account request or changed activity identity.
A separate instrumented test passed. Its 4.8145-second acknowledgement has little margin under the unchanged five-second limit.
The original failure's cause remains unproven. Historical failures do not enter passing counts.

Next, bind declared fee calculations to original current fills under the reviewed fee-context plan.
Then qualify fees and actions before risk, durable dispatch and the installed local rehearsal.
The failed fixtures, saved stops, original environment and terminal M3 audit history remain preserved.
No actual broker action occurred. Strata stays off.

See [the exact current cost report](../reports/M5_POSITION_COST_CONTEXT.md).

### Resolved storage pause

16 October 2026. **The next accounting increment is blocked at its storage check.** The census stopped after 70.0017 seconds. It counted 99,181 files but produced no complete capacity measurement. Its Job exited 1 with zero remaining children. No position-cost test folder, product test or package build started.

A separate 20-second diagnostic counted 30,218 files. It recorded file-check timing but did not establish one cause. Its Job closed successfully. That diagnostic grants no capacity admission. A busy `bf6` process coincided with the slowdown. Memory remained above the required floors. No other program was stopped.

The original comparison remains verified across 301 matching distinct cases per environment, with zero failures, errors or skips. Both complete byte checks and separate final reviews passed. Its published code checkpoint is `0cae4b5`. Master, GitHub and the requested clone matched that checkpoint. The failed fixture, saved stops, original environment and terminal M3 audit history remain preserved. Strata stays off.

Exact next action: require a measured external-load change, a diagnosed repair or scoped authority for another admission attempt. Then run one instrumented capacity check within the existing bounds. Keep scratch at 12 GiB, backups at 21 GiB and the total at 50 GiB. The prepared retry has not run. M5 gates 2-5 remain open. M6 remains 0/10 actual supervised sessions. Only M0 is fully accepted.

See [the exact blocker](../reports/M5_LOCAL_FINISH_BLOCKER.md) and [the bounded follow-up](M5_STORAGE_GATE_FOLLOWUP.md).

### Earlier verified comparison checkpoint

16 October 2026. **The original order and fill comparison is locally verified.** The accepted inventory has 301 matching distinct cases per environment. Failures, errors and skips are zero. It includes 71 calculation cases, 192 compatibility cases, 36 private-context cases and two native Windows stages per environment.

Both complete environment byte checks passed. The calculator and context each completed three independent review rounds. Both final reviews are clear. The isolated closed-database repair passed three focused checks per environment. Valid earlier cases are reused under recorded change comparisons.

The native checks used an invented account opening and local HTTP replies. The passing runtime stayed at its original path after a verified preservation archive. Its project and allocated reserve identities remain unchanged. The failed fixture, master stop, original environment and terminal M3 audit history remain preserved. Strata stays off.

The final census passed. Scratch has 40,286,760 bytes left after recorded holds under its 12 GiB ceiling. Backups have 1,041,917,984 bytes left under 21 GiB. The total stays 50 GiB.

Exact next action: define and freeze the next missing accounting producer. Fee liabilities, corporate actions and full position costs remain unverified. Then continue risk, durable dispatch and the integrated installed rehearsal. M5 gates 2-5 remain open. M6 remains 0/10 actual supervised sessions. Only M0 is fully accepted.

See [exact comparison evidence](../reports/M5_OWNERSHIP_COMPARISON.md).

### Earlier native activity checkpoint

16 October 2026. **The native activity producer is locally verified.** Source and installed checks each passed 271 matching cases. Failures, errors and skips are zero. Each inventory includes four native Windows stages and 267 pure or in-process cases. Both complete environment byte checks passed. Final independent code review round 3 is clear; all three rounds are used.

The producer binds the original account context, immutable opening, complete local history and credential identity. Native loopback checks cover collection, lost replies, encrypted publication, restart, cancellation and historical reopening. The account opening is invented test evidence. These checks grant no ownership, economic, risk or broker-write authority.

The owner approved 12 GiB scratch and 21 GiB backups under the unchanged 50 GiB total. The final census passed. Scratch has 141,360,336 bytes left after recorded holds. Backups have 1,074,264,096 bytes left. Both native fixture reserves and the failed fixture's halt remain preserved. The saved master stop, original environment and terminal M3 audit failure remain preserved. Strata stays off.

Exact next action: freeze the ownership and economic reconciliation cases against the immutable opening, complete history and native observations. Then complete risk, durable dispatch/recovery and the integrated local rehearsal in dependency order. M5 requirements 2-5 remain open. M6 remains 0/10 actual supervised sessions.

- [x] Verify the bounded native activity producer and encrypted historical evidence.
- [x] Verify matching source/installed cases and complete environments.
- [x] Verify native lifecycle, capacity and final independent review.
- [ ] Complete ownership/economics, risk, durable dispatch and the integrated rehearsal.

See [the exact native activity evidence](../reports/M5_NATIVE_ACTIVITY_PRODUCER.md).

### Earlier activity-parser checkpoint


16 October 2026. **Native retained records and the activity parser boundary are verified.** The combined inventory has 371 matching unique source/installed cases per environment. Failures, errors and skips are zero. It includes 99 new pure activity cases and 272 unchanged component cases. Both latest complete environment byte checks passed. Each dependency completed independent review round 3.

The parser fixes the original query and cursor chain. It preserves exact fill times and keeps missing native, ownership, fee, action and economic evidence blocking. No native activity producer, risk admission or actual dispatch is claimed.

The final census passed in 44.709 seconds. Scratch has 309,710,856 bytes left after a 128 MiB hold. Backups have 1,074,264,096 bytes left under the approved 21 GiB ceiling. Another 1 GiB native fixture exceeds scratch headroom by 764,030,968 bytes. The 11 GiB scratch decision remains pending. The 50 GiB total and emergency reserve remain unchanged.

Exact next action: resolve that allocation, then implement and qualify the private native activity producer. Continue ownership/economics, risk, durable dispatch/recovery and the installed local rehearsal in dependency order. M5 requirements 2-5 remain open. M6 remains 0/10 actual sessions. The saved master stop and terminal M3 audit failure remain preserved. Strata stays off.

- [x] Verify disjoint retained native records and complete external-history observations.
- [x] Verify the separate activity request, parser and exact timestamp boundary.
- [x] Verify matching cases, complete environments, capacity and independent reviews.
- [ ] Resolve the native fixture's pending scratch allocation.
- [ ] Complete native activity, ownership/economics, risk, durable dispatch and the integrated rehearsal.

See [exact current evidence](../reports/M5_ACTIVITY_BOUNDARY.md).


### Earlier native-record checkpoint

16 October 2026. **The native retained-attempt dependency is verified.** The accepted composite contains 272 matching unique source/installed cases per environment. Failures, errors and skips are zero. Both complete environment byte checks passed. Independent review round 3 is clear and all three rounds are used for this dependency.

The external guard preserves native write records separately from fake execution and preparation. Fake status and economics exclude native records. The portfolio reader now checks external retained history after an older SQLite restore. The first opening stays unchanged. Financial and transport authority remain false.

The owner approved a 21 GiB backup ceiling under the unchanged 50 GiB total. The full census passed in 45.262 seconds. Backup headroom is 1,074,264,096 bytes. Scratch headroom is 321,240,632 bytes after a 128 MiB additional hold. The saved master stop, original environment, emergency reserve and terminal M3 audit history remain preserved. Strata stays off.

- [x] Verify disjoint native retained records and fake-history separation.
- [x] Repair and verify complete external-history observations after an older restore.
- [x] Verify matching case inventories, complete environments and independent review.
- [x] Apply the approved backup ceiling and verify complete capacity.
- [ ] Verify the small activity protocol boundary and qualified native activity producer.
- [ ] Complete ownership/economics, risk, durable dispatch/recovery and the integrated local rehearsal.

Exact next action: freeze and execute the inert activity-request, parser and traversal cases within current capacity. The separate 11 GiB scratch decision remains pending for fresh full-reserve native lifecycle evidence. M5 requirements 2-5 remain open. M6 remains 0/10 actual sessions. See [the native-record report](../reports/M5_NATIVE_ATTEMPT_RECORDS.md).

### Earlier 16 October reader checkpoint

16 October 2026. **Workload limits are adjusted and the blocked private portfolio reader is verified.** Complete storage scans have 30 seconds and yield to heartbeat work; inventory freshness is 35 seconds. Recovery has a shared 240-second deadline. Authenticated commands allow 300 seconds, with five-second authentication and reply acknowledgement. The current task has 4 GiB temporary space inside a 10 GiB scratch category; the 50 GiB total and 1 GiB emergency reserve remain unchanged.

The reader passed **64 identical source/installed cases**, zero failures/errors/skips, with both final environments byte-verified and independent reader review clear. Installed native three-owner recovery also passed. The full final capacity census passed with 29.567 GiB allocated, including 8.492 GiB scratch, and 187.673 GiB physical disk free. Backups still have only 522,272 bytes of category headroom. Strata remains off; the original installed environment, saved master stop and terminal M3 audit history remain preserved.

- [x] Measure storage and revise the workload policy under current owner authority.
- [x] Verify timer, heartbeat, IPC, storage and recovery behavior; preserve failed runs.
- [x] Complete reader19 and its added history, schema, privacy and expiry checks.
- [x] Verify matching source/installed results and complete environment bytes.
- [x] Document measured timers, capacity and future space measurements.

Exact next action: implement the qualified native ownership/economic producer against the immutable opening and complete history. Resolve backup headroom before ordinary new recovery snapshots or any saved-stop recovery. M5 requirements 2-5 remain open and M6 remains 0/10 actual sessions. See [timers and storage](../reports/RESOURCE_TIMERS_AND_STORAGE.md) and [the private-reader report](../reports/M5_PRIVATE_PORTFOLIO_CONTEXT.md).

### Prior preview capacity refusal, preserved history

16 October 2026. **The preview resource check is fixed and independently reviewed.
One complete capacity census ran and refused the requested 1 GiB scratch hold.**
The hold exceeds remaining scratch capacity by **1,063,722,952 bytes**. All 31
simulated/pure checks passed, with zero failures, errors or skips. No product
tests ran. The preview was already absent at launch; this work did not stop or
restart it. This repair keeps the reviewed five-second limit. Separate edits
appeared afterward that change the scanner setting to 30 seconds and scratch
to 9 GiB; those edits are outside this review. All evidence and the saved stop
remain preserved. See [the result](../reports/PREVIEW_RESOURCE_CAPACITY.md).

- [x] Reproduce and correct lifetime CPU rejection without stopping the preview.
- [x] Independently review all 960 input bindings and the bounded launch procedure.
- [x] Run one capacity census and preserve its complete measurement and refusal.
- [x] Verify process exit, zero remaining children and unchanged database/stop bytes.
- [x] Record separate concurrent source changes without overwriting them.

Exact next action: resolve the measured storage shortfall while preserving all
records and current limits. No retry, candidate run, scratch write, clone update,
ordinary runtime, Strata start or saved-stop recovery follows this refusal.

### Prior preview refusal, preserved history

15 October 2026 continuation. **The owner approved 1 GiB of disk scratch. The
capacity launcher refused before startup because the existing Vesper website
preview exceeded its saved cumulative CPU allowance.** The preview remains
running; no census start receipt or native Job exists. Independent correction
review verified 933 frozen inputs. Two sets of eleven pure capacity checks
passed, zero failures, errors or skips. No product test, candidate build, scan
or installation ran. The later ten stages remain disabled.

Storage category caps and scanner limits, the reserve and saved watchdog stop remain unchanged.
Fresh checks matched 217 source files, 217 installed files, the coordinator
database and saved-stop bytes. The full 1 GiB hold still needs a complete capacity
check within the unchanged scratch category. Strata stays stopped.

Exact next action: obtain the owner's decision about temporarily stopping the
verified local preview and making one census launch. The stop procedure is
prepared and reviewed; it has not run. Preserve the refusal and refresh reviewed
documentation bindings before an approved launch. See
[the continuation report](../reports/STORAGE_FRAME_CONTINUATION.md).

### Earlier preparation, before the disk decision

15 October 2026. **Storage admission remains blocked; diagnosis and a bounded fix are prepared for review.** The four approved folders remain removed and all backups and prior evidence are preserved. One new read-only five-second profile measured 1.990421 seconds in directory acquisition/first query and 0.677391 seconds in checked closure before timing out. The last complete count, less the 718 removed directories, still leaves a derived 28,620 before later record growth. No current complete inventory or capacity pass is claimed.

The proposed change reuses at most 16 checked-closed buffers in the existing private native walker. It preserves caller-thread reads/callbacks and every current limit and check. Its timing benefit is unproved. The source diff is unapplied; no candidate was compiled, run, installed or promoted. Two in-memory diagnostic record checks passed with zero failures/skips; no product tests ran. Read [the diagnosis](../reports/STORAGE_ADMISSION_DIAGNOSIS.md) and [the bounded fix for review](STORAGE_ADMISSION_FIX_REVIEW.md).

All 217 source and 217 installed program files, prior failed receipts, backups, actual coordinator bytes, 1 GiB reserve and watchdog stop remain unchanged. Ordinary work, reader19, Strata and clone updates remain stopped. The twelve earlier scanner experiment rounds and five maintenance reviews stay used; no round-13 candidate or further live admission attempt ran. M5 requirements 2 through 5 remain open; M6 stays zero of ten actual sessions.

Preparation follow-up: the worker is on hold and confirmed that no native Job started. Unapplied integration and regression drafts now select 61 cases per lane. The preservation receipt exists. Complete isolated dependency payloads require at least 345,161,969 bytes, exceeding the 8,388,608-byte scratch ceiling. The executable procedure remains incomplete. See [the three preparation gaps and storage decision](STORAGE_PREPARATION_GAPS.md). No candidate or product test ran.

Exact next action: select a storage and installation approach before completing and reviewing the executable procedure. Keep the five-second limit, every saved record, and the worker hold. Do not run another admission check or clear the saved stop.

## Completed 31-link cleanup

15 October 2026. **The approved administrator cleanup removed exactly 31 old test shortcuts. All 31 target folders remain unchanged.** A separate live check confirmed every link is absent and every target retains its original identifier and properties. No target folder, saved evidence, permission or enabled Windows privilege was changed. The original link records and each removal intent were saved before removal.

The cleanup process exited with code 0 in 0.480002 seconds under its fifteen-second deadline. Fresh verification matched 65 original reports, 112 original receipt fingerprints, 43 inspection evidence fingerprints, and all 217 source plus 217 installed program files. No product tests ran: zero passed, failed or skipped cases. This is cleanup verification, not milestone acceptance.

The first canceled administrator request and both later preflight failures remain saved. The last preflight failure came from PowerShell converting a saved timestamp into a date value. The owner approved one additional review round, and the independently reviewed round-4 wrapper preserves that timestamp as text. The unchanged removal helper then completed. The unrelated Vesper website server remained running.

Private completion evidence is `artifacts/m5/old_test_link_cleanup_completed_verified.json`, SHA-256 `a0fd42a3006479fff67accf9202eeb5482e50766bc4ac096c762007801fd8251`. The exact procedure is `artifacts/m5/OLD_TEST_LINK_CLEANUP_PROCEDURE_V4.md`. Do not repeat the cleanup. See [the explanation and remaining decisions](FIXTURE_CONSOLIDATION_GATES.md).

This cleanup cleared the 31 denied entries from the earlier inventory. It did not authorize consolidation or restore ordinary admission. The later preparation above now records the owner's preservation choice and complete capacity measurements. All failed evidence and original runtime identities remain preserved. Scanner attempts 1 through 12 remain used, the 34 reader19 drafts remain unexecuted, M5 requirements 2 through 5 remain open, and M6 remains at zero of ten actual sessions.

## Prior storage investigation, before link cleanup

15 October 2026. The investigation of old test folders is closed, and **maintenance remains blocked**. The [decision record](FIXTURE_CONSOLIDATION_GATES.md) describes readable file properties for all 1,827 selected entries. Compressed contents and separate file-property records measure 1,161,181 bytes. All 320 backup links were readable, and the unchanged coordinator database contained zero space reservations. File-access audit rules could not be read for any selected entry. Of 1,669 workspace links, 31 old `current` links remained access-denied even when the check requested zero access rights. No incoming dependency was found among the other 1,638 links, but the missing targets leave that finding incomplete.

- [x] Preserve both failed inspections and the final diagnostic, which could not verify capacity. Every process exited and no children remained.
- [x] Measure directory disk use and additional file streams without changing the product scanner or file permissions.
- [x] Check the four reports written after the main count: the inspection caused a measured scratch overage of at least **310,888 bytes**. Stop further scratch writes and requested-clone updates.
- [x] Withdraw the 1.75 MiB backup proposal because it does not fit. Describe a smaller 1.5 MiB allowance for later review, without reserving space.
- [ ] Obtain the owner's choice about missing file properties, a way to read the 31 denied link records without changing them, and a decision about maintenance that writes no additional scratch files.

Exact next action: resolve those owner and access decisions before preparing a separately reviewed execution procedure. No backup was created and no folder was extracted, moved or removed. Ordinary work remains blocked. No reader test, additional scanner experiment or Strata start occurred. Scanner attempts 1 through 12 remain used. The 34 reader19 draft tests remain unexecuted, M5 requirements 2 through 5 remain open, and M6 remains at zero of ten actual sessions. Detailed private evidence remains in the three `m5-fixture-consolidation-gates-20261015-01` through `-03` folders and `artifacts/m5/fixture_gate_*` files. Documentation publication remains authorized; the requested clone waits for sufficient scratch capacity.

## Initial fixture plan, preceding gate resolution

15 October 2026. The owner accepted preparing a precise historical-fixture consolidation plan. Preparation has produced a concrete four-root passed-only candidate: 718 directories, 1,098 files and 11 links; measured compressed streams total1,067,977 bytes, with a proposed1.75MiB complete batch ceiling. No archive, move, removal or further scanner experiment occurred. See [the exact plan, evidence and execution gates](FIXTURE_CONSOLIDATION_PLAN.md).

- [x] Classify retained whole-job receipts and conservative individual-case proposals; preserve all failed/ambiguous roots.
- [x] Retain65 selected-tree measurements, exact file/link/identity manifests and bounded compressed-size counts.
- [x] Reconcile234 frozen inputs and217 unchanged source/installed product payload files after the job closed.
- [x] Preserve the final backup-capacity refusal: exit1,17.400211seconds,41,570,304-byte peak, observed exit and zero remaining children. The measurements completed; the overall inspection did not pass. Backup headroom is unknown.
- [x] Complete independent final plan review3/3: CLEAR_FOR_PLAN_DOCUMENTATION_PUBLICATION;65 report hashes and112 receipt pins independently reconciled. Publication status is recorded in the ignored receipt below.

Exact next action: resolve the concrete metadata, capacity and bounded maintenance-admission gates in the reviewed plan before preparing a separate execution procedure. Actual consolidation is outside this completed preparation scope. The ignored `artifacts/m5/fixture_consolidation_plan_published.json` receipt records publication and master/GitHub/clone equality. Resolve metadata preservation, incoming links, complete capacity/reservations and the distinct bounded maintenance-admission decision before preparing any removal. Current production admission remains blocked; scanner rounds1 through12 remain used. Reader19 is34 private drafts, zero executed; M5 gates2 through5 remain open andM6 remains0/10 actual sessions. Strata stays off. Private plan evidence is `.cache/test-runs/m5-fixture-consolidation-plan-20261015-01/plan-evidence.json`, SHA76012ef210139e1b37c4f182b49ccded8d2aa38eaad1810c9a8b91e33f67a3a7.

## Broader experiment closeout, preceding this plan

15 October 2026. The broader native traversal experiment is closed without a qualified replacement. Rounds 1 through 12 are used. The aligned round12 prototype matched two complete small inventories, then reached the unchanged five-second deadline after 83,623 files. All 23,749 opened handles closed; peak native Job memory was60,919,808 bytes. No prototype was promoted or installed. The 217 source/installed payload files and 326 historical native evidence pins are unchanged. See [the complete experiment report](../reports/M5_NATIVE_BATCH_EXPERIMENT.md).

- [x] Finish the original106 installed cases, with393 matching cases per lane and no failures/errors/skips.
- [x] Freeze and preserve the broader experiment, reproduce its alignment defect and add an explicit compile-time alignment assertion privately.
- [x] Match complete src/tests inventories and caller-thread callbacks in the aligned candidate.
- [x] Preserve the full-master timing refusal and audit all eight native Jobs, five exact archives and94 evidence pins.
- [ ] Restore reliable actual storage admission. The approved experiment did not qualify and its three additional rounds are used.
- [ ] Run the34 reader19 cases and complete M5 local gates2 through5 after admission qualifies.

Exact next action: publish this independently reviewed documentation closeout and keep admission blocked. No round13, compiler, test or equivalent scan is covered by this exhausted extension. Further work needs a concrete owner decision about the preservation/operating approach. Historical fixture copies account for substantial directory work, but failed fixtures remain outside passed-only cleanup authority. No consolidation, move or deletion of failed copies is authorized or prepared for execution. Do not relax limits, exclude files, reopen terminal M3 or start Strata.

The private audit is `.cache/test-runs/m5-native-batch-20261015-10/batch12-blocked-audit.json`, SHA `46aa5ebf603bf05184c241afd00e19b1d225839a6f00abdcda6e7a8897b918ce`. It confirms34 unchanged syntax-valid private reader case IDs, zero executed reader cases and no reader implementation. Maintenance08 remains unexecuted. The ignored `artifacts/m5/native_storage_batch12_published.json` receipt records publication review and master/GitHub/clone equality. M5/financial acceptance remains open; M6 remains0/10 actual sessions.

## Previous scanner checkpoints, superseded

15 October 2026. The owner approved the broader native scanning experiment and continuation after verification. Use [the bounded batch plan](STORAGE_BATCH_PLAN.md), at most rounds 10 through 12, carrying all nine used rounds. Every limit stays unchanged. Begin with frozen interface probes and a private C traversal prototype; qualify complete actual-limit scans before ordinary implementation resumes. Current product admission remains blocked. The prior closeout below is preserved history.

15 October 2026. The approved storage investigation is closed and **current admission remains blocked**. Scanner rounds 1 through 9 are used. The private candidates in rounds 7, 8 and 9 each reached the unchanged five-second deadline. No prototype was promoted; all 217 source/installed payload files and 326 historical native evidence pins remain unchanged. See [the investigation report](../reports/M5_STORAGE_COST_EXTENSION.md).

The final partial profile visited 102,561 files. Directory opens consumed 2.543 seconds. Caching checked native function pointers reduced repeated module/procedure lookups from 78,732 each to two each, but scanning still did not finish. This identifies the largest observed cost; it does not explain the earlier timing variation or establish a complete inventory. All eight native investigation Jobs closed with zero active children. The closure audit verified three exact input archives and 66 investigation evidence pins. No new product tests ran in this extension; one private missing-interface probe failed as expected against the unchanged original API before the candidate scan.

- [x] Complete the original 106 installed cases and the 393 matching source/package cases per lane.
- [x] Preserve the previously qualified native scanner and maintenance07 evidence.
- [x] Measure recurring scan costs and finish the approved rounds 7 through 9 without changing limits.
- [x] Audit closure, unchanged product bytes, historical evidence and the 34 frozen reader drafts.
- [ ] Restore reliable actual storage admission. The approved repair budget is exhausted.
- [ ] Execute the 34 reader19 cases and finish M5 local gates 2 through 5 after admission qualifies.

Exact next action: obtain a new bounded decision for a broader native batch-walker experiment, or leave admission blocked. The proposed experiment would reduce Python/C traversal calls while retaining every inventory, allocation, lock, callback and cleanup check. Its performance benefit is unproven. No round 10, compiler, test or equivalent scan launch is authorized by the exhausted extension. Qualification would still require exact inventory/fault checks, matching source/package cases, both complete environments and repeated full-master scans under the original one-CPU/128MiB/five-second watchdog.

Reader19 remains 34 private syntax-valid drafts, zero executed cases and no product implementation. Maintenance08 was refused before backup writes; no archive08 or cleanup08 occurred. Failed and full-reserve fixtures remain preserved. The original source_components01 fixture is a failed run and is ineligible for passed-only cleanup. No heavy job remains active. All resource/financial limits and the Strata prohibition remain in force.

The private audit is `.cache/test-runs/m5-native-portfolio-20261014-19/extension09-blocked-audit.json`, SHA `b3fc6ed61b6025043f5d248ece7c758c47463959c6291d9812ffdb857f5145ea`. The approved extension is recorded in `scanner-extension-approval07.json`; the older `blocked-checkpoint19.json` is preserved as superseded history. The seven-file documentation closeout will be published after independent review; its ignored publication receipt records the resulting master/GitHub/clone commit.

14 October 2026. Original intent release18 is verified: **393 matching cases per environment**, including all106 formerly pending installed cases; zero failures/errors/skips. All78 jobs closed. Independent original-release review3 CLEAR; aggregate SHA62601bca9b1606171ad3bbfd926a550ce6bd642f7249fccde9915e4409d7922d binds1027 pins. Published and synchronized master/primary GitHub/requested clone at140403c8e0e827935fc2f0563f9e3f43caa30787.

Native scanner qualification and final independent review6 are complete: **43 matching source/installed cases**,18 C boundary cases, both complete environments and three actual one-CPU128MiB full-master scans passed at4.566,4.948,4.930seconds. The last uses the original watchdog volume callback. All eight component jobs and the separate aggregate audit closed with zero active children. Python3.14.7 and38 dependencies are unchanged. Parent admission is not affinity capped; child test jobs have four CPUs. This is storage engineering verification, not a full managed session on master or milestone/financial acceptance.

Aggregate `artifacts/m5/native_storage_pair_verified.json`, SHAeb08494998a4dcd395c08e6a0423f790d76a3a7b0ab4c3ea7b8de36e61e4c58e, binds326 evidence pins,576 frozen inputs and217 package payload files. Source archive SHA6273bff6b4d29c0b4e22de32bb9e5652af3425ac5c70013019ebabf8646555cf; wheel SHA1b4f48710b0e3b337f7c9ba45b198d632238725fee8ba9993cfa31e171a56199. Native C/DLL/manifest are covered by the Python hash anchor and both full environment checks. See [the complete native report](../reports/M5_NATIVE_STORAGE.md).

Checklist:

- [x] Finish and independently verify the original106 continuation.
- [x] Qualify the new native scanner in source and installed environments with every limit unchanged.
- [x] Finish native final review6 and publish/synchronize at24b0a5c0fc17d673ddf9e648447a6005932d7f1f.
- [x] Archive and byte/link verify five closed passing scanner roots, then remove their disposable copies. Failed evidence is untouched.
- [ ] Complete native ownership/economic accounting, risk/admission, durable dispatch/recovery and the integrated local rehearsal under M5_PAPER_ADMISSION_PLAN.md.

Rounds1â€“3 remain used; the owner approved native rounds4â€“6 only. Review4 was BLOCKED by a reproduced DLL-reparse lock gap; review5 cleared its file-identity repair. The final variant uses FileAttributeTagInfo with the same directory/reparse checks. Earlier failures, prelaunch refusals and all failed roots remain. Two direct-script environment checks refused the outside helper origin and briefly overlapped; corrected inline checks ran serially and passed unchanged requirements. No cleanup occurred in this increment. Full history is in the report and private receipts.

Maintenance07 archived3280 files,796 directories and161 links into a600020-byte archive (SHA8b79a23aa9c4c8fc0c8041bde81a6a05e27bf513122a97131826d239ed0fe0ff), verified every byte/link, then removed only the five passed disposable roots. Independent maintenance review3 cleared closure; all326 native release evidence pins remain unchanged. The old full128MiB growth reservation refused before child creation. The reviewed follow-up requested4MiB of growth while preserving the128MiB namespace ceiling; its installed full-master scan passed in4.5859954seconds under the actual one-CPU128MiB/five-second watchdog. No children remain. Scratch headroom was89827744 bytes; backup headroom5093408 bytes.

Reader19's private API and34 draft cases are now frozen under docs/M5_NATIVE_PORTFOLIO_PROGRESS.md, but the current storage refusal above blocks execution. Use fresh m5-native-portfolio-20261014-19 scratch, justified sized growth grants and unchanged absolute limits. Native rounds4â€“6 and maintenance07 rounds1â€“3 are closed; reader19 has its own maximum three evidence-led review rounds, none used. Earlier maintenance04 helpers and the Python-only build namespace m5-storage-build-20261014-01 remain unexecuted. Keep Strata off, retain original M3 terminal history and every limit, and perform no actual broker action. M5/financial qualification remains open; M6 is0/10 actual sessions.

## Earlier partial checkpoint, superseded

Increment18 is implemented but **not fully verified**. Source:393 passed,0 failed/errors/skips in39 closed jobs. Installed:287 passed,0 failed/errors/skips in32 closed jobs;106 cases in seven groups remain. All116 new intent cases passed in both environments. The third installed continuation stopped before creating a process at STORAGE_SCAN_DEADLINE. All three refusal receipts and all failed preliminary evidence remain. Two verified historical passing test roots were archived and removed, but the subsequent three unchanged five-second production scans still refused. No further test was launched. The partial evidence audit passed and pins896 inputs: `artifacts/m5/native_intents_partial_storage_blocked.json`, SHA `dcc2e45b9263b582bd4473ec5d75ee0c4732742a93f66f3740d0a955abc45edf`. This is an incomplete checkpoint, not final acceptance.

Current checklist:
- [x] Implement exact intents/confirmations and repair reproduced integrity defects; implementation review2 CLEAR.
- [x] Complete393 source checks,287 installed checks, offline build/install and both full environment qualifications.
- [x] Diagnose and preserve three infrastructure refusals; byte-verify passing-only archives and retain failed roots.
- [x] Independently review and publish the partial checkpoint: 1b63360b1ebd6e440ae99b436e78bf4b768aa4ad. Master, primary GitHub and requested clone matched cleanly; partial-publication review1 is CLEAR_FOR_PARTIAL_PUBLICATION. Full increment18 acceptance remains pending.
- [ ] Restore production storage admission without weakening limits, then finish only the106 remaining installed cases if frozen inputs are unchanged.
- [ ] Complete ownership/accounting, risk, durable dispatch/recovery and the integrated local rehearsal under M5_PAPER_ADMISSION_PLAN.md. Reader19 is only a prerequisite to full accounting.

Exact next action: resolve the measured storage-admission blocker before another native job. Latest offline cost profile is diagnostic only:104,546 files,163,941,696 bytes scratch headroom and5,695,520 bytes backup headroom. A copied instrumented scan took8.902seconds; its instrumentation overhead means this is not the production scan duration. Production independently refused three times at its unchanged five-second limit. Do not repeat unchanged launches, raise limits, discard failed evidence or reopen M3's terminal failed audit. Any production scanner change needs a new input identity and affected requalification. Prepared groups-final18d.json and installed-continuation18d.json preserve287 completed cases and the exact seven remaining groups; they have not run. Full aggregate helpers18c/18d must not be used to claim success from the refused scans. Strata remains off; no actual broker action is authorized.

Verified increment14: [account-only private inputs](M5_ACCOUNT_CONTEXT_PROGRESS.md). **306 identical source/installed cases passed**, zero failures/errors/skips, all24 jobs closed. Both complete environments and aggregate verification passed;542 inputs/209 modules, unchanged Python and38 dependencies. Final independent review3/3 is **CLEAR**. Aggregate SHA `c927d7aadcb89ba7eb7f39a1495b9c5b774e995463c37f8aa263d63e4f8a159e`;251 evidence pins. Failed preliminary tests and the installed pre-process storage refusal remain preserved. Fourteen passed temporary roots were archived and byte-verified before checked cleanup. See [the complete report](../reports/M5_ACCOUNT_CONTEXT.md).

Current checklist:
- [x] Complete account-only implementation, matched source/package verification and final review.
- [x] Publish account14 and verify master/primary GitHub/requested-clone equality: `0bc6758c62fcc94e03c0d5453493af8691e7a7c1`.
- [x] Repair combined-context integrity;151 matching source/package cases and final review CLEAR3/3.
- [x] Publish/synchronize repair15: f4bae5b686a4beef8719553e68e2bac48913a8aa. Master, private GitHub main and requested clone match.
- [x] Repair account/presence integrity16;222 matching source/package cases, complete environments and final review CLEAR2/3.
- [x] Publish/synchronize integrity16: 1f490d6637a118e1915be50388072a464c45046b; master, primary GitHub and requested clone match.
- [x] Implement and verify private final proofs17:277 matching source/package cases, zero failures/errors/skips;46 closed jobs, complete environments and final aggregate review CLEAR. Aggregate SHA `ddefe3a8d6b74d2bdfe365e62c5f935288a13f4290b48b6e55c7e2e1b937be6d`. All failed evidence and the pre-process storage refusal are preserved.
- [x] Publish/synchronize proofs17: `1bd00dd3f5bdc5c12eb353d0e86cf4bef555eab1`; master, primary GitHub and requested clone match. Final review1 CLEAR;277 matching cases and653 evidence pins.
- [ ] Finish increment18 and the approved local rehearsal gates above. Older active-session descriptions are superseded by the storage-blocked checkpoint.


Verified repair16: **222 identical cases passed per environment**, zero failures/errors/skips; all34 jobs closed. Full environment qualifications and aggregate verification passed;544 frozen inputs/209 modules, unchanged Python and38 dependencies. Final review2/3 CLEAR. Aggregate SHA `1a420f02e2dcf30907571a0bc54e2038b3fbfab412522e9c3a9f4817387e7fe3`;275 evidence pins. The12 original failures and all source bytes remain preserved. Only passed temporary copies were archived/verified before cleanup. See [the report](../reports/M5_ACCOUNT_PRESENCE_INTEGRITY.md). Exact next action: preserve the closed passing installed16 fixtures, then run the39 frozen missing-interface probes for17 and implement their private final checks. No financial/M5 acceptance;M6 remains0/10.

Verified repair15: **151 identical cases passed per source/installed environment**, zero failures/errors/skips, all28 jobs closed. Offline build/install, both complete environment qualifications and aggregate verification passed;543 frozen inputs/209 modules, unchanged Python and38 dependencies. Final independent review3/3 is **CLEAR**. Aggregate SHA `d3daf070dbb018d9c1009b636ff19bd351c33f75601ef93232164886f2bb0735`;436 evidence pins. Original137/1 stopped source sequence, all preliminary failures and installed pre-process storage refusal remain preserved. Passing-only archives are byte-verified. See [the integrity report](../reports/M5_INPUT_INTEGRITY.md). Exact next action: publish/synchronize this checkpoint, then activate the12 account/presence probes under [repair16](M5_ACCOUNT_PRESENCE_INTEGRITY_PROGRESS.md), before exact native intents. No financial or M5 acceptance;M6 remains0/10.

Verified increment13: [native operator presence](M5_NATIVE_PRESENCE_PROGRESS.md). **314 identical cases passed per source/installed lane**, zero failures/errors/skips, all 26 jobs closed. Offline build/install, both complete environment checks and aggregate verification passed; Python and dependencies are unchanged. Aggregate SHA `9069d3d20f44d3372cbd9ac0aa90ede08298e98426b22bc0497425f9d7562694`; evidence map has 490 pins. Final review4/4 is CLEAR. Exact next action: publish/synchronize this checkpoint, then archive/verify the passed disposable13b fixtures before the next increment. Earlier304-case review-blocked evidence and failed fixtures remain preserved. The local `artifacts/m5/presence_published.json` receipt will record publication equality. Account-only test drafts and bounded verification/maintenance helpers are prepared in `.cache/test-runs/m5-account-context-20261014-14`; they have not run or changed product code. Continue [account-only inputs and exact intents](M5_NATIVE_INTENT_PROGRESS.md). No broker dispatch or actual account authority is added.

Active increment12: **255 identical source/installed cases passed**, zero failures/errors/skips, all24 jobs closed. Both complete environments and aggregate verification passed;537 frozen inputs/207 modules. Aggregate SHA `e7c0d1abe00717fd961966fc54f0fded1ffea4c372a239a6157f1d122d7facab`. The first aggregate helper's phase-counting error is preserved and corrected. Final independent review3/3 is CLEAR. Exact next action: publish and synchronize the clone; continue [native presence](M5_NATIVE_PRESENCE_PROGRESS.md). See [the live checklist](M5_INPUT_CONTEXT_PROGRESS.md). Increment11 below is published as `d2f7e53889b9fd83c98f4fc35ee5831ebef97b41`; master, primary GitHub and requested clone matched. Full M5/financial acceptance remains open; M6 is0/10.

Current increment11: **696 identical source/installed cases passed**, zero failures/errors/skips, all children closed. Includes one fresh native full1GiB lifecycle per lane; lost acknowledgements and three process generations preserve exact historical evidence without restoring grants. Both complete environments qualified;535 frozen files/206 modules. All95 repair plans/581 exact source blobs retained. Aggregate SHA `7a17f4f2b3532bd73670bf6a6d32de9642776c228f4ec8b80a9de7dd1ed48041`. Implementation review2/3 CLEAR; final review3/3 CLEAR. See [the publication report](../reports/M5_MARKET_LINEAGE_PUBLICATION.md). Exact next action: synchronize master/primary GitHub/requested clone, then implement the private input context in [the native admission plan](M5_PAPER_ADMISSION_PLAN.md). Financial/M5 acceptance remains open;M6 is0/10. Older next-action paragraphs below retain history.

Verified lineage foundation: **225 identical cases passed in each source/installed environment**; zero failures/errors/skips, all children closed. Both complete environments qualified; release08 freezes521 files/199 modules. Both real1GiB reserve fixtures are preserved with all bytes and identities unchanged. Aggregate verification passed; its first failed receipt-schema assumption is preserved. Final independent review3/3 is CLEAR. AggregateSHA `e374f67678b19123dc5f9648bfddebd7adb10cfbc271deed31ed659371d37b28`. Published `3a0481b3441a79a091a4978fa297475a9e05fbd1`; master, primary GitHub and requested clone matched. See [the foundation report](../reports/M5_MARKET_LINEAGE_FOUNDATION.md).

Consumption increment verified in both environments: **291 matching cases per lane**, zero failures/errors/skips and all children closed. Release09 binds525 inputs/201 modules; both complete environments qualified. Original consumption commits atomically with the consumed job, and owner-bound capture resolves/rechecks its original records. Five reproduced cleanup regressions are corrected. Review2/3 is CLEAR; final aggregate review3/3 is CLEAR. AggregateSHA `19b5bea29cc05ae58ddf27ff3e9e45abc350140ae41d6f93fb7a0e1eb9e1ec94`. See [the consumption report](../reports/M5_MARKET_CONSUMPTION.md). No actual provider/account/order request or Strata startup.

Current checklist:

- [x] Repair owner refusal/cleanup errors and publish verified release07.
- [x] Implement coherent private capture and strict historical reconstruction.
- [x] Complete matching225-case source/package checks, environment qualification and evidence preservation.
- [x] Finish foundation final review and publish verified checkpoint.
- [x] Save original grant consumption evidence and bind capture to owner records;291 matching checks per lane.
- [x] Add reserved encrypted lineage publication and native ACK/restart verification;696 matching cases per lane and final review CLEAR.
- [ ] Implement private owner-bound paper input context, then the remaining native admission dependencies.

Consumption checkpoint published as `4e17cf949c446bd120f6ba4fdee02e8aa29d7acc`; master, primary GitHub and requested clone matched. Private encryption/reopening is verified below. Continue with durable capture routes and ACK/restart recovery under [the publication plan](M5_MARKET_LINEAGE_PUBLICATION_PLAN.md). Full durable lineage and M5/M6 acceptance remain open.

Encrypted artifact increment10 verified: **243 identical source/installed cases**, zero failures/errors/skips and all children closed. Both complete environments qualified; release10 binds527 inputs/202 modules. Original record/proof reopening, purpose-separated encryption and held-HISTORY ownership checks pass. All failed evidence and exact source inputs are preserved. Implementation review2/3 is CLEAR; final aggregate review3/3 is CLEAR. AggregateSHA `10080bc62dd5f390f845af120c8fbec73c7dcbdc3a553c6f37ae33cfbeebe05d`. See [the encryption report](../reports/M5_MARKET_LINEAGE_ENCRYPTION.md). Exact next action: publish this reviewed checkpoint, then implement durable capture identity and explicit owner/coordinator transfer/ACK recovery under the publication plan. No actual provider/account/order request or Strata startup.

Increment10 storage maintenance is complete: the initial five-second scan refusal is preserved;46 verified passing temporary fixture roots were archived and checked before authorized cleanup. All failed fixtures and original reports remain. Preservation and aggregate verification then passed under the unchanged production scan. ArchiveSHA e3cc23f59b2d8c7fa6c008c01e6fd4ec31ec475f1b0911f24c6d27d5f55f515b; the encryption report and aggregate pin all receipts.

Current repair: **394 matching cases pass in each environment, plus 11 source-backed native connection cases**. Both actual lifecycle tests, full environment qualifications and aggregate verification passed. Release07 freezes 519 inputs and 198 modules. An acknowledged busy-checkpoint reply no longer closes healthy connections; malformed/transport failures still do. Exact barrier-release acknowledgement and snapshot cleanup are enforced. Passing scratch was archived and verified before cleanup; every failed native identity remains preserved. Final independent aggregate review is CLEAR3/3. Next: keep master/GitHub synchronized and implement [durable market-input lineage](M5_MARKET_LINEAGE_PLAN.md). See [the repair report](../reports/M5_MARKET_OWNER_REPAIR.md) and [repair checklist](M5_ERROR_REPAIR.md). The earlier exhausted round below is retained history, not the current action.

- [x] Owner selected private `BGonnermann/Compertum` as the primary repository. Master uses the existing BGonnermann account; old remote retained as `legacy-brennan`. The requested clone is `.cache/checkouts/Compertum-bgonnermann`, with all53 prior commits through `8fb43d609b02351e41df4e6380dc58020cde9792` retained. Only tracked files/history were cloned; runtime evidence and credentials remain in their original locations. Implementation stays in master.

- [x] Consolidate master and publish rollback checkpoints.
- [x] Verify repaired release: 592 distinct matching source/installed tests; zero test failures/errors/skips. Both complete environments qualified; unchanged Python and 38 dependencies; 486 frozen files and 190 matching modules.
- [x] Complete both 63-outcome campaigns in 120 native chunks, with exact mathematical payloads and zero failed/skipped calculations.
- [x] Complete and verify all 77 development audits/reviews, including 72 independent calculation audits.
- [x] Complete Final freeze, consume-before-price-access, one bounded batch and restart refusal checks.
- [x] Verify source Final auditor pause/resume, preserving its intended exit-125 attempt.
- [x] Close the lost installed audit through authenticated recover only. Attempt1 is BLOCKED; history/partial/source audit/Final preserved; no retry allowed.
- [x] Verify independent source terminal restart and four separate three-ridge jobs. Six annual fits, exact source/package calculation/audit outputs,15.857-26.166seconds/job, peak563.441MiB. Paired Final-audit acceptance remains blocked.
- [x] Record independent partial closeout review CLEAR2/3. Full M3 remains blocked; the separate provenance addendum pins repaired helpers and preserved failures.
- [x] Reconcile the failed preservation move: all 282 files unchanged, all 183 directory IDs changed. Content verified and retained; archived runtime cannot resume.
- [x] Integrate only M5 R's 20 mapped files; verify 521 exact cases per lane, including real 1 GiB reserve. Independent closeout CLEAR 1/3.
- [x] Integrate M5 S's eight mapped files and targeted negative-cash correction; verify95 opening and126 compatibility cases per lane. Final closeout CLEAR1/3.
- [x] Implement market grants/records, collection/publication, FRESH/composition and routing; freeze518files/198modules, build/install offline and qualify both complete environments.
- [x] Run346 matching component cases per source/installed lane; zero test failures/errors/skips in those six jobs; all children closed.
- [x] Complete native market restart verification in the subsequent authorized repair:394 matching cases per lane; original failed attempts remain preserved.
- [x] Complete aggregate repair closeout under the unchanged5-second storage scan after verified passing-fixture maintenance.

## Historical repair checkpoint, superseded by verified release07

The following paragraphs preserve the earlier failed state and its evidence; they are not current instructions. That bounded execution was incomplete. Its next diagnostic was to explain the repeated storage-scan deadline and retain native nonhealthy startup responses before another bounded integration attempt. The later authorized repair above completed that work without raising limits, erasing the watchdog halt or retrying failed runtime identities.

Current partial evidence: `artifacts/m5/market_owner_partial_checkpoint.json`, SHAe837e4cdafd6f77b97f5390be251312799d5d4d4842aed582f14f8b6d94cd3d2. **346 distinct cases pass per lane**:216market +125compatibility +5import/calendar. Each of the six final02 jobs has zero failures/errors/skips and all children closed. Maximum67.836seconds, peak246.254MiB aggregate Job memory. Full environments qualified; unchanged Python3.14.7 and38dependencies. Source/installed modules match exactly. No actual provider/account/order request or Strata startup.

Current frozen release: `.cache/test-runs/m5-market-native-20261014-01/release01.json`,518files/198modules. Source archiveSHAed07806c5cd9de7eb1ed2956789651ced80586d7dafc97cf1981abf7fbdd1e55; wheelSHAb328f808bbfebad4bf49dfe917d80f2bd3afa7c200e7dac97e1f952a4ecbb563. Installed now contains this project wheel. The targeted product correction lazily imports the calendar library only for actual calculations; the red import regression and all five final calendar/import checks are retained. Thresholds, interpreter, lock and coordinator/owner limits are unchanged.

Native attempts01-04 each failed one test. Native01 failed startup with1455; the import boundary correction is separately verified, without claiming aggregate Job memory proves coordinator RSS or sole cause. Native02 sent the forbidden request too early; native03 incorrectly expected checkpoint shutdown with held FRESH views. Native04 explicitly checked the required MARKET_CHECKPOINT_BUSY refusal and deliberate COMMAND_DENIED closure, then failed third-generation HEALTHY admission. The exact preserved halt is NATIVE_CALL_FAILED:PeekOwnerPipe:109; StorageMonitor retains RETAINED_WATCHDOG_HALT. Third-generation registrations exist. The helper discarded nonhealthy startup diagnostics and reported a generic15-second timeout. Final independent native review BLOCKED3/3; three repairs exhausted. Never clear this halt or claim general crash recovery.

Aggregate verifier component-proof01/02 failed the unchanged5-second storage scan after validating case sets, frozen source/package/environment bindings and preservation receipts. Attempt03 moved admission before archive hashing and added a planned4MiB output-headroom check; the initial scan failed before admission under the same deadline. **No successful aggregate closeout exists.** The six per-job passing results remain valid observations; this is a partial checkpoint. An earlier calendar prelaunch storage refusal and two post-rename scan failures remain preserved alongside their successful subsequent bounded checks.

All closed native02/03/04 fixtures are preserved at `backups/m5-market-source-reserve-failed-processNN-20261014-01/fixture`, every byte and file/directory identity unchanged. Native01 remains stationary. No deletion or runtime resume. Native renames record their brief unlock/relock intervals. `iteration-sources01.zip` retains524 exact blobs for all9 native/final plans, with no missing inputs. See [the full partial report](../reports/M5_MARKET_OWNER_PROGRESS.md).

Prior verified dependencies: R521matching cases, release496files/192modules, independently CLEAR1/3 and published `edd65c74f89a22d7cfe259525ec3272cdb3cc531`. S221matching fresh cases, corrected release502files/194modules, CLEAR1/3 and published `075bd51ba5ab09af932251963a3cd7b8752881b3`. Their full1GiB passing/failed fixtures remain preserved with all bytes and identities unchanged. Receipts: `artifacts/m5/master_retry_verified.json` and `master_opening_verified.json`; reports retain exact plans, corrections and reviews.

Earlier market source checkpoints271 and341 were published as `6ea60966b113579e93ca1615e62eb94776462f01` and `491244e6719062c1a947cd1d807006fc4e64e42d`; remote equality was verified. They are historical after the calendar correction. Source namespace `.cache/test-runs/m5-market-owner-20261014-01/iteration-sources04.zip` retains544 exact source blobs for35plans; one disclosed preliminary61-case passing test revision is unavailable and excluded. All failed/current source inputs for the present346-case release are retained.

One heavy job at a time; host admission16GiB/stop12GiB; workers120seconds/4GiB/fourCPU. M3's lost installed Final audit remains blocked. Durable FRESH/composed lineage, financial qualification and actual supervised walkthrough/session gates remain open. No scheduled automation.

## Verified interruption evidence

T = `.cache/test-runs/m3-pair-native-20261013-01`; original runtime prefix = `.cache/test-runs/m3-pair-runtime-20261013-01`. Its files now reside at `backups/m3-interrupted-runtime-20261014-01/runtime`. The preservation move failed its directory-identity requirement: all 282 files retain exact bytes and file IDs, but all 183 directory IDs changed. Read-only reconciliation passed with no missing paths; the historical runtime cannot be restored or resumed from this copy. Original receipts retain their original paths/identities. `artifacts/m3/pair_validation_runtime_preservation.json` records the mapping, failure and current storage admission. No physical disk space was freed.

Session 70191 is gone. It last saved installed-auditor readiness around 00:47 Eastern. Native process census at 06:43 found zero current test processes. Read-only inspection found wheel task `7a7c07e2-bf8c-580e-8579-e9070bf103a2` recorded RUNNING with one bound attempt and no exit receipt. Native identity observation verified the original worker absent. Absence proves closure, not success. Existing product behavior makes this attempt terminally BLOCKED after supported recovery.

`artifacts/m3/pair_validation_final_interruption.json` verifies all four Final stages, source pause/resume and mathematical output, original Final frame/journals/guard, and all 37 execution-input pins. Verification command `T/final-interruption-evidence01-command.json` exited 0 without timeout/overflow. Initial read-only inspection had a Windows path-formatting error; corrected inspection02 passed and both records remain. See [the interruption report](../reports/M3_FINAL_INTERRUPTION.md).

Generated Final selected momentum-h01/h05/h21, with 502 scoring sessions and zero ML fits. Three-ridge coverage remains separate. Partial training from 2023, three stocks, simulated availability and unverified zero fees prohibit financial acceptance.

## Preserved verified receipts

- Release: `T/release01.json`, SHA1e53f943d9224f22e772cf9c8188e6865fd27912ec16128a1775fc13a0a712cf.
- Regressions: `artifacts/m3/pair_validation_complete_regressions.json`, SHA39b7059683e5d790e09c8ca3955d6254e7f5712ffe74e11ad4089f8b7106fce7.
- Paired campaigns: `artifacts/m3/pair_validation_campaign_pair.json`, SHAfd5f68c1ab6dab3b2c280fb63d1c2b92d31bee2136e1ea1eb35d7cb2ebceafb0. Source63/59chunks, installed63/61chunks; 212 startup status errors and zero active-work control errors. Minimum free physical memory39.282GiB. Independent review CLEAR1/3.
- Complete77-output verifier: `T/audit-outputs01-command.json`, SHAbdb4af26995bb10883fea8ca85d6f27000a4b6736cfd4b6ee268d4ce3b248588; logSHAbd164a2cdaa0a771dd9e1009444fbea34252b587cb78e5ea727e750fd5bae5d1. Exit0; peakworker505.359MiB/coordinator51.008MiB.
- Original37pins file SHA9d3067ee80645a5c02d350ff5432a253eac973b1b5ad9d98b32ad09a956fe02d; pairSHAfefacc888816772da9bd13c0a72cef842d28467387b9244d88fb8ad204dbb342.
- Owner pause and its original12-audit prefix remain preserved in `artifacts/m3/pair_validation_owner_pause.json`. Both pause markers were renamed with verified hashes before the authorized continuation. Original session32591 exit1 was the deliberate pause boundary. No automation exists for resuming this work.
- Latest verified GitHub commit before this partial checkpoint publication: `491244e6719062c1a947cd1d807006fc4e64e42d`.

## Resource and authority limits

One heavy job at a time. Host admission16GiB free physical/commit; stop below12GiB. Workers4GiB/fourCPU/120seconds. Keep scratch5GiB, project50GiB and50GiB free-space floor. Do not change interpreter, lock, numerical thresholds or financial gates. Preserve failed evidence; remove only proven passing temporary fixtures after verified archival under existing owner authorization. Secrets, environments, runtime databases, datasets, detailed local evidence and backups stay out of Git.

## Preserved failures and cleanup

Two older full runs remain blocked and must never be resumed, reset or repinned. The development-folder run completed both 63-outcome campaigns and 37 reviews. The preceding master run completed both campaigns and 76 reviews, then pair task `e09d4e35-c8e2-58c6-a306-2ca439aa805b` blocked before worker execution. Final never started there. Its tooling/runtime remain in `m3-master-native-20261013-01` / `m3-master-runtime-20261013-01`.

The current 592-case proof explicitly preserves the source prelaunch storage refusal; recovery changed only that group's label, not its tests or bounds. Source recovery 37737 and qualification 96250 completed with exit 0. Subsequent sandbox storage-admission01/02 also exceeded the unchanged five-second bound; the same native helper passed admission03. Do not relabel these refusals as passing tests.

Only proven passing temporary fixture copies were removed under the owner's earlier approval, after archives and every file/directory/link were verified. All reports, plans, XMLs and failed evidence remain. Archives are under `backups/pair-installed-fixtures-20261013-01`, `pair-source-fixtures-20261013-01` and `pair-history-fixtures-20261013-01`; detailed receipts remain in T. Historical environments and other backups remain preserved.

Details: [native plan](M3_MASTER_NATIVE_PLAN.md), [repair record](M3_PAIR_VALIDATION_REPAIR.md), [acceptance requirements](M3_MASTER_ACCEPTANCE_MAP.md), [recovery report](../reports/M3_INTERRUPTION_RECOVERY.md). Historical continuity receipts are supporting evidence, not fresh test counts.

## Dependencies and authority

M0 accepted; M1 bounded real-data replay verified but full financial input qualification remains open; M2 synthetic components verified; M3 current native sequence incomplete; M4 fake-broker engineering accepted; M5 integration/walkthrough pending; **M6 has 0 of 10 actual supervised market sessions**.

The M5 map remains read-only at `C:\Users\bgonn\Desktop\Compertum-development\.cache\test-runs\m3-final-native-20261012-01\next-integration-map01.json`. Never extract a whole historical archive over master. R's20 mapped files are integrated and verified; S's8 plus the targeted correction are verified with221 matching fresh cases per lane. Original case inventory: `artifacts/m5/master_exact_case_inventory.json`, SHA502a4c7135c76aa673f898276099db5e1aff0f648846e01e578f6aca6191e345. Original S94 requires an added genuine process-restart check plus126 compatibility checks. Preserve closed full-reserve fixtures with verified native rename before another real1GiB case if namespace capacity requires it. Continue [the market-owner plan](M5_MARKET_OWNER_PLAN.md) after those dependencies pass.

Local engineering and meaningful verified GitHub checkpoints are authorized. New spending, new permissions, actual account/order actions, administrator/security changes, protected real-data evaluation and scheduled services are not authorized by this work. No new automation is needed. Credentials, datasets, runtime databases, detailed local evidence and backups stay out of Git. Use master for ongoing implementation; preserve historical siblings and their recorded identities.

Increment10 published as `7a8b3e5f3d901607ae8788269a871e8dff737702`; master, primary GitHub and requested clone verified equal. Implementation11 is active: persistence and transfer are implemented; source recovery checks and independent review are running. See [the active implementation checkpoint](M5_MARKET_LINEAGE_PROGRESS.md) for exact receipts and next action. Maximum three evidence-led review/repair iterations; existing resource and authority limits unchanged.
