"""Run one Git Bash command on the host and end every process it started."""
from __future__ import annotations

import ctypes
import subprocess
import threading
import time

HEAD, TAIL = 4 * 1024, 24 * 1024
SLICE = 0.2
KILL_ON_JOB_CLOSE, EXTENDED_LIMITS = 0x2000, 9
PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001


class _Basic(ctypes.Structure):
    _fields_ = [("user_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", ctypes.c_uint32),
                ("minimum_set", ctypes.c_size_t), ("maximum_set", ctypes.c_size_t), ("processes", ctypes.c_uint32),
                ("affinity", ctypes.c_size_t), ("priority", ctypes.c_uint32), ("scheduling", ctypes.c_uint32)]


class _Extended(ctypes.Structure):
    _fields_ = [("basic", _Basic), ("io", ctypes.c_uint64 * 6), ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]


class _Job:
    """A Job object that ends all member processes, including background children, when it closes."""

    def __init__(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel, self.handle = kernel, kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("cannot create a job object")
        limits = _Extended()
        limits.basic.flags = KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError("cannot set the job limits")

    def add(self, pid):
        process = self.kernel.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        try:
            if not process or not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise OSError("cannot add the shell to its job")
        finally:
            if process:
                self.kernel.CloseHandle(process)

    def close(self):
        if self.handle:
            self.kernel.TerminateJobObject(self.handle, 1)
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _clip(head, tail, total):
    """Join the kept output. Drop partial lines at the cut, so no secret is split past the hiding rules."""
    if total <= len(head) + len(tail):
        return bytes(head + tail)
    head = head[:head.rfind(b"\n") + 1]
    tail = tail[tail.find(b"\n") + 1:]
    skipped = total - len(head) - len(tail)
    return bytes(head) + f"... {skipped} bytes skipped ...\n".encode() + bytes(tail)


def run(shell, command, cwd, env, seconds):
    """Return (exit code, timed out, output text). Every process the command started ends before return."""
    job = _Job()
    try:
        process = subprocess.Popen([str(shell), "-c", command], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    except OSError:
        job.close()
        raise
    head, tail, total = bytearray(), bytearray(), [0]

    def collect():
        # read1 returns as soon as output arrives. Only the head and tail stay in memory.
        for chunk in iter(lambda: process.stdout.read1(8192), b""):
            total[0] += len(chunk)
            room = HEAD - len(head)
            head.extend(chunk[:max(room, 0)])
            tail.extend(chunk[max(room, 0):])
            del tail[:-TAIL]

    reader = threading.Thread(target=collect, daemon=True)
    timed_out = False
    try:
        job.add(process.pid)
        reader.start()
        end = time.monotonic() + seconds
        # Short waits let Ctrl+C stop the command at once.
        while process.poll() is None:
            if time.monotonic() >= end:
                timed_out = True
                break
            try:
                process.wait(timeout=SLICE)
            except subprocess.TimeoutExpired:
                pass
    except BaseException:
        process.kill()  # The job may not hold the shell yet.
        raise
    finally:
        job.close()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass
    reader.join(timeout=10)
    return process.returncode, timed_out, _clip(head, tail, total[0]).decode("utf-8", "replace")
