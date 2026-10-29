import re
from io import StringIO

from compertum.harness.cli import LazyClient, main
from compertum.harness.display import Display
from compertum.harness.runs import RunManager


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
    sessions = list((root / "state" / "harness" / "sessions").glob("session-*.jsonl"))
    output = StringIO()
    result = main(["--project", str(root), "--resume", sessions[0].stem], display=Display(output, color=False),
                  input_fn=lambda _: "/exit")
    assert result == 0
    assert sessions[0].stem in output.getvalue()


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
    assert "use CYCLES REQUESTS HOURS NOTE" in text
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

    def answers():
        yield "/model kimi"
        yield "/new"
        sessions = sorted((root / "state" / "harness" / "sessions").glob("session-*.jsonl"))
        yield f"/resume {sessions[-1].stem}"
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
    assert '"model": "kimi-exact"' in status_model(root, ["--resume", sorted((root / "state" / "harness" / "sessions").glob("*.jsonl"))[0].stem])
    assert '"model": "scripted"' in status_model(root, ["--models", "local"])
    assert '"model": "kimi-exact"' in status_model(root)  # Start options do not change the saved /model choice.
    (root / "config" / "models-kimi.toml").unlink()
    text = status_model(root)
    assert "The saved model choice kimi kimi-exact no longer loads. Using local." in text and '"model": "scripted"' in text


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
    text = status_model(root, answers=("/model kimi", "/status", "/exit"))
    assert "is not set in your user environment. Requests to kimi will fail until you set it." in text
    assert '"model": "kimi-default"' in text
