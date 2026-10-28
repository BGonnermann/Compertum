"""A small interactive composer with a box, hints, and Tab completion."""
from __future__ import annotations

import shutil
import sys
import time

from .commands import DESCRIPTIONS, EXAMPLES, complete, matching_commands

VISIBLE_COMMANDS = 4


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


class LineEditor:
    def __init__(self, out=None, sessions=(), runs=(), get_key=windows_key, width=None, model_files=(), model_ids=None):
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
        hints = ["  ↑ more"] if start else []
        for index in range(start, end):
            hints.append(("› " if index == self.selected else "  ") + matches[index])
        if end < len(matches):
            hints.append("  ↓ more")
        name = matches[self.selected].split(maxsplit=1)[0]
        hints.extend(["  " + DESCRIPTIONS[name], "  Example: " + EXAMPLES[name]])
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
        columns = max(1, self.width or shutil.get_terminal_size((100, 24)).columns)
        if self._frame == (frame, columns):
            return
        top, middle, bottom, hints, column = frame
        if self.rendered:
            previous, _ = self._frame
            old_top, _, _, _, old_column = previous
            top_rows = max(1, (len(old_top) + columns - 1) // columns)
            input_row = (old_column - 1) // columns
            self.out.write(f"\x1b[{top_rows + input_row}A")
        self.out.write("\r\x1b[J")
        lines = [top, middle, bottom, *hints]
        self.out.write("\r" + "\n".join(lines))
        if len(lines) > 1:
            self.out.write(f"\x1b[{len(lines) - 2}A")
        self.out.write(f"\x1b[{column}G")
        self.out.flush()
        self.rendered = len(lines)
        self._frame = frame, columns

    def _finish(self):
        if self.rendered > 2:
            self.out.write(f"\x1b[{self.rendered - 2}B")
        self.out.write("\r\n")
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
        while True:
            self._render()
            key = self.get_key()
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
