import importlib
import io
import json
import math
import os
import sys
import threading

TASK = "c03_max_drawdown"
LIMIT = 10.0


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def triple(got, want):
    mdd, peak, trough = got
    return near(mdd, want[0]) and peak == want[1] and trough == want[2]


CHECKS = [
    ("basic", lambda m: triple(m.max_drawdown([100, 120, 90, 110, 80, 130]), (1 / 3, 1, 4))),
    ("fraction", lambda m: triple(m.max_drawdown([400, 340, 360]), (0.15, 0, 1))),
    ("rising", lambda m: triple(m.max_drawdown([1, 2, 3, 4]), (0.0, 0, 0))),
    ("single", lambda m: triple(m.max_drawdown([5.0]), (0.0, 0, 0))),
    ("empty", lambda m: raises(lambda: m.max_drawdown([]))),
    ("zero value", lambda m: raises(lambda: m.max_drawdown([10, 0, 5]))),
    ("peak tie", lambda m: triple(m.max_drawdown([100, 90, 100, 40]), (0.6, 0, 3))),
    ("trough tie", lambda m: triple(m.max_drawdown([100, 50, 100, 50]), (0.5, 0, 1))),
    ("later peak", lambda m: triple(m.max_drawdown([10, 8, 20, 12, 25, 10]), (0.6, 4, 5))),
    ("flat start", lambda m: triple(m.max_drawdown([5, 5, 5, 4]), (0.2, 0, 3))),
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
