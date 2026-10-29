import ctypes
import os
import re
import sys
from io import StringIO
from random import Random

import pytest

from compertum.harness.commands import COMMANDS, DESCRIPTIONS, EXAMPLES, complete, help_text
from compertum.harness.editor import SYNC_END, SYNC_START, LineEditor, Picker, _InputRecord, console_keys


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
    assert complete("/report te") is None


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


def test_box_title_shows_the_model_and_tab_leaves_out_optional_parts():
    editor = LineEditor(StringIO(), get_key=lambda: "\r", width=60, title="Compertum · deepseek-flash")
    top, middle, _, _, _ = editor._lines()
    assert top.startswith("╭─ Compertum · deepseek-flash ─") and len(top) == len(middle) == 58
    keys = iter(["/", "\xe0P", "\xe0P", "\t", "\r"])
    assert LineEditor(StringIO(), get_key=lambda: next(keys), width=80).read() == "/model "
    assert complete("/model") == "/model " and complete("/watc") == "/watch " and complete("/res") == "/resume SESSION_ID"


def test_enter_runs_the_highlighted_command_or_fills_its_template():
    # The owner typed "/", moved to /runs and pressed Enter; the harness sent "/" instead of /runs.
    def typed(*keys):
        pressed = iter(keys)
        return LineEditor(StringIO(), get_key=lambda: next(pressed), width=100).read()

    assert typed("/", "r", "u", "\xe0P", "\r") == "/runs"
    assert typed("/", "\r") == "/help"
    assert typed(*"/model", "\r") == "/model"
    assert typed(*"/ge", "\r", "\r") == "/gepa CYCLES REQUESTS HOURS NOTE"
    assert typed(*"/res", "\r", *["\x08"] * 10, *"session-1", "\r") == "/resume session-1"
    assert typed(*"/nothing", "\r") == "/nothing"
    assert typed(*"hello /", "\r") == "hello /"


def test_paste_keeps_line_breaks_and_tabs_in_one_task():
    keys = ["l", "1", "\r", "\t", "l", "2", "\r"]
    # Characters wait after every pasted key except the last Enter, which sends the whole paste.
    editor = LineEditor(StringIO(), get_key=lambda: keys.pop(0), width=60, more=lambda: bool(keys))
    assert editor.read() == "l1\n\tl2"
    _, middle, _, _, _ = editor._lines()
    assert "l1↵→l2" in middle


def test_composer_keys_for_clearing_moving_deleting_words_and_emoji():
    def typed(*keys):
        pressed = iter(keys)
        return LineEditor(StringIO(), get_key=lambda: next(pressed), width=60).read()

    assert typed(*"draft", "\x1b", *"new", "\r") == "new"
    assert typed(*"hello", "\x01", "x", "\x05", "y", "\r") == "xhelloy"
    assert typed(*"one two", "\x7f", *"three", "\r") == "one three"
    assert typed(*"keep", "\x1a", "\r") == "keep"  # Ctrl+Z with text keeps the text; it quits only from an empty box.
    assert typed("a", "\ud83d", "\ude00", "b", "\r") == "a\U0001F600b"
    with pytest.raises(EOFError):
        typed("\x1a")


def test_enter_on_a_menu_choice_shows_the_command_that_runs():
    output, screen = StringIO(), Screen(100)
    pressed = iter(["/", "r", "u", "\xe0P", "\r"])
    assert LineEditor(output, get_key=lambda: next(pressed), width=100).read() == "/runs"
    screen.feed(output.getvalue())
    assert screen.text()[1].startswith("│ /runs ")


def test_tab_after_a_space_completes_the_argument_not_the_template():
    sessions = lambda: ["session-20261029-one"]
    runs = lambda: {"gepa-20261029-one": {}}
    assert complete("/resume ", sessions, runs) == "/resume session-20261029-one"
    assert complete("/report ", sessions, runs) == "/report gepa-20261029-one"
    assert complete("/gepa ") is None
    assert complete("/model ", model_files=lambda: ["kimi"]) == "/model kimi"


def test_picker_moves_selects_cancels_and_clears_its_rows():
    options = [f"model-{n}" for n in range(12)]
    for keys, result in ((["\xe0P", "\xe0P", "\r"], 2), (["\xe0H", "\x1b"], None)):
        output, screen, pressed = StringIO(), Screen(60), iter(keys)
        assert Picker(output, options, 0, get_key=lambda: next(pressed), width=60, title="Choose a model").read() == result
        screen.feed(output.getvalue())
        # No box, and nothing left behind: the result line prints where the picker was.
        assert "╭" not in output.getvalue() and set(screen.text()) == {""} and (screen.row, screen.column) == (0, 0)
        assert output.getvalue().startswith("\x1b[?25l") and output.getvalue().endswith("\x1b[?25h")
    picker = Picker(StringIO(), options, 11, get_key=lambda: "\r", width=60, title="Choose a model")
    heading, blank, first, rows, _ = picker._lines()
    assert heading.startswith("Choose a model · ↑/↓ choose") and blank == "" and first == "    model-4"
    assert rows[-2] == "  › model-11" and rows[-1] == "    ↑ 4 more"
    keys = iter(["\xe0H", "\r"])
    assert Picker(StringIO(), options, 0, get_key=lambda: next(keys), width=60).read() == 11


def test_enter_erases_the_command_menu():
    output = StringIO()
    keys = iter(["/", "\r"])
    screen = Screen(80)
    LineEditor(output, get_key=lambda: next(keys), width=80).read()
    screen.feed(output.getvalue())
    assert screen.text()[3:] == [] or set(screen.text()[3:]) == {""}
    assert (screen.row, screen.column) == (3, 0)


def test_editor_supports_cursor_editing():
    keys = iter([*"abc", "\x00K", "\x08", "\x00O", "d", "\x00G", "z", "\x00S", "\r"])
    editor = LineEditor(StringIO(), get_key=lambda: next(keys), width=60)
    assert editor.read() == "zcd"


class Writes(StringIO):
    def __init__(self):
        super().__init__()
        self.frames = []

    def write(self, text):
        self.frames.append(text)
        return super().write(text)


class Screen:
    """A minimal terminal: enough cursor control to check what the composer leaves on screen."""

    def __init__(self, columns):
        self.columns, self.rows, self.row, self.column = columns, [[]], 0, 0

    def feed(self, text):
        for code in re.findall(r"\x1b\[\??[0-9]*[A-Za-z]|.", text, re.S):
            if code.startswith("\x1b["):
                count, op = int(code[2:-1].lstrip("?") or 1), code[-1]
                if code in (SYNC_START, SYNC_END, "\x1b[?25l", "\x1b[?25h"):
                    continue
                if op == "A":
                    assert count <= self.row, "the composer moved above its first row"
                    self.row -= count
                elif op == "B":
                    assert self.row + count < len(self.rows), "the composer moved below its last row"
                    self.row += count
                elif op == "G":
                    self.column = count - 1
                elif op == "J":
                    del self.rows[self.row + 1:]
                    del self.rows[self.row][self.column:]
                elif code == "\x1b[2K":
                    self.rows[self.row] = []
                else:
                    raise AssertionError(f"unexpected control {code!r}")
            elif code == "\r":
                self.column = 0
            elif code == "\n":
                # Windows text output writes "\n" as "\r\n".
                self.row, self.column = self.row + 1, 0
                if self.row == len(self.rows):
                    self.rows.append([])
            else:
                assert self.column < self.columns, "the composer wrapped a row"
                line = self.rows[self.row]
                line.extend(" " * (self.column - len(line)))
                line[self.column:self.column + 1] = [code]
                self.column += 1

    def text(self):
        # Erased rows below the frame stay on screen as blank rows.
        rows = ["".join(line).rstrip() for line in self.rows]
        while len(rows) > 1 and not rows[-1] and self.row < len(rows) - 1:
            rows.pop()
        return rows


def body(text):
    assert text.startswith(SYNC_START) and text.endswith(SYNC_END)
    return text[len(SYNC_START):-len(SYNC_END)]


def test_console_events_translate_to_editor_keys():
    assert console_keys(1, True, 0x41, "a") == ["a"]
    assert console_keys(1, True, 0x41, "a", repeat=3) == ["a", "a", "a"]
    assert console_keys(1, True, 0x26) == ["\xe0H"]
    assert console_keys(1, True, 0x28) == ["\xe0P"]
    assert console_keys(1, True, 0x25) == ["\xe0K"]
    assert console_keys(1, True, 0x27) == ["\xe0M"]
    assert console_keys(1, True, 0x24) == ["\xe0G"]
    assert console_keys(1, True, 0x23) == ["\xe0O"]
    assert console_keys(1, True, 0x2E) == ["\xe0S"]
    assert console_keys(1, True, 0x0D, "\r") == ["\r"]
    assert console_keys(1, True, 0x43, "\x03") == ["\x03"]
    assert console_keys(1, False, 0x41, "a") == []
    assert console_keys(1, False, 0x12, "é") == ["é"]
    assert console_keys(1, True, 0x10) == []
    assert console_keys(4) == []
    assert console_keys(1, True, 0x25, control=0x8) == []
    assert console_keys(1, True, 0x26, control=0x2) == []
    assert console_keys(1, True, 0x41, "a", control=0x2) == []
    assert console_keys(1, True, 0x09, "\t", control=0x10) == []
    assert console_keys(1, True, 0x51, "@", control=0x1 | 0x8) == ["@"]
    assert console_keys(1, True, 0x41, "A", control=0x10) == ["A"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console record layout")
def test_console_record_matches_the_windows_layout():
    assert ctypes.sizeof(_InputRecord) == 20


def test_each_frame_is_one_synchronized_write():
    output = Writes()
    keys = iter([*"/ge", "\xe0P", "\t", "\r"])
    editor = LineEditor(output, get_key=lambda: next(keys), width=80)
    editor.read()
    frames = output.frames[:-1]
    # Down on the only match changes nothing, so it writes no frame.
    assert len(frames) == 5
    assert all(frame.startswith(SYNC_START) and frame.endswith(SYNC_END) for frame in frames)
    assert output.frames[-1] == "\x1b[1B\r\n"


def test_stable_frame_rewrites_only_changed_rows():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=60)
    editor._render()
    output.seek(0)
    output.truncate()
    editor.buffer, editor.cursor = "a", 1
    editor._render()
    _, middle, _, _, _ = editor._lines()
    assert body(output.getvalue()) == "\r\x1b[2K" + middle + "\x1b[4G"
    output.seek(0)
    output.truncate()
    editor.cursor = 0
    editor._render()
    assert body(output.getvalue()) == "\x1b[3G"


def test_height_change_forces_a_full_redraw(monkeypatch):
    size = [os.terminal_size((80, 30))]
    monkeypatch.setattr("compertum.harness.editor.shutil.get_terminal_size", lambda fallback: size[0])
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r")
    editor.buffer, editor.cursor = "/", 1
    editor._render()
    editor._move_menu(1)
    size[0] = os.terminal_size((80, 12))
    output.seek(0)
    output.truncate()
    editor._render()
    assert body(output.getvalue()).startswith("\x1b[1A\r\x1b[J")


def test_menu_movement_rewrites_menu_rows_without_the_box():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=100)
    editor.buffer, editor.cursor = "/", 1
    editor._render()
    top, middle, bottom, _, _ = editor._lines()
    output.seek(0)
    output.truncate()
    editor._move_menu(1)
    editor._render()
    patch = body(output.getvalue())
    assert top not in patch and middle not in patch and bottom not in patch
    assert "› " in patch and "\x1b[J" not in patch


def test_redraw_returns_to_the_input_row_and_borders_align():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=60)
    editor._render()
    assert body(output.getvalue()).endswith("\x1b[1A\x1b[3G")
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
    assert body(output.getvalue()).startswith("\x1b[3A\r\x1b[J")
    top, middle, bottom, _, _ = editor._lines()
    assert len(top) == len(middle) == len(bottom) == 38
    output.seek(0)
    output.truncate()
    editor.width = 100
    editor._render()
    assert body(output.getvalue()).startswith("\x1b[1A\r\x1b[J")


def test_typing_menu_movement_and_widening_leave_only_the_current_frame():
    random = Random(20261028)
    keys = ["g", "e", "m", "o", "n", "x", " ", "\x08", "\xe0H", "\xe0P", "\xe0P", "\xe0P", "\xe0K", "\xe0M", "\t"]
    # Each round opens the command menu, edits and scrolls it, then clears the input.
    script = [key for _ in range(25) for key in ["/", *random.choices(keys, k=12), "\xe0O", *["\x08"] * 60]]
    sizes = [60] * 300 + list(range(61, 201)) + [200] * len(script)
    output = StringIO()
    screen = Screen(60)
    editor = LineEditor(output, width=60)
    steps = iter(zip(sizes, script))
    checked = 0

    def next_key():
        nonlocal checked
        screen.feed(output.getvalue())
        output.seek(0)
        output.truncate()
        top, middle, bottom, hints, column = editor._lines()
        assert screen.text() == [top, middle, bottom, *hints]
        assert (screen.row, screen.column) == (1, column - 1)
        checked += 1
        width, key = next(steps, (screen.columns, "\r"))
        # Widening keeps every short row in place, so this screen needs no reflow model.
        editor.width = screen.columns = width
        return key

    editor.get_key = next_key
    editor.read()
    assert checked == len(script) + 1


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
    assert hints == ["", "  › /gepa CYCLES REQUESTS HOURS NOTE   start a bounded GEPA run", "",
                     "    Example: /gepa 20 450 2 improve reversal capture"]


def test_command_menu_aligns_descriptions_and_spaces_its_sections():
    editor = LineEditor(StringIO(), get_key=lambda: "\r", width=100)
    editor.buffer = editor.menu_text = "/"
    editor.selected = 6
    _, _, _, hints, _ = editor._lines()
    assert hints[0] == "" and hints[-2] == ""
    rows = hints[1:7]
    assert rows[-1].startswith("  › /resume SESSION_ID ")
    descriptions = [DESCRIPTIONS[name] for name in ("/status", "/model", "/models", "/new", "/sessions", "/resume")]
    assert len({row.index(text) for row, text in zip(rows, descriptions)}) == 1
    assert hints[7] == "    ↑ 1 more   ↓ 11 more"
    assert hints[-1] == "    Example: /resume session-20261028-104110-7382a492"


def test_narrow_command_menu_moves_the_description_below_the_list():
    editor = LineEditor(StringIO(), get_key=lambda: "\r", width=44)
    editor.buffer = editor.menu_text = "/"
    editor.selected = 6
    _, _, _, hints, _ = editor._lines()
    assert "  › /resume SESSION_ID" in hints
    assert hints[-2:] == ["    resume a conversation", "    Example: /resume session-20261028-1041"]


def test_command_menu_scrolls_and_tab_inserts_highlighted_command():
    output = StringIO()
    keys = iter(["/", *["\xe0P"] * 6, "\t", "\r"])
    editor = LineEditor(output, get_key=lambda: next(keys), width=100)
    assert editor.read() == "/resume SESSION_ID"
    rendered = output.getvalue()
    assert "↑ 1 more   ↓ 11 more" in rendered
    assert "› /resume" in rendered
    assert "Example: /resume" in rendered


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
    visible = [hint for hint in hints if hint.startswith(("  › /", "    /"))]
    assert len(visible) == 6
    assert visible[-1].startswith("  › /exit ")
    assert "    ↑ 12 more" in hints and not any("↓" in hint for hint in hints)


def test_redraw_repositions_cursor_when_menu_rows_grow_and_shrink():
    output = StringIO()
    editor = LineEditor(output, get_key=lambda: "\r", width=80)
    editor._render()
    editor.buffer, editor.cursor = "/", 1
    output.seek(0)
    output.truncate()
    editor._render()
    assert body(output.getvalue()).startswith("\x1b[1A\r\x1b[J")
    assert body(output.getvalue()).endswith("\x1b[11A\x1b[4G")
    editor.buffer, editor.cursor = "/x", 2
    output.seek(0)
    output.truncate()
    editor._render()
    patch = body(output.getvalue())
    assert patch.startswith("\r\x1b[2K│ /x")
    assert "\x1b[2B\r\x1b[J" in patch
    assert patch.endswith("\x1b[2A\x1b[5G")
