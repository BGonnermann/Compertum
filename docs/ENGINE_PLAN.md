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
- [ ] E2: AppContainer sandbox and escape tests. Built 23 October 2026. Review round 1 `CHANGES_REQUIRED` (one blocker, seven should-fixes, five notes; all applied or recorded). Round 2: one should-fix (revoke on every path), applied; `E2_OK` on the code. 19 tests passed, 1 failed, 0 skipped. The failed test is the loopback escape; see "Stage E2 design" and the owner decision below.

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
- **Verification.** `verify_sandbox` runs one plain job, then the fixed probe in a second job, and checks twelve controls: AppContainer token, integrity level 4096, external network denied, loopback denied, listener saw no connection, outside read denied, outside write denied, outside file absent, earlier job folder read denied, inside write allowed, child process denied, memory limit enforced.
  Each denial must carry the exact error the boundary produces (`PermissionError`, `WinError 1816`, `MemoryError` or an out-of-memory exit). A timeout, a missing file or a crash never counts as a pass.
  `require_verified` recomputes the failed list from the controls and refuses with `SANDBOX_UNVERIFIED:<controls>` unless all twelve hold. The engine must call it before the first Engineer job of each run (section 19: "Before first use, deliberate escape tests must prove the sandbox").
  The external probe target is `1.1.1.1:53`. A packet leaves the host only if the boundary has already failed.
- **Not in E2.** `run_sandboxed` does not check the one-heavy-job slot; the engine holds the slot before calling it. The probe does not yet target the real vault, ledger and rules paths or the owner named pipe; E3 adds those targets when it fixes the paths.
- **Resource overruns.** Memory: `MemoryError` or job kill. Time: exit code 124 and `timed_out`. Processes: `WinError 1816`. Disk: measured after the run; `disk_overrun` marks the job failed. Windows has no live disk quota for a folder.

### Loopback finding, 23 October 2026

On this host (Windows 11 Home 10.0.26300) a capability-less AppContainer connects to a loopback listener. The listener saw the connection. External network stays denied (`WinError 10013`).
Microsoft documents loopback as blocked for AppContainers unless exempted, and `CheckNetIsolation LoopbackExempt -s` lists no exemption for the sandbox. One independent report on Windows 11 build 26200 shows the same behavior.
Defender Firewall is on for all profiles; Bitdefender Firewall is registered but its state is off; Developer Mode is on. The cause is not verified.
Windows Firewall rules do not filter loopback traffic, so no rule and no administrator-free setting restores the block.

Consequence: the section 19 statement "The job has no network access" is not fully met. Loopback is reachable, so sandboxed code could call the model server outside the ledger. Files, the vault, child processes, memory, time and external network are all denied.
`require_verified` refuses every Engineer job on this host until the loopback control holds. Stage E3 cannot give the Engineer an execution tool before then.

Owner decision needed, one of:

1. **Accept loopback reachability as a documented limitation** of section 19 on this host and drop `loopback_denied` and `loopback_unseen_by_listener` from the required controls. Compensating control: the engine records every sandbox job and the E5 request limit stays enforced at the ledger. Code in the sandbox still cannot read the vault or write a fixed part.
2. **Authorize a loopback block** for the sandbox identity. This needs a Windows Filtering Platform filter, which needs administrator rights and new native code. It is a security change under `AGENTS.md`. I would prepare a reviewed plan first.
3. **Stop E2 here** until the cause is found. No Engineer execution until then.

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
