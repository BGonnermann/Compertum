"""A small interactive composer with a box, hints, and Tab completion."""
from __future__ import annotations

import ctypes
import shutil
import sys
import time

from .commands import DESCRIPTIONS, EXAMPLES, complete, matching_commands

VISIBLE_COMMANDS = 4
# The menu indents rows under the input text and needs room for this much description beside the commands.
MENU_INDENT, MENU_GAP, MIN_DESCRIPTION = 4, 3, 16
SYNC_START, SYNC_END = "\x1b[?2026h", "\x1b[?2026l"
KEY_EVENT, VK_MENU = 0x1, 0x12
ALT_PRESSED, CTRL_PRESSED, SHIFT_PRESSED = 0x1 | 0x2, 0x4 | 0x8, 0x10
VIRTUAL_KEYS = {0x26: "\xe0H", 0x28: "\xe0P", 0x25: "\xe0K", 0x27: "\xe0M", 0x24: "\xe0G", 0x23: "\xe0O", 0x2E: "\xe0S"}
# Processed, line, echo and virtual-terminal input stay off while the composer reads. Window input reports resizes.
RAW_CLEAR, WINDOW_INPUT = 0x1 | 0x2 | 0x4 | 0x200, 0x8
# A missed resize event still repairs the frame within this wait. Unchanged frames write nothing.
SAFETY_WAIT_MS, WAIT_TIMEOUT = 500, 0x102


def enable_vt(out):
    if not out.isatty():
        return False
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError, ValueError):
        return False


def windows_key():
    import msvcrt
    if not msvcrt.kbhit():
        time.sleep(0.05)
        return ""
    key = msvcrt.getwch()
    return key + msvcrt.getwch() if key in ("\x00", "\xe0") else key


def console_keys(event_type, key_down=False, virtual_key=0, char="\x00", repeat=1, control=0):
    """Translate one console input record into the editor's key strings."""
    if event_type != KEY_EVENT:
        return []
    if not key_down:
        # Alt+numpad entry delivers its character when Alt is released.
        return [char] if virtual_key == VK_MENU and char != "\x00" else []
    if char == "\x00":
        # Modified navigation keys, including numpad keys during Alt-code entry, did nothing with keyboard polling.
        key = None if control & (ALT_PRESSED | CTRL_PRESSED) else VIRTUAL_KEYS.get(virtual_key)
    elif control & ALT_PRESSED and not control & CTRL_PRESSED or char == "\t" and control & SHIFT_PRESSED:
        key = None  # Alt+letter and Shift+Tab were ignored too. AltGr sets Ctrl as well, so its characters still type.
    else:
        key = char
    return [key] * max(1, repeat) if key else []


class _KeyEvent(ctypes.Structure):
    _fields_ = [("key_down", ctypes.c_int), ("repeat", ctypes.c_ushort), ("virtual_key", ctypes.c_ushort),
                ("scan_code", ctypes.c_ushort), ("char", ctypes.c_wchar), ("control", ctypes.c_uint32)]


class _Event(ctypes.Union):
    _fields_ = [("key", _KeyEvent), ("raw", ctypes.c_byte * 16)]


class _InputRecord(ctypes.Structure):
    _fields_ = [("event_type", ctypes.c_ushort), ("event", _Event)]


class ConsoleInput:
    """Wait for Windows console key and resize events instead of polling the keyboard."""

    def __init__(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.restype = ctypes.c_void_p
        self.kernel, self.handle, self.pending = kernel, ctypes.c_void_p(kernel.GetStdHandle(-10)), []
        self.mode = ctypes.c_uint32()
        if not kernel.GetConsoleMode(self.handle, ctypes.byref(self.mode)):
            raise OSError("console input is unavailable")

    def __enter__(self):
        if not self.kernel.SetConsoleMode(self.handle, (self.mode.value & ~RAW_CLEAR) | WINDOW_INPUT):
            raise OSError("console input mode is unavailable")
        return self

    def __exit__(self, *exc):
        self.kernel.SetConsoleMode(self.handle, self.mode.value)

    def read(self):
        if self.pending:
            return self.pending.pop(0)
        waited = self.kernel.WaitForSingleObject(self.handle, SAFETY_WAIT_MS)
        record, count = _InputRecord(), ctypes.c_uint32()
        if waited != 0 or not self.kernel.ReadConsoleInputW(self.handle, ctypes.byref(record), 1, ctypes.byref(count)):
            if waited != WAIT_TIMEOUT:
                time.sleep(0.05)  # A failed console call must not spin the processor.
            return ""
        key = record.event.key
        self.pending = console_keys(record.event_type, key.key_down, key.virtual_key, key.char, key.repeat, key.control)
        # Resize and ignored events return an empty key, so the editor redraws only when the frame changed.
        return self.pending.pop(0) if self.pending else ""


def _move(rows):
    return f"\x1b[{rows}B" if rows > 0 else f"\x1b[{-rows}A" if rows < 0 else ""


class LineEditor:
    def __init__(self, out=None, sessions=(), runs=(), get_key=None, width=None, model_files=(), model_ids=None):
        self.out = out or sys.stdout
        self.sessions, self.runs, self.get_key = sessions, runs, get_key
        self.model_files, self.model_ids = model_files, model_ids
        self.width = width
        self.buffer, self.cursor, self.rendered = "", 0, 0
        self.menu_text, self.selected, self.menu_offset = None, 0, 0
        self._frame = None

    def _size(self):
        terminal = self.width or shutil.get_terminal_size((100, 24)).columns
        return max(15, terminal - 2)

    def _command_matches(self):
        if not self.buffer.startswith("/") or any(c.isspace() for c in self.buffer):
            return []
        return matching_commands(self.buffer, limit=None)

    def _hints(self, width):
        if self.buffer != self.menu_text:
            self.menu_text, self.selected, self.menu_offset = self.buffer, 0, 0
        matches = self._command_matches()
        if not matches:
            return []
        self.selected = min(self.selected, len(matches) - 1)
        if self.selected < self.menu_offset:
            self.menu_offset = self.selected
        elif self.selected >= self.menu_offset + VISIBLE_COMMANDS:
            self.menu_offset = self.selected - VISIBLE_COMMANDS + 1
        self.menu_offset = max(0, min(self.menu_offset, len(matches) - VISIBLE_COMMANDS))
        start = self.menu_offset
        end = min(start + VISIBLE_COMMANDS, len(matches))
        # Descriptions share one column across all matches, so scrolling does not shift them.
        column = max(map(len, matches)) + MENU_GAP
        inline = width >= MENU_INDENT + column + MIN_DESCRIPTION
        indent = " " * MENU_INDENT
        hints = [""]
        for index in range(start, end):
            usage = matches[index]
            row = usage.ljust(column) + DESCRIPTIONS[usage.split(maxsplit=1)[0]] if inline else usage
            hints.append(("  › " if index == self.selected else indent) + row)
        more = [f"↑ {start} more"] * bool(start) + [f"↓ {len(matches) - end} more"] * (end < len(matches))
        if more:
            hints.append(indent + "   ".join(more))
        name = matches[self.selected].split(maxsplit=1)[0]
        hints.append("")
        if not inline:
            hints.append(indent + DESCRIPTIONS[name])
        hints.append(indent + "Example: " + EXAMPLES[name])
        return [hint[:width] for hint in hints]

    def _lines(self):
        width = self._size()
        top = "╭─ Compertum " + "─" * max(1, width - 14) + "╮"
        inside = width - 4
        start = max(0, self.cursor - inside + 1) if self.cursor >= inside else 0
        shown = self.buffer[start:start + inside]
        middle = "│ " + shown + " " * max(0, inside - len(shown)) + " │"
        bottom = "╰" + "─" * max(1, width - 2) + "╯"
        return top, middle, bottom, self._hints(width), self.cursor - start + 3

    def _render(self):
        frame = self._lines()
        terminal = shutil.get_terminal_size((100, 24))
        columns = max(1, self.width or terminal.columns)
        # A height change can push frame rows out of view, so it also forces a full redraw.
        size = columns, None if self.width else terminal.lines
        if self._frame == (frame, size):
            return
        top, middle, bottom, hints, column = frame
        lines = [top, middle, bottom, *hints]
        body = self._patch(lines) if self._can_patch(lines, size) else self._redraw(lines, columns)
        # One synchronized write lets supporting terminals show the whole frame at once. Others ignore the markers.
        self.out.write(SYNC_START + body + f"\x1b[{column}G" + SYNC_END)
        self.out.flush()
        self.rendered = len(lines)
        self._frame = frame, size

    def _rows(self):
        top, middle, bottom, hints, _ = self._frame[0]
        return [top, middle, bottom, *hints]

    def _can_patch(self, lines, size):
        # Rows can be patched in place only when no row reached the edge and the frame did not grow past existing rows.
        if not self.rendered or self._frame[1] != size:
            return False
        old = self._rows()
        return len(lines) <= len(old) and all(len(line) < size[0] for line in [*old, *lines])

    def _patch(self, lines):
        old, parts, row = self._rows(), [], 1
        for index, line in enumerate(lines):
            if old[index] != line:
                parts.append(_move(index - row) + "\r\x1b[2K" + line)
                row = index
        if len(lines) < len(old):
            parts.append(_move(len(lines) - row) + "\r\x1b[J")
            row = len(lines)
        parts.append(_move(1 - row))
        return "".join(parts)

    def _redraw(self, lines, columns):
        parts = []
        if self.rendered:
            old_top, _, _, _, old_column = self._frame[0]
            top_rows = max(1, (len(old_top) + columns - 1) // columns)
            input_row = (old_column - 1) // columns
            parts.append(f"\x1b[{top_rows + input_row}A")
        parts.append("\r\x1b[J\r" + "\n".join(lines))
        if len(lines) > 1:
            parts.append(f"\x1b[{len(lines) - 2}A")
        return "".join(parts)

    def _finish(self):
        self.out.write(_move(self.rendered - 2) * (self.rendered > 2) + "\r\n")
        self.out.flush()
        return self.buffer

    def _complete(self):
        matches = self._command_matches()
        replacement = matches[min(self.selected, len(matches) - 1)] if matches else complete(
            self.buffer, self.sessions, self.runs, self.model_files, self.model_ids)
        if replacement is not None:
            self.buffer, self.cursor = replacement, len(replacement)

    def _move_menu(self, delta):
        matches = self._command_matches()
        if matches:
            self.selected = (self.selected + delta) % len(matches)

    def read(self):
        if self.get_key is not None:
            return self._read(self.get_key)
        try:
            console = ConsoleInput().__enter__()
        except (AttributeError, OSError):
            return self._read(windows_key)
        try:
            return self._read(console.read)
        finally:
            console.__exit__()

    def _read(self, get_key):
        while True:
            self._render()
            key = get_key()
            if key in ("\r", "\n"):
                return self._finish()
            if key == "\t":
                self._complete()
            elif key == "\x03":
                raise KeyboardInterrupt()
            elif key in ("\x04", "\x1a"):
                raise EOFError()
            elif key == "\x08":
                if self.cursor:
                    self.buffer = self.buffer[:self.cursor - 1] + self.buffer[self.cursor:]
                    self.cursor -= 1
            elif key in ("\x00H", "\xe0H"):
                self._move_menu(-1)
            elif key in ("\x00P", "\xe0P"):
                self._move_menu(1)
            elif key in ("\x00K", "\xe0K"):
                self.cursor = max(0, self.cursor - 1)
            elif key in ("\x00M", "\xe0M"):
                self.cursor = min(len(self.buffer), self.cursor + 1)
            elif key in ("\x00G", "\xe0G"):
                self.cursor = 0
            elif key in ("\x00O", "\xe0O"):
                self.cursor = len(self.buffer)
            elif key in ("\x00S", "\xe0S"):
                self.buffer = self.buffer[:self.cursor] + self.buffer[self.cursor + 1:]
            elif len(key) == 1 and key.isprintable():
                self.buffer = self.buffer[:self.cursor] + key + self.buffer[self.cursor:]
                self.cursor += 1
