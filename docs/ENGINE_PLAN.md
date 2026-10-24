# Autoresearch engine plan: Deep Agents and GEPA

23 October 2026. M3 engineering acceptance closed today (`reports/M3_REPAIR_ACCEPTANCE.md`), so section 19 work may start.
The owner chose two libraries for the engine: **Deep Agents** for the AI roles and **GEPA** for prompt improvement.
This plan places them inside the section 19 design in `docs/BUILD_SPEC.md`. It does not change that design.

## Terms

- **Deep Agents:** LangChain's `deepagents` Python library. It builds an agent with a plan list, file tools and subagents on top of LangGraph.
  It accepts any LangChain chat model, so it can use a loopback OpenAI-compatible server.
  The installed `managed-deepagents` uv tool (`mda`) is a different, unknown package. The engine does not use it.
- **GEPA:** the `gepa` Python library (also available as `dspy.GEPA`). It improves text prompts by running them, scoring the results,
  and asking a model to reflect on failures and propose better prompts. It keeps a Pareto set of the best prompts. A call budget bounds each run.
- **Harness:** the prompts, tools, memory and limits around a model. GEPA changes harness text. It never changes model weights.

## Where each library fits

| Section 19 part | Library | Role |
| --- | --- | --- |
| Director, Researcher, Mathematician, Engineer (AI roles) | Deep Agents | One deep agent per role. The Director uses the plan list. The other roles are subagents. |
| Model calls | E1 interface | Every Deep Agents and GEPA call goes through the E1 interface. The ledger records each call. |
| Validator, Archivist, Auditor (code) | None | These stay deterministic code. No library changes them. |
| Role prompt improvement | GEPA | Improves the system prompts of the AI roles. The score comes from the Validator on TRAIN and VALIDATION only. |

## Fixed limits that apply to both libraries

- GEPA may change role prompts only. It never changes the judge, the Auditor, the baseline, the vault, the data tiers, the ledger, or the rules.
- GEPA scores use TRAIN and VALIDATION only. GEPA never sees the vault.
- Every strategy that a GEPA candidate prompt produces counts as a trial. The deflated Sharpe ratio and the trial count include it (stage E4).
- Deep Agents file tools use the in-memory file store or the E2 sandbox folder. They never write to the real project folders.
- Deep Agents shell or code execution runs only in the E2 sandbox. Until E2 passes, the roles get no execution tool.
- Model addresses are loopback only. Host memory is checked before every job. One heavy job runs at a time. Strata stays off.
- The current product caps stay: 40 AI requests and 8 AI tasks per day (`src/compertum/ai/manual.py`).
  A GEPA run needs far more calls. Stage E5 adds per-run request limits that the owner approves. The engine never raises a cap by itself.

## Stages

Each stage ends with tests, one independent review, and a stop for the owner's OK (section 19).

| Stage | Work | Library |
| --- | --- | --- |
| E1 | General loopback model interface, `config/models.toml`, model identity check, memory check, ledger record for each call | None |
| E2 | AppContainer sandbox and escape tests | None |
| E3 | Roles and one supervised cycle on a synthetic market | Deep Agents |
| E4 | Trial count, deflated Sharpe, candidate queue | None |
| E5 | Bounded runs, request limits, kill switch, Auditor freeze, daily summary | None |
| E6 | Engine acceptance: a bounded run finds a planted pattern | Deep Agents |
| E7 (new) | GEPA prompt improvement of the roles, inside a bounded run | GEPA |

E7 is new. It needs the owner's OK to add it to section 19 before work starts. It runs after E6, because GEPA needs a working cycle and a fair score.

## Practice runs before E3

- Serve Flint (`flint-Q4_K_M.gguf`, 22.5 GiB, in LM Studio) on a loopback port. Keep the expert weights on the CPU if VRAM is short.
- Measure tokens per second, VRAM, RAM and free host memory with the model loaded. The model must leave free memory above the floor.
- Run the E1 interface against it with fixed test prompts. Record the server-reported model ID.

## Owner decisions

Decided on 23 October 2026:

1. **Dependencies:** a separate engine environment. Deep Agents needs `deepagents`, `langgraph`, `langchain` and `langchain-openai`. GEPA needs `gepa`.
   They download from PyPI at $0. The qualified product lock and the M3 environments stay unchanged.
2. **Stage E7:** approved. Section 19 of `docs/BUILD_SPEC.md` now lists E7.
3. **Pending work:** verify the owner's uncommitted 19 October work (registration repair and supervised research cycle), get one independent review, and commit it. E1 builds on that commit.

Still open:

4. **Request limits.** Approve the first per-run AI request hard maximum before E5 (section 19 requires this).

## Current state

- [x] M3 engineering acceptance closed.
- [x] Plan written and pushed.
- [x] Verify and commit the 19 October work. 253 source tests passed; review `COMMIT_OK`; commit `3310653`.
- [x] E1: loopback model interface. 34 new tests passed (58 with the adapter tests), zero failed, zero skipped. Review `E1_OK` in round 2. Owner OK on 23 October 2026. Source lane only; see "Stage E1 design" below.
- [x] E2: AppContainer sandbox and escape tests. Built 23 October 2026. Review round 1 `CHANGES_REQUIRED` (one blocker, seven should-fixes, five notes; all applied or recorded). Round 2: one should-fix (revoke on every path), applied; `E2_OK` on the code. First run 19 tests passed, 1 failed, 0 skipped; the failed test was the loopback escape. Owner decision on 23 October 2026: option 1, loopback accepted as a documented limitation. After the decision: 20 passed, 0 failed, 0 skipped. See "Stage E2 design" and "Loopback finding" below.
- [x] E3: Deep Agents roles, one supervised cycle on a synthetic market, loopback watcher, fixed-part probe targets, heavy-job slot. Built 24 October 2026; owner OK on 24 October 2026 (commit `38af592`). Review round 1 `CHANGES_REQUIRED` (no blocker, six should-fixes, five notes; all applied); round 2 `E3_OK` with two notes. Engine environment lane: `tests/test_engine_roles.py` 12 passed, 0 failed, 0 skipped. Product lane: `tests/test_engine_sandbox.py` 25 passed; `tests/test_ai_models_interface.py` 39 passed; the engine module reports 1 skipped there. Full product suite on 24 October 2026: 7162 passed, 3 failed, 12 skipped in 1 h 56 min; none of the three failures touches E3 code (see `docs/CURRENT_CHECKPOINT.md`). See "Stage E3 design".
- [ ] E4: total trial count, deflated Sharpe ratio, candidate queue with sealed vault batches. Built 24 October 2026. Product lane: `tests/test_engine_validator.py` 9 passed, 0 failed, 0 skipped (hand-calculated cases); `tests/test_engine_sandbox.py` and `tests/test_ai_models_interface.py` 64 passed. Engine environment lane: `tests/test_engine_roles.py` and `tests/test_engine_validator.py` 21 passed, 0 failed, 0 skipped. Review round 1 `E4_OK` with one should-fix and seven notes; the should-fix and six notes applied, one note (sandbox probe targets) deferred to E6. The reviewer recomputed the hand values and matched them to better than 1e-8. Owner OK pending. See "Stage E4 design".

## Stage E2 design

Files: `src/compertum/runtime/sandbox.py`, `tests/test_engine_sandbox.py`. Authority: the owner authorized the AppContainer sandbox on 22 October 2026 (`docs/BUILD_SPEC.md`, Sandbox).
The 18 October plan `docs/M5_PIPE_LAUNCH_CONTEXT_PLAN.md` said "Do not add AppContainer creation to Compertum". That line bounded the M5 pipe correction only. The 22 October authority replaces it for section 19.

- **Boundary.** Each Engineer job runs the system interpreter `C:\Program Files\Python314\python.exe` with `-I -B` inside a Windows AppContainer. The container has no capabilities.
  Windows gives every container read access to Program Files, so the interpreter runs without any new grant. The job folder gets one access entry for the container identity. Nothing else is granted.
- **Fresh profile, fixed identity.** `run_sandboxed` creates the profile `Compertum.Engine.Sandbox` before the job and deletes it after. Deletion removes the container's own package folder and registry storage, so no state survives between jobs.
  Windows derives the identity (SID) from the name, so every job has the same SID: `S-1-15-2-247429629-1862752366-810889432-850981423-3343541058-2994282404-1727303319`. A stale profile from an interrupted job is refused (`SANDBOX_PROFILE_EXISTS`) and removed only by `remove_stale_profile`, a separate recorded step.
- **Grant and revoke.** The job folder gets one Modify entry (read, write, execute, delete; no right to change permissions or owner). When the job ends the entry is revoked and the effective rights are read back as zero.
  Review round 1 found that without the revoke, the shared identity let a later job read and alter an earlier job folder. The probe now reads a file from an earlier job and must be denied.
- **Hostile folder.** A finished job folder is treated as hostile. The disk measurement skips reparse points (a junction to `C:\Windows` is not followed) and output capture reads at most 64 KiB. Stage E3 must refuse reparse points before any host-side read or copy.
- **Job Object.** One process, one CPU, process and job memory limit, kill on close, deadline by `TerminateJobObject` with exit code 124. The limits are read back and must match.
- **Environment.** Three Windows variables only: `SYSTEMROOT`, `WINDIR`, `LOCALAPPDATA`, plus `TEMP` and `TMP` set to the job folder and three Python flags. The probe showed the inherited environment carries API keys; the container never sees it.
  Inside the container Windows points `LOCALAPPDATA` at the package's own writable folder. Its bytes count toward the disk limit and the folder is deleted with the profile.
- **Output.** `stdout.txt` and `stderr.txt` in the job folder, through inherited handles; the result keeps the first 64 KiB of each. `SandboxResult.record()` is the plain-JSON ledger entry.
- **Refusals before any process exists:** job folder not one level under the root, absolute or `..` arguments, deadline outside 1 s to 3600 s, memory outside 64 MiB to 8 GiB, disk limit outside 1 B to 1 GiB, free host memory below the floor, missing Windows variables.
- **Verification.** `verify_sandbox` runs one plain job, then the fixed probe in a second job, and checks ten controls: AppContainer token, integrity level 4096, external network denied, outside read denied, outside write denied, outside file absent, earlier job folder read denied, inside write allowed, child process denied, memory limit enforced.
  Each denial must carry the exact error the boundary produces (`PermissionError`, `WinError 1816`, `MemoryError` or an out-of-memory exit). A timeout, a missing file or a crash never counts as a pass.
  `require_verified` recomputes the failed list from the controls and refuses with `SANDBOX_UNVERIFIED:<controls>` unless all ten hold. The engine must call it before the first Engineer job of each run (section 19: "Before first use, deliberate escape tests must prove the sandbox").
  The probe also tries a loopback connection. The result is recorded as two observations, `loopback_connected` and `loopback_seen_by_listener`. Observations never pass or fail the gate; the engine records them with every run. See "Loopback finding".
  The external probe target is `1.1.1.1:53`. A packet leaves the host only if the boundary has already failed.
- **Not in E2.** `run_sandboxed` does not check the one-heavy-job slot; the engine holds the slot before calling it. The probe does not yet target the real vault, ledger and rules paths or the owner named pipe; E3 adds those targets when it fixes the paths.
- **Resource overruns.** Memory: `MemoryError` or job kill. Time: exit code 124 and `timed_out`. Processes: `WinError 1816`. Disk: measured after the run; `disk_overrun` marks the job failed. Windows has no live disk quota for a folder.

### Loopback finding, 23 October 2026

On this host (Windows 11 Home 10.0.26300) a capability-less AppContainer connects to a loopback listener. The listener saw the connection. External network stays denied (`WinError 10013`).
Microsoft documents loopback as blocked for AppContainers unless exempted, and `CheckNetIsolation LoopbackExempt -s` lists no exemption for the sandbox. One independent report on Windows 11 build 26200 shows the same behavior.
Defender Firewall is on for all profiles; Bitdefender Firewall is registered but its state is off; Developer Mode is on. The cause is not verified.
Windows Firewall rules do not filter loopback traffic, so no rule and no administrator-free setting restores the block.

Consequence: the section 19 statement "The job has no network access" is not fully met. Loopback is reachable, so sandboxed code could call the model server outside the ledger. Files, the vault, child processes, memory, time and external network are all denied.
Before the decision, `require_verified` refused every Engineer job on this host because the loopback control did not hold.

The owner was offered three options on 23 October 2026:

1. **Accept loopback reachability as a documented limitation** of section 19 on this host and drop `loopback_denied` and `loopback_unseen_by_listener` from the required controls. Compensating control: the engine records every sandbox job and the E5 request limit stays enforced at the ledger. Code in the sandbox still cannot read the vault or write a fixed part.
2. **Authorize a loopback block** for the sandbox identity. This needs a Windows Filtering Platform filter, which needs administrator rights and new native code. It is a security change under `AGENTS.md`. I would prepare a reviewed plan first.
3. **Stop E2 here** until the cause is found. No Engineer execution until then.

**Owner decision, 23 October 2026: option 1.** The owner confirmed that the research and training portions must have no internet access, and accepted loopback reach on this host as a documented limitation. Recorded consequences:

- `CONTROLS` has ten entries. The two loopback controls are gone from the gate. The probe still tries loopback and `verify_sandbox` records `loopback_connected` and `loopback_seen_by_listener` as observations with every verification.
- The limitation is recorded here and in `docs/CURRENT_CHECKPOINT.md`. `docs/BUILD_SPEC.md` is not changed; its hash must keep matching the preparation brief. Where section 19 says "The job has no network access", read: external network denied and proven; loopback reachable on this host.
- What loopback reach allows: code in a job can reach a listener on this machine. Compertum has no listener of its own, so the only target that matters is the model server the owner starts for a run. Such calls would bypass the ledger and the per-run AI request maximum.
- What it does not allow: internet access, reads of the vault, the ledger, the rules or an earlier job folder, writes outside the job folder, child processes, or more memory or time than the limits.
- **Compensating control, required in E3.** While a job runs, the launcher samples the sandbox process's TCP connections. Any loopback connection fails the job, records the event, and raises an Auditor freeze. Sampling can miss a very short connection, so this is a deterrent with evidence, not a proof. The E5 request limit stays enforced at the ledger.
- Revisit: if an elevated read-only `netsh wfp show filters` ever shows why the AppContainer loopback block is absent on this build, reopen this record. Only the owner runs elevated commands.

## Stage E3 design

Started 24 October 2026 after the owner's OK on E2. Files: `src/compertum/ai/engine/` (new package), `config/engine_prompts/*.md`, changes to `src/compertum/ai/models.py`, `src/compertum/runtime/sandbox.py` and `src/compertum/runtime/jobs.py`, tests `tests/test_engine_roles.py`, additions to `tests/test_ai_models_interface.py` and `tests/test_engine_sandbox.py`.

- **Engine environment.** `.cache/engine-env`, a separate `uv` environment on the same Python 3.14 interpreter, holds `deepagents` 0.7.32, `langgraph`, `langchain`, `langchain-openai`, `gepa` 0.1.4 and the project in editable form. The product lock and the M3 environments are unchanged.
  The package set pulls in LangSmith tracing and the Anthropic and Google provider packages, which stay unused. `roles.py` turns tracing off (four LangSmith and LangChain variables) and removes provider key names from its own process environment before it imports LangChain. No key value is displayed or recorded. The engine environment must be built on the system interpreter `C:\Program Files\Python314\python.exe`; a uv-managed interpreter under AppData cannot be loaded inside the AppContainer.
  Engine tests that import `deepagents` run in this environment only. In the product environment they are skipped and reported as skipped, never as passed.
- **One model path.** `LedgerChatModel` is the only chat model the agents see. It converts LangChain messages to Chat Completions messages and calls the E1 `ModelClient`. Every model call, including a tool call, is one ledger row with the same checks as E1: loopback address, server-reported model, memory floor, request limit, bounded response.
- **Tool calls in E1.** `ModelClient.complete_tools(role, messages, tools, ...)` sends an allowlist of at most 16 tool schemas and accepts at most 8 tool calls in one reply. A tool call must name a tool in the allowlist and carry a JSON object as arguments. The ledger row records the tool names offered and, for each call, the tool name and the SHA-256 of its arguments. `complete()` is unchanged: without an allowlist, any tool call is still refused. A tool-result message (role `tool`) is admitted with or without an allowlist, because it is text the engine produced.
  The engine, not the model, executes a tool. The only tools are the in-memory file tools and, for the Engineer, `run_job`.
- **Roles with Deep Agents.** One `create_deep_agent` per role: Director, Researcher, Mathematician, Engineer. A registered harness profile for the `compertum` provider removes `execute` and `task`, disables the general-purpose subagent and the summarization middleware. File tools work on the in-memory `StateBackend`; `delete` and `execute` are not offered. Nothing an agent writes reaches the real file system except through `run_job`.
  Each role gets a short, fresh conversation per step and a recursion limit of 40 graph steps. The request limit on the E1 client bounds the whole cycle.
  Role system prompts live in `config/engine_prompts/<role>.md`, bounded to 16 KiB, read from inside the project. Stage E7 (GEPA) edits these files and nothing else.
- **Engineer `run_job`.** The tool copies the agent's in-memory files (at most 32 text files, 256 KiB in total, relative paths only) into a fresh job folder with `train.csv` and `validation.csv`, then calls `run_sandboxed`. The vault is never copied. The result returned to the agent is bounded: exit code, timeout flag, the first 8 KiB of stdout and stderr.
  Before the run the engine checks the sandbox verification (`require_verified`), the freeze table, and the heavy-job slot. `hold_job_slot(lease)` in `runtime/jobs.py` takes the same slot the campaign launcher uses; a busy slot refuses with `JOB_SLOT_BUSY`.
- **Loopback compensating control.** `LoopbackWatcher` samples the Windows TCP table (`GetExtendedTcpTable`, owner PID) every 25 ms while the sandbox process runs. Any connection owned by the sandbox process to a loopback address is recorded with its remote port. The job fails, the Archivist records the event, and the engine writes a freeze row. Sampling can miss a connection shorter than one sample; the record says so.
- **Fixed-part probe targets.** `verify_sandbox` takes `fixed_targets`: real files that must be unreadable from the sandbox (the ledger `state/research.sqlite` when present, `docs/BUILD_SPEC.md`, `AGENTS.md`, `config/default.toml`) and `pipe`: a named pipe the test opens as a server. New controls `fixed_targets_read_denied` and `pipe_open_denied` need the exact `PermissionError`.
- **Cycle.** `run_cycle` runs the seven section 19 steps in trusted code. The Director picks at most 3 hypotheses from the ledger summary. The Researcher writes one memo per hypothesis. The Director approves or rejects each memo. The Mathematician writes one specification per approved memo and later reviews the Engineer's code (advice only). The Engineer builds each specification with `run_job`. The Validator scores each candidate. The Archivist records every step before and after it runs.
  Each cycle records its candidate list in the ledger before any run. Every candidate counts as a trial, including failures. The agenda review at every tenth cycle is recorded as a step; stage E5 gives it a run context.
- **Synthetic market and Validator adapter.** `engine/market.py` generates a deterministic daily market from a seed with an optional planted pattern. TRAIN and VALIDATION are session ranges of that market; there is no vault in E3. The Validator adapter turns the Engineer's `signals.csv` (one position in {0, 1} per validation session) into a NAV series with a fixed cost per position change and scores it with the existing `simulation.metrics.metrics` against the buy-and-hold benchmark. A candidate beats the baseline only if its annual mean excess is positive and its Sharpe ratio is defined and above the benchmark's. This adapter is for the synthetic market. The connection to the real walk-forward Validator with the deflated Sharpe ratio is stage E4 work.
- **Archivist tables.** `engine_cycles` and `engine_steps` in the coordinator store, insert-only, plain JSON records. `engine_freeze` holds freeze rows; `require_unfrozen` refuses every engine action while an uncleared row exists. Clearing is an owner action; stage E5 gives it a command.
- **Limits stated.** `require_verified` runs once per `EngineerSandbox`, so once per cycle, not before each run. The slot holder is `hold_job_slot(lease, purpose)`. Sandbox runs go to the table `engine_runs`. Memo, specification and review texts enter the END record by SHA-256 and size only; the code stays in the job folder. In E3 a freeze follows a loopback connection only; a denied write to a fixed part is a failed run with `PermissionError` in its stderr. `cycle_id` is `cycle-<index>-<random8>`. The watcher matches `127.*`, `::1` and `::ffff:127.*`. The Director summary is bounded to 16 KiB; the oldest cycles drop first. A review task above 48 KiB is skipped and recorded as `REVIEW_SKIPPED`. Any unexpected exception closes the cycle as `FAILED_UNEXPECTED` and propagates. Job stdout and stderr can show the job folder path to the model; that path is under the sandbox root and is not a fixed part. No vault file is a probe target yet, because E3 has no vault.
- **Not in E3.** No bounded unattended run, no kill switch wiring, no daily summary, no per-run request maximum (E5). No deflated Sharpe ratio or candidate queue (E4). No real model server test; the practice run with Flint stays a separate owner-started step.

## Stage E4 design

Started 24 October 2026 after the owner's OK on E3. Files: `src/compertum/ai/engine/deflation.py` and `vault.py` (new), additions to `engine/ledger.py`, `engine/market.py` and `engine/cycle.py`, tests `tests/test_engine_validator.py` (product lane) and three assertions in `tests/test_engine_roles.py`. No library. No change to the judge, the Auditor, the baseline, the sealed protocols or section 10 code.

- **Total trial count.** Table `engine_trials`, insert-only. The cycle records one row per candidate right after the Archivist's candidate list, before any run. A candidate that never runs, fails or returns no signals stays counted. `record_external_trials(source, count, evidence)` adds the trials of other campaigns once per source (for example the fixed family of 12 of a registered campaign). `total_trials()` is the sum. Stage E6 wiring decides which registered campaigns are entered.
- **Deflated Sharpe ratio** (Bailey and López de Prado, 2014) in `deflation.py`, deterministic code with the standard library only. Per-period Sharpe ratio, skewness and kurtosis come from the candidate's VALIDATION returns (`score_signals` now returns them as `deflation_inputs`). The expected maximum Sharpe ratio of N trials is `SR0 = sqrt(V) * ((1 - g) Z(1 - 1/N) + g Z(1 - 1/(N e)))`; one trial gives `SR0 = 0`. The deflated Sharpe ratio is the probabilistic Sharpe ratio against `SR0`. The gate is `DSR >= 0.95`, a constant in code; only the owner changes it through a reviewed commit.
  `V` is the sample variance of the per-period Sharpe ratios of all scored trials, the current one included, and never below the null sampling variance of one estimate, `(1 + SR^2/2) / (T - 1)` (Lo, 2002). So the bar never drops to zero when few trials exist. Scores are recorded once per trial in `engine_trial_scores`.
  Candidate status after scoring: `BEATS_BASELINE_PENDING_AUDIT` only when it beats the baseline and passes the deflation gate; `REJECTED_DEFLATED` when it beats the baseline but fails the gate; `REJECTED` otherwise. The Validator step records the full deflation record and the variance inputs.
- **Section 10 family size.** The deflation record carries `section_10_family_size = max(12, total trials)`. The sealed protocols still hold `family_size 12`; wiring the grown family into a sealed protocol is an owner-reviewed change to a fixed part, not engine work. The addition never lowers a section 10 threshold because nothing in section 10 code changed.
- **Candidate queue and vault batches** in `vault.py`. Events in `engine_queue` (insert-only): `QUEUED`, `DENIED`, `LOOK_COUNTED`, `VAULT_EVALUATED`; a candidate's state is the fold of its events. `admit` queues a candidate only when it beats the baseline on VALIDATION, its deflation status is `PASS`, `tests_passed` is True and `auditor_passed` is True; every denial is recorded with its reasons. Queued candidates wait; there is no allowance. `open_batch(candidate_ids, owner_note)` needs an owner note (1 to 1024 characters), at most 16 queued candidates, and writes the look row with its seal (SHA-256 of the batch body) and the `LOOK_COUNTED` events in one transaction: all rows exist, or none. `evaluate_in_vault(look_id, candidate_id, signals_text, read_vault)` takes the vault as a callable with no arguments and calls it only after the look and the candidate's state pass, so a repeat or a denied attempt never reads a vault row; it scores once with the same adapter and records the result; a second attempt is `ENGINE_VAULT_REPEAT`, also after an invalid signals file. `admit` also checks the deflation record's own numbers (minimum `0.95`, DSR at or above it), not only its status word. The deflation gate compares the unrounded value; the record keeps the 8-place text. The synthetic market gains `split_market_tiers` (TRAIN, VALIDATION, VAULT as consecutive ranges); the Engineer never receives the vault range.
- **Hand-calculated cases** in the tests: standard normal quantiles against the table; `SR0` for 10 trials with variance 0.01 (0.1574598) and 100 trials with variance 0.04 (0.5061206); DSR for a Sharpe ratio of 0.2 over 100 returns as the only trial (0.9756019, pass), as one of 10 trials (0.6624281, fail), with skewness -1 and kurtosis 6 (0.9624528); a Sharpe ratio of 0.5 over 250 returns as one of 100 trials (0.4637234, fail); moments of a six-return series; the variance floor. The expected values were computed separately with the standard library's `NormalDist`.
- **Limits stated.** The deflation uses per-period Sharpe ratios of synthetic-market candidates; the connection to the real walk-forward Validator's returns is E6 work. `auditor_passed` is an input to `admit`; the engine does not yet call the Auditor (E6). The owner note is the recorded form of the owner's OK for a batch; E5 gives it a command. The vault evaluation runs the candidate's frozen signals through the adapter; running frozen code on vault data inside the sandbox is E6 wiring. `trial_variance` floors at the candidate's own observation count. External trial sources are recorded by name; nothing verifies them against a scorecard yet. The caller of `evaluate_in_vault` supplies the reader; E6 wiring must pass a reader that opens the vault only when called. E6 must also add `engine/deflation.py`, `engine/vault.py` and the coordinator store database to the sandbox write-denial and read-probe targets, because `DSR_MIN` and the family size live in those files.
- **Not in E4.** No bounded run, request maximum, kill switch, daily summary (E5). No Auditor call, no real data tiers, no planted-pattern acceptance run (E6).

## Stage E1 design

Files: `config/models.toml`, `src/compertum/ai/models.py`, `tests/test_ai_models_interface.py`. No schema or `domain.py` change in E1; role tasks come in E3.

- `load_models(path, project_root)` reads one bounded TOML file inside the project. It has one table, `roles`, with exactly the four AI roles: `director`, `researcher`, `mathematician`, `engineer`.
  Each role has `base_url` and `model`. `base_url` must be `http://127.0.0.1:<port>` or `http://localhost:<port>`, with no user, query or fragment. Any port works. The path must be empty or `/v1`.
- `ModelClient(roles, ledger, memory_floor_bytes, request_limit)` sends one Chat Completions request per call.
  Before each call it checks free host memory against the floor, checks the request count against the limit, rejects secret-shaped text, and asks the server for its model list. The configured model must be in that list.
  Responses are bounded to 64 KiB. One choice with `finish_reason: stop` is accepted. Anything else is refused.
- The ledger records every call and every refusal: role, provider `loopback`, address, requested and server-reported model, settings, prompt SHA-256, response SHA-256, usage, elapsed seconds, free memory, floor, status.
  `StoreLedger` writes rows to the `engine_model_calls` table in the project store.
- The adapter process keeps the existing one-thread, 256 MiB, no-child native limits (`constrain_ai_adapter`).
  Warning: with `native_limits=True` (the default) construction puts the calling process into that Job for the rest of its life.
  Only a dedicated adapter process may construct the client that way. The supervisor, the coordinator and tests pass `native_limits=False`.
- The client rechecks every address and model ID itself. A `RoleModel` built by hand gets no exemption from the loopback rule.
- Every call, every refusal and every unexpected failure leaves one ledger row. An unknown role is recorded with no address.
- Installed-package lane: the `.venv` holds the M3 release wheel, which predates this module. The installed lane needs a new wheel build.
  Until then, E1 verification is source-lane only. The record states this.
- The memory floor comes from config `dispatch_available_ram_bytes` (8 GiB) unless the caller gives a higher value. The request limit is per client instance. Stage E5 adds the per-run hard maximum.
