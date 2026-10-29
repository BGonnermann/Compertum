import ctypes
import json
import os
import subprocess
import sys
import time

import pytest

PARENT = r"""
import subprocess, sys, time
from compertum.harness.runs import GROUP, spawn_detached

CHILD = ("import ctypes, json, sys, time; ids = (ctypes.c_uint32 * 64)(); "
         "count = ctypes.windll.kernel32.GetConsoleProcessList(ids, 64); "
         "open(sys.argv[1], 'w').write(json.dumps(list(ids[:count]))); time.sleep(60)")
options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
detached = spawn_detached(subprocess.Popen, [sys.executable, "-c", CHILD, "detached.json"], **options)
attached = subprocess.Popen([sys.executable, "-c", CHILD, "attached.json"], creationflags=GROUP, **options)
print(detached.pid, attached.pid, flush=True)
time.sleep(60)
"""

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows consoles and job objects")


def _job(breakaway):
    from compertum.harness.shell import EXTENDED_LIMITS, KILL_ON_JOB_CLOSE, _Extended, _Job
    job = _Job()
    limits = _Extended()
    limits.basic.flags = KILL_ON_JOB_CLOSE | (0x800 if breakaway else 0)
    assert job.kernel.SetInformationJobObject(job.handle, EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits))
    return job


def _console(path):
    end = time.monotonic() + 30
    while time.monotonic() < end:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            time.sleep(0.1)
    pytest.fail(f"{path.name} was not written")


@pytest.mark.parametrize("breakaway", [True, False], ids=["job-allows-breakaway", "job-forbids-breakaway"])
def test_engine_run_leaves_the_console_and_job_that_started_it(tmp_path, breakaway):
    from compertum.harness.runs import OwnedProcess
    job = _job(breakaway)
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
    parent = subprocess.Popen([sys.executable, "-c", PARENT], cwd=tmp_path, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=subprocess.CREATE_NO_WINDOW | 0x4)
    children = []
    try:
        job.add(parent.pid)
        ntdll.NtResumeProcess(int(parent._handle))
        line = parent.stdout.readline()
        assert line, parent.stderr.read()
        children = [OwnedProcess(int(pid)) for pid in line.split()]
        detached, attached = (_console(tmp_path / name) for name in ("detached.json", "attached.json"))
        assert parent.pid in attached
        assert parent.pid not in detached
        job.close()
        parent.wait(timeout=10)
        time.sleep(1)
        assert children[1].poll() is not None
        assert (children[0].poll() is None) is breakaway
    finally:
        job.close()
        for child in children:
            child.terminate()
        if parent.poll() is None:
            parent.kill()
