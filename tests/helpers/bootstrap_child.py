"""Trusted bounded native fixture. No capability is written or printed."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4
from public_gate import read_gate
from compertum.runtime.bootstrap import receive_bootstrap, inspect_worker_request, _credential, encode_worker_frame
from compertum.runtime.ipc import PeerRegistration, encode_envelope
from compertum.runtime._pipes import NativePipeAPI, deadline_after, verify_peer
from compertum.runtime.errors import RuntimeRefused
from compertum.domain import ProcessIdentity


def registration(value):
    return PeerRegistration(**{**value, "identity": ProcessIdentity(**value["identity"])})


def main():
    config = json.loads(Path(sys.argv[2]).read_text())  # public expectation only
    if config["mode"] in {"bootstrap_bad_ack", "bootstrap_no_ack"}:
        from compertum.runtime._windows import OwnedHandle
        from compertum.runtime.bootstrap import decode_bootstrap, _observation
        api = NativePipeAPI(); parent = registration(config["supervisor"])
        with OwnedHandle(api, int(sys.argv[1])) as handle:
            if not api.handle_flags(handle) & 1: raise RuntimeRefused("BOOTSTRAP_DENIED")
            api.set_inheritable(handle, False)
            with api.peer(handle, server_side=False) as peer, api.open_process(os.getpid()) as own:
                verify_peer(parent, peer); Path(config["ready"]).touch()
                raw = api.read_frame(handle, deadline_after(5))
                decode_bootstrap(raw, expected_supervisor=parent, observed_supervisor=peer,
                                 observed_child=_observation(api, own))
                Path(config["received"]).touch()
                if config["mode"] == "bootstrap_bad_ack":
                    ack = bytearray(hashlib.sha256(raw).digest()); ack[0] ^= 1
                    api.write_frame(handle, bytes(ack), deadline_after(5))
                end = time.monotonic() + 6
                while not Path(config["gate"]).exists():
                    if time.monotonic() >= end: raise RuntimeRefused("FIXTURE_DEADLINE")
                    time.sleep(.01)
        raise RuntimeRefused("FIXTURE_ACK_FAULT")
    credential = receive_bootstrap(int(sys.argv[1]), expected_supervisor=registration(config["supervisor"]))
    packet = _credential(credential)
    instruction = read_gate(Path(config["gate"]), timeout=6)
    target = registration(instruction["target"]) if "target" in instruction else credential.target
    value = {"schema_version": 1, "request_id": str(uuid4()), "target_role": target.identity.role,
        "target_generation": target.generation, "action": "status", "payload": {},
        "actor": {"kind": "worker", "role": credential.registration.identity.role,
            "instance_id": credential.registration.identity.process_instance_id, "generation": credential.registration.generation}}
    mode = config["mode"]
    if mode == "normal": return asdict(inspect_worker_request(credential, value))
    if mode == "wrong_role": value["actor"]["role"] = "execution"
    if mode == "wrong_generation": value["actor"]["generation"] += 1
    if mode == "wrong_instance": value["actor"]["instance_id"] = str(uuid4())
    if mode == "operator": value["actor"] = {"kind": "operator"}; value["action"] = "resume_research"
    secret = "b" * 64 if mode == "wrong_secret" else packet.secret
    raw = encode_envelope(value) if mode == "operator" else encode_worker_frame(value, secret)
    api = NativePipeAPI(); deadline = deadline_after(5)
    with api.client(target) as handle, api.peer(handle, server_side=False) as peer:
        verify_peer(target, peer)
        api.write_frame(handle, raw, deadline)
        api.read_frame(handle, deadline)
        if mode == "bad_ack": api.write_frame(handle, b"incorrect acknowledgement", deadline)
    raise RuntimeRefused("UNEXPECTED_REPLY")


if __name__ == "__main__":
    try:
        print(json.dumps(main(), sort_keys=True)); sys.exit(0)
    except RuntimeRefused as error:
        print(json.dumps({"status": str(error), "can_dispatch": False}, sort_keys=True)); sys.exit(3)
