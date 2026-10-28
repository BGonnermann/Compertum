"""The minimum Compertum terminal harness."""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from compertum.runtime.errors import RuntimeRefused

from . import __version__
from .agent import Agent, Limits
from .commands import help_text
from .config import load
from .display import Display
from .editor import LineEditor, enable_vt
from .endpoint import parse
from .model import ModelClient, ModelError
from .runs import RunError, RunManager
from .sessions import SessionError, SessionStore
from .tools import WorkspaceTools

class LazyClient:
    def __init__(self, settings):
        self.settings = settings

    def make(self):
        spec = self.settings.model
        return ModelClient(parse(spec.base_url), spec.model, self.settings.headers(),
                           request_timeout=spec.seconds or 300, max_tokens=spec.max_tokens or 8192)

    def chat(self, *args):
        return self.make().chat(*args)

    def list_models(self):
        return self.make().list_models()


def _arguments(text):
    try:
        return shlex.split(text)
    except ValueError:
        raise RunError("the command has an unfinished quote") from None


def _run_args(parts):
    if len(parts) < 5:
        raise RunError("use CYCLES REQUESTS HOURS NOTE")
    return {"cycles": int(parts[1]), "requests": int(parts[2]), "hours": float(parts[3]), "note": " ".join(parts[4:])}


def main(argv=None, display=None, input_fn=None):
    parser = argparse.ArgumentParser(prog="compertum.harness", description="The minimum Compertum terminal agent harness.")
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--models", default="local")
    parser.add_argument("--model")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-minutes", type=float, default=15)
    parser.add_argument("--resume")
    args = parser.parse_args(argv)
    output = display or Display()
    try:
        root = args.project.resolve(strict=True)
        settings = load(root, args.workspace or root, args.models, args.model, args.max_steps, args.max_minutes)
        sessions = SessionStore(root)
        session = sessions.load(args.resume) if args.resume else sessions.create()
        runs = RunManager(root, args.models, args.model)
        agent = Agent(LazyClient(settings), WorkspaceTools(root, settings.workspace, busy=runs.busy),
                      Limits(settings.max_steps, settings.max_seconds), output, settings.workspace, emit=session.append)
        agent.start(getattr(session, "messages", None))
    except (OSError, ValueError, RuntimeRefused, SessionError) as exc:
        output.error(getattr(exc, "code", str(exc)))
        return 2
    output.banner(__version__, [("model", settings.model.model), ("workspace", str(settings.workspace)),
                                ("session", session.identity), ("mode", "YOLO; fixed boundaries still apply")])
    if input_fn is None:
        if sys.stdin.isatty() and output.out.isatty() and enable_vt(output.out):
            input_fn = lambda prompt: LineEditor(output.out, sessions.list, runs.active).read()
        else:
            input_fn = input
    while True:
        try:
            text = input_fn("\ncompertum> ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            output.note("\nNo task is running. Type /exit to quit.")
            continue
        if not text:
            continue
        if text in ("/exit", "/quit"):
            break
        try:
            if text == "/help":
                output.line(help_text())
            elif text == "/status":
                output.json({"model": settings.model.model, "session": session.identity, "runs": runs.cards()})
            elif text == "/models":
                output.json({"models": agent.client.list_models(), "completion_sent": False})
            elif text == "/new":
                session = sessions.create()
                agent = Agent(LazyClient(settings), WorkspaceTools(root, settings.workspace, busy=runs.busy),
                              Limits(settings.max_steps, settings.max_seconds), output, settings.workspace, emit=session.append)
                agent.start()
                output.note(f"Started {session.identity}.")
            elif text == "/sessions":
                output.json({"sessions": sessions.list()})
            elif text.startswith("/resume "):
                session = sessions.load(text.split(maxsplit=1)[1])
                agent = Agent(LazyClient(settings), WorkspaceTools(root, settings.workspace, busy=runs.busy),
                              Limits(settings.max_steps, settings.max_seconds), output, settings.workspace, emit=session.append)
                agent.start(session.messages)
                output.note(f"Resumed {session.identity}.")
            elif text == "/runs":
                output.json({"runs": runs.cards()})
            elif text == "/watch" or text.startswith("/watch "):
                parts = _arguments(text)
                identity = parts[1] if len(parts) > 1 else next(reversed(runs.active), None)
                if identity is None:
                    output.note("No runs yet.")
                else:
                    output.json(runs.card(identity))
            elif text.startswith("/stop "):
                output.json(runs.stop(text.split(maxsplit=1)[1]))
            elif text.startswith("/clear "):
                output.json(runs.clear(text.split(maxsplit=1)[1]))
            elif text.startswith("/report "):
                output.json(runs.report(text.split(maxsplit=1)[1]))
            elif text == "/test" or text.startswith("/test "):
                output.json(runs.start("test", paths=_arguments(text)[1:]))
            elif text in ("/run", "/gepa", "/bench") or text.startswith(("/run ", "/gepa ", "/bench ")):
                parts = _arguments(text)
                kind = parts[0][1:]
                output.json(runs.start(kind, **_run_args(parts)))
            elif text.startswith("/"):
                output.error("unknown command; /help shows the commands")
            else:
                output.outcome(agent.run_task(text))
        except (RunError, SessionError, ModelError, RuntimeRefused, ValueError, StopIteration) as exc:
            output.error(getattr(exc, "code", str(exc)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
