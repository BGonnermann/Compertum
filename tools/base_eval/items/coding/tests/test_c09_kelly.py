import importlib
import io
import json
import math
import os
import sys
import threading

TASK = "c09_kelly"
LIMIT = 10.0


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


CHECKS = [
    ("even odds", lambda m: near(m.kelly_binary(0.6, 1.0), 0.2)),
    ("two to one", lambda m: near(m.kelly_binary(0.5, 2.0), 0.25)),
    ("negative edge", lambda m: near(m.kelly_binary(0.4, 1.0), -0.2)),
    ("certain win", lambda m: near(m.kelly_binary(1.0, 3.0), 1.0)),
    ("certain loss", lambda m: near(m.kelly_binary(0.0, 1.0), -1.0)),
    ("bad odds", lambda m: raises(lambda: m.kelly_binary(0.6, 0.0)) and raises(lambda: m.kelly_binary(0.6, -1.0))),
    ("bad probability", lambda m: raises(lambda: m.kelly_binary(1.5, 1.0)) and raises(lambda: m.kelly_binary(-0.1, 1.0))),
    ("continuous", lambda m: near(m.kelly_continuous(0.08, 0.2), 2.0)),
    ("risk free", lambda m: near(m.kelly_continuous(0.08, 0.2, 0.03), 1.25) and near(m.kelly_continuous(0.08, 0.2, risk_free=0.03), 1.25)),
    ("negative drift", lambda m: near(m.kelly_continuous(-0.02, 0.1), -2.0)),
    ("bad sigma", lambda m: raises(lambda: m.kelly_continuous(0.05, 0.0)) and raises(lambda: m.kelly_continuous(0.05, -0.1))),
]


def run_one(target):
    box = {}

    def body():
        try:
            box["value"] = target()
        except BaseException as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=body, daemon=True)
    worker.start()
    worker.join(LIMIT)
    if worker.is_alive():
        return None, "timeout"
    return box.get("value"), box.get("error")


def main():
    real = sys.stdout
    sys.stdout = io.StringIO()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    failures = []
    passed = 0
    module, error = run_one(lambda: importlib.import_module("solution"))
    if error:
        failures.append(f"import: {error}"[:200])
    else:
        for name, check in CHECKS:
            ok, error = run_one(lambda c=check: c(module))
            if error is None and ok is True:
                passed += 1
            else:
                failures.append(f"{name}: {error or 'wrong result'}"[:200])
    line = {"id": TASK, "passed": passed, "total": len(CHECKS), "failures": failures}
    real.write(json.dumps(line) + "\n")
    real.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
