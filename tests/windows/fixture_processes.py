"""Launch trusted Python fixtures; not a product worker launcher."""
from pathlib import Path
import subprocess
import sys


def python_process(arguments, *, env, **kwargs):
    executable = sys.executable
    child_env = dict(env)
    if sys.platform == "win32":
        # The Windows venv redirector creates another process. Retaining its
        # Popen handle would authenticate the launcher, not our Python worker.
        # Use the same base runtime directly, with CPython's venv path marker.
        # Never discover a replacement interpreter through PATH.
        executable = getattr(sys, "_base_executable", None)
        if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
            raise RuntimeError("FIXTURE_RUNTIME_UNAVAILABLE")
        child_env["__PYVENV_LAUNCHER__"] = sys.executable
    return subprocess.Popen([sys.executable, *arguments], executable=executable, env=child_env, **kwargs)
