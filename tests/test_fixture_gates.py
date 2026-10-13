"""Native sharing races in public fixture files, not product authority."""
import importlib.util
import os
from pathlib import Path
import threading
import time
import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='NATIVE_WINDOWS_UNAVAILABLE')


def reader():
    spec = importlib.util.spec_from_file_location('public_gate', Path(__file__).parent / 'helpers/public_gate.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.read_gate


def test_published_gate_waits_for_transient_sharing_handle(tmp_path):
    from compertum.runtime._windows import WindowsAPI
    path = tmp_path / 'gate.json'; path.write_text('{"action":"inspect"}')
    handle = WindowsAPI().open_file(path, 0x80000000, 0)
    closer = threading.Thread(target=lambda: (time.sleep(.1), handle.close()))
    closer.start()
    try:
        assert reader()(path, timeout=1) == {'action': 'inspect'}
    finally: closer.join(); handle.close()


def test_unreadable_gate_has_bounded_refusal(tmp_path):
    from compertum.runtime._windows import WindowsAPI
    from compertum.runtime.errors import RuntimeRefused
    path = tmp_path / 'gate.json'; path.write_text('{}')
    with WindowsAPI().open_file(path, 0x80000000, 0):
        started = time.monotonic()
        with pytest.raises(RuntimeRefused, match='FIXTURE_GATE_UNAVAILABLE'):
            reader()(path, timeout=.05)
        assert time.monotonic() - started < 1
