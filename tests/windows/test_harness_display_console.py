import json
import os
import subprocess
import sys

import pytest

CHILD = r"""
import ctypes, json, sys, time
from compertum.harness.display import SPINNER, Display

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.CreateFileW.restype = ctypes.c_void_p
handle = ctypes.c_void_p(kernel.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None))
kernel.SetStdHandle(-11, handle)
out = open("CONOUT$", "w", encoding="utf-8")
display = Display(out)
display.step(1, 40, 0)
time.sleep(0.5)
display.line("answer")
display.idle("")

class Coord(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]

class Info(ctypes.Structure):
    _fields_ = [("size", Coord), ("cursor", Coord), ("attributes", ctypes.c_ushort),
                ("window", ctypes.c_short * 4), ("maximum", Coord)]

info = Info()
kernel.GetConsoleScreenBufferInfo(handle, ctypes.byref(info))
rows = []
for y in range(info.cursor.y + 1):
    buffer, read = ctypes.create_unicode_buffer(info.size.x), ctypes.c_uint32()
    kernel.ReadConsoleOutputCharacterW(handle, buffer, info.size.x, Coord(0, y), ctypes.byref(read))
    rows.append(buffer.value[:read.value].rstrip())
json.dump({"animate": display.animate, "rows": rows, "spinner": SPINNER}, sys.stderr)
"""

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows console output")


def test_spinner_leaves_only_the_answer_in_a_real_console(tmp_path):
    # A hidden console gives the child a real screen buffer without opening a window.
    result = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, encoding="utf-8",
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stderr)
    assert report["animate"] is True
    screen = [row for row in report["rows"] if row]
    assert screen == ["answer"]
    assert not any(frame in "".join(report["rows"]) for frame in report["spinner"])
