"""Regression for partial command publication; no native qualification."""
import importlib.util
import json
from pathlib import Path


def test_consumer_cannot_observe_a_partially_written_gate(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("fixture_files", Path(__file__).parent / "windows/fixture_files.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    gate = tmp_path / "command.go"; real_write = Path.write_text; visible_while_writing = []
    def write(path, content, *args, **kwargs):
        real_write(path, "{", *args, **kwargs)
        visible_while_writing.append(gate.exists())
        return real_write(path, content, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", write)
    module.publish_gate(gate, {"action": "inspect"})
    assert visible_while_writing == [False]
    assert json.loads(gate.read_text()) == {"action": "inspect"}
    assert list(tmp_path.iterdir()) == [gate]
