"""The minimum Compertum terminal harness."""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from compertum.runtime.errors import RuntimeRefused

from . import __version__
from .agent import Agent, Limits
from .commands import EXAMPLES, USAGES, help_text
from .config import known_models, load, model_files, remember, remember_models, remembered
from .display import Display, readable
from .editor import LineEditor, LiveView, Picker, enable_vt
from .engine_watch import engine_card, engine_runs
from .endpoint import parse
from .model import ModelClient, ModelError
from .runs import RunError, RunManager
from .sessions import SessionError, SessionStore
from .tools import WorkspaceTools

# Providers whose subscription terms allow interactive use only. Engine runs are batch work, so they need another model.
INTERACTIVE_ONLY = {"kimi": "Kimi Code subscriptions are for interactive use only"}


class LazyClient:
    def __init__(self, settings):
        self.settings = settings

    def select(self, settings):
        self.settings = settings

    def make(self):
        spec = self.settings.model
        try:
            headers = self.settings.headers()
        except RuntimeRefused as exc:
            # A model error ends the task cleanly and tells the owner what to do.
            raise ModelError(f"{exc.code}: {spec.key_env or 'the key variable'} is not set. Set it as a user "
                             "environment variable, or choose another model with /model") from None
        return ModelClient(parse(spec.base_url), spec.model, headers,
                           request_timeout=spec.seconds or 300, max_tokens=spec.max_tokens or 8192)

    def chat(self, *args):
        return self.make().chat(*args)

    def list_models(self):
        return self.make().list_models()


def _arguments(text):
    """Split a command. Quotes group words; backslashes stay, so Windows paths keep their separators."""
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        raise RunError("the command has an unfinished quote") from None
    return [part[1:-1] if len(part) > 1 and part[0] == part[-1] and part[0] in "\"'" else part for part in parts]


def _identity(text):
    """Return the one session or run ID after a command, with the same quote rules for every command."""
    parts = _arguments(text)
    if len(parts) != 2:
        raise RunError(f"use {USAGES[parts[0]]}, for example {EXAMPLES[parts[0]]}")
    return parts[1]


def _run_args(text):
    """Read CYCLES REQUESTS HOURS and keep the rest as the note, word for word, including apostrophes."""
    parts = text.split(maxsplit=4)
    example = f"for example {EXAMPLES[parts[0]]}"
    if len(parts) < 5:
        raise RunError(f"use {USAGES[parts[0]]}, {example}")
    try:
        cycles, requests, hours = int(parts[1]), int(parts[2]), float(parts[3])
    except ValueError:
        raise RunError(f"CYCLES and REQUESTS need whole numbers and HOURS a number, {example}") from None
    if parts[4] == "NOTE":
        raise RunError(f"replace NOTE with a short description, {example}")
    return {"cycles": cycles, "requests": requests, "hours": hours, "note": parts[4]}


def main(argv=None, display=None, input_fn=None, choose=None, pick_run=None, watch=None):
    output = display or Display()
    try:
        return _console(argv, output, input_fn, choose, pick_run, watch)
    finally:
        output.idle("")  # An empty title returns the tab to the terminal's own title, even after an error.


def _console(argv, display, input_fn, choose, pick_run, watch):
    parser = argparse.ArgumentParser(prog="compertum.harness", description="The minimum Compertum terminal agent harness.")
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--models", help="model file; default: the last /model choice, else local")
    parser.add_argument("--model")
    # Owner choice, 29 October 2026: a real bug hunt needs room, so tasks default to the highest limits.
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--max-minutes", type=float, default=60)
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
    # Known model IDs persist, so the picker keeps every model the owner used or listed, not only the active one.
    catalog = known_models(root)
    catalog[settings.models] = sorted({*catalog.get(settings.models, ()), settings.model.model})

    def select(models, model=None):
        nonlocal settings
        if models.startswith("[") or (model or "").startswith("["):
            raise ValueError("replace the bracketed words, for example /model kimi or /model deepseek deepseek-v4-pro")
        if models not in model_files(root):
            raise ValueError("unknown model file; /model shows the choices")
        updated = load(root, settings.workspace, models, model, settings.max_steps, settings.max_seconds / 60)
        if model and catalog.get(models) and model not in catalog[models]:
            # An unknown ID may be new, so it is selected. A typing mistake would fail at every request, so warn.
            output.note(f"{model} is not a known model for {models}. /models {models} lists what the provider offers.")
        agent.client.select(updated)
        runs.select(updated.models, updated.model.model)
        settings = updated
        catalog[updated.models] = sorted({*catalog.get(updated.models, ()), updated.model.model})
        remember(root, updated.models, updated.model.model)
        remember_models(root, updated.models, [updated.model.model])
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
        remember_models(root, models, catalog[models], replace=True)  # A fresh listing drops IDs the provider removed.
        return catalog[models]

    output.banner(__version__, [("model", settings.model.model), ("workspace", str(settings.workspace)),
                                ("session", session.identity), ("mode", "YOLO; fixed boundaries still apply")])
    if input_fn is None:
        if sys.stdin.isatty() and output.out.isatty() and enable_vt(output.out):
            input_fn = lambda prompt: LineEditor(output.out, sessions.list, runs.active,
                                                 model_files=lambda: model_files(root),
                                                 model_ids=lambda name: catalog.get(name, ()),
                                                 title=f"Compertum · {settings.model.model}",
                                                 color=output.color).read()
            if choose is None:
                choose = lambda options, chosen: Picker(output.out, options, chosen, title="Choose a model",
                                                         prompt="↑/↓ choose · Enter selects · Esc keeps the current model",
                                                         color=output.color).read()
            if pick_run is None:
                pick_run = lambda options: Picker(output.out, options, 0, title="Choose a run to watch",
                                                  prompt="↑/↓ choose · Enter watches · Esc cancels", color=output.color).read()
            if watch is None:
                watch = lambda title, fetch: LiveView(output.out, fetch, title, color=output.color).read()
        else:
            input_fn = input

    def run_card(identity):
        """Return a harness run card with its last log lines, or an engine run's progress."""
        if identity in runs.active:
            card = runs.report(identity)
            card["log_tail"] = "\n".join(card.get("log_tail", "").splitlines()[-10:])
            return card
        return engine_card(root, identity)

    def watch_choices():
        """List runs to watch: running ones first, then the newest ended ones. Engine runs started outside count too."""
        rows = []
        for identity in sorted(runs.active, key=lambda key: runs.active[key]["started_wall"], reverse=True):
            if runs.active[identity].get("dismissed"):
                continue
            card = runs.card(identity)
            rows.append((card["status"] != "RUNNING", identity,
                         f"{identity}  {card['type']}  {card['status']}  {card.get('progress', '')}".rstrip()))
        for item in engine_runs(root):
            rows.append((item["status"] != "RUNNING", item["run"],
                         f"{item['run']}  {item['type']}  {item['status']}  cycles {item['cycles']}  {item['elapsed']}"))
        rows.sort(key=lambda row: row[0])  # Stable: running first, newest first within each group.
        return [(identity, label) for _, identity, label in rows[:12]]

    def model_choices():
        """List each model file's default, the active model and IDs cached by /models. Nothing is requested."""
        choices = []
        for name in model_files(root):
            try:
                default = load(root, settings.workspace, name, None, settings.max_steps, settings.max_seconds / 60)
            except (ValueError, RuntimeRefused):
                continue
            try:
                default.headers()
                missing = None
            except RuntimeRefused:
                missing = default.model.key_env or "the key variable"
            ids = [default.model.model, *catalog.get(name, ())]
            if name == settings.models:
                ids.append(settings.model.model)
            choices.extend((name, model, missing) for model in dict.fromkeys(ids))
        return choices
    while True:
        try:
            output.gap()
            text = input_fn("\ncompertum> ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            output.note("\nNo task is running. Type /exit to quit.")
            continue
        if not text:
            continue
        head, _, rest = text.partition(" ")
        if head.startswith("/"):
            text = head.lower() + (" " + rest if rest else "")  # Command names work in any case; arguments keep theirs.
        if text in ("/exit", "/quit"):
            break
        try:
            if text in ("/resume", "/stop", "/clear", "/report"):
                raise ValueError(f"use {USAGES[text]}, for example {EXAMPLES[text]}")
            if text == "/help":
                output.help(help_text())
            elif text == "/status":
                output.json({"model": settings.model.model, "model_file": settings.models,
                             "session": session.identity, "runs": runs.cards()})
            elif text == "/model" or text.startswith("/model "):
                parts = _arguments(text)
                if len(parts) == 1 and choose is not None:
                    choices = model_choices()
                    current = next((index for index, (name, model, _) in enumerate(choices)
                                    if name == settings.models and model == settings.model.model), 0)
                    width = max(len(model) for _, model, _ in choices) + 3
                    labels = [(model.ljust(width) + name.ljust(10)
                               + ("current" if index == current else f"{missing} not set" if missing else "")).rstrip()
                              for index, (name, model, missing) in enumerate(choices)]
                    picked = choose(labels, current)
                    if picked is None or picked == current:
                        output.note(f"Kept {settings.model.model}. /models NAME lists more model IDs.")
                    else:
                        updated = select(*choices[picked][:2])
                        output.note(f"Selected {updated.model.model} from {updated.models}. The choice is saved.")
                elif len(parts) == 1:
                    output.json({"model": settings.model.model, "model_file": settings.models,
                                 "model_files": model_files(root), "usage": "/model [NAME] [MODEL_ID]"})
                elif len(parts) == 2:
                    files = {name.lower(): name for name in model_files(root)}
                    name = parts[1]
                    updated = select(files[name.lower()]) if name.lower() in files else select(settings.models, name)
                    output.json({"model": updated.model.model, "model_file": updated.models, "session": session.identity})
                elif len(parts) == 3:
                    files = {name.lower(): name for name in model_files(root)}
                    updated = select(files.get(parts[1].lower(), parts[1]), parts[2])
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
                output.idle("Compertum")
                output.note(f"Started {session.identity}.")
            elif text == "/sessions":
                output.json({"sessions": sessions.summaries()})
            elif text.startswith("/resume "):
                session = sessions.load(_identity(text))
                agent = Agent(LazyClient(settings), WorkspaceTools(root, settings.workspace, busy=runs.busy),
                              Limits(settings.max_steps, settings.max_seconds), output, settings.workspace, emit=session.append)
                agent.start(session.messages)
                output.idle("Compertum")
                output.note(f"Resumed {session.identity}.")
            elif text == "/runs":
                output.json({"runs": runs.cards(), "engine_runs": engine_runs(root)})
            elif text == "/watch" or text.startswith("/watch "):
                identity = _identity(text) if " " in text else None
                if identity is None:
                    choices = watch_choices()
                    if not choices:
                        output.note("No runs yet.")
                    elif pick_run is None:
                        identity = choices[0][0]  # Scripted input: the newest running run, else the newest run.
                    else:
                        picked = pick_run([label for _, label in choices])
                        identity = None if picked is None else choices[picked][0]
                if identity is not None:
                    fetch = lambda: run_card(identity)
                    fetch()  # An unknown run reports its error before any view opens.
                    if watch is not None:
                        watch(f"Watching {identity}", lambda: readable(fetch()).splitlines())
                    output.json(fetch())  # The last snapshot stays on screen after the live view closes.
            elif text.startswith("/stop "):
                output.json(runs.stop(_identity(text)))
            elif text.startswith("/clear "):
                output.json(runs.clear(_identity(text)))
            elif text.startswith("/report "):
                output.json(runs.report(_identity(text)))
            elif text == "/test" or text.startswith("/test "):
                output.json(runs.start("test", paths=_arguments(text)[1:]))
            elif text in ("/run", "/gepa", "/bench") or text.startswith(("/run ", "/gepa ", "/bench ")):
                command = text.split(maxsplit=1)[0]
                kind = "practice" if command == "/run" else command[1:]
                if settings.model.provider in INTERACTIVE_ONLY:
                    raise ValueError(f"engine runs cannot use {settings.model.model}: {INTERACTIVE_ONLY[settings.model.provider]}. "
                                     "Choose a DeepSeek or local model with /model first")
                output.json(runs.start(kind, **_run_args(text)))
            elif text == "/limits" or text.startswith("/limits "):
                parts = _arguments(text)
                if len(parts) == 3:
                    try:
                        steps, minutes = int(parts[1]), float(parts[2])
                    except ValueError:
                        raise ValueError("use /limits STEPS MINUTES, for example /limits 100 60") from None
                    settings = load(root, settings.workspace, settings.models, settings.model.model, steps, minutes)
                    agent.limits = Limits(settings.max_steps, settings.max_seconds)
                elif len(parts) != 1:
                    raise ValueError("use /limits STEPS MINUTES, for example /limits 100 60")
                output.json({"max_steps": settings.max_steps, "max_minutes": settings.max_seconds / 60,
                             "range": "1 to 100 steps and 1 to 60 minutes per task"})
            elif text.startswith("/"):
                output.error("unknown command; /help shows the commands")
            else:
                output.outcome(agent.run_task(text))
        except (RunError, SessionError, ModelError, RuntimeRefused, ValueError, StopIteration) as exc:
            output.error(getattr(exc, "code", str(exc)))
        except KeyboardInterrupt:
            output.note("Stopped the command.")  # Ctrl+C ends a slow command, not the harness.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
