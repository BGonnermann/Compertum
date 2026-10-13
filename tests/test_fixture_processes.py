"""Fixture launch selection only; native PID/handle proof is separate."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest


def fixture_module():
    spec = importlib.util.spec_from_file_location("fixture_processes", Path(__file__).parent / "windows/fixture_processes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_fixture_launches_the_runtime_directly_with_the_same_venv(tmp_path, monkeypatch):
    module = fixture_module()
    runtime = tmp_path / "python.exe"; runtime.touch()
    redirector = str(tmp_path / "venv/Scripts/python.exe")
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32", executable=redirector,
                                                     _base_executable=str(runtime)))
    received = {}
    def capture(args, **kwargs):
        received.update(args=args, **kwargs)
        return "child"
    monkeypatch.setattr(module.subprocess, "Popen", capture)
    env = {"SYSTEMROOT": "fixture", "__PYVENV_LAUNCHER__": "untrusted-parent-value"}
    startup = object()
    assert module.python_process(["-B", "fixture.py"], env=env, close_fds=True, startupinfo=startup) == "child"
    assert received["executable"] == str(runtime)
    assert received["args"] == [redirector, "-B", "fixture.py"]
    assert received["env"]["__PYVENV_LAUNCHER__"] == redirector
    assert env["__PYVENV_LAUNCHER__"] == "untrusted-parent-value"
    assert received["startupinfo"] is startup and received["close_fds"] is True


def test_missing_windows_runtime_does_not_fall_back_to_a_redirector(tmp_path, monkeypatch):
    module = fixture_module()
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32", executable="redirector",
                                                     _base_executable=str(tmp_path / "absent.exe")))
    def forbidden(*args, **kwargs): pytest.fail("an unverified executable was launched")
    monkeypatch.setattr(module.subprocess, "Popen", forbidden)
    with pytest.raises(RuntimeError, match="FIXTURE_RUNTIME_UNAVAILABLE"):
        module.python_process(["fixture.py"], env={})
