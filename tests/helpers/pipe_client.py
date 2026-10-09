"""Credential-free bounded IPC fixture. It never dispatches an effect."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
from compertum.domain import ProcessIdentity
from compertum.runtime.ipc import PeerRegistration, PipeDescriptor, inspect_request
from compertum.runtime.errors import RuntimeRefused

try:
    raw = Path(sys.argv[1]).read_bytes()
    if len(raw) > 8192: raise RuntimeRefused("FIXTURE_INPUT_TOO_LARGE")
    packet = json.loads(raw)
    registration = packet["registration"]
    registration["identity"] = ProcessIdentity(**registration["identity"])
    descriptor = PipeDescriptor(PeerRegistration(**registration))
    if packet.get("raw"):
        # Deliberately malformed native input, to exercise the receiver rather
        # than merely demonstrate client-side validation.
        from compertum.runtime._pipes import NativePipeAPI, deadline_after, verify_peer
        api = NativePipeAPI(); deadline = deadline_after(5)
        with api.client(descriptor.registration) as handle, api.peer(handle, server_side=False) as observed:
            verify_peer(descriptor.registration, observed)
            api.write_frame(handle, json.dumps(packet["command"]).encode(), deadline)
            api.read_frame(handle, deadline)
        raise RuntimeRefused("UNEXPECTED_REPLY")
    result = inspect_request(descriptor, packet["command"], timeout=5)
    print(json.dumps(asdict(result)), flush=True)
except RuntimeRefused as error:
    print(json.dumps({"status": str(error)}), flush=True)
    raise SystemExit(3)
