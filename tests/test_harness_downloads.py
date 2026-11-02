import json
from datetime import datetime, timezone
from io import StringIO

import pytest

from compertum.harness import pane
from compertum.harness.cli import main
from compertum.harness.commands import DESCRIPTIONS, EXAMPLES, USAGES, help_text
from compertum.harness.display import Display
from compertum.harness.downloads import PROGRESS, DownloadView, painted, progress_lines, read_progress
from compertum.harness.runs import RunError

NOW = datetime(2026, 11, 1, 22, 40, 30, tzinfo=timezone.utc)


def record(**changes):
    value = {"schema": "pull-progress-v1", "job": "S&P 500 history", "started_utc": "2026-11-01T22:18:50Z",
             "updated_utc": "2026-11-01T22:40:03Z", "total": 359, "done": 271, "loaded": 262, "failed": 9,
             "current": {"symbol": "MON", "years": "2016-2018"}, "rate_per_min": 5.4, "eta_minutes": 16.3,
             "finished": False,
             "recent": [{"symbol": "PX", "status": "loaded"},
                        {"symbol": "MON", "status": "failed", "code": "PROVIDER_EVIDENCE_INVALID_PROVIDER_NUMBER"}],
             "pending": ["NOC", "NOV", "NRG"]}
    value.update(changes)
    return value


def project(tmp_path, progress=None):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    entry = 'base_url = "http://127.0.0.1:1234/v1"\nmodel = "scripted"\n'
    (root / "config" / "models.toml").write_text("".join(f"[roles.{role}]\n{entry}" for role in
                                                         ("director", "researcher", "mathematician", "engineer")))
    if progress is not None:
        (root / PROGRESS).parent.mkdir(parents=True)
        text = progress if isinstance(progress, str) else json.dumps(progress)
        (root / PROGRESS).write_text(text, encoding="utf-8")
    return root


def test_running_view():
    lines = progress_lines(record(), width=60, now=NOW)
    assert lines[0].startswith("S&P 500 history  █") and lines[0].endswith("░  271/359  75%")
    assert len(lines[0]) == 59
    assert lines[1] == "loaded 262 · failed 9 · now: MON (2016–2018) · 5.4/min"
    assert progress_lines(record(), width=80, now=NOW)[1] == (
        "loaded 262 · failed 9 · now: MON (2016–2018) · 5.4/min · ~16 min left")
    assert lines[2:] == ["", "recent", "  ✓ PX", "  ✗ MON  PROVIDER_EVIDENCE_INVALID_PROVIDER_NUMBER", "",
                         "next  NOC  NOV  NRG"]
    wide = progress_lines(record(), width=120, now=NOW)[0]
    assert wide.count("█") + wide.count("░") == 60 and len(wide) < 120


def test_view_limits():
    progress = record(recent=[{"symbol": f"S{index}", "status": "loaded"} for index in range(20)],
                      pending=[f"P{index}" for index in range(20)])
    lines = progress_lines(progress, width=200, now=NOW)
    assert [line for line in lines if line.startswith("  ✓ ")] == [f"  ✓ S{index}" for index in range(12, 20)]
    assert lines[-1] == "next  " + "  ".join(f"P{index}" for index in range(8))
    assert all(not (first == second == "") for first, second in zip(lines, lines[1:]))


def test_finished_view():
    lines = progress_lines(record(finished=True, done=359, loaded=350, updated_utc="2026-11-01T23:31:00Z"), now=NOW)
    assert lines[0].endswith("359/359  100%") and "░" not in lines[0]
    assert lines[1] == "finished · loaded 350 · failed 9 · took 1 h 12 min"
    assert not any(line.startswith(("next", "No update")) for line in lines)


def test_missing_file(tmp_path):
    root = project(tmp_path)
    assert read_progress(root) is None
    assert progress_lines(read_progress(root)) == ["No download has started."]


def test_stale_file():
    lines = progress_lines(record(updated_utc="2026-11-01T22:30:00Z"), now=NOW)
    assert "No update for 10 minutes; the download may have stopped." in lines
    assert not any("No update" in line for line in progress_lines(record(), now=NOW))
    finished = progress_lines(record(updated_utc="2026-11-01T20:00:00Z", finished=True), now=NOW)
    assert not any("No update" in line for line in finished)


@pytest.mark.parametrize("progress", [
    {},
    [],
    "text",
    7,
    {"schema": "pull-progress-v1", "total": "359", "done": None, "loaded": -1, "failed": True, "current": "MON",
     "rate_per_min": float("nan"), "eta_minutes": [], "finished": "yes", "recent": {"symbol": "PX"},
     "pending": "NOC", "started_utc": 5, "updated_utc": "yesterday", "job": {"name": "x"}},
    {"total": 0, "done": 5, "recent": [None, 3, {"symbol": 4}, {"symbol": "OK", "status": None}],
     "pending": [1, None, "NOC\x1b[2J"], "current": {"symbol": None, "years": 2016}, "job": "x" * 500},
    {"total": 10, "done": 50, "finished": True, "started_utc": "2026-11-01T23:00:00Z", "updated_utc": "2026-11-01T22:00:00Z"},
    {"total": 10 ** 400, "done": 10 ** 400, "loaded": 10 ** 400, "rate_per_min": 10 ** 400, "eta_minutes": 10 ** 400},
])
def test_bad_types(progress):
    lines = progress_lines(progress, width=40, now=NOW)
    assert lines and all(isinstance(line, str) and len(line) <= 40 and "\x1b" not in line for line in lines)
    for index, line in enumerate(lines):
        painted(line, first=index == 0)


def test_malformed_file(tmp_path):
    assert progress_lines(read_progress(project(tmp_path, '{"schema": "pull-progress-v1", "done":'))) == [
        "The progress file cannot be read now."]
    assert progress_lines({"schema": "pull-progress-v9"}) == ["The progress file has an unknown format: pull-progress-v9."]
    lines = progress_lines({"total": "359", "done": "x", "job": None, "recent": [None]}, now=NOW)
    assert lines == ["History download  0 done"]


def test_data_command():
    assert USAGES["/data"] == "/data" and EXAMPLES["/data"] == "/data"
    assert DESCRIPTIONS["/data"] == "watch history downloads"
    assert "/data" in help_text()


def test_console_print(tmp_path):
    root = project(tmp_path, record())
    output = StringIO()
    steps = iter(["/data", "/data now", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps))
    text = output.getvalue()
    assert "S&P 500 history" in text and "271/359  75%" in text and "next  NOC  NOV  NRG" in text
    assert "Error: use /data" in text


def test_side_pane(tmp_path):
    root = project(tmp_path, record())
    opened, output = [], StringIO()
    steps = iter(["/data", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         downloads=lambda: opened.append(True))
    assert opened == [True] and "pane on the right" in output.getvalue() and "271/359" not in output.getvalue()
    commands = []
    pane.open_downloads(root, spawn=lambda command, **kwargs: commands.append(command), which=lambda name: "wt.exe")
    command = commands[0]
    assert command[:5] == ["wt.exe", "-w", "0", "split-pane", "-V"]
    assert command[command.index("-m") + 1] == "compertum.harness.pane"
    assert command[-4:] == ["--downloads", ";", "move-focus", "left"]

    def refuse(command, **kwargs):
        raise OSError("no terminal")

    with pytest.raises(RunError, match="cannot open"):
        pane.open_downloads(root, spawn=refuse, which=lambda name: "wt.exe")


def test_read_only(tmp_path):
    root = project(tmp_path, record())
    path = root / PROGRESS
    before = (path.read_bytes(), path.stat().st_mtime_ns, sorted(item.name for item in path.parent.iterdir()))
    out = StringIO()
    keys = iter(["", "", "q"])
    assert pane.main(["--project", str(root), "--downloads"], out=out, get_key=lambda: next(keys)) == 0
    text = out.getvalue()
    assert "History downloads" in text and "q closes this pane" in text and "271/359" in text
    assert (path.read_bytes(), path.stat().st_mtime_ns, sorted(item.name for item in path.parent.iterdir())) == before
    with pytest.raises(SystemExit):
        pane.main(["--project", str(root)], out=StringIO(), get_key=lambda: "q")
    with pytest.raises(SystemExit):
        pane.main(["--project", str(root), "--downloads", "run-x"], out=StringIO(), get_key=lambda: "q")


def test_refresh_stop(tmp_path):
    root = project(tmp_path, record())
    path = root / PROGRESS
    reads = []
    view = DownloadView(StringIO(), root, get_key=lambda: "", width=80, clock=lambda: 0.0)
    original = view._fetch

    def fetch():
        reads.append(1)
        return original()

    view.fetch = fetch
    view._refresh()
    assert not view.done and view.every == 1.0
    path.write_text(json.dumps(record(finished=True, done=359)), encoding="utf-8")
    view._refresh()
    assert view.done and "finished" in view._lines()[0]
    path.unlink()
    view._refresh()
    view._refresh()
    assert len(reads) == 2 and view.rows[0].endswith("359/359  100%")


def test_palette_colors():
    assert "\x1b[38;2;120;190;120m" in painted("  ✓ PX") and "\x1b[38;2;226;98;92m" in painted("  ✗ MON  CODE")
    head = painted(progress_lines(record(), now=NOW)[0], first=True)
    assert head.startswith("\x1b[1;38;2;232;131;58mS&P 500 history")
    assert "\x1b[38;2;226;98;92mNo update" in painted("No update for 3 minutes; the download may have stopped.")
    assert painted("No download has started.", first=True) == "\x1b[38;2;160;152;142mNo download has started.\x1b[0m"


def test_other_statuses():
    lines = progress_lines(record(recent=[{"symbol": "AB", "status": "skipped"}], pending=[]), now=NOW)
    assert lines[-2:] == ["recent", "  · AB  skipped"]
