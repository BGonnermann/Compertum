"""A read-only run or download view in a Windows Terminal pane beside the harness."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .display import readable
from .downloads import DownloadView
from .editor import LiveView, enable_vt
from .engine_watch import NEWEST
from .runs import RunError
from .watch import JOB_ID, watch_card


def card(root: Path, identity: str):
    return watch_card(root, identity)


def available(environ=os.environ, which=shutil.which):
    return bool(environ.get("WT_SESSION")) and which("wt") is not None


def _split(root: Path, title: str, arguments, spawn, which):
    command = [which("wt"), "-w", "0", "split-pane", "-V", "--size", "0.4", "--title", title,
               "-d", str(root), sys.executable, "-m", "compertum.harness.pane", "--project", str(root), *arguments,
               ";", "move-focus", "left"]
    try:
        spawn(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        raise RunError("cannot open a Windows Terminal pane") from None


def open_pane(root: Path, identity: str, spawn=subprocess.Popen, which=shutil.which):
    if not JOB_ID.fullmatch(identity):
        raise RunError("the run ID is not valid")
    _split(root, "Watch the newest run" if identity == NEWEST else f"Watch {identity}", [identity], spawn, which)


def open_downloads(root: Path, spawn=subprocess.Popen, which=shutil.which):
    _split(root, "History downloads", ["--downloads"], spawn, which)


def main(argv=None, out=None, get_key=None):
    parser = argparse.ArgumentParser(prog="compertum.harness.pane",
                                     description="Watch one run or the history downloads, read-only.")
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--downloads", action="store_true")
    parser.add_argument("run", nargs="?")
    args = parser.parse_args(argv)
    if args.downloads == bool(args.run):
        parser.error("give one run ID or --downloads")
    root = args.project.resolve(strict=True)
    out = out or sys.stdout
    color = get_key is None and out.isatty() and enable_vt(out) and not os.environ.get("NO_COLOR")
    if args.downloads:
        view = DownloadView(out, root, get_key=get_key, color=color)
    else:
        title = "Watching the newest run" if args.run == NEWEST else f"Watching {args.run}"
        view = LiveView(out, lambda: readable(card(root, args.run)).splitlines(), title,
                        get_key=get_key, color=color, hint="q closes this pane")
    try:
        view.read()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
