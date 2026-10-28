from io import StringIO

import pytest

from compertum.harness.commands import COMMANDS, EXAMPLES, complete, help_text
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
    assert "Up/Down selects commands" in text
    assert "Tab inserts the selection and completes identifiers" in text


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
    editor.buffer = "a"
    editor.cursor = 1
    editor._render()
    assert output.getvalue().startswith("\x1b[1A\r\x1b[J")
    top, middle, bottom, _, _ = editor._lines()
    assert len(top) == len(middle) == len(bottom) == 58


def test_resize_rewinds_reflowed_lines_and_erases_from_line_start():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=100)
    editor._render()
    output.seek(0)
    output.truncate()
    editor.width = 40
    editor._render()
    assert output.getvalue().startswith("\x1b[3A\r\x1b[J")
    top, middle, bottom, _, _ = editor._lines()
    assert len(top) == len(middle) == len(bottom) == 38
    output.seek(0)
    output.truncate()
    editor.width = 100
    editor._render()
    assert output.getvalue().startswith("\x1b[1A\r\x1b[J")


def test_unchanged_frame_does_not_write_during_resize_polling():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=60)
    editor._render()
    output.seek(0)
    output.truncate()
    editor._render()
    assert output.getvalue() == ""


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


def test_command_menu_shows_description_and_example():
    editor = LineEditor(StringIO(), get_key=lambda: "\r", width=100)
    editor.buffer = "/gepa"
    _, _, _, hints, _ = editor._lines()
    assert "› /gepa CYCLES REQUESTS HOURS NOTE" in hints
    assert "  start a bounded GEPA run" in hints
    assert "  Example: /gepa 20 450 2 improve reversal capture" in hints


def test_command_menu_scrolls_and_tab_inserts_highlighted_command():
    output = StringIO()
    keys = iter(["/", *["\xe0P"] * 4, "\t", "\r"])
    editor = LineEditor(output, get_key=lambda: next(keys), width=100)
    assert editor.read() == "/new"
    rendered = output.getvalue()
    assert "↑ more" in rendered and "↓ more" in rendered
    assert "› /new" in rendered
    assert "Example: /new" in rendered


def test_command_examples_cover_every_registered_command():
    assert set(EXAMPLES) == {command for command, _, _ in COMMANDS}
    assert all(EXAMPLES.values())


def test_command_menu_up_wraps_to_last_and_limits_visible_rows():
    output = StringIO()
    keys = iter(["/", "\xe0H", "\t", "\r"])
    editor = LineEditor(output, get_key=lambda: next(keys), width=100)
    assert editor.read() == "/exit"
    menu = LineEditor(StringIO(), get_key=lambda: "\r", width=100)
    menu.buffer = menu.menu_text = "/"
    menu.selected = len(menu._command_matches()) - 1
    _, _, _, hints, _ = menu._lines()
    visible = [hint for hint in hints if hint.startswith(("› /", "  /"))]
    assert len(visible) == 4
    assert visible[-1] == "› /exit"
    assert "  ↑ more" in hints and "  ↓ more" not in hints


def test_redraw_repositions_cursor_when_menu_rows_grow_and_shrink():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=80)
    editor._render()
    editor.buffer, editor.cursor = "/", 1
    output.seek(0)
    output.truncate()
    editor._render()
    assert output.getvalue().startswith("\x1b[1A\r\x1b[J")
    assert output.getvalue().endswith("\x1b[8A\x1b[4G")
    editor.buffer, editor.cursor = "/x", 2
    output.seek(0)
    output.truncate()
    editor._render()
    assert output.getvalue().startswith("\x1b[1A\r\x1b[J")
    assert output.getvalue().endswith("\x1b[1A\x1b[5G")
