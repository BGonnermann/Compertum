import json
import os
import subprocess
import sys

import pytest

CHILD = r"""
import ctypes, json, sys
from io import StringIO
from compertum.harness import editor
from compertum.harness.editor import KEY_EVENT, LineEditor, _InputRecord

def polling(*args):
    raise AssertionError("the composer fell back to keyboard polling")

editor.windows_key = polling
reading = []
read = editor.ConsoleInput.read

def checked_read(self):
    mode = ctypes.c_uint32()
    kernel.GetConsoleMode(handle, ctypes.byref(mode))
    reading.append(mode.value)
    return read(self)

editor.ConsoleInput.read = checked_read

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.CreateFileW.restype = ctypes.c_void_p
handle = ctypes.c_void_p(kernel.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None))
kernel.SetStdHandle(-10, handle)
before = ctypes.c_uint32()
kernel.GetConsoleMode(handle, ctypes.byref(before))

def key(char="\x00", virtual_key=0):
    records = []
    for down in (1, 0):
        record = _InputRecord(event_type=KEY_EVENT)
        record.event.key.key_down, record.event.key.repeat = down, 1
        record.event.key.virtual_key, record.event.key.char = virtual_key, char
        records.append(record)
    return records

resize = _InputRecord(event_type=0x4)
records = [*key("/"), *key("g"), resize, *key(virtual_key=0x28), *key("e"), *key("\t"), resize, *key("\r")]
array = (_InputRecord * len(records))(*records)
written = ctypes.c_uint32()
assert kernel.WriteConsoleInputW(handle, array, len(records), ctypes.byref(written)) and written.value == len(records)
output = StringIO()
text = LineEditor(output, width=80).read()
after = ctypes.c_uint32()
kernel.GetConsoleMode(handle, ctypes.byref(after))
json.dump({"text": text, "before": before.value, "after": after.value, "reading": reading,
           "output": output.getvalue()}, sys.stdout)
"""

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows console input")


def test_composer_reads_real_console_key_and_resize_events(tmp_path):
    # A hidden console gives the child a real input buffer without opening a window.
    result = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, encoding="utf-8",
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["text"] == "/gepa CYCLES REQUESTS HOURS NOTE"
    assert report["after"] == report["before"]
    # Window input is on. Processed, line, echo and virtual-terminal input are off during every read.
    assert report["reading"] and all(mode & 0x8 and not mode & 0x207 for mode in report["reading"])
    assert "\x1b[?2026h" in report["output"]
