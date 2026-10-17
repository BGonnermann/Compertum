# Live activity in the Compertum Hub

The Hub reads current agent events, native Windows processes, and explicit job receipts.
Open Current work for activity. Open Whole loop for the full route and each stage's observations.
Live observations refresh every two seconds while visible. Saved documents refresh every ten seconds.
If a connection fails, the page marks retained observations stale.

## What each source establishes

| Source | What it establishes | What it does not establish |
| --- | --- | --- |
| Current project agent events | Recent turn, tool, file-change, and command-exit observations | Unreported work, complete transcript history, or milestone acceptance |
| Native process metadata | An accessible project process with a current creation identity | Successful completion, CPU activity, or financial qualification |
| Explicit job receipt | The reporting wrapper's current child identity, heartbeat, stage, and observed exit | Permission to run a command or accept a strategy |
| Saved checkpoint | The latest declared engineering state and its source time | Current process or chat activity |

The native observer reads accessible 64-bit Windows process metadata without elevation.
It binds a process to its actual working directory and creation time. It does not display command text.
A vanished process becomes an unknown outcome. Only an actual exit receipt supplies an exit code.
An unfamiliar process remains a generic project process. The Hub does not guess its business role.

Agent observations use recent local Codex session records for this exact project folder.
The reader exports fixed labels and timestamps. It never serves prompts, reasoning, messages, command bodies, or tool output.
Other project records are excluded after their project identity is checked.
The local record format can change. Unsupported or incomplete records give partial coverage.
A working agent without a signal for 90 seconds becomes stale. Pending tools are not proof of successful tests.

## Give a trusted job an explicit stage

Use this only for an already authorized command. The wrapper adds reporting; it grants no operating or account authority.
Existing job limits, financial gates, saved stops, and one-heavy-job rules still apply.

For the Hub's own small checks:

```powershell
python -B hub/run_job.py --stage verification -- python -B -m unittest discover -s hub/tests -v
```

The default kind is `engineering`. Engineering work never makes an operational stage running or accepted.
For a separately authorized operational job, select its exact stage and `--kind operational`.
Never use that option to relabel a fixture, test, or unqualified paper action.

The supported operational stages are data, quality, proposals, experiments, mathematics, development_audit,
final_evaluation, independent_audit, qualification, authorization, signals, risk, intentions, execution,
reconciliation, reports, and feedback.

The wrapper writes a small receipt outside the repository, under the current user's `.codex/visualizations/compertum-live-<project-hash>/jobs` folder.
It retains at most 64 job slots, with eight KiB per record. It preserves completed and failed receipts.
When those slots are full, it refuses another launch through that wrapper. Choose an evidence-preserving archive or new folder deliberately.
It never removes old evidence or silently turns an unavailable reporting source into a passing result.
The Hub reads the default project folder. A custom `--event-folder` is useful for isolated checks and is not automatically exposed.

## Whole-loop meaning

The diagram includes branches, independent audits, owner approval, risk, reconciliation, and feedback.
Mathematics is a parallel branch. Reconciliation returns to current risk checks.
Dashed connections identify unfinished proposal dispatch and research feedback.

A stage without an explicit operational event stays Not observed.
A completed stage job shows its recorded exit and time in the details. That does not complete the milestone.
The existing product does not yet publish all operational stage events. The page makes this missing connection visible.
Connect each trusted producer before relying on the diagram for supervised operational coverage.
The Hub never starts the product or imports its runtime to manufacture an observation.
