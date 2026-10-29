import json
import re
import time
from io import StringIO
from types import SimpleNamespace

from compertum.harness.display import (ACCENT, BAD, DIFF_ROWS, FAINT, GOOD, MUTED, SPINNER, TAB_BUSY, TAB_IDLE, Display,
                                       diff_rows)
from compertum.harness.tools import WorkspaceTools


class Terminal(StringIO):
    def isatty(self):
        return True


def test_diff_rows_number_changes_and_count_them():
    rows, added, removed = diff_rows("a\nb\nc\nd\n", "a\nB\nc\nd\ne\n")
    assert (added, removed) == (2, 1)
    assert rows == [(" ", 1, "a"), ("-", 2, "b"), ("+", 2, "B"), (" ", 3, "c"), (" ", 4, "d"), ("+", 5, "e")]
    rows, _, _ = diff_rows("".join(f"{n}\n" for n in range(20)), "".join(f"{n}\n" for n in range(20)).replace("2\n", "x\n", 1).replace("17\n", "y\n"))
    assert ("⋮", None, "") in rows


def test_edit_shows_a_colored_diff_with_line_numbers():
    out = StringIO()
    display = Display(out, color=True, animate=False)
    display.tool_call("edit", {"path": "notes.py", "old": "b", "new": "B"})
    display.tool_result("edited notes.py", True, name="edit", change=("notes.py", "a\nb\nc\n", "a\nB\nc\n"))
    text = out.getvalue()
    assert f"Edit\x1b[0m \x1b[{MUTED}mnotes.py" in text
    assert "Added 1 line, removed 1 line" in text
    assert f"\x1b[{BAD}m    2 - b\x1b[0m" in text
    assert f"\x1b[{GOOD}m    2 + B\x1b[0m" in text
    assert '"old"' not in text


def test_terminal_output_separates_blocks_and_colors_status_words():
    out = StringIO()
    display = Display(out, color=True, animate=True)
    display.busy = lambda *args, **kwargs: None
    display._terminal = lambda text: None
    display.model_event("reasoning", "plan")
    display.tool_call("read", {"path": "a.txt"})
    display.tool_result("x\ny", True, name="read")
    display.tool_call("read", {"path": "b.txt"})
    display.model_event("content", "answer")
    display.outcome(SimpleNamespace(status="done", steps=2, seconds=5, detail=""))
    display.gap()
    display.gap()
    display.json({"run": "r1", "status": "RUNNING", "elapsed_seconds": 1.0})
    display.error("AVAILABLE_RAM_FLOOR")
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out.getvalue())
    assert plain == ("thinking: plan\n\n● Read a.txt\n  ⎿ Read 2 lines\n\n● Read b.txt\n\nanswer\n\n✓ done  ·  2 steps  ·  0:05\n\n"
                     "run:             r1\nstatus:          RUNNING\nelapsed seconds: 1.0\n\n✗ Error: AVAILABLE_RAM_FLOOR\n")
    assert f"\x1b[{ACCENT}mRUNNING\x1b[0m" in out.getvalue()
    help_out = StringIO()
    Display(help_out, color=True, animate=False).help("Commands:\n  /runs    show run cards\nTab completes.")
    assert help_out.getvalue() == (f"\x1b[1;{ACCENT}mCommands:\x1b[0m\n  /runs    \x1b[{MUTED}mshow run cards\x1b[0m\n"
                                   f"\x1b[{FAINT}mTab completes.\x1b[0m\n")
    script = StringIO()
    Display(script, color=False, animate=False).help("Commands:\n  /runs    show run cards")
    assert script.getvalue() == "Commands:\n  /runs    show run cards\n"


def test_new_file_and_long_diff_are_summarized():
    out = StringIO()
    display = Display(out, color=False, animate=False)
    content = "".join(f"row {n}\n" for n in range(1, 31))
    display.tool_result("wrote big.py", True, name="write", change=("big.py", "", content, True))
    text = out.getvalue()
    assert "Created big.py with 30 lines" in text
    assert "   1 + row 1" in text and f"  {DIFF_ROWS} + row {DIFF_ROWS}" in text
    assert "row 21" not in text and "... 10 more diff lines" in text
    out.seek(0)
    out.truncate()
    display.tool_result("wrote big.py", True, name="write", change=("big.py", content, content))
    assert "No changes" in out.getvalue()
    display.tool_result("wrote big.py", True, name="write", change=("big.py", None, content))
    assert "the previous file cannot be shown" in out.getvalue()


def test_read_run_and_failure_results_are_readable():
    out = StringIO()
    display = Display(out, color=False, animate=False)
    display.tool_call("read", {"path": "config/gepa_goal.md"})
    display.tool_result("a\nb\nc", True, name="read")
    display.tool_call("run", {"path": "main.py", "args": ["--fast"]})
    result = {"status": "FAILED", "exit_code": 1, "timed_out": False, "stdout": "1\n2\n3\n4\n5\n6\n", "stderr": "boom\n"}
    display.tool_result(json.dumps(result), True, name="run")
    display.tool_result("error: the old text must occur exactly once", False, name="edit")
    lines = out.getvalue().splitlines()
    assert lines[:2] == ["● Read config/gepa_goal.md", "  ⎿ Read 3 lines"]
    assert lines[2:4] == ["● Run main.py --fast", "  ⎿ exit 1"]
    assert lines[4:10] == ["    3", "    4", "    5", "    6", "    ... 2 earlier stdout lines", "    boom"]
    assert lines[-1] == "  ⎿ error: the old text must occur exactly once"


def test_tools_record_the_change_only_for_the_display(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    assert tools.run("write", {"path": "a.txt", "content": "one\n"}, time.monotonic() + 5) == "wrote a.txt (4 bytes)"
    assert tools.take_change() == ("a.txt", "", "one\n", True)
    assert tools.take_change() is None
    assert tools.run("edit", {"path": "a.txt", "old": "one", "new": "two"}, time.monotonic() + 5) == "edited a.txt"
    assert tools.take_change() == ("a.txt", "one\n", "two\n", False)
    tools.run("read", {"path": "a.txt"}, time.monotonic() + 5)
    assert tools.take_change() is None


def test_spinner_animates_until_the_next_output_and_marks_the_tab():
    out = Terminal()
    display = Display(out, color=False, animate=True)
    display.step(1, 40, 3.0)
    deadline = time.monotonic() + 5
    while SPINNER[0] not in out.getvalue() and time.monotonic() < deadline:
        time.sleep(0.02)
    display.line("answer")
    text = out.getvalue()
    assert TAB_BUSY in text and "\x1b]0;Compertum · working\x07" in text
    assert f"\r\x1b[2K{SPINNER[0]} Working · step 1/40 · 0:0" in text
    assert text.endswith("\r\x1b[2Kanswer\n")
    assert display._spinner is None
    time.sleep(0.25)
    assert out.getvalue() == text
    display.outcome(SimpleNamespace(status="done", steps=1, seconds=4, detail=""))
    assert TAB_IDLE in out.getvalue() and "\x1b]0;Compertum · done\x07" in out.getvalue()


def test_fast_tool_does_not_flash_the_spinner_and_scripts_get_no_controls():
    out = Terminal()
    display = Display(out, color=False, animate=True)
    display.tool_call("read", {"path": "a.txt"})
    display.tool_result("x", True, name="read")
    assert SPINNER[0] not in out.getvalue()
    plain = StringIO()
    quiet = Display(plain, color=False)
    quiet.step(1, 40, 0)
    quiet.outcome(SimpleNamespace(status="done", steps=1, seconds=1, detail=""))
    assert "\x1b" not in plain.getvalue()
    assert "[asking] step 1/40 | 0:00" in plain.getvalue()


def test_empty_and_existing_empty_files_are_reported_without_a_crash(tmp_path):
    out = StringIO()
    display = Display(out, color=False, animate=False)
    tools = WorkspaceTools(tmp_path, tmp_path)
    tools.run("write", {"path": "pkg/__init__.py", "content": ""}, time.monotonic() + 5)
    display.tool_result("wrote pkg/__init__.py (0 bytes)", True, name="write", change=tools.take_change())
    tools.run("write", {"path": "pkg/__init__.py", "content": "x = 1\n"}, time.monotonic() + 5)
    display.tool_result("wrote pkg/__init__.py (6 bytes)", True, name="write", change=tools.take_change())
    text = out.getvalue()
    assert "Created pkg/__init__.py with 0 lines" in text
    assert "Added 1 line, removed 0 lines" in text and "1 + x = 1" in text


def test_display_failure_never_reaches_the_task():
    out = StringIO()
    display = Display(out, color=False, animate=False)
    display.tool_result("wrote a.py", True, name="write", change=("a.py", 5, "text", False))
    assert "finished; the details cannot be shown" in out.getvalue()


def test_large_changed_region_shows_a_summary_quickly():
    out = StringIO()
    display = Display(out, color=False, animate=False)
    started = time.monotonic()
    display.tool_result("wrote big.txt", True, name="write", change=("big.txt", "x\n" * 10000, "x\ny\n" * 5000, False))
    assert time.monotonic() - started < 2
    assert "Changed big.txt from 10000 lines to 10000; the diff is too large to show" in out.getvalue()
    started = time.monotonic()
    assert diff_rows("x\n" * 200, "x\ny\n" * 100) is not None
    assert time.monotonic() - started < 2
    rows, added, removed = diff_rows("".join(f"{n}\n" for n in range(900)), "".join(f"{n}\n" for n in range(900)).replace("450\n", "half\n"))
    assert (added, removed) == (1, 1)
    assert rows == [(" ", 450, "449"), ("-", 451, "450"), ("+", 451, "half"), (" ", 452, "451")]


def test_diff_numbers_stay_correct_after_a_gap_and_line_endings_are_named():
    old = "".join(f"{n}\n" for n in range(1, 21))
    rows, _, _ = diff_rows(old, old.replace("3\n", "c\n", 1).replace("18\n", "r\n"))
    gap = rows.index(("⋮", None, ""))
    assert rows[gap + 1:] == [(" ", 17, "17"), ("-", 18, "18"), ("+", 18, "r"), (" ", 19, "19")]
    out = StringIO()
    Display(out, color=False, animate=False).tool_result("wrote a.txt", True, name="write",
                                                        change=("a.txt", "a\r\nb\r\n", "a\nb\n", False))
    assert "Changed only line endings" in out.getvalue()


def test_terminal_controls_from_models_files_and_programs_are_shown_as_text():
    out = Terminal()
    display = Display(out, color=False, animate=True)
    display.tool_call("write", {"path": "a\x1b]52;c;ZXZpbA==\x07.txt"})
    display.tool_result("wrote a.txt", True, name="write", change=("a.txt", "", "\x1b[2Khidden\n", True))
    run = {"status": "COMPLETED", "exit_code": 0, "timed_out": False, "stdout": "\x1b]0;pwn\x07\n", "stderr": ""}
    display.tool_result(json.dumps(run), True, name="run")
    display.model_event("content", "reply\x1b[31m\r\n")
    text = out.getvalue()
    assert "\x1b]52" not in text and "\x1b]0;pwn" not in text and "\x1b[2Khidden" not in text and "\x1b[31m" not in text
    assert "a\\x1b]52;c;ZXZpbA==\\x07.txt" in text and "\\x1b[2Khidden" in text and "reply\\x1b[31m\n" in text


def test_error_after_a_started_step_returns_the_tab_to_idle():
    out = Terminal()
    display = Display(out, color=False, animate=True)
    display.step(1, 40, 0)
    display.error("AI_CREDENTIAL_UNAVAILABLE")
    text = out.getvalue()
    assert text.index(TAB_BUSY) < text.index(TAB_IDLE) < text.index("Error: AI_CREDENTIAL_UNAVAILABLE")
    assert "\x1b]0;Compertum · error\x07" in text and display._spinner is None
