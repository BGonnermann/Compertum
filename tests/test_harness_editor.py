from io import StringIO

import pytest

from compertum.harness.commands import complete, help_text
from compertum.harness.editor import LineEditor


def test_slash_completion_inserts_an_editable_run_template():
    assert complete("/ge") == "/gepa CYCLES REQUESTS HOURS NOTE"
    assert complete("/run") == "/run CYCLES REQUESTS HOURS NOTE"
    assert complete("/bench") == "/bench CYCLES REQUESTS HOURS NOTE"
    assert complete("ordinary text") is None


def test_identifier_completion_uses_session_and_run_ids():
    sessions = lambda: ["session-20261028-one"]
    runs = lambda: {"test-20261028-one": {}}
    assert complete("/resume ses", sessions, runs) == "/resume session-20261028-one"
    assert complete("/watch te", sessions, runs) == "/watch test-20261028-one"
    assert complete("/stop te", sessions, runs) == "/stop test-20261028-one"


def test_help_comes_from_the_same_command_registry():
    text = help_text()
    assert "/gepa CYCLES REQUESTS HOURS NOTE" in text
    assert "/model [NAME] [MODEL_ID]" in text
    assert "Tab completes commands and identifiers" in text


def test_model_completion_uses_model_files_and_cached_ids():
    files = lambda: ["deepseek", "kimi", "local"]
    ids = lambda name: ["k3", "k3.1-pro"] if name == "kimi" else []
    assert complete("/model ki") is None
    assert complete("/model ki", model_files=files, model_ids=ids) == "/model kimi"
    assert complete("/models de", model_files=files, model_ids=ids) == "/models deepseek"
    assert complete("/model kimi k3", model_files=files, model_ids=ids) is None
    assert complete("/model kimi k3.", model_files=files, model_ids=ids) == "/model kimi k3.1-pro"
    assert complete("/models kimi ", model_files=files, model_ids=ids) is None


def test_editor_passes_model_completion_sources():
    keys = iter([*"/model ki", "\t", "\r"])
    editor = LineEditor(StringIO(), get_key=lambda: next(keys), width=80, model_files=lambda: ["kimi"])
    assert editor.read() == "/model kimi"


def test_editor_completes_and_draws_the_box_and_hint():
    output = StringIO()
    keys = iter([*"/ge", "\t", "\r"])
    editor = LineEditor(output, get_key=lambda: next(keys), width=80)
    assert editor.read() == "/gepa CYCLES REQUESTS HOURS NOTE"
    rendered = output.getvalue()
    assert "╭─ Compertum" in rendered
    assert "/gepa CYCLES REQUESTS HOURS NOTE" in rendered
    assert "start a bounded GEPA run" in rendered


def test_editor_supports_cursor_editing():
    keys = iter([*"abc", "\x00K", "\x08", "\x00O", "d", "\x00G", "z", "\x00S", "\r"])
    editor = LineEditor(StringIO(), get_key=lambda: next(keys), width=60)
    assert editor.read() == "zcd"


def test_redraw_returns_to_the_input_row_and_borders_align():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=60)
    editor._render()
    assert output.getvalue().endswith("\x1b[1A\x1b[3G")
    output.seek(0)
    output.truncate()
    editor._render()
    assert output.getvalue().startswith("\x1b[1A\x1b[J")
    top, middle, bottom, _, _ = editor._lines()
    assert len(top) == len(middle) == len(bottom) == 58


def test_composer_width_follows_terminal_and_long_input_scrolls():
    editor = LineEditor(StringIO(), get_key=lambda: "\r", width=80)
    editor.buffer = "x" * 20
    assert editor._size() == 78
    editor.buffer = "x" * 200
    editor.cursor = len(editor.buffer)
    assert editor._size() == 78
    top, middle, bottom, _, column = editor._lines()
    assert len(top) == len(middle) == len(bottom) == 78
    assert middle == "│ " + "x" * 73 + "  │"
    assert column == 76
    editor.width = 42
    assert editor._size() == 40


def test_editor_ctrl_z_reaches_eof():
    editor = LineEditor(StringIO(), get_key=lambda: "\x1a", width=60)
    with pytest.raises(EOFError):
        editor.read()


def test_editor_ctrl_c_interrupts_without_a_command():
    editor = LineEditor(StringIO(), get_key=lambda: "\x03", width=60)
    with pytest.raises(KeyboardInterrupt):
        editor.read()
