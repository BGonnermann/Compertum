# Harness plan: a Compertum variant of Vesper core

Status, 25 October 2026: plan only. The owner said not to start now. No code exists for this plan.

## Owner direction, 25 October 2026

- Make a Compertum variant of the v harness. Same style as the v harness.
- No barriers, in the way the pi harness has none: a few plain tools, no permission popups.
- Keep it barebones. It grows with the project, one small piece at a time.

## Owner direction, 26 October 2026: GEPA as the main improvement tool

The owner read GEPA's `optimize_anything` post (https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) and agreed: "we can use it for our eventual harness, the tools, and really anything we think it can work on."

- `optimize_anything` is in the installed GEPA 0.1.4 (`.cache/engine-env/Lib/site-packages/gepa/optimize_anything.py`). It searches over any text artifact with a user-supplied evaluator. It accepts a callable reflection model, so it runs on Flint through our ledgered client. Its default reflection model is a cloud model name, so every call must pass our own.
- Prompts, skills and task wording: GEPA searches and scores them. The owner applies the winners.
- The harness and its tools: GEPA may propose changes. No proposal is applied automatically. Each one becomes an ordinary code change with tests, review and the owner's OK, because harness code runs outside the sandbox.
- Strategy code: only inside the section 19 sandbox, and every scored candidate counts as a trial.
- Never a target: the judge (Validator, deflation gate), the Auditor, the vault, the ledger, the rules, and the evaluator of the search itself.
- GEPA cannot fix code bugs, server features or model weights. Those stay ordinary work (`docs/HARNESS_TOOLS_RESEARCH.md`).

## What the base is

- **Vesper core.** The folder `C:\Users\bgonn\Desktop\v harness\vesper_core` holds 709 lines of Python.
  It uses only the standard library. It has a task loop with a step limit, a time limit and Ctrl+C.
  It accepts only loopback model addresses. It reads one checked config file.
  It has no tools yet. Its own plan adds workspace tools in Step 2.
- **The variant.** Copy the 709 lines into Compertum as a new package. Keep the style: small files, plain code, no dependencies.
  The copy is the owner's choice. The v harness repository stays unchanged. Later fixes in one place are copied by hand to the other.
- **Legacy Vesper.** The 9,279 lines in `vesper_harness` are not copied.
- **Pi.** Pi is a minimal terminal agent. It gives the model four tools: read, write, edit and bash. It has no permission prompts.
  It adds other features through small extensions. This plan follows the same idea.

## How "no barriers" fits the owner's rules

Pi has no prompts and no box. Compertum has rules that the owner wrote in `AGENTS.md`.
The two fit together if the barrier is a box, not a prompt.

- **Free inside the box.** The model gets four tools: read, write, edit and run. No question is asked before any of them.
  The `run` tool runs in the section 19 sandbox, the AppContainer that already denies reads and writes outside its folder.
  The sandbox was tested against 16 probe targets that include the judge, the Auditor and the ledger.
  So the model can try anything, and the fixed parts stay out of reach.
- **Why not a plain bash tool.** `AGENTS.md` says AI-written code runs only in the section 19 sandbox.
  A bash tool on the host would break that rule. A run tool in the sandbox keeps it.
- **Owner commands.** The owner types `/run`, `/stop` and the other commands. Those are the owner acting, not the model.
- **Reading results.** The sandbox cannot see the ledger. So the model gets a few fixed read-only tools for results.
  They list runs, read a summary and read a bounded part of the ledger. They cannot write.
- **New tools.** A new tool is a small file. The developer adds it by a commit, with a test.
  A tool written by the model is code that runs on the host, so it is reviewed before it loads.

One rule stays as it is until the owner changes it: `AGENTS.md` says the owner starts each run.
So the model cannot start a run by itself. See "Decisions".

## Stages

Each stage is small, has tests and one review, and needs the owner's OK before the next.

1. **The variant, no model needed.** One command opens the console. The model, the memory check and the runs start from slash commands:
   `/status`, `/models`, `/load`, `/unload`, `/run`, `/gepa`, `/watch`, `/stop`, `/report`, `/apply-prompts`.
   This replaces `tools\practice.ps1` and the separate PowerShell commands.
   `/watch` is required (owner request, 25 October 2026). It shows one progress line: cycle n of N, requests used of the limit, elapsed time, the current step and the free memory.
   Under it, each model call shows a clock time, the role, the seconds, the prompt and completion tokens, the tokens per second and the tool called.
   The ledger stores no clock time for a model call today, so stage 1 adds one.
   `/watch` also flags a completion near the 2048 request limit, because a cut-off reply fails.
   Add a **preflight check**: before a run, build each role task from fixture data and refuse if it holds an unfilled placeholder, an empty section or missing content.
   This would have caught the missing specification of 24 October 2026.
2. **The four tools.** Read, write, edit and sandbox run, plus the read-only result tools. The model can then work and answer questions about runs.
   `/report` groups failures by class, such as repeated reads, no run, or a missing signal file.
   Limit: the model server has one prediction slot. The model answers between runs, or from the ledger alone while a run is active.
3. **Wider GEPA surface.** Move the editable text into versioned files: the Engineer's starter program, the task wording, the tool descriptions.
   `/improve` runs GEPA over only those files. It writes candidates. The owner applies one with `/apply`.
4. **Real data.** Connect the Validator to real historical bars from the existing read-only Alpaca access. This is a separate engine stage.
   It waits until runs on the synthetic market show that the engine works end to end.

## What this plan does not build

- No plugins, skills, providers or API models. Loopback models only. New spending stays $0.
- No Deep Agents inside the console. The console uses the 138-line Vesper loop. Deep Agents stays in the engine for the Engineer role.
- No GEPA over harness code. GEPA improves text only. Code changes stay with the developer, with tests and a review.
- No background service and no schedule.

## Decisions

1. Should the model be able to start runs by itself? The simple answer today is no: the owner types `/run`.
   If the owner says yes later, `AGENTS.md` must change first. Then the owner sets the limits in advance, such as at most 8 cycles and 400 requests.
2. Order of work: the harness first, real data after practice runs 11 and 12 show a working Engineer.
   This is the developer's recommendation. The owner can reverse it.
3. The console command is called `compertum`, unless the owner names another.
