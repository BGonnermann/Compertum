import json
import sqlite3
from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest

from compertum.harness.cli import main
from compertum.harness.display import Display
from compertum.harness.editor import LiveView
from compertum.harness.engine_watch import duration, engine_card, engine_runs
from compertum.harness.runs import RunError


def store(root, runs):
    """Write a small research store with the two tables the watcher reads."""
    (root / "state").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "state" / "research.sqlite")
    con.execute("create table engine_bounded_runs (row_id text, run_id text, phase text, recorded_at text, record text)")
    con.execute("create table engine_cycles (cycle_id text, cycle_index integer, phase text, record text)")
    now = datetime.now(timezone.utc)
    for run_id, kind, minutes_ago, ended, cycles in runs:
        started = (now - timedelta(minutes=minutes_ago)).isoformat()
        start = {"run_id": run_id, "kind": kind, "started_at": started, "recorded_at": started,
                 "limits": {"cycle_limit": 100, "request_limit": 1000, "hour_limit": None},
                 "models": {"director": {"model": "deepseek-flash"}}}
        con.execute("insert into engine_bounded_runs values (?, ?, 'START', ?, ?)",
                    (f"{run_id}:START", run_id, started, json.dumps(start)))
        for index in range(cycles):
            record = {"run_id": run_id, "cycle_index": index + 1, "status": "COMPLETED", "requests_after": 10 * (index + 1),
                      "recorded_at": now.isoformat(), "hypotheses": [{"idea": f"idea {index + 1}: details"}],
                      "candidates": [{"deflation": {"status": "FAIL"}, "audit": {"label": "VERIFIED_PASS"}}],
                      "scores": {"h1": {"beats_baseline": index % 2 == 0}}}
            con.execute("insert into engine_cycles values (?, ?, 'END', ?)", (f"c{index}:END", index + 1, json.dumps(record)))
        if ended:
            end = {"reason": "CYCLE_LIMIT", "elapsed_seconds": 3725, "requests": 40}
            con.execute("insert into engine_bounded_runs values (?, ?, 'END', ?, ?)",
                        (f"{run_id}:END", run_id, now.isoformat(), json.dumps(end)))
    con.commit()
    con.close()


def project(tmp_path):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    entry = 'base_url = "http://127.0.0.1:1234/v1"\nmodel = "scripted"\n'
    (root / "config" / "models.toml").write_text("".join(f"[roles.{role}]\n{entry}" for role in
                                                         ("director", "researcher", "mathematician", "engineer")))
    return root


def test_running_first(tmp_path):
    root = project(tmp_path)
    assert engine_runs(root) == []
    store(root, [("run-old", "bench", 300, True, 4), ("run-live", "gepa", 42, False, 3)])
    runs = engine_runs(root)
    assert [item["run"] for item in runs] == ["run-live", "run-old"]
    assert runs[0]["status"] == "RUNNING" and runs[0]["cycles"] == "3 of 100 (3%)" and runs[0]["requests"] == "30 of 1000"
    assert runs[1]["status"] == "ENDED (CYCLE_LIMIT)" and runs[1]["elapsed"] == "1:02:05"
    card = engine_card(root, "run-live")
    assert card["recent_cycles"][0] == "cycle 1 · COMPLETED · beats buy-and-hold · deflation FAIL · VERIFIED_PASS · idea 1"
    with pytest.raises(RunError, match="not found"):
        engine_card(root, "run-missing")
    assert duration(59) == "0:59" and duration(3725) == "1:02:05"


def test_outside_run(tmp_path):
    root = project(tmp_path)
    store(root, [("run-live", "gepa", 5, False, 2)])
    shown, watched = [], []

    def pick_run(options):
        shown.append(options)
        return 1

    def watch(title, fetch):
        watched.append((title, fetch()))

    output = StringIO()
    steps = iter(["/watch", "/runs", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         pick_run=pick_run, watch=watch)
    assert shown[0][0].startswith("newest  follows the newest run of any kind")
    assert shown[0][1].startswith("run-live  gepa  RUNNING  cycles 2 of 100 (2%)")
    title, lines = watched[0]
    assert title == "Watching run-live" and "status: RUNNING" in lines and "cycles: 2 of 100 (2%)" in lines
    text = output.getvalue()
    assert '"run": "run-live"' in text and '"engine_runs": [' in text


def test_scripted_watch(tmp_path):
    root = project(tmp_path)
    store(root, [("run-old", "bench", 300, True, 1), ("run-live", "gepa", 5, False, 1)])
    output = StringIO()
    steps = iter(["/watch", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps))
    assert '"run": "run-live"' in output.getvalue()
    output = StringIO()
    steps = iter(["/watch", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         pick_run=lambda options: None, watch=lambda title, fetch: pytest.fail("Esc must not open a view"))
    assert '"run":' not in output.getvalue()


def test_live_refresh():
    keys = iter(["", "", "", "q"])
    ticks = iter([0.0, 0.5, 1.0, 2.5, 2.5, 3.0])
    calls = []

    def fetch():
        calls.append(len(calls))
        if len(calls) == 2:
            raise RunError("the research store cannot be read now")
        return [f"refresh {len(calls)}"]

    output = StringIO()
    view = LiveView(output, fetch, "Watching run-x", get_key=lambda: next(keys), width=80, clock=lambda: next(ticks))
    assert view.read() is None
    assert calls == [0, 1]
    text = output.getvalue()
    assert "refresh 1" in text and "cannot read progress now: the research store cannot be read now" in text
    assert text.startswith("\x1b[?25l") and text.endswith("\x1b[?25h")


def test_side_pane(tmp_path):
    from compertum.harness import pane
    root = project(tmp_path)
    store(root, [("run-live", "gepa", 5, False, 2)])
    opened = []
    output = StringIO()
    steps = iter(["/watch run-live", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         watch=lambda title, fetch: pytest.fail("the side pane replaces the inline view"), side=opened.append)
    assert opened == ["run-live"]
    assert "in the pane on the right" in output.getvalue() and '"run": "run-live"' not in output.getvalue()
    commands = []
    pane.open_pane(root, "run-live", spawn=lambda command, **kwargs: commands.append(command), which=lambda name: "wt.exe")
    command = commands[0]
    assert command[:5] == ["wt.exe", "-w", "0", "split-pane", "-V"]
    assert command[-4:] == ["run-live", ";", "move-focus", "left"]
    assert command[command.index("-m") + 1] == "compertum.harness.pane"
    with pytest.raises(RunError, match="not valid"):
        pane.open_pane(root, "run;new-tab", spawn=lambda command, **kwargs: pytest.fail("bad ID"), which=lambda name: "wt")
    assert pane.available({"WT_SESSION": "x"}, lambda name: "wt") and not pane.available({}, lambda name: "wt")
    assert not pane.available({"WT_SESSION": "x"}, lambda name: None)


def test_pane_readonly(tmp_path):
    import os
    from compertum.harness import pane
    root = project(tmp_path)
    store(root, [("run-live", "gepa", 5, False, 2)])
    out = StringIO()
    keys = iter(["", "q"])
    assert pane.main(["--project", str(root), "run-live"], out=out, get_key=lambda: next(keys)) == 0
    assert "Watching run-live" in out.getvalue() and "q closes this pane" in out.getvalue()
    assert "cycles: 2 of 100 (2%)" in out.getvalue()
    folder = root / "state" / "harness" / "runs"
    folder.mkdir(parents=True)
    record = {"id": "test-1", "kind": "test", "pid": os.getpid(), "started_wall": 1.0, "deadline": 60, "log": "test-1.log"}
    (folder / "test-1.json").write_text(json.dumps(record), encoding="utf-8")
    (folder / "test-1.log").write_text("tests/a.py .. [ 40%]\n", encoding="utf-8")
    before = sorted((path.name, path.stat().st_mtime_ns) for path in folder.iterdir())
    card = pane.card(root, "test-1")
    assert card["status"] == "RUNNING" and card["progress"] == "40%" and card["exit_code"] is None
    (folder / "test-1.json").write_text(json.dumps({**record, "exit_code": 0}), encoding="utf-8")
    before = sorted((path.name, path.stat().st_mtime_ns) for path in folder.iterdir())
    assert pane.card(root, "test-1")["status"] == "COMPLETED"
    assert sorted((path.name, path.stat().st_mtime_ns) for path in folder.iterdir()) == before
    assert not (root / "state" / "engine" / "STOP").exists()
    with pytest.raises(RunError, match="not found"):
        pane.card(root, "run-missing")


def test_cycle_share():
    from compertum.harness.engine_watch import _share
    assert _share(7, 20) == "7 of 20 (35%)" and _share(0, 20) == "0 of 20 (0%)" and _share(25, 20) == "25 of 20 (100%)"
    assert _share(3, None) == "3 of ?" and _share(3, "x") == "3 of x"


def test_recent_activity(tmp_path):
    """The card's activity shows the last 15 transcript steps, oldest first: the reply's first line, or the tools called with their files."""
    from compertum.harness.engine_watch import activity
    folder = tmp_path / "state" / "engine" / "transcripts"
    folder.mkdir(parents=True)
    rows = [{"cycle_id": "cycle-0007-aaaaaaaa", "role": "researcher", "content": f"Memo {i}\nmore", "status": "COMPLETED"} for i in range(16)]
    rows += [{"cycle_id": "cycle-0007-aaaaaaaa", "role": "engineer", "content": "", "status": "COMPLETED",
              "tool_calls": [{"name": "write_file", "arguments": {"file_path": "/main.py", "content": "x"}}, {"name": "run_job", "arguments": '{"entry": "main.py"}'}]},
             {"cycle_id": "cycle-0007-aaaaaaaa", "role": "director", "content": "1. Pick\nMomentum on \x1b[31mred\x1b[0m industries", "status": "FAILED"}]
    text = "\n".join(json.dumps(r) for r in rows) + "\n{broken\n"
    (folder / "run-20261103-0000aaaa.jsonl").write_text(text, encoding="utf-8")
    lines = activity(tmp_path, "run-20261103-0000aaaa")
    assert len(lines) == 15 and lines[0] == "cycle 7 · researcher · Memo 3 more"
    assert lines[-2] == "cycle 7 · engineer · write_file /main.py, run_job main.py"
    assert lines[-1].startswith("cycle 7 · director · 1. Pick Momentum on ") and "\x1b" not in lines[-1] and lines[-1].endswith(" · FAILED")
    assert activity(tmp_path, "run-20261103-0000bbbb") == ["no transcript yet"] and activity(tmp_path, "../../etc") == ["no transcript"]


def test_follow_newest(tmp_path):
    """/watch newest shows the newest engine run, and a run that starts later replaces it at the next refresh."""
    from compertum.harness import pane
    from compertum.harness.watch import newest, watch_card
    root = project(tmp_path)
    assert newest(root) is None and watch_card(root, "newest")["status"] == "WAITING"
    store(root, [("run-old", "bench", 300, True, 1)])
    assert watch_card(root, "newest")["run"] == "run-old"
    (root / "state" / "research.sqlite").unlink()
    store(root, [("run-old", "bench", 300, True, 1), ("run-new", "gepa", 1, False, 2)])
    assert newest(root) == "run-new" and watch_card(root, "newest")["cycles"] == "2 of 100 (2%)"
    watched = []
    output = StringIO()
    steps = iter(["/watch", "/watch newest", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         pick_run=lambda options: 0, watch=lambda title, fetch: watched.append((title, fetch())))
    assert [title for title, _ in watched] == ["Watching the newest run"] * 2
    assert "run: run-new" in watched[0][1] and "/watch [RUN_ID|newest]" in main.__globals__["help_text"]()
    out = StringIO()
    keys = iter(["", "q"])
    assert pane.main(["--project", str(root), "newest"], out=out, get_key=lambda: next(keys)) == 0
    assert "Watching the newest run" in out.getvalue() and "run: run-new" in out.getvalue()
    commands = []
    pane.open_pane(root, "newest", spawn=lambda command, **kwargs: commands.append(command), which=lambda name: "wt.exe")
    assert "Watch the newest run" in commands[0] and commands[0][-4] == "newest"


def test_any_run(tmp_path):
    """Test jobs, check lanes, nested jobs and library sweeps get cards, join the picker, and can be followed. Nothing is written."""
    from compertum.harness import pane
    from compertum.harness.watch import newest, sweeps, test_jobs, watch_card
    root = project(tmp_path)
    store(root, [("run-old", "bench", 300, True, 1)])
    base = root / ".cache" / "test-runs"
    stamp = lambda minutes: (datetime.now() - timedelta(minutes=minutes)).strftime("%Y%m%d-%H%M%S")
    done, lane, nested, failed = f"unit-{stamp(30)}", f"check-engine-{stamp(10)}", f"suite-{stamp(20)}", f"check-tools-{stamp(40)}"
    for name in (done, lane, f"m5-economics/{nested}", failed):
        (base / name / "tmp" / "t1").mkdir(parents=True)
    (base / done / "output.txt").write_text("command: python -m pytest tests/a.py\n.. [100%]\n2 passed in 1.0s\n", encoding="utf-8")
    (base / done / "retention.json").write_text(json.dumps({"passed": True, "summary": "2 passed in 1.0s", "elapsed_seconds": 3.2}), encoding="utf-8")
    (base / lane / "output.txt").write_text("..F. [  4/20]\n.E   [  6/20]\n", encoding="utf-8")
    (base / "m5-economics" / nested / "output.txt").write_text("command: python -m pytest tests\n", encoding="utf-8")
    (base / failed / "output.txt").write_text("F [1/1]\n1 failed in 2.0s\n", encoding="utf-8")
    (base / failed / "failed.json").write_text(json.dumps({"passed": False, "summary": "1 failed in 2.0s", "seconds": 2.5}), encoding="utf-8")
    (base / "check-history.jsonl").write_text(json.dumps({"run": "check-harness-20261103-105802", "passed": True,
                                                          "summary": "147 passed", "seconds": 12.4}) + "\n", encoding="utf-8")
    con = sqlite3.connect(root / "state" / "research.sqlite")
    con.execute("create table engine_trials (trial_id text, source text, count integer, recorded_at text, record text)")
    for run_id, minutes in (("library-multi-20261103-aaaaaaaa", 50), ("library-20261103-bbbbbbbb", 60)):
        at = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        source = f"{run_id.rsplit('-', 2)[0]}:{run_id}"
        con.execute("insert into engine_trials values (?, ?, 75, ?, ?)",
                    (f"external:{source}", source, at, json.dumps({"evidence": {"note": "sweep note"}})))
    con.commit()
    con.close()
    (root / "state" / "engine" / "library").mkdir(parents=True)
    rows = [{"universe": "french49", "family": "breadth", "gate": "FAIL", "deflated_sharpe": "0.31"},
            {"universe": "french49", "family": "trend", "gate": "PASS", "deflated_sharpe": 0.97}]
    (root / "state" / "engine" / "library" / "library-multi-20261103-aaaaaaaa.json").write_text(
        json.dumps({"rows": rows, "total_trials": 900}), encoding="utf-8")
    before = sorted((str(path), path.stat().st_mtime_ns) for path in root.rglob("*"))

    card = watch_card(root, lane)
    assert card["type"] == "check lane" and card["status"] == "RUNNING" and card["progress"] == "6/20 tests (30%)" and card["failed"] == 2
    card = watch_card(root, f"m5-economics/{nested}")
    assert card["type"] == "test job" and card["status"] == "RUNNING" and card["progress"] == "1 tmp folders so far"
    card = watch_card(root, done)
    assert card["status"] == "COMPLETED" and card["result"] == "2 passed in 1.0s" and card["elapsed"] == "0:03"
    assert watch_card(root, failed)["status"] == "FAILED"
    card = watch_card(root, "check-harness-20261103-105802")
    assert card["status"] == "COMPLETED" and card["folder"] == "removed after the pass"
    card = watch_card(root, "library-multi-20261103-aaaaaaaa")
    assert card["status"] == "COMPLETED" and card["gates"] == "1 of 2 PASS" and card["best_rows"][0] == "french49 trend · PASS · deflated 0.97"
    card = watch_card(root, "library-20261103-bbbbbbbb")
    assert card["status"].startswith("NO REPORT AFTER") and card["note"] == "sweep note"
    assert [item["run"] for item in sweeps(root)] == ["library-multi-20261103-aaaaaaaa", "library-20261103-bbbbbbbb"]
    assert [item["run"] for item in test_jobs(root)] == [lane, f"m5-economics/{nested}", done, failed]
    assert newest(root) == lane
    for bad in ("../outside-20261103-101010", "a;b", "m5-economics/../x-20261103-101010", "plain-name", "a/b/c-20261103-101010"):
        with pytest.raises(RunError):
            watch_card(root, bad)
    with pytest.raises(RunError, match="not valid"):
        pane.open_pane(root, "a;new-tab", spawn=lambda command, **kwargs: pytest.fail("bad ID"), which=lambda name: "wt")
    assert sorted((str(path), path.stat().st_mtime_ns) for path in root.rglob("*")) == before

    shown = []
    output = StringIO()
    steps = iter(["/watch", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         pick_run=lambda options: shown.append(options), watch=lambda title, fetch: None)
    labels = shown[0]
    assert labels[0].startswith("newest  follows the newest run of any kind")
    assert labels[1].startswith(f"{lane}  check lane  RUNNING  6/20 tests (30%)")
    assert any(label.startswith("library-multi-20261103-aaaaaaaa  library sweep  COMPLETED") for label in labels)


def test_view_fits():
    """A card taller than the pane keeps every label and the newest list rows; the oldest rows of the last list go first."""
    from compertum.harness.editor import fit
    rows = ["run: x", "recent cycles:", "  - c1", "  - c2", "recent activity:", *(f"  - a{i}" for i in range(6))]
    assert fit(rows, 20) == rows
    assert fit(rows, 8) == ["run: x", "recent cycles:", "  - c1", "  - c2", "recent activity:", "  - a3", "  - a4", "  - a5"]
    assert fit(rows, 5) == ["run: x", "recent cycles:", "  - c2", "recent activity:", "  - a5"]
    assert fit(rows, 3) == ["run: x", "recent cycles:", "↓ 3 more rows; a taller pane shows them"]
    assert fit(["a", "b"], 0) == ["↓ 2 more rows; a taller pane shows them"]
    output = StringIO()
    keys = iter(["q"])
    view = LiveView(output, lambda: rows, "Watching run-x", get_key=lambda: next(keys), width=80, height=10)
    view.read()
    assert "a5" in output.getvalue() and "a2" not in output.getvalue() and "c1" in output.getvalue()
