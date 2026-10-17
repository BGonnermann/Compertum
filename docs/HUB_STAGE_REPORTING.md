# Mathematics, qualification, signals, and feedback reports

These four reporting interfaces are implemented. The Hub reads their receipts every two seconds while visible.
A stage without a report says No report received. This does not mean that its calculation or operational program has run.
The interface does not implement missing operational signals, financial qualification, or automatic research feedback.
It never starts those programs. Product source, installed packages, runtime journals, and original identities remain unchanged by this reporting feature.
Existing frozen native workers are not modified. Work that does not use the reporting interface or job wrapper cannot provide these internal-stage events.

## Existing authorized jobs

The existing `hub/run_job.py` wrapper now publishes stage reports for these four stages automatically.
Select the stage that matches the actual authorized work. Its default work type is engineering.
Keep using the original command, resource limits, and approval requirements.
Do not label a test or fixture as operational. A report cannot grant authority or financial acceptance.

The supported stage names are `mathematics`, `qualification`, `signals`, and `feedback`.
The wrapper binds each report to its actual child process and observed exit.
If a report write fails after launch, the child keeps running and returns its actual exit code.
The original 64-job prelaunch receipt limit remains. A full job namespace still refuses a new wrapper launch.
No job, calculation, model, or operational loop starts from the Hub page.

## Progress inside an existing program

An authorized Python program can use `StageReport` from `hub/stage_reporting.py` around its existing work.
Make that module available in the program's normal module search path. Do not change a frozen native worker's environment or identity.
Pass the actual project directory. The report binds to that directory's Windows identity and the current process identity.
Use `update` only for counts the program actually measured. Do not send names, symbols, prices, prompts, exceptions, or free text.

| Stage | Allowed progress fields | Additional reported outcomes |
| --- | --- | --- |
| Mathematics | checks_completed, checks_total, counterexamples | Counterexample found |
| Qualification | checks_passed, checks_failed, checks_total | Rejected |
| Signals | signals_count, blocked_count, items_checked | No signal |
| Feedback | items_reviewed, revisions_requested, items_total | Revision requested, No change |

Each progress value must be an integer from zero through one billion. Boolean values are rejected.
All stages also support Completed, Failed, Interrupted, and Blocked.
Use `finish` for a specific outcome. Otherwise, normal scope exit reports Completed.
An exception reports Failed and remains the original exception. Its text is never serialized.
A keyboard interruption reports Interrupted. An error after an explicit finish still records the failure.

This example belongs inside an already authorized program with its existing checks. It is not a new job instruction.

```python
from stage_reporting import StageReport

with StageReport(project_root, "mathematics") as report:
    for completed, check in enumerate(existing_checks, 1):
        check()
        report.update(checks_completed=completed, checks_total=len(existing_checks))
```

The default work type is `engineering`. A separately authorized operational producer can identify its report as `operational`.
That field describes the producer's declared work type. The Hub never treats it as permission or accepted financial evidence.

## Meaning and limits

A Running report needs a matching native process identity and a heartbeat no older than eight seconds.
A missing process gives Process not verified. A late heartbeat gives Stale observation. Neither becomes a successful result.
Completed means the producer reported completion. The wrapper's job receipt separately retains its actual child exit code.
Blocked, Rejected, No signal, and Revision requested remain distinct. They do not approve a candidate or continue the loop.

The publisher writes only small receipts outside the repository in the existing project-specific visualization folder.
It retains 32 operations per stage, with eight KiB per receipt. The reader displays the latest 12 reports per stage.
Completed and failed receipts remain preserved. No automatic deletion or archive job is added.
If all slots are used or reporting becomes unavailable, the reporting interface warns and lets the original work continue.
The Hub does not create a reporting folder when it reads. Missing and invalid sources remain explicit.
Only fixed states, work types, identities, timestamps, and allowed progress counts reach the page.
