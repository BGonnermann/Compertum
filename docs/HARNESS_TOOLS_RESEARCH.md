# Harness tools research, 25 to 26 October 2026

Status: research record. Nothing here is installed or changed. Each install or change needs the owner's OK. The plan that uses these findings is `docs/MATHEMATICIAN_PLAN.md`.

## Method

The owner asked which tools can help with the problems that GEPA cannot fix, and then asked for "all available information". Two research workflows ran:
1. A first scan with three agents: JSON and reply length, fault records and loops, fine-tuning.
2. A deep pass with four agents: Flint and LM Studio, the installed stack, fine-tuning on this hardware, and alternatives to GEPA. A fifth agent then re-checked the ten claims that most affect a decision against primary sources and local files, and listed contradictions and gaps.

All agents only read. None installed anything or sent a request to the model server, because bench baseline 1 was live. Local facts come from files on this PC. External facts come from repositories, official documentation, PyPI and issue trackers, checked on 26 October 2026.

## The problems

1. The Director's JSON replies sometimes fail to parse.
2. Some replies reach the 2,048-token cap.
3. Our client changes most refusals to `AI_RESPONSE_REJECTED` and does not keep the server's stop reason.
4. The Engineer sometimes repeats the same tool call.
5. The owner wants to fine-tune a model to Compertum's transcripts in the future.

GEPA changes only prompt text. It cannot fix code, server settings or model weights.

## Facts about Flint and the model server (checked)

- **Flint** is `RecursiveSI/flint`, Apache-2.0, trained from scratch: 39.8B total parameters, about 2.5B active per token, 49 layers, 256 experts with 6 selected, a 262,144-token context. Source: https://huggingface.co/RecursiveSI/flint
- **Shared experts: unresolved.** The model card says one shared expert. The GGUF header on this PC says `flint.expert_shared_count=2`. Our docs say 2, which matches the file. Do not change them until this is settled.
- **Flint has no thinking switch.** The model decides on each turn whether to reason. `enable_thinking` has no effect. Reasoning counts toward `max_tokens`. Source: the vendor's SGLang README on the model page.
- **Vendor sampling settings:** temperature 1.0, top_p 0.95, top_k 20. The vendor states "Greedy decoding is not validated."
- **Our settings:** 1,043 of 1,050 logged requests used temperature 0. `docs/BUILD_SPEC.md` (line 473) sets temperature 0 as the default for the local adapter. Line 326 says temperature zero is not a determinism guarantee. A change is the owner's decision.
- **Model server:** Bionic 1.1.9+6 (LM Studio), llama.cpp runtime 2.64.0 on build b11840. Flint support entered llama.cpp on 21 October 2026. Source: `C:\Users\bgonn\AppData\Local\Programs\Bionic\resources\app\package.json` and the backend folder under `C:\Users\bgonn\.lmstudio\extensions\backends`.
- **The reasoning budget works.** The per-model setting `reasoning.budgetTokens` is 512 and checked. The 25 October server log shows `"reasoning_tokens": 518` on 600 replies and none higher. Source: `C:\Users\bgonn\.lmstudio\apps\bionic\server-logs\2026-10\2026-10-25.1.log`.
- **Correction to the earlier diagnosis.** The capped Mathematician reviews were not long reasoning. Each of the three `length` stops had about 518 reasoning tokens and about 1,530 tokens of visible answer. So the answer was too long, and a length limit on the review task is the correct fix.
- **Structured output with reasoning is uncertain on this server.** LM Studio issues 1698 (JSON lands in `reasoning_content`), 1783 (grammar may force `{` first), 1974 (budget), 1990, 2222 and 2413 (`reasoning_effort` ignored) are all open. The vendor's own SGLang setup constrains only the answer after `</think>`. Whether Bionic does the same for Flint is not confirmed.
- **Per-request budget:** Bionic's bundle contains validation text for a `thinking_budget_tokens` field. Whether it reaches the engine is not tested.
- llama.cpp issue 31000 (open) reports that Flint can put a tool call inside its reasoning. It was seen on a different build (NVFP4, b11823). Its effect on our Engineer is not confirmed.

## Facts about our own code (read from the source)

- **Installed versions:** deepagents 0.7.32, langchain 1.4.7, langchain_core 1.7.0, langchain_openai 1.7.2, langgraph 1.2.17, openai 3.37.0, gepa 0.1.4. All MIT.
- **Hidden refusal codes.** In `src/compertum/ai/models.py`, `_complete` checks `finish_reason` before it reads `usage`. A `length` stop raises `AI_RESPONSE_INCOMPLETE`. The `except RuntimeRefused` block then raises `AI_RESPONSE_REJECTED`. So the specific code, the stop reason and the token counts are all lost for a truncated reply. The same block hides `AI_RESPONSE_INVALID`, `AI_TOOL_EXECUTION_DENIED`, `AI_USAGE_BOUND`, `AI_RESPONSE_BOUND` and the codes from the secret check.
- **The LangChain message** that `LedgerChatModel` in `roles.py` builds has no `finish_reason` and no `usage_metadata`.
- **Tests that name the old code** and must change with fix 1: `tests/test_ai_models_interface.py` (near lines 150, 159 to 161 and 190) and `tests/test_engine_roles.py` (near lines 424 to 428).
- **No structured output today.** The client sends no `response_format`. `LedgerChatModel` refuses a forced `tool_choice`, so LangChain's `with_structured_output` cannot work through it as it is.
- **Loop guards.** Our `_guard_repeats` in `roles.py` is the only identical-call detector in the stack. The installed LangChain middleware only counts calls.
- **Telemetry.** `src/compertum/ai/engine/__init__.py` turns LangSmith tracing off and removes provider key names before any LangChain import.

## Tools, by problem

### Problems 1 and 2: JSON and reply length

| Tool | License | Windows / Python 3.14 | Fit |
|---|---|---|---|
| LM Studio `response_format` with `json_schema` | LM Studio terms; llama.cpp MIT | yes / our code | Good for valid JSON, after one owner-started test with Flint, because of the open reasoning bugs |
| Instructor | MIT | pure Python; Windows not stated | Good: schema check with a bounded retry. Our own parser and retry already do the same, so it adds little |
| json_repair | MIT | pure Python | A last fallback only; log every repair as a fault |
| BAML | Apache-2.0 | `win_amd64` wheel | Possible: reads reasoning then JSON, but adds its own schema language; telemetry not confirmed |
| Outlines | Apache-2.0 | requires Python below 3.14 | Poor: it also replaces the inference engine |
| XGrammar, llguidance, Guidance, LM Format Enforcer | Apache-2.0 or MIT | some Windows wheels | Poor: they constrain inside the engine, not through LM Studio |

### Problem 3: fault records and traces

| Tool | License | Windows / Python 3.14 | Fit |
|---|---|---|---|
| Our own client (fix 1) | ours | yes | The only path that records the stop reason. Needed in every case |
| OpenTelemetry SDK with `openinference-instrumentation-langchain`, `ConsoleSpanExporter` to a file | Apache-2.0 | pure Python / supports 3.14 | Good later: standard spans in a local JSONL file, no server |
| mlflow-skinny or mlflow-tracing | Apache-2.0 | likely / used by GEPA on 3.14 | Possible: telemetry on by default (`MLFLOW_DISABLE_TELEMETRY=true`), and the setting does not reach child processes with an empty environment |
| mlflow 3.17.2 (full) | Apache-2.0 | wheels exist | Heavy: it would downgrade pyarrow 26 and pins langchain at 1.4.3 or lower |
| Arize Phoenix | Elastic License 2.0 | not confirmed | Strong, but the license is not open source; telemetry on by default |
| Langfuse (self-hosted) | open core | needs Docker and several databases | Poor on this host |

### Problem 4: loops

| Tool | Fit |
|---|---|
| Our `_guard_repeats`, `ENGINE_NO_PROGRESS` guard and step limit | Keep. Nothing installed detects identical calls |
| `ToolCallLimitMiddleware(tool_name="run_job", run_limit=k, exit_behavior="error")` through `create_deep_agent(middleware=...)` | Optional: a per-tool cap on expensive sandbox jobs, with a fault code |
| `ModelCallLimitMiddleware` | Not needed: it duplicates the step limit |
| `ModelRetryMiddleware`, `ToolRetryMiddleware` | Reject: they retry every exception, including our refusals, use up the request limit, and can hide the code |
| LongGuard 0.1.4 (MIT) | Too new (first release 5 September 2026) |

### Problem 5: fine-tuning

- **Flint cannot be fine-tuned on this PC.** Its 16-bit weights are about 80 GB, the publisher includes no Transformers model code, Unsloth has no Flint support, and the GPU has 16 GiB.
- **Hardware:** NVIDIA GeForce RTX 5070 Ti, 16 GiB, Blackwell (compute capability 12.0), driver 617.42.
- **No new administrator rights are needed.** Visual Studio Build Tools 2022 and 2026 with C++ tools, and CUDA Toolkits 12.8 to 13.4, are already installed. PyTorch pip wheels carry their own CUDA runtime. triton-windows states that it needs no administrator rights. The Unsloth installer warns against running as administrator.
- **Software path (pip wheels):** torch 2.14.1 with CUDA 13.0 (cp313 and cp314 wheels), bitsandbytes 0.50.2 (Windows, includes sm_120), triton-windows below 3.9, and `unsloth` 2026.10.8.
- **Licenses:** `unsloth` core is Apache-2.0. `unsloth-zoo`, a required dependency, is LGPL-3.0. Unsloth Studio, an optional interface, is AGPL-3.0. The owner should accept these before an install.
- **Python:** the core package allows Python 3.9 to 3.14, but Unsloth Studio and its installer need 3.11 to 3.13. Use a separate training environment, never `.cache/engine-env`. Our earlier `0xC0000135` failure with uv-managed CPython may also matter here (see the engine environment notes).
- **Memory:** 4-bit QLoRA needs about 5 GB for 7B, 6 GB for 8B and 8.5 GB for 14B models (Unsloth's minimums). Long transcripts need more. Unload Flint first; training is a heavy job.
- **Candidate models for the Engineer role** (all Apache-2.0 unless stated): Qwen3.5-9B, Qwen3-14B (ready 4-bit version), Gemma 4 12B, Ministral 3 14B Reasoning (has the same reasoning cap risk), Qwen2.5-Coder-14B, Phi-4 (MIT). Tool-calling quality must be tested on our tasks.
- **Data:** published results suggest 500 to 1,000 checked, varied transcripts for a useful first adapter (FireAct, LIMA). Risks: the model can learn quirks of the synthetic markets, and repeated training on its own outputs can lower quality. Bench, holdout and vault data must never be training data.
- **Path back to LM Studio:** merge the adapter, convert with llama.cpp's `convert_hf_to_gguf.py`, quantize with the prebuilt `llama-quantize`, and import with `lms import`. LM Studio has no option to load a separate LoRA file. Running `llama-server` directly would be a second model server and needs the owner's OK.
- **Storage:** torch, CUDA wheels and model weights need tens of GiB. A training environment must fit the storage budgets; no estimate exists yet.

### Alternatives to GEPA

- **GEPA 0.1.4 (15 July 2026) is the latest release.** Keep it.
- **DSPy 3.4.1** (MIT; MIPROv2 and SIMBA) adds few-shot example selection, but it needs LiteLLM (which fetches a price map from GitHub unless `LITELLM_LOCAL_MODEL_COST_MAP=True`) and a rewrite of the roles as DSPy modules. Not now.
- **TextGrad** looks stale (last release March 2025).
- **Code-evolution systems** (OpenEvolve 0.4.0, Apache-2.0; ShinkaEvolve, Apache-2.0): they evolve code against a fixed evaluator, which fits a fixed judge, but neither isolates the code it runs. Use only inside the section 19 sandbox, with every scored candidate counted as a trial. Not before M5.

## Contradictions the checker resolved

1. The reasoning budget does apply to API requests (log evidence).
2. Keep our repeat guard rather than replacing it with middleware. A `continue` exit would give no fault code.
3. Usage counts are kept only for completed replies, not truncated ones.
4. `reasoning_effort` exists in the API, but its "off" value has an open bug, and its effect on Flint is not confirmed.

## Open questions

1. Does Bionic's `json_schema` grammar for Flint start after `</think>`, or force `{` first? One owner-started test settles it.
2. Does Bionic forward `thinking_budget_tokens` per request? The same test settles it.
3. Should the engine use the vendor's sampling settings instead of temperature 0? This touches `docs/BUILD_SPEC.md`, so the owner decides.
4. Is Flint's shared-expert count 1 or 2?
5. Are the LGPL and AGPL licenses in the Unsloth path acceptable?
6. How much storage does a training environment need?
7. Which LM Studio release does Bionic 1.1.9+6 match? This decides whether fixes for the open issues are included.

## Recommendation, in order

1. Fix 1 in our client: keep the specific refusal code, read `usage` before the stop check, record `finish_reason` and the reasoning token count, and pass both into the LangChain message. No new package.
2. Fix 2: a length limit in the review task. The research confirms that the visible answer, not the reasoning, filled the cap.
3. One small owner-started test on Flint, when the server is free: one Director request with `response_format` `json_schema`, and one with `thinking_budget_tokens`. It settles open questions 1 and 2. Until then, keep the strict parser and the one retry.
4. The owner decides on temperature: keep 0 as the spec says, or test the vendor's settings on the bench.
5. Saved transcripts (step S3), then fine-tuning a 9B to 14B model for the Engineer role with Unsloth in a separate environment, after the owner accepts the licenses and the storage cost.
6. Optional: a `run_job` call cap, and OpenTelemetry spans to a file.
