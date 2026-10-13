"""Bounded read of atomically published public fixture instructions."""
import json
import time
from compertum.runtime.errors import RuntimeRefused


def read_gate(path, timeout=6):
    deadline = time.monotonic() + timeout
    while True:
        try:
            with path.open('rb') as stream:
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise RuntimeRefused('FIXTURE_INPUT_TOO_LARGE')
            return json.loads(raw)
        except (FileNotFoundError, PermissionError):
            # Windows can expose the renamed destination before the publisher's
            # handle is closed. Retry only the public file, within the same bound.
            if time.monotonic() >= deadline:
                raise RuntimeRefused('FIXTURE_GATE_UNAVAILABLE') from None
            time.sleep(.01)
