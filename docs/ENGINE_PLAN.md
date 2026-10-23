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
- [ ] Verify and commit the 19 October work.
- [ ] E1 started.
