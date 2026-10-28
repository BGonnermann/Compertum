"""Slash-command usage and help in one place."""

COMMANDS = (
    ("/help", "/help", "show commands"),
    ("/status", "/status", "show model, session, and run state"),
    ("/model", "/model [NAME] [MODEL_ID]", "select a model without restarting"),
    ("/models", "/models [NAME]", "list models without a completion"),
    ("/new", "/new", "start a new conversation"),
    ("/sessions", "/sessions", "list saved conversations"),
    ("/resume", "/resume SESSION_ID", "resume a conversation"),
    ("/test", "/test [TEST_PATH ...]", "run bounded product tests"),
    ("/run", "/run CYCLES REQUESTS HOURS NOTE", "start a bounded practice run"),
    ("/gepa", "/gepa CYCLES REQUESTS HOURS NOTE", "start a bounded GEPA run"),
    ("/bench", "/bench CYCLES REQUESTS HOURS NOTE", "start a bounded bench run"),
    ("/runs", "/runs", "show uniform run cards"),
    ("/watch", "/watch [RUN_ID]", "show the latest run card"),
    ("/stop", "/stop RUN_ID", "stop a run you started"),
    ("/clear", "/clear RUN_ID", "dismiss a terminal or unverifiable run"),
    ("/report", "/report RUN_ID", "show a run card and bounded log tail"),
    ("/exit", "/exit", "quit"),
)

USAGES = {name: usage for name, usage, _ in COMMANDS}
DESCRIPTIONS = {name: description for name, _, description in COMMANDS}
EXAMPLES = {
    "/help": "/help",
    "/status": "/status",
    "/model": "/model kimi",
    "/models": "/models kimi",
    "/new": "/new",
    "/sessions": "/sessions",
    "/resume": "/resume session-20261028-104110-7382a492",
    "/test": "/test tests/test_harness_cli.py",
    "/run": "/run 8 450 2 test current prompts",
    "/gepa": "/gepa 20 450 2 improve reversal capture",
    "/bench": "/bench 4 600 2 compare baseline",
    "/runs": "/runs",
    "/watch": "/watch",
    "/stop": "/stop test-20261028-104319-3e2d2a0a",
    "/clear": "/clear test-20261028-104319-3e2d2a0a",
    "/report": "/report test-20261028-104319-3e2d2a0a",
    "/exit": "/exit",
}
RUN_ID_COMMANDS = frozenset({"/watch", "/stop", "/clear", "/report"})


def help_text():
    lines = ["Commands:"]
    lines.extend(f"  {usage:<38}{DESCRIPTIONS[name]}" for name, usage, _ in COMMANDS)
    lines.append("Up/Down selects commands. Tab inserts the selection and completes identifiers.")
    lines.append("Ctrl+C stops the current model task. The owner starts every engine run.")
    return "\n".join(lines)


def common_prefix(values):
    if not values:
        return ""
    prefix = values[0]
    for value in values[1:]:
        while not value.startswith(prefix):
            prefix = prefix[:-1]
    return prefix


def matching_commands(text, limit=6):
    if not text.startswith("/"):
        return []
    name = text.split(maxsplit=1)[0]
    matches = [usage for command, usage, _ in COMMANDS if command.startswith(name)]
    return matches if limit is None else matches[:limit]


def _completion(values, prefix, start):
    matches = [value for value in sorted(values) if value.startswith(prefix)]
    shared = common_prefix(matches)
    return start + shared if shared and len(shared) > len(prefix) else None


def complete(text, sessions=(), runs=(), model_files=(), model_ids=None):
    if not isinstance(text, str) or not text.startswith("/"):
        return None
    parts = text.split(maxsplit=1)
    command = parts[0]
    if len(parts) == 2 and (command == "/resume" or command in RUN_ID_COMMANDS):
        values = sessions() if command == "/resume" else runs()
        return _completion(values, parts[1], f"{command} ")
    if len(parts) == 2 and command in ("/model", "/models"):
        argument = parts[1]
        if command == "/models" or " " not in argument:
            if command == "/models" and " " in argument:
                return None
            values = model_files() if callable(model_files) else model_files
            return _completion(values, argument, f"{command} ")
        name, _, prefix = argument.partition(" ")
        values = model_ids(name) if model_ids else ()
        return _completion(values, prefix, f"{command} {name} ")
    if len(parts) != 1:
        return None
    if command in USAGES:
        return USAGES[command]
    matches = [name for name, _, _ in COMMANDS if name.startswith(command)]
    if len(matches) == 1:
        return USAGES[matches[0]]
    shared = common_prefix(matches)
    if shared and len(shared) > len(command):
        return shared
    return None
