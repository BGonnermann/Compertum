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
from .config import load, model_files, remember, remembered
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

    def select(self, settings):
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
    output = display or Display()
    try:
        return _console(argv, output, input_fn)
    finally:
        output.idle("")  # An empty title returns the tab to the terminal's own title, even after an error.


def _console(argv, display, input_fn):
    parser = argparse.ArgumentParser(prog="compertum.harness", description="The minimum Compertum terminal agent harness.")
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--models", help="model file; default: the last /model choice, else local")
    parser.add_argument("--model")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-minutes", type=float, default=15)
    parser.add_argument("--resume")
    args = parser.parse_args(argv)
    output = display or Display()
    try:
        root = args.project.resolve(strict=True)
        # Explicit options win. Otherwise the last /model choice applies, so a restart or resume keeps the model.
        saved = None if args.models else remembered(root)
        models, model = (args.models, args.model) if args.models else (saved[0], args.model or saved[1]) if saved else ("local", args.model)
        try:
            settings = load(root, args.workspace or root, models, model, args.max_steps, args.max_minutes)
        except (ValueError, RuntimeRefused):
            if not saved:
                raise
            # A saved choice whose model file changed must not stop the harness from starting.
            output.note(f"The saved model choice {models} {model or ''} no longer loads. Using local.".replace("  ", " "))
            settings = load(root, args.workspace or root, "local", args.model, args.max_steps, args.max_minutes)
        sessions = SessionStore(root)
        session = sessions.load(args.resume) if args.resume else sessions.create()
        runs = RunManager(root, settings.models, settings.model.model)
        agent = Agent(LazyClient(settings), WorkspaceTools(root, settings.workspace, busy=runs.busy),
                      Limits(settings.max_steps, settings.max_seconds), output, settings.workspace, emit=session.append)
        agent.start(getattr(session, "messages", None))
    except (OSError, ValueError, RuntimeRefused, SessionError) as exc:
        output.error(getattr(exc, "code", str(exc)))
        return 2
    catalog = {settings.models: [settings.model.model]}

    def select(models, model=None):
        nonlocal settings
        if models.startswith("[") or (model or "").startswith("["):
            raise ValueError("replace the bracketed words, for example /model kimi or /model deepseek deepseek-v4-pro")
        if models not in model_files(root):
            raise ValueError("unknown model file; /model shows the choices")
        updated = load(root, settings.workspace, models, model, settings.max_steps, settings.max_seconds / 60)
        agent.client.select(updated)
        runs.select(updated.models, updated.model.model)
        settings = updated
        catalog[updated.models] = sorted({*catalog.get(updated.models, ()), updated.model.model})
        remember(root, updated.models, updated.model.model)
        try:
            updated.headers()
        except RuntimeRefused:
            # The choice stands, so the owner can set the key later. Requests fail until then.
            output.note(f"{updated.model.key_env or 'The key variable'} is not set in your user environment. Requests to {updated.models} "
                        "will fail until you set it.")
        return updated

    def listed_models(models):
        if models not in model_files(root):
            raise ValueError("unknown model file; /model shows the choices")
        listed = settings if models == settings.models else load(root, settings.workspace, models, None,
                                                                settings.max_steps, settings.max_seconds / 60)
        catalog[models] = LazyClient(listed).list_models()
        return catalog[models]

    output.banner(__version__, [("model", settings.model.model), ("workspace", str(settings.workspace)),
                                ("session", session.identity), ("mode", "YOLO; fixed boundaries still apply")])
    if input_fn is None:
        if sys.stdin.isatty() and output.out.isatty() and enable_vt(output.out):
            input_fn = lambda prompt: LineEditor(output.out, sessions.list, runs.active,
                                                 model_files=lambda: model_files(root),
                                                 model_ids=lambda name: catalog.get(name, ()),
                                                 title=f"Compertum · {settings.model.model}").read()
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
                output.json({"model": settings.model.model, "model_file": settings.models,
                             "session": session.identity, "runs": runs.cards()})
            elif text == "/model" or text.startswith("/model "):
                parts = _arguments(text)
                if len(parts) == 1:
                    output.json({"model": settings.model.model, "model_file": settings.models,
                                 "model_files": model_files(root), "usage": "/model [NAME] [MODEL_ID]"})
                elif len(parts) == 2:
                    name = parts[1]
                    updated = select(name) if name in model_files(root) else select(settings.models, name)
                    output.json({"model": updated.model.model, "model_file": updated.models, "session": session.identity})
                elif len(parts) == 3:
                    updated = select(parts[1], parts[2])
                    output.json({"model": updated.model.model, "model_file": updated.models, "session": session.identity})
                else:
                    raise ValueError("use /model [NAME] [MODEL_ID]")
            elif text == "/models" or text.startswith("/models "):
                parts = _arguments(text)
                if len(parts) > 2:
                    raise ValueError("use /models [NAME]")
                name = settings.models if len(parts) == 1 else parts[1]
                output.json({"models": listed_models(name), "model_file": name, "completion_sent": False})
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
                kind = "practice" if parts[0] == "/run" else parts[0][1:]
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
