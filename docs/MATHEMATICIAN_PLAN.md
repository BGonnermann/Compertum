# Mathematician plan: three changes, one at a time, after the bench baseline

Status, 25 October 2026: plan only. The owner asked for it "for after the bench". No code or prompt is changed. Each change starts only with the owner's OK, after the bench baseline (`run-20261026-84433f03`) is recorded.

## Why

Today the Mathematician turns a memo into a four-part specification (features, model, assumptions, failure modes) and reviews the Engineer's code. It never sees a number. In a quant firm the same person would also study the training data, judge whether the sample can detect the effect, and choose parameters by a stated rule. Three changes move the role in that direction without letting it touch the judge.

## Fixed rules for all three changes

- The Validator, the deflation gate, the Auditor, the vault and the ledger stay unchanged.
- No model sees a validation or vault row, or a statistic computed from one. The preflight check keeps refusing any task that shows a validation row.
- Every new piece of task text is built by code (in `tasks.py`, like the market brief), so GEPA cannot remove or change it.
- Each change is measured alone on the bench (`tools\practice.ps1 -Mode bench`, 4 cycles per market) and compared with the baseline. The comparison uses the bench report: patterns found, capture, false discoveries on the two empty markets, mean bench level, requests per cycle and minutes per cycle.
- A change that adds a false discovery on an empty market is rejected, however much it helps elsewhere.
- The holdout is used only once, for the final combination, before the owner applies anything permanent.

## Two fixes first, from the bench baseline run (added 25 October 2026)

In bench cycle 77 (`run-20261026-84433f03`), the Mathematician review call continued for 43.5 seconds and the client refused it with `AI_RESPONSE_REJECTED`. Flint writes approximately 46 tokens each second, so the reply had approximately 2,000 tokens. The limit for one reply is 2,048 tokens. The server probably stopped the reply at the limit. The record does not show this cause, so the cause is an inference from the call time.
Research on 26 October 2026 (`docs/HARNESS_TOOLS_RESEARCH.md`) confirmed it from the server log: the three `length` stops on 25 October each had about 518 reasoning tokens and about 1,530 tokens of visible answer. The 512-token reasoning budget works. The visible review was too long.

**Fix 1: record the real cause of a refused reply.**
- Problem: in `src/compertum/ai/models.py`, `_complete` (used by `complete` and `complete_tools`) changes every refusal inside the request block to `AI_RESPONSE_REJECTED`. Thus, `AI_RESPONSE_INCOMPLETE`, `AI_RESPONSE_INVALID`, `AI_TOOL_EXECUTION_DENIED` and `AI_USAGE_BOUND` are not visible in the ledger.
- Change, in four parts:
  1. Read `usage`, including the reasoning token count, before the stop-reason check, so a truncated reply keeps its counts.
  2. Record the `finish_reason` from the server in the model-call record.
  3. Re-raise the specific inner code instead of `AI_RESPONSE_REJECTED`.
  4. Pass `finish_reason` and the token counts into the LangChain message that `LedgerChatModel` in `roles.py` builds.
- Tests to update: `tests/test_ai_models_interface.py` and `tests/test_engine_roles.py` name the old code.
- Rule: no refusal becomes an acceptance. The step-fault list in `cycle.py` (`STEP_FAULTS`) already contains each specific code, so the cycle behavior does not change.
- Tests: one test for each code, with a scripted server that sends a reply with `finish_reason` "length", a malformed reply, and a reply with a bad usage field.
- Size: approximately two hours. `models.py` is the stage E1 client, so the change needs its own tests and a short review.

**Fix 2: a length limit for the Mathematician review.**
- Problem: the review gives advice only, but a long review uses up to 2,048 tokens and approximately 44 seconds, and it can stop before the end.
- Change: `tasks.review_task` adds one fixed sentence: "Write at most 150 words." The sentence is in code, so GEPA cannot remove it. The preflight check confirms the sentence.
- Alternative: increase the token limit for one reply. Each long call then takes more time, so this plan does not recommend it.
- Effect on the bench: the review does not change any score. It changes the requests, the minutes for each cycle and the review faults. The bench report compares these values with the baseline.

**Built on 26 October 2026, during bench baseline 1 (the running process does not reload its files):**
- Fix 1, in `src/compertum/ai/models.py`: every model-call record now holds `finish_reason` and `refusal_detail` (the inner code). Token counts, including `reasoning_tokens`, are recorded before the reply checks, so a refused reply keeps them. A stop at the token cap is the new code `AI_RESPONSE_TRUNCATED`, added to `STEP_FAULTS`. The reply-check codes `AI_RESPONSE_INVALID`, `AI_RESPONSE_INCOMPLETE`, `AI_RESPONSE_BOUND`, `AI_TOOL_EXECUTION_DENIED` and `AI_USAGE_BOUND` now reach the caller. Every other inner refusal (bad JSON, an HTTP error, a secret in the reply) still raises `AI_RESPONSE_REJECTED`, so no tolerated fault became a cycle stop. `roles.py` passes `finish_reason` and the token counts into the LangChain message.
- Fix 2, in `src/compertum/ai/engine/tasks.py`: the review task ends its first line with "Write at most 150 words." (`REVIEW_LENGTH_RULE`). The preflight check refuses a review task without it. The pinned task hash changed on purpose.
- Tests: product lane (model interface, preflight, bench) 81 passed, 0 failed, 1 skipped (the cycle import test needs the engine library). Engine environment, the tests that use no sandbox, 19 passed, 0 failed, 0 skipped. The full engine lane waits until the bench run ends, because its tests share the sandbox profile.

These two fixes come before change A. They do not change what the model knows about the market, so they do not need their own bench run. Change A's bench run measures them together with change A.

## Two harness steps toward fine-tuning (added 25 October 2026)

The owner wants to fine-tune a model to the way Compertum works, in the future. Fine-tuning Flint itself is not possible now: the model is too large for this PC, cloud training costs money, and no training data exists. These two steps come first. Neither step needs a model.

**Step S1: structured output for the JSON replies.**
- Problem: the Director's pick and approval replies, and the agenda reply, must be JSON. In the early practice runs, many pick replies did not parse. Each failure costs one retry request, and a second failure leaves the cycle with nothing to build.
- Change: for these three tasks, the client sends a JSON schema with the request (`response_format` with type `json_schema`, which the LM Studio server supports). The server then can only produce text that matches the schema. Today the client in `src/compertum/ai/models.py` sends no `response_format`.
- Research note (26 October 2026): six LM Studio issues about structured output and reasoning are open, and Flint has no switch to turn reasoning off. If the test shows that the grammar forces `{` before the reasoning, use a two-call step instead: one call reasons in plain text, and a short second call returns the schema-checked JSON. A related open question is the sampling setting: our requests use temperature 0, as `docs/BUILD_SPEC.md` sets, but Flint's publisher says greedy decoding is not validated. The owner decides.
- The parsers stay. `parse_hypotheses` and `parse_decision` still check every reply, and the retry stays as a second safety.
- Risk: Flint reasons before it answers. A schema can block or cut the reasoning part, and the answer quality can fall. So the first test is a small owner-started check with a few calls on Flint, before any bench run.
- Measure: the bench report and the ledger give unusable replies, retries, requests and minutes for each cycle, against the baseline.
- Build: an optional schema parameter in the E1 client, three fixed schemas in code, client tests with a scripted server. About half a day.

**Step S3: save full transcripts of practice cycles as future training data.**
- Problem: the ledger keeps only hashes of each task and reply. The cycle keeps the text in memory for GEPA (`state['transcript']`, each text clipped at 8,192 bytes), then discards it. So no training examples exist.
- Change: after each practice cycle, write its transcript to `state/engine/transcripts/<run id>/<cycle id>.jsonl`: one line for each step, with the role, the task kind, the full task, the full reply and the step outcome. Then add the cycle's level and the candidate levels, so later work can select good examples.
- Rules:
  - Bench and holdout cycles are never saved. They must not become training data, as they never reach GEPA or the lessons table.
  - Each text passes the existing secret check (`sanitized`) before it is written.
  - The files stay private under `state/`, outside Git, and count against the records storage budget.
  - Each file has a size limit, and a run stops saving if the records category nears its ceiling.
- Use later: select steps from cycles at level 7 or higher to train a small model for one role, for example the Engineer, with LoRA (a method that trains only a small add-on to the model). The selection must exclude the bench and holdout markets.
- Build: a small writer module, tests that confirm no evaluation cycle is saved and no secret passes, and a storage check. About half a day.

S1 and S3 come after fixes 1 and 2 and before change A. S1 changes the model's replies, so the bench run for change A also measures S1. S3 changes no reply.

## Two speed steps (added 26 October 2026)

The owner asked whether GEPA can make the runs faster. During bench baseline 1, 11 cycles took 51.6 minutes, about 4.7 minutes each, and about 21 model calls each. Flint writes about 46 tokens each second. A cycle gets faster only with more tokens each second, fewer tokens, or fewer calls.

**Step V1: move some of Flint's expert layers to the GPU (the largest gain expected).**
- Today: `llm.load.numCpuExpertLayersRatio = 1` in Flint's saved settings (`C:\Users\bgonn\.lmstudio\apps\bionic\.internal\user-concrete-model-default-config\lmstudio-community\flint-GGUF\flint-Q4_K_M.gguf.json`). All 47 expert layers keep their experts in host memory and run on the CPU. The GPU (16 GiB) used 3.8 GiB during the bench.
- Change: lower the ratio in steps, for example 0.8 (about 9 layers on the GPU), then 0.6 (about 19 layers). Each expert layer is about 0.45 GiB. Keep at least 2 GiB of GPU memory free for the display and the cache.
- Second benefit: each layer moved off the CPU frees about 0.45 GiB of host memory, the memory that the 16 GiB start floor checks. Bench baseline 1 had only 17.5 GiB free after 11 cycles.
- The weights stay the same, so the replies should not change in quality. The bench still checks this.
- Who acts: the owner changes the setting in Bionic, or approves the change. A changed setting takes effect at the next model load. The wrapper `tools\practice.ps1` unloads and loads the model for each run.
- Measure, before and after, with the model alone on the PC: tokens each second from the server log, minutes for each cycle, free host memory and used GPU memory (the wrapper's memory record), and the bench report.
- Stop rule: if free GPU memory falls under 2 GiB, or the server fails to load, go back to the previous ratio.

**V1 results so far (26 October 2026).** Speed comes from Bionic's server log; memory from the wrapper's memory record.

| Ratio | Run | Generation | Prompt reading | Model server RAM at start | Free RAM at start |
|---|---|---|---|---|---|
| 1 (baseline) | bench baseline 1, 228 replies | 48.2 tok/s | about 500 tok/s | 21.6 GiB | 23.6 GiB |
| 0.8 | `run-20261026-0f3194ec`, 1 cycle, 15 replies | 57.5 tok/s (+19%) | about 617 tok/s | 17.3 GiB | 27.5 GiB |
| 0.6 | `run-20261026-82cbf6c3`, 1 cycle, 20 replies | 68.1 tok/s (+41%) | about 700 tok/s | 12.9 GiB | 31.9 GiB |

About 4.3 GiB moved from RAM to the GPU at 0.8, and 8.7 GiB at 0.6. At 0.6 the GPU used 12.2 to 12.3 GiB of 15.9 GiB, steady through the run, so about 3.5 GiB stayed free. **Decision: keep 0.6.** Ratio 0.5 would leave about 1.3 GiB of GPU memory free, under the 2 GiB margin, and 0.4 would not fit. Backup of the original settings: `flint-Q4_K_M.gguf.json.backup-20261026-before-offload`. The wrapper's memory record now has a `gpu_used_gib` column. The check run also showed fix 1 working: an Engineer build stopped with `AI_RESPONSE_TRUNCATED`, a program reply that reached the 2,048-token cap. That cause was hidden before fix 1. Possible follow-ups: a larger reply cap for the Engineer only, or an instruction to write shorter programs and fix them with `edit_file`.

**More load settings, 26 October 2026 (owner: "you do those").** Added to Flint's saved settings after another backup (`flint-Q4_K_M.gguf.json.backup-20261026-before-fa-threads-batch`): `flashAttention` true, `cpuThreadPoolSize` 8 (was llama.cpp's 6 on the 8-core Ryzen 7 7700X), `evalBatchSize` 2048, `physicalBatchSize` 1024. A load test confirmed 8 threads in the llama.cpp log and showed GPU use of 12.7 GiB (12.3 before; the larger batches use about 0.4 GiB). The log does not show flash attention or the batch sizes at its level, so those two are applied by configuration but not confirmed. The owner also enables the RAM's EXPO profile: the DDR5-6000 kit (G.Skill F5-6000J3040G32G, 2 x 32 GB) ran at 5000 MT/s. One one-cycle check after the restart measures all of this against 68.1 tok/s. If it is worse, the settings are undone one at a time.
Check result (`run-20261026-205df989`, 1 cycle, 23 requests, RAM still at 5000 MT/s, so without EXPO): generation 66.9 tok/s against 68.1 at ratio 0.6 alone, within the spread of single replies (65 to 69); prompt reading about 1,272 tok/s against about 700 (+82%, from the larger batches); GPU 12.1 GiB during the run. Decision: keep all three. Writing speed is limited by RAM bandwidth for the experts still on the CPU, so EXPO is the next measurement; a later check at 6 threads can settle whether 8 threads matter.
XMP check (`run-20261026-ef20f055`, 1 cycle, 10 requests, RAM at its rated 6000 MT/s after the owner enabled XMP Profile 1 on the MSI B650 board): generation 67.1 tok/s (8 replies, 65 to 70) against 66.9, so no change; prompt reading about 1,422 tok/s against about 1,272 (+12%); GPU 11.6 to 11.8 GiB. RAM bandwidth does not limit generation at ratio 0.6; the GPU-CPU handover per layer and the CPU experts' work probably do, which also explains why 8 threads gave no gain. Decision: keep XMP if the PC stays stable. Speed work total: generation 48.2 to about 67 tok/s (+39%), prompt reading about 500 to about 1,420 tok/s.
The same day's log also shows fix 2 working: a Mathematician review reply of 665 tokens (518 reasoning, about 147 visible), against about 2,048 before the limit.

**Step V2: GEPA run 3 with speed as a tie-breaker.**
- Today GEPA's score is the outcome level divided by 10 (`gepa_run.score_for_cycle`). Time does not count, so GEPA has no reason to prefer a faster prompt.
- Change: add a small speed bonus from the cycle's own records (requests, completion tokens and minutes, all in the ledger). The bonus is always smaller than the smallest possible difference between two level scores, so a faster prompt can win only when its levels are equal. GEPA can never trade research quality for speed.
- What GEPA can shorten through the prompts: long Mathematician reviews, Engineers that rewrite the whole program several times instead of one edit, memos that the Director then rejects, Director JSON retries, and Engineer loops.
- What GEPA cannot change: Flint's token speed (step V1), the sandbox, and the server.
- The change is in our GEPA adapter, not in the judge. Tests prove that a lower level always scores below a higher level, whatever the speed.

**V2 built on 26 October 2026** (`src/compertum/ai/engine/gepa_run.py`): `speed_for_calls` reads the cycle's own model-call records (the calls added to the client's ledger during that cycle) and computes the mean number of output tokens per call. `score_with_speed` adds at most `SPEED_WEIGHT` = 0.009 to the level score, which is below the smallest gap between two mean level scores (0.1 divided by `MAX_MARKETS` = 8, so 0.0125). The measure is per call, not per cycle, so a cycle that builds more candidates is not penalized. The feedback to GEPA's reflection states the calls and the mean tokens. Without token data the score is the level score alone. Tests: product lane GEPA tests 11 passed, including a check over every level and 1 to 8 markets; engine environment, all engine files, 165 passed, 0 failed, 0 skipped; product lane engine files 169 passed, 7 skipped.

Order: fix 2 (review length) first, then V1, then GEPA run 3 with V2. Fix 2, V1 (ratio 0.6) and V2 are done; GEPA run 3 is next. Each step gets its own bench comparison.

## Change A: a power check in every specification (first, smallest)

**What.** The specification gets a fifth heading, "5. Detectability". The Mathematician states the edge the rule expects and compares it with the edge the sample can detect. Code puts the reference numbers into the specify task, so the model does not compute them:

| Trials counted | Smallest per-session Sharpe that passes | Annualized |
|---|---|---|
| 1 | 0.135 | 2.15 |
| 15 | 0.281 | 4.46 |
| 60 | 0.328 | 5.21 |
| 100 | 0.343 | 5.45 |

These are for 150 validation sessions and a one-sided 95 percent level, with the null variance only and no skew or kurtosis correction, so they are lower bounds. They match the bench finding: the exact planted rule has a per-session Sharpe of 0.30 to 0.39, and only values above about 0.33 passed at 60 trials.

**Effect expected.** Fewer candidates that cannot pass by construction, for example slow rules with a handful of trades. A specification may end with "not detectable in this sample". The Director then sees that outcome in the lessons table.

**Build.** A code-built table in `tasks.specify_task`, using the real trial count of the ledger at task time; one line in `config/engine_prompts/mathematician.md`; preflight and content tests. About half a day.

**Open point.** Whether "not detectable" should skip the Engineer step. First version: no. It is recorded only, so the bench measures the effect of the information alone.

## Change B: a train-only data summary

**What.** The specify task (and the memo task) gets a summary of the TRAIN rows, built by code:
- session count, mean and standard deviation of returns, share of up sessions;
- autocorrelation of returns at lags 1 to 10;
- the mean return after N up sessions and after N down sessions, for N from 1 to 5;
- volatility in the first and second half of the train period.

**Effect expected.** Hypotheses and parameters grounded in the data instead of guesses. On the synthetic markets this summary will often show the planted pattern directly, for example the lag structure of a momentum window. That is legitimate, because it is training data, and the same thing a quant would look at. It also makes the empty markets more important: a harness that reads noise in the summary as a pattern must show up as a false discovery there.

**Build.** A `train_summary(train_rows)` function in `tasks.py`, product environment, deterministic; tests that it uses no validation row; preflight extended to check that it is present and computed from train rows only. About one day.

**Risk.** Data snooping. Many statistics shown to a model invite fishing. The summary stays short and fixed, and the deflation gate still counts every candidate.

## Change C: parameters chosen on train data by a stated rule

**What.** The specification may say "choose the window from {3, 5, 10} by the highest train Sharpe" instead of hard-coding 5. The Engineer's program does the choice inside `decide()` on `train.csv` only, before it sets any validation position.

**Effect expected.** Parameters that fit the market instead of the model's habit.

**The hard part: hidden trials.** A grid of 3 values searched inside one candidate is 3 tries, but the ledger counts one trial. The deflation gate would then understate the selection effect. Options, for the owner to decide before building:
1. The specification declares the grid size, and the ledger counts it as that many trials. This changes trial accounting, which is part of the judge, so only the owner decides it.
2. A fixed small maximum grid, for example 5 values in total, and no change to the count. Simpler, but it understates selection by up to 5 times.
3. Not allowed: parameter search without declaration.

The Auditor already reruns the frozen code with the last validation rows perturbed, so a choice that peeks at validation data is caught. The plan adds a test candidate that chooses on validation and must fail the Auditor.

**Build.** Specification and Engineer prompt lines, the declared-grid field in the specification, the trial accounting the owner chooses, and Auditor and bench tests. About two days.

## Order and cost

0. Fixes 1 and 2, then steps S1 and S3, with their tests. No model is necessary, except a few owner-started calls to check S1 on Flint.
1. Change A, then a bench run (about 80 minutes with Flint).
2. Change B, then a bench run.
3. The owner decides the trial accounting for change C; then change C and a bench run.
4. The best combination, one holdout run, then the owner decides what to keep.

Each bench run is owner-started. No change here needs new software, spending or account access.
