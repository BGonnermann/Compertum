import re
from io import StringIO

from compertum.harness.cli import LazyClient, main
from compertum.harness.display import Display
from compertum.harness.runs import RunManager
from compertum.harness.sessions import SessionStore


def config(root):
    root.mkdir()
    (root / "config").mkdir()
    model_file(root, "local", "scripted")


def model_file(root, name, model):
    entry = f'base_url = "http://127.0.0.1:1234/v1"\nmodel = "{model}"\n'
    text = "[roles.director]\n" + entry + "[roles.researcher]\n" + entry + "[roles.mathematician]\n" + entry
    text += "[roles.engineer]\n" + entry
    filename = "models.toml" if name == "local" else f"models-{name}.toml"
    (root / "config" / filename).write_text(text, encoding="utf-8")


def saved_session(root):
    session = SessionStore(root).create()
    session.append("message", {"role": "system", "content": "start"})
    session.append("message", {"role": "user", "content": "an earlier task"})
    return session.identity


def test_console_opens_without_a_model_request_and_lists_sessions(tmp_path):
    root = tmp_path / "project"
    config(root)
    answers = iter(["/status", "/sessions", "/exit"])
    output = StringIO()
    result = main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(answers))
    assert result == 0
    text = output.getvalue()
    assert "Compertum harness" in text
    assert "session-" in text
    assert '"completion_sent"' not in text


def test_console_can_resume_a_saved_session_without_a_model(tmp_path):
    root = tmp_path / "project"
    config(root)
    first = main(["--project", str(root)], display=Display(StringIO(), color=False), input_fn=lambda _: "/exit")
    assert first == 0
    # Opening and closing the console without a task leaves no session file.
    assert not list((root / "state" / "harness" / "sessions").glob("session-*.jsonl"))
    identity = saved_session(root)
    output = StringIO()
    result = main(["--project", str(root), "--resume", identity], display=Display(output, color=False),
                  input_fn=lambda _: "/exit")
    assert result == 0
    assert identity in output.getvalue()


def test_watch_without_runs_has_a_clear_message(tmp_path):
    root = tmp_path / "project"
    config(root)
    answers = iter(["/watch", "/exit"])
    output = StringIO()
    result = main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(answers))
    assert result == 0
    assert "No runs yet." in output.getvalue()
    assert "Error:" not in output.getvalue()


def test_watch_prefix_and_bare_run_command_have_correct_errors(tmp_path):
    root = tmp_path / "project"
    config(root)
    answers = iter(["/watchdog", "/gepa", "/exit"])
    output = StringIO()
    result = main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(answers))
    assert result == 0
    text = output.getvalue()
    assert "unknown command" in text
    assert "use /gepa CYCLES REQUESTS HOURS NOTE, for example /gepa 20 450 2 improve reversal capture" in text
    assert '"status": "RUNNING"' not in text


def test_model_selection_preserves_the_session_and_changes_future_run_defaults(tmp_path, monkeypatch):
    from compertum.harness.model import Reply

    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    started, chats = [], []
    monkeypatch.setattr(RunManager, "start", lambda self, kind, **kwargs: started.append((self.models, self.model, kind)) or {})
    monkeypatch.setattr(LazyClient, "chat", lambda self, messages, *args:
                        chats.append((self.settings.models, self.settings.model.model, list(messages))) or Reply(content="selected"))
    answers = iter(["/model", "before", "/model kimi", "/model kimi kimi-exact", "/status", "after",
                    "/run 1 20 1 selected model", "/new", "/status", "/exit"])
    output = StringIO()
    result = main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(answers))
    assert result == 0
    text = output.getvalue()
    sessions = re.findall(r'"session": "([^"]+)"', text)
    assert sessions[0] == sessions[1]
    assert started == [("kimi", "kimi-exact", "practice")]
    assert [call[:2] for call in chats] == [("local", "scripted"), ("kimi", "kimi-exact")]
    assert "before" in [message["content"] for message in chats[1][2]]
    assert '"model_files": [' in text and '"kimi"' in text and '"local"' in text
    assert text.count('"model": "kimi-exact"') == 3
    assert text.count('"model_file": "kimi"') == 4


def test_failed_model_selection_keeps_the_active_model(tmp_path):
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    answers = iter(["/model kimi", "/model missing exact", "/status", "/exit"])
    output = StringIO()
    result = main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(answers))
    assert result == 0
    text = output.getvalue()
    assert "Error: unknown model file; /model shows the choices" in text
    assert text.count('"model": "kimi-default"') == 2
    assert '"model": "exact"' not in text


def test_model_listing_uses_the_named_file_without_switching(tmp_path, monkeypatch):
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    calls = []
    monkeypatch.setattr(LazyClient, "list_models", lambda self: calls.append(self.settings.models) or ["k3.1-pro", "k3"])
    answers = iter(["/models kimi", "/status", "/exit"])
    output = StringIO()
    result = main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(answers))
    assert result == 0
    text = output.getvalue()
    assert calls == ["kimi"]
    assert '"k3.1-pro"' in text and '"completion_sent": false' in text
    assert '"model": "scripted"' in text and '"model_file": "local"' in text


def test_model_selection_survives_resume_inside_the_console(tmp_path):
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    identity = saved_session(root)

    def answers():
        yield "/model kimi"
        yield "/new"
        yield f"/resume {identity}"
        yield "/status"
        yield "/exit"

    sequence = answers()
    output = StringIO()
    result = main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(sequence))
    assert result == 0
    text = output.getvalue()
    assert '"model": "kimi-default"' in text and '"model_file": "kimi"' in text


def status_model(root, argv=(), answers=("/status", "/exit")):
    output = StringIO()
    steps = iter(answers)
    main(["--project", str(root), *argv], display=Display(output, color=False), input_fn=lambda _: next(steps))
    return output.getvalue()


def test_model_choice_survives_a_restart_and_options_still_win(tmp_path):
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    status_model(root, answers=("/model kimi kimi-exact", "/exit"))
    assert '"model": "kimi-exact"' in status_model(root)
    assert '"model": "kimi-exact"' in status_model(root, ["--resume", saved_session(root)])
    assert '"model": "scripted"' in status_model(root, ["--models", "local"])
    assert '"model": "kimi-exact"' in status_model(root)  # Start options do not change the saved /model choice.
    (root / "config" / "models-kimi.toml").unlink()
    text = status_model(root)
    assert "The saved model choice kimi kimi-exact no longer loads. Using local." in text and '"model": "scripted"' in text


def test_plain_model_command_opens_a_picker_that_selects_and_saves(tmp_path):
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    shown = []

    def choose(options, chosen):
        shown.append((options, chosen))
        return next(index for index, label in enumerate(options) if label.startswith("kimi-default"))

    output = StringIO()
    steps = iter(["/model", "/status", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps), choose=choose)
    options, chosen = shown[0]
    assert options[chosen].startswith("scripted") and options[chosen].endswith("current")
    assert any(label.startswith("kimi-default") and "kimi" in label for label in options)
    text = output.getvalue()
    assert "Selected kimi-default from kimi. The choice is saved." in text and '"model": "kimi-default"' in text
    assert '"model": "kimi-default"' in status_model(root)
    output = StringIO()
    steps = iter(["/model", "/exit"])
    main(["--project", str(root)], display=Display(output, color=False), input_fn=lambda _: next(steps),
         choose=lambda options, chosen: None)
    assert "Kept kimi-default." in output.getvalue()


def test_picker_keeps_models_used_before_and_a_listing_refreshes_them(tmp_path, monkeypatch):
    # The owner used deepseek-flash, switched to Kimi and then v4-pro; flash then vanished from the picker.
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    status_model(root, answers=("/model local flash-id", "/model kimi", "/exit"))
    shown = []
    steps = iter(["/model", "/exit"])
    main(["--project", str(root)], display=Display(StringIO(), color=False), input_fn=lambda _: next(steps),
         choose=lambda options, chosen: shown.append(options))
    assert any(label.startswith("flash-id") for label in shown[0])
    monkeypatch.setattr(LazyClient, "list_models", lambda self: ["scripted", "new-id"])
    status_model(root, answers=("/models local", "/exit"))
    shown.clear()
    steps = iter(["/model", "/exit"])
    main(["--project", str(root)], display=Display(StringIO(), color=False), input_fn=lambda _: next(steps),
         choose=lambda options, chosen: shown.append(options))
    labels = [label.split()[0] for label in shown[0]]
    assert "new-id" in labels and "flash-id" not in labels


def test_commands_accept_real_notes_paths_case_and_explain_missing_parts(tmp_path, monkeypatch):
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    started = []
    monkeypatch.setattr(RunManager, "start", lambda self, kind, **kwargs: started.append((kind, kwargs)) or {"status": "RUNNING"})
    text = status_model(root, answers=(
        "/gepa 20 450 2 improve the owner's prompts in C:\\Users\\notes",
        "/test tests\\test_harness_cli.py",
        "/run CYCLES REQUESTS HOURS NOTE", "/run 8 450 2 NOTE",
        "/HELP", "/Model KIMI", "/resume", "/report", "/stop \"gepa-1\"",
        "/model kimi kimi-typo", "/sessions", "/exit"))
    assert started[0] == ("gepa", {"cycles": 20, "requests": 450, "hours": 2.0,
                                   "note": "improve the owner's prompts in C:\\Users\\notes"})
    assert started[1] == ("test", {"paths": ["tests\\test_harness_cli.py"]})
    assert "CYCLES and REQUESTS need whole numbers and HOURS a number, for example /run 8 450 2" in text
    assert "replace NOTE with a short description" in text
    assert "Commands:" in text and '"model_file": "kimi"' in text
    assert "use /resume SESSION_ID, for example /resume session-" in text
    assert "use /report RUN_ID, for example /report test-" in text
    assert "Error: the run was not found" in text  # The quoted ID was read as gepa-1, without its quotes.
    assert "kimi-typo is not a known model for kimi. /models kimi lists what the provider offers." in text


def test_ctrl_c_during_a_command_keeps_the_harness_open(tmp_path, monkeypatch):
    root = tmp_path / "project"
    config(root)

    def slow(self):
        raise KeyboardInterrupt()

    monkeypatch.setattr(LazyClient, "list_models", slow)
    text = status_model(root, answers=("/models", "/status", "/exit"))
    assert "Stopped the command." in text and '"model": "scripted"' in text


def test_sessions_list_dates_and_first_tasks(tmp_path):
    root = tmp_path / "project"
    config(root)
    identity = saved_session(root)
    text = status_model(root, answers=("/sessions", "/exit"))
    assert f"{identity}  {identity[8:12]}-{identity[12:14]}-{identity[14:16]}" in text and "an earlier task" in text


def test_engine_runs_refuse_an_interactive_only_provider(tmp_path, monkeypatch):
    root = tmp_path / "project"
    config(root)
    started = []
    monkeypatch.setattr(RunManager, "start", lambda self, kind, **kwargs: started.append(kind) or {"status": "RUNNING"})
    from compertum.harness import cli
    monkeypatch.setitem(cli.INTERACTIVE_ONLY, "loopback", "test subscriptions are for interactive use only")
    text = status_model(root, answers=("/gepa 1 20 1 note", "/test", "/exit"))
    assert "engine runs cannot use scripted: test subscriptions are for interactive use only" in text
    assert "Choose a DeepSeek or local model with /model first" in text
    assert started == ["test"]


def test_tasks_default_to_the_highest_limits_and_limits_can_change(tmp_path):
    root = tmp_path / "project"
    config(root)
    text = status_model(root, answers=("/limits", "/limits 40 20", "/limits 0 5", "/limits x", "/exit"))
    blocks = re.findall(r'"max_minutes": ([\d.]+),\s+"max_steps": (\d+)', text)
    assert blocks == [("60.0", "100"), ("20.0", "40")]
    assert "task limits must be 1 to 100 steps and 1 to 60 minutes" in text
    assert "use /limits STEPS MINUTES, for example /limits 100 60" in text


def test_bracket_placeholders_and_missing_keys_get_clear_messages(tmp_path, monkeypatch):
    root = tmp_path / "project"
    config(root)
    model_file(root, "kimi", "kimi-default")
    text = status_model(root, answers=("/model [NAME] [MODEL_ID]", "/exit"))
    assert "replace the bracketed words, for example /model kimi" in text
    from compertum.harness.config import Settings
    from compertum.runtime.errors import RuntimeRefused

    def refuse(self):
        raise RuntimeRefused("AI_CREDENTIAL_UNAVAILABLE")

    monkeypatch.setattr(Settings, "headers", refuse)
    text = status_model(root, answers=("/model kimi", "/status", "hello", "/exit"))
    assert "is not set in your user environment. Requests to kimi will fail until you set it." in text
    assert '"model": "kimi-default"' in text
    # The task ends as a normal error outcome with the fix, not a bare code from the console loop.
    assert "[error] 1 steps | 0:00 AI_CREDENTIAL_UNAVAILABLE: the key variable is not set." in text
    assert "or choose another model with /model" in text and "Error: AI_CREDENTIAL_UNAVAILABLE" not in text
