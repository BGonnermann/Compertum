"""Four plain tools with hard boundaries and no permission prompts."""
from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from compertum.ai.manual import sanitized
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.sandbox import run_sandboxed

from .agent import ToolError

MAX_TEXT = 32 * 1024
MAX_OUTPUT = 64 * 1024
MEMORY_FLOOR = 8 * 1024**3
BLOCKED_PARTS = {".git", ".venv", ".cache", "state", "backups", "credentials", "__pycache__"}
BLOCKED_NAMES = {"id_rsa", "id_ed25519", "credentials.json"}
PROTECTED_WRITERS = {"agents.md", "build_spec.md", "audit.py", "auditor.py", "baseline.py", "deflation.py",
                     "vault.py", "ledger.py", "persistence.py"}
PROTECTED_FOLDERS = {"config", "schemas", "evaluation", "ai", "runtime", "harness"}


def _schema(description, properties, required):
    return {"type": "function", "function": {"name": description[0], "description": description[1],
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


def _previous(path):
    """Return a file's text before a write, or None when it is missing or cannot be shown."""
    try:
        # Check the size first, so a large data file is never loaded just to be refused.
        if not path.is_file() or path.stat().st_size > MAX_TEXT:
            return None
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        return None


class WorkspaceTools:
    def __init__(self, root: Path, workspace: Path, runner=run_sandboxed, busy=None):
        self.root, self.workspace, self.runner = root.resolve(), workspace.resolve(), runner
        self.busy = busy or (lambda: False)
        # The display shows this (path, before, after, created) record. The model receives only the short result.
        # Before is None when the previous file cannot be shown.
        self.change = None

    def take_change(self):
        change, self.change = self.change, None
        return change

    def specs(self):
        path = {"type": "string", "description": "a path relative to the workspace"}
        return [
            _schema(("read", "Read one bounded UTF-8 project file."), {"path": path}, ["path"]),
            _schema(("write", "Replace a project file with supplied text."),
                    {"path": path, "content": {"type": "string"}}, ["path", "content"]),
            _schema(("edit", "Replace one exact text match in a project file."),
                    {"path": path, "old": {"type": "string"}, "new": {"type": "string"}}, ["path", "old", "new"]),
            _schema(("run", "Run one Python file in the AppContainer sandbox."),
                    {"path": path, "args": {"type": "array", "items": {"type": "string"}},
                     "seconds": {"type": "integer", "minimum": 1, "maximum": 600}}, ["path"]),
        ]

    def _path(self, value, writing=False):
        if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
            raise ToolError("the path is not valid")
        supplied = Path(value)
        if supplied.is_absolute() or ".." in supplied.parts:
            raise ToolError("the path must stay inside the workspace")
        lowered = {part.lower() for part in supplied.parts}
        name = supplied.name.lower()
        if lowered & BLOCKED_PARTS or name in BLOCKED_NAMES or name == ".env" or name.startswith(".env."):
            raise ToolError("the path is protected")
        if name.endswith((".pem", ".key", ".pfx", ".p12")):
            raise ToolError("the path is protected")
        path = (self.workspace / supplied).resolve(strict=False)
        if not path.is_relative_to(self.workspace):
            raise ToolError("the path must stay inside the workspace")
        resolved = {part.lower() for part in path.relative_to(self.workspace).parts}
        if resolved & BLOCKED_PARTS:
            raise ToolError("the resolved path is protected")
        current = self.workspace
        for part in supplied.parts:
            current = current / part
            if current.is_symlink():
                raise ToolError("links are not allowed")
        if writing and (name in PROTECTED_WRITERS or (lowered | resolved) & PROTECTED_FOLDERS):
            raise ToolError("the path is protected from model writes")
        return path

    def run(self, name, args, deadline):
        if name == "read":
            return self._read(args)
        if name == "write":
            return self._write(args)
        if name == "edit":
            return self._edit(args)
        if name == "run":
            return self._sandbox(args, deadline)
        raise ToolError(f"unknown tool {name!r}")

    def _read(self, args):
        path = self._path(args.get("path"))
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ToolError(f"cannot read the file: {exc}") from None
        if len(raw) > MAX_TEXT:
            raise ToolError("the file is too large")
        try:
            return sanitized(raw)
        except RuntimeRefused as error:
            raise ToolError(error.code) from None

    def _write(self, args):
        path = self._path(args.get("path"), writing=True)
        content = args.get("content")
        if not isinstance(content, str) or len(content.encode()) > MAX_TEXT:
            raise ToolError("the content is not valid or is too large")
        created, before = not path.exists(), _previous(path)
        try:
            sanitized(content.encode())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        except (OSError, RuntimeRefused) as exc:
            raise ToolError(getattr(exc, "code", "cannot write the file")) from None
        self.change = path.relative_to(self.workspace).as_posix(), "" if created else before, content, created
        return f"wrote {path.relative_to(self.workspace).as_posix()} ({len(content.encode())} bytes)"

    def _edit(self, args):
        path = self._path(args.get("path"), writing=True)
        old, new = args.get("old"), args.get("new")
        if not isinstance(old, str) or not old or not isinstance(new, str) or len(new.encode()) > MAX_TEXT:
            raise ToolError("the edit is not valid")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ToolError(f"cannot read the file: {exc}") from None
        if text.count(old) != 1:
            raise ToolError("the old text must occur exactly once")
        updated = text.replace(old, new, 1)
        if len(updated.encode()) > MAX_TEXT:
            raise ToolError("the edited file is too large")
        try:
            sanitized(updated.encode())
            path.write_text(updated, encoding="utf-8", newline="\n")
        except (OSError, RuntimeRefused) as error:
            raise ToolError(getattr(error, "code", "cannot write the file")) from None
        self.change = path.relative_to(self.workspace).as_posix(), text, updated, False
        return f"edited {path.relative_to(self.workspace).as_posix()}"

    def _sandbox(self, args, deadline):
        if self.busy():
            raise ToolError("JOB_SLOT_BUSY")
        source = self._path(args.get("path"))
        values = args.get("args", [])
        seconds = args.get("seconds", 120)
        if source.suffix != ".py" or not source.is_file() or type(seconds) is not int or not 1 <= seconds <= 600:
            raise ToolError("run needs one Python file and 1 to 600 seconds")
        if not isinstance(values, list) or len(values) > 16 or any(not isinstance(v, str) or len(v) > 256 for v in values):
            raise ToolError("run arguments are not valid")
        try:
            sanitized(source.read_bytes())
            root = self.root / ".cache" / "test-runs" / f"harness-{uuid4().hex[:12]}"
            root.mkdir(parents=True)
            job = root / "job"
            job.mkdir()
            (job / "main.py").write_bytes(source.read_bytes())
            remaining = max(1, int(deadline - time.monotonic()))
            result = self.runner(root, job, ["main.py", *values], seconds=min(seconds, remaining),
                                 memory_bytes=256 * 1024**2, disk_bytes=64 * 1024**2, memory_floor_bytes=MEMORY_FLOOR)
            output = {"status": "COMPLETED" if result.exit_code == 0 and not result.timed_out else "FAILED",
                      "exit_code": result.exit_code, "timed_out": result.timed_out,
                      "stdout": result.stdout[-MAX_OUTPUT:].decode("utf-8", "replace"),
                      "stderr": result.stderr[-MAX_OUTPUT:].decode("utf-8", "replace")}
            sanitized(json.dumps(output).encode())
            return json.dumps(output)
        except (OSError, RuntimeRefused) as exc:
            raise ToolError(getattr(exc, "code", "the sandbox run failed")) from None
