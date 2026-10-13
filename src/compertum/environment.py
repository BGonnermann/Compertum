"""Read-only setup evidence. This is not M0 acceptance or a provider probe."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DEPENDENCIES = (
    "numpy", "pandas", "scipy", "scikit-learn", "sympy", "pyarrow", "httpx",
    "jsonschema", "exchange-calendars", "tzdata", "pytest", "setuptools", "wheel",
)
DOCUMENTS = (
    "docs/BUILD_SPEC.md", "docs/M0_IMPLEMENTATION_PLAN.md", "docs/CLOUD_HANDOFF.md",
    "Solo_Quant_System_Build_Preparation.md",
)
SOURCE_DIRECTORIES = ("src", "tools", "tests", "schemas", "config")
SOURCE_FILES = ("pyproject.toml", ".python-version", "uv.lock", "AGENTS.md", "README.md", ".gitignore")
MAX_HASH_FILE_BYTES = 8 * 1024 * 1024
MAX_HASH_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SCAN_ENTRIES = 1024
MAX_SCAN_DEPTH = 16


def _regular_file(root: Path, relative: str) -> Path:
    path = root
    for part in Path(relative).parts:
        if part in ("..", "."):
            raise ValueError("unsafe relative path")
        path /= part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("symlink or reparse path")
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_HASH_FILE_BYTES:
        raise ValueError("non-regular or oversized source")
    return path


def _command(args: list[str], root: Path) -> str | None:
    if not shutil.which(args[0]):
        return None
    try:
        result = subprocess.run(args, cwd=root, capture_output=True, timeout=5, check=False)
        if result.returncode == 0 and len(result.stdout) <= 4096:
            return result.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def collect_environment(project_root: Path) -> dict:
    """Observe this interpreter/workspace; never write, log in or contact providers.

    File hashes are bounded setup observations, not a snapshot under an owner
    lock. Runtime/native validation must establish those stronger guarantees.
    """
    root = Path(project_root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("project root must be an existing non-symlink directory")
    hashes: dict[str, str | None] = {}
    unsafe: list[str] = []
    total_hashed = 0
    scanned_entries = 0
    hash_observation_complete = True

    def incomplete(relative: str) -> None:
        nonlocal hash_observation_complete
        hash_observation_complete = False
        unsafe.append(relative)

    def observe(relative: str) -> None:
        nonlocal total_hashed
        try:
            path = _regular_file(root, relative)
            size = path.stat().st_size
            if total_hashed + size > MAX_HASH_TOTAL_BYTES:
                raise ValueError("source hashing budget exceeded")
            admitted_bytes = min(MAX_HASH_FILE_BYTES, MAX_HASH_TOTAL_BYTES - total_hashed)
            with path.open("rb") as stream:
                content = stream.read(admitted_bytes + 1)
            if len(content) > admitted_bytes:
                raise ValueError("source changed beyond the admitted hashing budget")
            hashes[relative] = hashlib.sha256(content).hexdigest()
            total_hashed += len(content)
        except FileNotFoundError:
            hashes[relative] = None
        except (OSError, ValueError):
            hashes[relative] = None
            incomplete(relative)

    for relative in DOCUMENTS + SOURCE_FILES:
        observe(relative)

    def scan(directory: Path, depth: int) -> None:
        nonlocal scanned_entries
        relative = directory.relative_to(root).as_posix()
        if depth > MAX_SCAN_DEPTH or scanned_entries >= MAX_SCAN_ENTRIES:
            incomplete(relative)
            return
        try:
            info = directory.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                incomplete(relative)
                return
            if not stat.S_ISDIR(info.st_mode):
                incomplete(relative)
                return
            with os.scandir(directory) as entries:
                for entry in entries:
                    if scanned_entries >= MAX_SCAN_ENTRIES or total_hashed >= MAX_HASH_TOTAL_BYTES:
                        incomplete(relative)
                        return
                    scanned_entries += 1
                    path = Path(entry.path)
                    child_relative = path.relative_to(root).as_posix()
                    entry_info = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(entry_info.st_mode) or getattr(entry_info, "st_file_attributes", 0) & 0x400:
                        incomplete(child_relative)
                    elif stat.S_ISDIR(entry_info.st_mode):
                        if entry.name != "__pycache__":
                            scan(path, depth + 1)
                    elif path.suffix in (".py", ".json", ".toml"):
                        observe(child_relative)
        except FileNotFoundError:
            pass
        except OSError:
            incomplete(relative)

    for directory in SOURCE_DIRECTORIES:
        scan(root / directory, 0)
    versions = {}
    for dependency in DEPENDENCIES:
        try:
            versions[dependency] = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            versions[dependency] = None
    source_hashes = {key: value for key, value in sorted(hashes.items()) if key not in DOCUMENTS}
    source_digest = (
        hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest()
        if hash_observation_complete else None
    )
    try:
        usage = shutil.disk_usage(root)
        disk = {"total_bytes": usage.total, "free_bytes": usage.free}
    except OSError:
        disk = {"total_bytes": None, "free_bytes": None}
    try:
        total_ram = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):
        total_ram = None
    return {
        "schema_version": "environment.setup.v1",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evidence_scope": "CURRENT_INTERPRETER_AND_WORKSPACE_ONLY",
        "m0_status": "INCOMPLETE",
        "native_validation": "UNVERIFIED",
        "native_target": {"os": "Windows 11", "python": "3.14.7", "evidence": "UNVERIFIED"},
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "os": {"system": platform.system(), "release": platform.release(), "build": platform.version()},
        "hardware": {"logical_cpus": os.cpu_count(), "total_ram_bytes": total_ram, "gpu": None},
        "volume": disk,
        "tools": {"git": _command(["git", "--version"], root), "uv": _command(["uv", "--version"], root)},
        "git_commit": _command(["git", "--no-optional-locks", "rev-parse", "HEAD"], root),
        "dependencies": versions,
        "dependency_imports": "UNVERIFIED",
        "document_hashes": {key: hashes[key] for key in DOCUMENTS},
        "source_hashes": source_hashes,
        "source_bundle_hash": source_digest,
        "hash_observation_complete": hash_observation_complete,
        "unreadable_or_unsafe_paths": sorted(set(unsafe)),
        "home_strata": "UNVERIFIED",
        "subscription_access": "UNVERIFIED",
        "github_sync": "UNVERIFIED",
        "spending_usd": "0.00",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        receipt = collect_environment(args.project_root)
    except (OSError, ValueError):
        print(json.dumps({"status": "INVALID_PROJECT_ROOT", "m0_status": "INCOMPLETE"}))
        return 2
    print(json.dumps(receipt, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
