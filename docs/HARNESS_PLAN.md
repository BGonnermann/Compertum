# Harness plan: a Compertum variant of Vesper core

Status, 28 October 2026: the minimum harness is implemented in `src/compertum/harness`.
The owner started it after agreeing the minimum target in this session.

The console opens without a model request. It supports local models and owner-listed providers through the existing provider checks.
Harness 0.5 has six tools: read, write, edit, search, bash and sandbox run. The model receives no run-start tool.
Owner decision, 28 October 2026: `bash` runs Git Bash commands on the host, as in the pi agent. `AGENTS.md` records this exception.
The shell gets no variables with key, token, secret, password, credential or auth in their names. Provider key variables are also removed.
The shell could still read keys from the registry, so this removal is a safeguard, not a boundary.
Bash output keeps the first 4 KiB and the last 24 KiB. Lines that match common secret formats are hidden; the list is not complete.
Each command runs in a Windows Job object. Every process it started, including background processes, ends when the command ends.
Commands time out after 1 to 600 seconds. Ctrl+C stops a command within 0.2 seconds. Bash waits while an owner-started run holds the job slot.
Bash bypasses the read, write and edit path protections. The system prompt forbids pushing, installing, engine runs and credential reads.
`search` finds regular-expression matches with file and line numbers. It skips Git-ignored files and the protected folders.
Hard refusals protect credentials, runtime state, fixed code and rules. YOLO removes prompts, not these boundaries.
Sessions are append-only under `state/harness/sessions`. Run records and logs stay under `state/harness/runs`.
A new console can recover a live process only when its process number and creation time match. A dead process is marked `LOST`.
The owner starts tests, practice, bench and GEPA with slash commands. Engine commands require cycle, request and hour limits.
The interactive composer draws a box and shows matching commands. Tab inserts editable usage templates and completes identifiers.
Up/Down scrolls through six visible commands. Descriptions share one aligned column. Blank rows separate the box, the list and the example.
The selected command shows a concrete example. Narrow terminals show its description above the example. Tab inserts the selection.
The composer width follows the terminal. It detects resizing and redraws from the frame start without leaving old borders.
Long input scrolls horizontally without changing the box width. Unchanged frames produce no output.
Harness 0.3.4 waits for Windows console key and resize events instead of polling every 50 milliseconds.
Each frame is one synchronized-output write. A stable frame rewrites only its changed rows. A resize or a taller frame still uses a full redraw.
Modified navigation keys, Alt+letter and Shift+Tab stay ignored, as they were with keyboard polling. AltGr characters still type.
The editor supports backspace, delete, arrows, Home and End. Scripted input keeps the original plain prompt.
Harness 0.4 shows each tool step as a short line, such as `● Edit src/x.py`. Edits and writes show a coloured diff with line numbers.
The diff is display only. The model still receives the short tool result. A changed region over about 200 by 200 lines shows a summary.
A spinner shows the step and elapsed time while the model or a tool works. The Windows Terminal tab shows a busy ring and a working title.
Control characters from the model, files and programs appear as visible escapes. They cannot write to the clipboard or change the terminal.
The `/watch` command returns one uniform run card. The `/report` command adds a bounded log tail.
The owner can dismiss a terminal or unverifiable record with `/clear RUN_ID`. Dismissal never stops a process or deletes evidence.

Harness 0.3 adds model selection without a restart. `/model` shows the selection and configured model files without a request.
`/model NAME` selects a model file's default. `/model NAME MODEL_ID` selects an exact model. `/model MODEL_ID` uses the active model file.
A NAME that matches a model file takes precedence. Use the three-part form to select an identical model ID explicitly.
`/models` lists IDs from the active endpoint. `/models NAME` lists another endpoint without changing the selection. Neither sends a completion.
Selection preserves the conversation and changes future engine-run defaults. A failed selection leaves the active model unchanged.
Tab completes model-file names and IDs cached by `/models`. Tab itself sends no request.
Harness 0.5.2 saves each `/model` choice in `state/harness/model.json`. A restart or `/resume` uses it; `--models` overrides it for one start.
The box title shows the active model. Selecting a model without its key variable shows a warning at once.
Tab leaves out optional `[...]` parts, so `/model` inserts `/model ` and never sends a bracket by mistake.
Harness 0.5.3: plain `/model` in the interactive console opens an arrow-key picker. Enter selects and saves; Esc keeps the model.
Harness 0.5.8 keeps every model ID the owner has used or listed in `state/harness/models-known.json`.
The picker shows them after restarts. A fresh `/models NAME` listing replaces that file's IDs, so removed models drop out.
Harness 0.5.7 refuses `/run`, `/gepa` and `/bench` while a Kimi model is selected. Kimi Code subscriptions are interactive-only.
Tasks default to 100 steps and 60 minutes, the highest allowed. `/limits STEPS MINUTES` changes them for the open console.
Any unexpected error now ends a task with an outcome. A failed session save shows a note instead of hiding the outcome.
Harness 0.5.6 sends no `temperature`, so each provider uses its default. Kimi `k3.1-pro` accepts only 1.
A refused request now shows the server's short reason after the HTTP status. The engine keeps its own fixed settings.
Harness 0.5.4 shows the picker as plain text without a box. It hides the text cursor and erases itself, so only the result line stays.
The picker lists each model file's default, the active model and IDs cached by `/models`. It sends no request.
It marks the current model and any model whose key variable is not set. Scripted input still receives the JSON listing.
Enter now erases the command menu, so only the box and the answer stay on screen.
The `/run` command now maps to the practice run kind. `/bench` uses only `-CyclesPerMarket`, as the wrapper requires.

Verification for harness 0.6.0: 108 product-environment unit tests passed, zero failed and zero skipped.
These tests use scripted local models and fake process runners.
The native lane passed four tests, zero failed and zero skipped. It covered real AppContainer execution, process-identity recovery,
real console typing and paste events, and spinner removal from a real console screen.

Harness 0.6.4: after Enter, the box is replaced by a one-line echo, `› task`. A finished box broke apart when the terminal was resized.
Inside Windows Terminal, `/watch` opens a read-only view in a split pane on the right, and focus returns to the harness.
The pane runs `python -m compertum.harness.pane`. It reads run records and the research store and never arms, stops or writes anything.
Press q in the pane to close it. Outside Windows Terminal, `/watch` keeps the inline view.
Harness 0.6.3: the terminal display uses the project map's palette: orange for marks and status, warm grey for detail.
A blank line separates the task box, thinking, each tool step, the answer, the result line and each command result.
Run cards align their keys and color status words. `/help`, the box, the command menu and the pickers have the same colors.
Scripts and logs still get plain text without blank-line spacing.
Harness 0.6.2: `/run`, `/gepa` and `/bench` start the engine run in its own hidden console.
The run also leaves the console's job object when that job allows it. So closing the Windows Terminal tab no longer ends the run.
A reopened harness finds the run again through its saved process identity. `/stop` still uses the kill switch.
`/test` runs stay tied to the console, because only an open console enforces a test deadline. Engine runs keep their own hour limit.
If a job forbids leaving, the run still gets its own console, but it ends when that job closes.
Harness 0.6.1: `/watch` without an ID opens a picker of runs, running ones first. It includes engine runs that
`tools\practice.ps1` started outside the harness. They are read from `state/research.sqlite` in read-only mode.
Enter opens a live view that refreshes every 2 seconds. Esc, Enter or q returns to the prompt, and the last snapshot stays.
The view shows status, cycles, requests, elapsed time and the last six cycles. Watching never changes or stops a run.
`/runs` also lists engine runs. Scripted `/watch` prints the newest running run's card.
Harness 0.6.0 fixes the owner's report and a bug hunt. Enter on the command menu runs the highlighted command.
A command that needs details gets its template first. A multi-line paste is one task. Esc clears the box.
Ctrl+A and Ctrl+E move to the start and end. Ctrl+Backspace deletes a word. Ctrl+Z quits only from an empty box. Emoji type.
Command names work in any case. Run notes keep apostrophes and paths keep backslashes. Missing details and placeholders get examples.
Ctrl+C during a slash command stops the command, not the harness. `/model` matches file names in any case and warns about unknown IDs.
Results print as labelled lines in a terminal. Scripted input keeps JSON. `/sessions` shows dates and first tasks.
A session file starts with its first task. `/watch` shows the newest run that was not dismissed. Finished run times stop.
The harness removes a kill switch that it set once the stopped run ends. A STOP file left by anyone else blocks engine runs with a clear message.
Run processes get no console input. Bare `/test` runs every `tests/test_harness_*.py` file.
Known limits (0.6.2 fixed the closed-tab limit for engine runs): wide characters can misalign the box.
Keys typed ahead while the harness is busy can count as a paste, so a typed-ahead Tab stays a tab. Up and Down have no prompt history.
An independent review found a client-switch test gap and small hardening items. The fixes and new regression checks pass.
A separate menu review found no blockers. Registry, wrap-around and changing-row cursor checks were added.
A separate interactive-code review found cursor and key-code defects. The fixes passed review with no blockers.
The owner's real interactive Windows Terminal check remains pending. Unit streams cannot emulate a physical console cursor.
Interactive mode enables terminal escape processing for the console session. It uses the plain prompt when that mode is unavailable.
An earlier LF-only output assertion failed on Windows CRLF. A later dead-process check also corrected the Windows error-channel read.
The exact DeepSeek console command opened and resumed `session-20261028-052057-dd2947b2`. Those checks sent no provider request.
The owner then completed a live DeepSeek smoke task. It read the goal, wrote `harness_smoke.py` and completed the sandbox run with exit code 0.
The owner-started `/test` command completed with 24 passed. Its run card showed `COMPLETED` and exit code 0.
An independent review found eight defects. The fixes are applied and regression-tested. The focused re-review found no blockers.
Long conversations still need `/new` when they reach the model packet limit. The harness records a clean refusal instead of losing the session.
Harness 0.5 replaces the reused 64 KiB event-record limit with a 512 KiB conversation limit, the owner's choice on 28 October 2026.
The secret scan still checks all local text, from the system prompt, the owner and the tools, before each request.
Every tool result, resumed message and new task passes the same rules first, so refused text cannot enter the conversation.
Model replies get only a size check, because they hold only what the model wrote. A search for a word such as password no longer ends a task. A note appears at 80 percent, and a full conversation reports `CONVERSATION_FULL`.

Remaining limits: no live engine run has started from this console.
Process deadlines re-arm after recovery, but a closed console cannot enforce a test-process deadline. Engine cycle, request and hour limits still apply.
The model has no ledger-reading tools yet. `/watch` does not yet show engine cycle, request, step or free-memory fields.
The minimum does not include `/load`, `/unload`, `/apply-prompts` or automatic failure grouping.

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
  Superseded on 28 October 2026: the owner chose a host `bash` tool, recorded as an `AGENTS.md` exception for this tool only.
- **Owner commands.** The owner types `/run`, `/stop` and the other commands. Those are the owner acting, not the model.
- **Reading results.** The owner uses `/runs`, `/watch` and `/report` for bounded results.
  The model has no ledger-reading tools in the minimum. Fixed read-only tools can come later.
- **New tools.** A new tool is a small file. The developer adds it by a commit, with a test.
  A tool written by the model is code that runs on the host, so it is reviewed before it loads.

One rule stays as it is until the owner changes it: `AGENTS.md` says the owner starts each run.
So the model cannot start a run by itself. See "Decisions".

## Original stages and current scope

The minimum implements the console and the four tools from stages 1 and 2.
It keeps `tools\practice.ps1` underneath. It does not replace that wrapper.
The existing engine preflight check protects every owner-started engine run.

Later work can add richer engine fields to `/watch` and fixed read-only ledger tools.
Later work can also group failures by class and add model-loading commands.
The wider GEPA surface and owner-applied text candidates remain separate stages.
Real-market manifests now exist from separate evaluation work. Retained-format fixtures verify their adapter.
The original Alpaca evidence files were not found. No actual Alpaca practice run has occurred.

## What this plan does not build

- No plugins, skills or unlisted providers. Local models and owner-listed DeepSeek providers are supported.
- No Deep Agents inside the console. Deep Agents stays in the engine for the Engineer role.
- No automatic GEPA changes to harness code. Code changes need tests and review.
- No background service and no schedule.

## Decisions

1. The model cannot start runs by itself. The owner types each run command.
2. The minimum starts with `python -m compertum.harness`. The existing `compertum` product CLI is unchanged.
