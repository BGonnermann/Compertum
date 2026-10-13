"""Bounded real-pipe fault fixture. All bytes and markers are nonsecret."""
import ctypes
import json
from pathlib import Path
import struct
import sys
import time
from compertum.runtime.bootstrap import _registration
from compertum.runtime._pipes import NativePipeAPI, deadline_after, verify_peer
from compertum.runtime.errors import RuntimeRefused


def main():
    raw = Path(sys.argv[1]).read_bytes()
    if len(raw) > 8192: raise RuntimeRefused("FIXTURE_INPUT_TOO_LARGE")
    config = json.loads(raw); api = NativePipeAPI(); target = _registration(config["target"])
    with api.client(target) as handle, api.peer(handle, server_side=False) as observed:
        verify_peer(target, observed)
        Path(config["ready"]).touch()
        mode = config["mode"]
        if mode == "partial":
            raw = struct.pack("<I", 32) + b"x"
            buffer = ctypes.create_string_buffer(raw)
            if api._io(handle, "write", buffer, len(raw), deadline_after(5)) != len(raw):
                raise RuntimeRefused("FIXTURE_WRITE_UNVERIFIED")
        if mode in {"bad_ack", "no_ack"}:
            api.write_frame(handle, json.dumps(config["command"]).encode(), deadline_after(5))
            api.read_frame(handle, deadline_after(5))
            Path(config["received"]).touch()
            if mode == "bad_ack": api.write_frame(handle, b"incorrect acknowledgement", deadline_after(5))
        end = time.monotonic() + 6
        while not Path(config["stop"]).exists():
            if time.monotonic() >= end: raise RuntimeRefused("FIXTURE_DEADLINE")
            time.sleep(.01)
    return {"status": "FAULT_FIXTURE_DONE"}


if __name__ == "__main__":
    try:
        print(json.dumps(main())); sys.exit(0)
    except RuntimeRefused as error:
        print(json.dumps({"status": str(error)})); sys.exit(3)
