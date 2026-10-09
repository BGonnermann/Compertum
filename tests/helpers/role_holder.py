"""Bounded, credential-free native owner fixture; never a product worker."""
import argparse
import json
from pathlib import Path
import threading
import time
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner, release_owner


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--barrier", required=True)
    p.add_argument("--stop", required=True)
    p.add_argument("--dead-thread", action="store_true")
    p.add_argument("--release-live", action="store_true")
    a = p.parse_args()
    end = time.monotonic() + 30
    while not Path(a.barrier).exists():
        if time.monotonic() >= end: return 3
        time.sleep(.02)
    leases = []; errors = []
    def own():
        try: leases.append(acquire_owner(resolve_project(Path(a.root)), "execution"))
        except RuntimeRefused as e: errors.append(e.code)
    if a.dead_thread:
        t = threading.Thread(target=own); t.start(); t.join(5)
        if t.is_alive(): return 3
    else: own()
    if errors:
        print(json.dumps({"status": errors[0]}), flush=True); return 3
    lease = leases[0]
    if a.release_live: release_owner(lease)
    print(json.dumps({"status": "HELD" if not a.release_live else "RELEASED_LIVE",
                      "pid": lease.identity.pid, "creation_filetime": lease.identity.creation_filetime,
                      "generation": lease.generation}), flush=True)
    try:
        while not Path(a.stop).exists() and time.monotonic() < end: time.sleep(.02)
    finally:
        if not a.release_live: release_owner(lease)
    return 0


if __name__ == "__main__": raise SystemExit(main())
