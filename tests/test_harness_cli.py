from io import StringIO

from compertum.harness.cli import main
from compertum.harness.display import Display


def config(root):
    root.mkdir()
    (root / "config").mkdir()
    entry = 'base_url = "http://127.0.0.1:1234/v1"\nmodel = "scripted"\n'
    (root / "config" / "models.toml").write_text("[roles.director]\n" + entry + "[roles.researcher]\n" + entry +
                                                   "[roles.mathematician]\n" + entry + "[roles.engineer]\n" + entry)


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
