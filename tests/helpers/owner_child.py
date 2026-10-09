"""Trusted bounded separate-owner fixture; public output contains no secrets."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from uuid import uuid4
from compertum.runtime.bootstrap import _registration
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.ipc import start_role_pipe, inspect_request, PipeDescriptor
from compertum.runtime.owner_channel import receive_owner_channel
from compertum.runtime.owners import acquire_owner, release_owner, _LEASES


def main():
    raw = Path(sys.argv[2]).read_bytes()
    if len(raw) > 8192: raise RuntimeRefused("FIXTURE_INPUT_TOO_LARGE")
    config = json.loads(raw)
    lease = acquire_owner(resolve_project(Path(config["root"])), config["role"])
    try:
        endpoint = start_role_pipe(lease, frozenset(config["commands"]))
        try:
            channel = receive_owner_channel(int(sys.argv[1]), expected_supervisor=_registration(config["supervisor"]),
                                            endpoint=endpoint)
        except RuntimeRefused:
            if "operator_target" not in config: raise
            target = _registration(config["operator_target"])
            value = {"schema_version": 1, "request_id": str(uuid4()), "target_role": target.identity.role,
                "target_generation": target.generation, "action": "resume_research", "payload": {}, "actor": {"kind": "operator"}}
            return asdict(inspect_request(PipeDescriptor(target), value))
        gate = Path(config["gate"]); end = time.monotonic() + 12
        while not gate.exists():
            if time.monotonic() >= end: raise RuntimeRefused("FIXTURE_DEADLINE")
            time.sleep(.01)
        action = json.loads(gate.read_text()).get("action", "inspect")
        if action == "release":
            release_owner(lease)
            return {"status": "RELEASED", "endpoint_closed": endpoint.closed, "can_dispatch": False}
        if action == "stale_session": channel.session = "0" * 64
        if action == "stale_sequence": channel.sequence += 1
        return asdict(endpoint.inspect_once(timeout=5))
    finally:
        if lease in _LEASES: release_owner(lease)


if __name__ == "__main__":
    try:
        print(json.dumps(main(), sort_keys=True)); sys.exit(0)
    except RuntimeRefused as error:
        print(json.dumps({"status": str(error), "can_dispatch": False}, sort_keys=True)); sys.exit(3)
