# Base-model comparison for the quant-research assistant

Owner request, 2 November 2026: compare three open-weight models as the base for a quant-research assistant that we will fine-tune later.
Target hardware: one RTX 5070 Ti with 16 GB (16,303 MiB). The host has this card. Owner: "text only no images."
Results: `reports/BASE_MODEL_COMPARISON.md`. Raw outputs stay outside Git in `.cache/test-runs/base-eval-20261102/`.

## Models and files

All files come from Hugging Face. They are stored in `D:\models\hf` and linked into LM Studio with `lms import --symbolic-link`. Each SHA-256 matched the Hugging Face record.
No vision projector (mmproj) file was downloaded, so every model ran text only.

| Setup | Repository | File | Bytes |
|---|---|---|---|
| gpt-oss-20b | lmstudio-community/gpt-oss-20b-GGUF | gpt-oss-20b-MXFP4.gguf (native MXFP4) | 12,109,565,632 |
| Gemma 4 26B-A4B | lmstudio-community/gemma-4-26B-A4B-it-QAT-GGUF | gemma-4-26B-A4B-it-QAT-Q4_0.gguf (Google QAT weights) | 14,439,363,264 |
| Qwen3.6-35B-A3B, 3-bit | unsloth/Qwen3.6-35B-A3B-GGUF | Qwen3.6-35B-A3B-UD-IQ3_S.gguf | 13,676,723,168 |
| Qwen3.6-35B-A3B, 4-bit, CPU offload | lmstudio-community/Qwen3.6-35B-A3B-GGUF | Qwen3.6-35B-A3B-Q4_K_M.gguf | 21,166,757,728 |

Engine: LM Studio, llama.cpp CUDA 12 runtime 2.67.0, one prediction slot. The owner approved the LM Studio server start for this job.

## Settings, the same for every model

- Temperature 0. Context 32,768 tokens for the scored items. Each reply is limited to 16,384 tokens. At most 12 model turns per item.
- One system prompt (`SYSTEM` in `tools/base_eval/run.py`) and one tool, `python`, with one argument, `code`.
- Reasoning on:
  - gpt-oss: the line `Reasoning: high` before the system prompt. Measured: "low" gave 313 completion tokens, the default 489 and "high" 814 on one question. The `reasoning_effort` request field had no effect in LM Studio.
  - Gemma 4: LM Studio returns a thinking block by default, also when tools are offered. The `<|think|>` tag and `enable_thinking` changed little, so no prefix was used.
  - Qwen3.6: thinking is on by default.
- Every `python` call and every hidden test runs in the section 19 AppContainer sandbox (`compertum.runtime.sandbox`), after `verify_sandbox` with the engine's fixed targets and a named pipe. The sandbox Python has the standard library only, so every task says so.
- The 4-bit Qwen ran with LM Studio GPU offload 0.7. At 0.75 it filled the card (15,962 MiB), and at 0.8 generation fell to 15 tokens per second.

## Measurements

- Fit: GPU memory after loading at a given context (`nvidia-smi`, the card shows 0 MiB when nothing is loaded). Maximum context: the largest tested context at which generation speed stays at the 8K level. Past that point the driver spills to shared memory and speed falls by 3 to 5 times.
- Speed: LM Studio's own statistics (`/api/v0/chat/completions`), batch 1, 8K context. Prompt processing: about 3,000 prompt tokens divided by time to first token. Each run uses a different prompt, so the prompt cache cannot help. Generation: 512 tokens. Three runs; the median is reported. The first run is a warm-up and is slower.

## Items (`tools/base_eval/items/`)

- Coding: 10 tasks with hidden tests (`coding/tests`), graded in the sandbox. Each reference solution passes every check, and 18 deliberately wrong solutions each fail at least one check.
- Finance maths: 20 FinQA-style table questions (`finqa/questions.json`). The final `ANSWER:` must match within 1% relative. `finqa/verify.py` checks every answer from its arithmetic program.
- Research judgment: 6 studies (`judgment/items.json`): look-ahead, survivorship, data snooping, no costs, in-sample only, and one clean study.
- Honesty: 5 prompts where the right answer is "cannot conclude" or "need more data".
- Synthetic market: `market.py` makes two seeded series of 3,000 days. m1 has a planted signal (x today predicts the next return, t = 3.2 on training rows, 2.6 on test rows). m2 is noise.
- Rubrics: `judgment/rubric.md` and `market_rubric.md`.

## Grading

- Coding and finance maths are graded automatically: `python tools/base_eval/run.py grade --out DIR`.
- Judgment, honesty and market answers are packed with `run.py pack`. Each setup gets a random letter, and the key is kept apart. One grader that does not know the letters scores every packet with the rubrics.
- The packet lists numbers in the answer that appear neither in the prompt nor in any tool output (`untraced_numbers`). The grader checks each one before it marks an answer as invented.

## Commands

    lms server start --port 1234
    python tools/base_eval/run.py fit --label NAME --model KEY --out DIR --contexts 8192,16384,...
    python tools/base_eval/run.py speed --label NAME --model KEY --out DIR --context 8192 [--gpu 0.7]
    python tools/base_eval/run.py tasks --label NAME --model eval --out DIR --extra "{\"max_tokens\":16384}" [--prefix "Reasoning: high"]
    python tools/base_eval/run.py grade --out DIR
    python tools/base_eval/run.py pack --out DIR

Use the engine environment (`.cache/engine-env`). Set `PYTHONIOENCODING=utf-8`, because `lms` prints progress characters.
