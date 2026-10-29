"""A read-only run view in a Windows Terminal pane beside the harness."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .display import readable
from .editor import LiveView, enable_vt
from .engine_watch import engine_card
from .runs import RunError, read_card

RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")


def card(root: Path, identity: str):
    if (root / "state" / "harness" / "runs" / f"{identity}.json").is_file():
        return read_card(root, identity)
    return engine_card(root, identity)


def available(environ=os.environ, which=shutil.which):
    return bool(environ.get("WT_SESSION")) and which("wt") is not None


def open_pane(root: Path, identity: str, spawn=subprocess.Popen, which=shutil.which):
    if not RUN_ID.fullmatch(identity):
        raise RunError("the run ID is not valid")
    command = [which("wt"), "-w", "0", "split-pane", "-V", "--size", "0.4", "--title", f"Watch {identity}",
               "-d", str(root), sys.executable, "-m", "compertum.harness.pane", "--project", str(root), identity,
               ";", "move-focus", "left"]
    try:
        spawn(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        raise RunError("cannot open a Windows Terminal pane") from None


def main(argv=None, out=None, get_key=None):
    parser = argparse.ArgumentParser(prog="compertum.harness.pane", description="Watch one run, read-only.")
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("run")
    args = parser.parse_args(argv)
    root = args.project.resolve(strict=True)
    out = out or sys.stdout
    color = get_key is None and out.isatty() and enable_vt(out) and not os.environ.get("NO_COLOR")
    view = LiveView(out, lambda: readable(card(root, args.run)).splitlines(), f"Watching {args.run}",
                    get_key=get_key, color=color, hint="q closes this pane")
    try:
        view.read()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
