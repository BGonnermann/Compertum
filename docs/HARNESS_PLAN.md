# Harness plan: one console that starts, runs, reports and improves

Status, 25 October 2026: plan only. The owner said not to start now. No code exists for this plan.

## Goal

One program that the owner opens once. It starts the model, runs the engine, reports, and later helps improve itself.
It stays as small as possible. It grows one small piece at a time, with the project.

## What exists today

- **Vesper core.** The folder `C:\Users\bgonn\Desktop\v harness\vesper_core` holds 709 lines of Python. It has its own git repository.
  It uses only the standard library. It has a task loop with a step limit, a time limit and Ctrl+C.
  It accepts only loopback model addresses. It reads one checked config file. It refuses a workspace that holds its own code, config or Python.
  It has no tools yet. Its own plan adds workspace tools in Step 2 and permission rules in Step 3.
- **Legacy Vesper.** The folder `vesper_harness` in the same repository holds 9,279 lines.
  It adds providers, plugins, skills, a full terminal screen and sessions. This plan does not merge it.
- **Compertum pieces.** `practice.py` runs the engine. `control.py` holds the owner commands.
  `tools\practice.ps1` loads the model and runs. `tools\engine_tail.py` watches a run. The daily summaries are in `state/engine/`.

## Decision 1: how to merge

1. **Use Vesper core as a library. Recommended.** The Compertum console imports `ModelClient`, `Agent`, `Display`, the endpoint check and the config check.
   It has its own main loop of about 60 lines. The Vesper repository stays unchanged.
   Vesper core can keep growing in its own place. Compertum keeps its own tools and rules.
2. Copy the 709 lines into Compertum. Two copies drift apart. Not recommended.
3. Add Compertum commands inside Vesper core. This ties Vesper to one project. Not recommended.

One constraint: Vesper core refuses a workspace that holds the Python that runs it.
The engine environment is inside the Compertum folder. So the console workspace is a small separate folder, for example `state/console`.
The console reaches the rest of Compertum only through its fixed tools.

## Rules that stay fixed

- The owner starts every run, with explicit limits. The assistant may propose a run. The owner confirms each one.
- Loopback model addresses only. New spending stays $0. No API providers.
- Nothing in the console may change the judge, the Auditor, the baseline, the vault, the data tiers, the ledger or the rules.
- The assistant has only the tools in a fixed list. A power that is not a tool does not exist for it.
- The console writes a short command log under `state/console/`. The engine ledger stays the only record of runs.
- No background service and no schedule.

## Stages

Each stage is small, has tests and one review, and needs the owner's OK before the next.

1. **Console without a model.** One command opens it. Slash commands replace the separate PowerShell steps:
   `/status`, `/models`, `/load`, `/unload`, `/run`, `/gepa`, `/watch`, `/stop`, `/report`, `/apply-prompts`.
   The model lifecycle moves from `practice.ps1` into Python. The memory floor check stays.
   Add a **preflight check**: before a run, build each role task from fixture data and refuse if it holds an unfilled placeholder, an empty section or missing content.
   This would have caught the missing specification of 24 October 2026.
   Done when: one command replaces `practice.ps1`, and the preflight refuses a task with a placeholder in a test.
2. **Read-only assistant.** The model answers questions about runs, for example "why did cycle 24 fail?".
   Its tools only read: list runs, read a summary, read a bounded part of the ledger, show failure counts.
   `/report` groups failures by class, such as repeated reads, no run, or a missing signal file.
   Limit: the model server has one prediction slot. The assistant answers between runs, or from the ledger alone while a run is active.
3. **Propose and confirm.** The assistant can propose `run 8 cycles, 400 requests`. The console shows the exact limits and waits for the owner's `y`.
   The proposal cannot pass the owner's hard maximum for requests.
4. **Wider GEPA surface.** Move the editable text into versioned files: the Engineer's starter program, the task wording, the tool descriptions.
   Code that builds a task reads those files and refuses a missing or broken placeholder.
   `/improve` runs GEPA over only those named files. It writes candidates. The owner applies one with `/apply`.
5. **Real data.** Connect the Validator to real historical bars from the existing read-only Alpaca access. This is a separate engine stage with its own approval.

## What this plan does not build

- No plugins, no skills, no providers, no sessions of the legacy harness.
- No Deep Agents inside the console. The assistant uses Vesper's 138-line loop. Deep Agents stays in the engine for the Engineer role.
- No GEPA over harness code. GEPA improves text only. Code changes stay with the developer, with tests and a review.

## Open questions for the owner

1. Is Decision 1, option 1, right: Vesper core as a library, no change in the Vesper repository?
2. Which comes first when work resumes: the console or real data?
3. Should the console command be called `compertum`?
