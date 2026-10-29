"""Owner-started bounded processes and uniform run cards."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from compertum.ai.manual import sanitized
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.jobs import available_physical_memory

MEMORY_FLOOR = 8 * 1024**3
STILL_ACTIVE = 259
GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
DETACHED = GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
BREAKAWAY = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)


class RunError(Exception):
    pass


def spawn_detached(spawn, command, **options):
    try:
        return spawn(command, creationflags=DETACHED | BREAKAWAY, **options)
    except PermissionError:
        return spawn(command, creationflags=DETACHED, **options)


def _process_handle(pid, terminate=False):
    if sys.platform != "win32":
        return None
    import ctypes
    access = 0x1000 | (0x0001 if terminate else 0)
    ctypes.windll.kernel32.OpenProcess.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    return ctypes.windll.kernel32.OpenProcess(access, False, pid)


def _creation(handle):
    import ctypes
    times = (ctypes.c_ulonglong * 4)()
    pointers = [ctypes.byref(times, offset) for offset in (0, 8, 16, 24)]
    if not ctypes.windll.kernel32.GetProcessTimes(handle, *pointers):
        return None
    return times[0]


def process_creation(pid):
    handle = _process_handle(pid)
    if not handle:
        return None
    import ctypes
    try:
        return _creation(handle)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class OwnedProcess:
    """A recovered Windows process, accepted only when its creation time matches."""
    def __init__(self, pid, created=None):
        self.pid, self.created, self._handle, self.gone = pid, created, None, False
        if sys.platform == "win32":
            import ctypes
            self._handle = _process_handle(pid, terminate=True) or None
            self.gone = self._handle is None and ctypes.windll.kernel32.GetLastError() == 87
            if self._handle and created is not None and _creation(self._handle) != created:
                self._close()
        if self._handle and self.created is None:
            self.created = _creation(self._handle)

    def _close(self):
        if self._handle:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None

    def poll(self):
        if not self._handle:
            return "LOST" if self.gone else "UNKNOWN"
        import ctypes
        code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            self._close()
            return "UNKNOWN"
        if code.value != STILL_ACTIVE:
            self._close()
        return None if code.value == STILL_ACTIVE else code.value

    def terminate(self):
        if self._handle:
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(self._handle, 1)


class FinishedProcess:
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code

    def terminate(self):
        return None


class RunManager:
    def __init__(self, root: Path, models="local", model=None, spawn=subprocess.Popen,
                 available_memory=available_physical_memory, adopt=None):
        self.root, self.models, self.model = root, models, model
        self.spawn, self.available_memory = spawn, available_memory
        self.folder = root / "state" / "harness" / "runs"
        self.active = {}
        self.adopt = adopt or (lambda meta: OwnedProcess(meta["pid"], meta.get("created")))
        self._recover()

    def select(self, models, model):
        self.models, self.model = models, model

    def _recover(self):
        if not self.folder.is_dir():
            return
        # The newest records come first, so the cap never drops a run that is still active.
        for path in sorted(self.folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:256]:
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
                if (meta.get("id") != path.stem or meta.get("kind") not in ("test", "practice", "gepa", "bench")
                        or type(meta.get("pid")) is not int or type(meta.get("started_wall")) not in (int, float)
                        or type(meta.get("deadline")) is not int or meta.get("log") != f"{path.stem}.log"):
                    continue
                process = FinishedProcess(meta["exit_code"]) if type(meta.get("exit_code")) is int else self.adopt(meta)
                record = {**meta, "started": time.monotonic() - max(0, time.time() - meta["started_wall"]),
                          "log": str(self.folder / meta["log"]), "process": process, "recovered": True}
                self.active[path.stem] = record
                if record["process"].poll() is None:
                    self._arm(record, max(1, record["deadline"] - int(time.time() - record["started_wall"])))
            except (OSError, ValueError, TypeError):
                continue

    def _arm(self, record, seconds):
        timer = threading.Timer(seconds, self._expire, args=(record["id"],))
        timer.daemon = True
        record["timer"] = timer
        timer.start()

    def _save(self, record):
        keys = ("id", "kind", "pid", "started_wall", "started_at", "deadline", "created", "exit_code", "dismissed",
                "planted_stop")
        meta = {key: record.get(key) for key in keys}
        path = self.folder / f"{record['id']}.json"
        path.write_text(json.dumps({**meta, "log": f"{record['id']}.log"}, sort_keys=True), encoding="utf-8")

    def start(self, kind, *, cycles=1, requests=100, note="owner started", paths=None, hours=None):
        if any(not record.get("dismissed") and record["process"].poll() in (None, "UNKNOWN") for record in self.active.values()):
            raise RunError("another harness run is active or unverified")
        available = self.available_memory()
        if type(available) is not int or available < MEMORY_FLOOR:
            raise RunError("AVAILABLE_RAM_FLOOR")
        if type(cycles) is not int or not 1 <= cycles <= 1000 or type(requests) is not int or not 1 <= requests <= 10000:
            raise RunError("the run limits are not valid")
        if not isinstance(note, str) or not 1 <= len(note) <= 256:
            raise RunError("the run note is not valid")
        if kind != "test" and self._stop_file().exists():
            raise RunError("state/engine/STOP exists. It stops every engine run. Delete it if no stop is intended, "
                           "then start the run again")
        try:
            sanitized(note.encode())
        except RuntimeRefused as error:
            raise RunError(error.code) from None
        identity = f"{kind}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        self.folder.mkdir(parents=True, exist_ok=True)
        log = self.folder / f"{identity}.log"
        temp = self.root / ".cache" / "test-runs" / identity
        if kind == "test":
            paths = paths or sorted(path.relative_to(self.root).as_posix()
                                    for path in (self.root / "tests").glob("test_harness_*.py"))
            if not paths:
                raise RunError("no harness test files were found; name the tests to run")  # Never the whole project.
            if not isinstance(paths, list) or len(paths) > 16 or any(not isinstance(p, str) or p.startswith("-") or ".." in Path(p).parts for p in paths):
                raise RunError("the test paths are not valid")
            checked = []
            for value in paths:
                path = (self.root / value).resolve(strict=False)
                if not path.is_relative_to(self.root):
                    raise RunError("test paths must stay inside the project")
                checked.append(path.relative_to(self.root).as_posix())
            paths = checked
            python = self.root / ".cache" / "clean-env-m0" / "Scripts" / "python.exe"
            command = [str(python), "-m", "pytest", *paths, f"--basetemp={temp}"]
            seconds = 10800
        elif kind in ("practice", "gepa", "bench"):
            mode = "run" if kind == "practice" else kind
            command = ["powershell.exe", "-NoProfile", "-File", str(self.root / "tools" / "practice.ps1"),
                       "-Models", self.models, "-Mode", mode, "-Requests", str(requests), "-Note", note]
            command.extend(["-CyclesPerMarket" if kind == "bench" else "-Cycles", str(cycles)])
            if self.model:
                command.extend(["-Model", self.model])
            if hours is None or not 0.01 <= hours <= 24:
                raise RunError("an hour limit from 0.01 to 24 is required")
            command.extend(["-Hours", str(hours)])
            seconds = int(hours * 3600) + 600
        else:
            raise RunError("unknown run kind")
        try:
            with log.open("wb") as stream:
                # No console input: a run must not read the owner's keys or change the composer's console mode.
                options = {"cwd": self.root, "stdin": subprocess.DEVNULL, "stdout": stream, "stderr": subprocess.STDOUT}
                if kind == "test":
                    process = self.spawn(command, creationflags=GROUP, **options)
                else:
                    process = spawn_detached(self.spawn, command, **options)
        except OSError:
            raise RunError("cannot start the process") from None
        wall = time.time()
        record = {"id": identity, "kind": kind, "pid": process.pid, "log": str(log), "started": time.monotonic(),
                  "started_wall": wall, "started_at": datetime.now(timezone.utc).isoformat(), "deadline": seconds,
                  "created": process_creation(process.pid), "process": process}
        self.active[identity] = record
        try:
            self._save(record)
        except OSError:
            process.terminate()
            raise RunError("cannot save the run record") from None
        self._arm(record, seconds)
        return self.card(identity)

    def _expire(self, identity):
        record = self.active.get(identity)
        if record and record["process"].poll() is None:
            record["expired"] = True
            if record["kind"] == "test":
                record["process"].terminate()
            else:
                self._stop_engine(record)

    def card(self, identity):
        record = self.active.get(identity)
        if record is None:
            raise RunError("the run was not found")
        code = record["process"].poll()
        if type(code) is int and record.get("exit_code") != code:
            record["exit_code"] = code
            try:
                self._save(record)
            except OSError:
                pass
        if type(code) is int and record.get("planted_stop"):
            # The stopped run has ended, so the kill switch the harness set has done its job. Leave any other STOP.
            record["planted_stop"] = False
            try:
                self._stop_file().unlink(missing_ok=True)
                self._save(record)
            except OSError:
                pass
        status = ("DISMISSED" if record.get("dismissed") else code if code in ("UNKNOWN", "LOST")
                  else "RUNNING" if code is None else "EXPIRED" if record.get("expired") else "COMPLETED" if code == 0 else "FAILED")
        card = {"run": identity, "type": record["kind"], "status": status,
                "elapsed_seconds": self._elapsed(record, code),
                "exit_code": None if code in ("UNKNOWN", "LOST") else code}
        if record.get("recovered"):
            card["recovered"] = True
        tail = self._tail(record["log"])
        progress = re.findall(r"\[\s*(\d+)%\]", tail)
        if progress:
            card["progress"] = f"{progress[-1]}%"
        summary = re.findall(r"=+ (.*?(?:passed|failed|error|skipped).*?) =+", tail)
        if summary:
            card["result"] = summary[-1]
        return card

    @staticmethod
    def _elapsed(record, code):
        if code is None:
            return round(time.monotonic() - record["started"], 1)
        # A finished run stops at its last log write, so its time does not keep growing after a restart.
        try:
            return round(max(0.0, Path(record["log"]).stat().st_mtime - record["started_wall"]), 1)
        except OSError:
            return None

    def cards(self):
        return [self.card(identity) for identity in self.active]

    def latest(self):
        """Return the newest run that was not dismissed, or None."""
        shown = [record for record in self.active.values() if not record.get("dismissed")]
        return max(shown, key=lambda record: record["started_wall"])["id"] if shown else None

    def busy(self):
        return any(not record.get("dismissed") and record["process"].poll() in (None, "UNKNOWN")
                   for record in self.active.values())

    def clear(self, identity):
        record = self.active.get(identity)
        if record is None:
            raise RunError("the run was not found")
        if record["process"].poll() is None:
            raise RunError("an active run cannot be dismissed")
        record["dismissed"] = True
        try:
            self._save(record)
        except OSError:
            raise RunError("cannot save the dismissed run record") from None
        return self.card(identity)

    def _stop_file(self):
        return self.root / "state" / "engine" / "STOP"

    def _stop_engine(self, record):
        stop = self._stop_file()
        stop.parent.mkdir(parents=True, exist_ok=True)
        if not stop.exists():
            # Only a STOP the harness set is removed later. An owner's own kill switch stays.
            record["planted_stop"] = True
            try:
                self._save(record)
            except OSError:
                pass
        stop.touch()

    def stop(self, identity):
        record = self.active.get(identity)
        if record is None:
            raise RunError("the run was not found")
        code = record["process"].poll()
        if code is not None:
            return self.card(identity)
        if record["kind"] == "test":
            record["process"].terminate()
        else:
            self._stop_engine(record)
        return self.card(identity)

    def report(self, identity):
        card = self.card(identity)
        card["log_tail"] = self._tail(self.active[identity]["log"], 4096)
        return card

    @staticmethod
    def _tail(path, maximum=8192):
        try:
            with Path(path).open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - maximum))
                return stream.read().decode("utf-8", "replace")
        except OSError:
            return ""
