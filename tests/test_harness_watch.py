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


def test_engine_runs_list_running_first_with_progress(tmp_path):
    root = project(tmp_path)
    assert engine_runs(root) == []
    store(root, [("run-old", "bench", 300, True, 4), ("run-live", "gepa", 42, False, 3)])
    runs = engine_runs(root)
    assert [item["run"] for item in runs] == ["run-live", "run-old"]
    assert runs[0]["status"] == "RUNNING" and runs[0]["cycles"] == "3 of 100" and runs[0]["requests"] == "30 of 1000"
    assert runs[1]["status"] == "ENDED (CYCLE_LIMIT)" and runs[1]["elapsed"] == "1:02:05"
    card = engine_card(root, "run-live")
    assert card["recent_cycles"][0] == "cycle 1 · COMPLETED · beats buy-and-hold · deflation FAIL · VERIFIED_PASS · idea 1"
    with pytest.raises(RunError, match="not found"):
        engine_card(root, "run-missing")
    assert duration(59) == "0:59" and duration(3725) == "1:02:05"


def test_watch_picks_an_outside_engine_run_and_opens_the_live_view(tmp_path):
    root = project(tmp_path)
    store(root, [("run-live", "gepa", 5, False, 2)])
    shown, watched = [], []

    def pick_run(options):
        shown.append(options)
        return 0

    def watch(title, fetch):
        watched.append((title, fetch()))

    output = StringIO()
    steps = iter(["/watch", "/runs", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         pick_run=pick_run, watch=watch)
    assert shown[0][0].startswith("run-live  gepa  RUNNING  cycles 2 of 100")
    title, lines = watched[0]
    assert title == "Watching run-live" and "status: RUNNING" in lines and "cycles: 2 of 100" in lines
    text = output.getvalue()
    assert '"run": "run-live"' in text and '"engine_runs": [' in text


def test_scripted_watch_shows_the_newest_running_run_and_cancel_shows_nothing(tmp_path):
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


def test_live_view_refreshes_on_its_interval_and_survives_a_read_error():
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
