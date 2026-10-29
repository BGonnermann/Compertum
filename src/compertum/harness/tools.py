"""Plain tools with no permission prompts: read, write, edit, search, bash and sandbox run."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import time
import tomllib
from pathlib import Path
from uuid import uuid4

from compertum.ai.manual import sanitized
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.jobs import available_physical_memory
from compertum.runtime.sandbox import run_sandboxed

from . import shell
from .agent import ToolError
from .packets import hide_secrets, looks_secret

MAX_TEXT = 32 * 1024
MAX_OUTPUT = 64 * 1024
# Search stops at a match, file and size limit.
MAX_MATCHES, MAX_SEARCH_FILES, MAX_SEARCH_FILE = 200, 20000, 1024**2
# Variables with these words in their names never reach the shell. The shell could still read the registry.
SECRET_VARIABLE = re.compile(r"(?i)key|token|secret|passw|credential|(?<!git_)auth|dsn|database_url")
SECRET_TEXT = "[text hidden: it looks like a secret]"
MEMORY_FLOOR = 8 * 1024**3
BLOCKED_PARTS = {".git", ".venv", ".cache", "state", "backups", "credentials", "__pycache__"}
BLOCKED_NAMES = {"id_rsa", "id_ed25519", "credentials.json"}
PROTECTED_WRITERS = {"agents.md", "build_spec.md", "audit.py", "auditor.py", "baseline.py", "deflation.py",
                     "vault.py", "ledger.py", "persistence.py"}
PROTECTED_FOLDERS = {"config", "schemas", "evaluation", "ai", "runtime", "harness"}


def _schema(description, properties, required):
    return {"type": "function", "function": {"name": description[0], "description": description[1],
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


def _git_bash():
    """Find Git Bash. The bash.exe in System32 starts WSL, so the tool never uses it."""
    git = shutil.which("git")
    candidates = [Path(git).resolve().parents[1] / "bin" / "bash.exe"] if git else []
    candidates.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe")
    return next((path for path in candidates if path.is_file()), None)


def _shell_environment(root):
    names = set()
    try:
        providers = tomllib.loads((root / "config" / "providers.toml").read_text(encoding="utf-8"))
        # The file holds [providers.NAME] tables, each with an optional key_variable.
        names = {str(entry.get("key_variable", "")).upper() for entry in providers.get("providers", {}).values()
                 if isinstance(entry, dict)} - {""}
    except (OSError, ValueError, AttributeError):
        pass
    return {name: value for name, value in os.environ.items()
            if not SECRET_VARIABLE.search(name) and name.upper() not in names}


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
            _schema(("search", "Search project files with a regular expression. Returns path:line: text matches. "
                     "With names_only, returns the matching file paths. Credential, state and cache folders are skipped."),
                    {"pattern": {"type": "string"}, "path": {**path, "description": "a folder or file; default ."},
                     "glob": {"type": "string", "description": "a file name pattern such as *.py"},
                     "names_only": {"type": "boolean"}}, ["pattern"]),
            _schema(("bash", "Run a command with Git Bash on the host in the workspace folder. Output keeps the first "
                     "4 KiB and the last 24 KiB. Use it for ls, find, git status, git diff and tests. "
                     "Do not push, install software, start engine runs or read credentials."),
                    {"command": {"type": "string"}, "seconds": {"type": "integer", "minimum": 1, "maximum": 600}},
                    ["command"]),
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
        if name == "search":
            return self._search(args, deadline)
        if name == "bash":
            return self._bash(args, deadline)
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

    def _search(self, args, deadline):
        pattern, glob, names_only = args.get("pattern"), args.get("glob"), args.get("names_only", False)
        if not isinstance(pattern, str) or not pattern or len(pattern) > 512 or type(names_only) is not bool:
            raise ToolError("search needs a pattern of 1 to 512 characters")
        if glob is not None and (not isinstance(glob, str) or not glob or len(glob) > 128):
            raise ToolError("the glob is not valid")
        try:
            expression = re.compile(pattern)
        except re.error as exc:
            raise ToolError(f"the pattern is not a valid regular expression: {exc}") from None
        base = args.get("path", ".")
        start = self.workspace if base in (".", "./", "") else self._path(base)
        if not start.exists():
            raise ToolError("the search path does not exist")
        found, scanned = [], 0
        for path in self._search_files(start):
            relative = path.relative_to(self.workspace).as_posix()
            lowered, parts = path.name.lower(), {part.lower() for part in Path(relative).parts}
            if (parts & BLOCKED_PARTS or lowered in BLOCKED_NAMES or lowered == ".env" or lowered.startswith(".env.")
                    or lowered.endswith((".pem", ".key", ".pfx", ".p12"))):
                continue
            if glob and not (fnmatch.fnmatch(path.name, glob) or fnmatch.fnmatch(relative, glob)):
                continue
            scanned += 1
            if scanned > MAX_SEARCH_FILES or time.monotonic() > deadline:
                found.append(f"... the search stopped after {scanned - 1} files")
                break
            try:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SEARCH_FILE:
                    continue
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\0" in raw[:8192]:
                continue
            for number, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
                if not expression.search(line):
                    continue
                if names_only:
                    found.append(relative)
                    break
                shown = line.strip()[:300]
                found.append(f"{relative}:{number}: {SECRET_TEXT if looks_secret(shown) else shown}")
                if len(found) >= MAX_MATCHES:
                    break
            if len(found) >= MAX_MATCHES:
                found.append("... more results; narrow the pattern, path or glob")
                break
        return self._found(found, names_only)

    def _search_files(self, start):
        """List files under start. In a Git repository, skip ignored files, as ripgrep does."""
        if start.is_file():
            return [start]
        # Use Git only when the workspace is the repository top. A parent repository may ignore the whole workspace.
        trusted = ["git", "-c", f"safe.directory={self.workspace.as_posix()}"]
        quiet = {"cwd": self.workspace, "capture_output": True, "timeout": 30, "creationflags": subprocess.CREATE_NO_WINDOW}
        try:
            top = subprocess.run([*trusted, "rev-parse", "--show-toplevel"], **quiet)
            if top.returncode == 0 and Path(top.stdout.decode("utf-8", "replace").strip()).resolve() == self.workspace:
                listed = subprocess.run([*trusted, "ls-files", "-co", "--exclude-standard", "-z", "--", str(start)], **quiet)
                if listed.returncode == 0:
                    names = listed.stdout.decode("utf-8", "replace").split("\0")
                    return sorted(self.workspace / name for name in names if name)
        except (OSError, subprocess.SubprocessError):
            pass
        files = []
        for folder, dirs, names in os.walk(start):
            dirs[:] = sorted(d for d in dirs if d.lower() not in BLOCKED_PARTS)
            files.extend(Path(folder) / name for name in sorted(names))
        return files

    def _found(self, found, names_only):
        text = hide_secrets("\n".join(found)) if found else ("no matching files" if names_only else "no matches")
        try:
            return sanitized(text.encode("utf-8"))
        except RuntimeRefused as error:
            raise ToolError(error.code) from None

    def _bash(self, args, deadline):
        command, seconds = args.get("command"), args.get("seconds", 120)
        if not isinstance(command, str) or not command.strip() or len(command) > 8192 or "\0" in command:
            raise ToolError("bash needs a command of 1 to 8192 characters")
        if type(seconds) is not int or not 1 <= seconds <= 600:
            raise ToolError("bash needs 1 to 600 seconds")
        if self.busy():
            # One heavy job at a time: an owner-started run holds the job slot.
            raise ToolError("JOB_SLOT_BUSY: an owner-started run is active; read and search still work")
        if available_physical_memory() < MEMORY_FLOOR:
            raise ToolError("AVAILABLE_RAM_FLOOR")
        program = _git_bash()
        if program is None:
            raise ToolError("Git Bash is not installed")
        limit = max(1, min(seconds, int(deadline - time.monotonic())))
        try:
            code, timed_out, output = shell.run(program, command, self.workspace, _shell_environment(self.root), limit)
        except OSError as exc:
            raise ToolError(f"cannot start the command: {exc}") from None
        result = {"status": "COMPLETED" if code == 0 and not timed_out else "FAILED",
                  "exit_code": code, "timed_out": timed_out,
                  "stdout": hide_secrets(output.replace("\r\n", "\n")), "stderr": ""}
        try:
            # Raw UTF-8 keeps binary output near its own size. ASCII escapes would grow it six times.
            return sanitized(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except RuntimeRefused as error:
            raise ToolError(error.code) from None

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
