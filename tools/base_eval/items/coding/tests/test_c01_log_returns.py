import importlib
import io
import json
import math
import os
import sys
import threading

TASK = "c01_log_returns"
LIMIT = 10.0


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def near_list(got, want):
    got = list(got)
    return len(got) == len(want) and all(near(g, w) for g, w in zip(got, want))


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def telescoping(m):
    prices = [100 + (i * 7) % 11 + i * 0.5 for i in range(50)]
    got = list(m.log_returns(prices))
    return len(got) == 49 and near(sum(got), math.log(prices[-1] / prices[0]))


CHECKS = [
    ("basic", lambda m: near_list(m.log_returns([100, 110, 99]), [math.log(1.1), math.log(0.9)])),
    ("ints", lambda m: near_list(m.log_returns([1, 2, 4]), [math.log(2), math.log(2)])),
    ("floats", lambda m: near_list(m.log_returns([1.5, 1.2, 1.8]), [math.log(0.8), math.log(1.5)])),
    ("length", lambda m: len(list(m.log_returns([5, 6, 7, 8, 9, 10]))) == 5),
    ("empty", lambda m: len(list(m.log_returns([]))) == 0),
    ("single", lambda m: len(list(m.log_returns([42.0]))) == 0),
    ("zero price", lambda m: raises(lambda: m.log_returns([100, 0, 50]))),
    ("negative price", lambda m: raises(lambda: m.log_returns([100, -5, 50]))),
    ("constant", lambda m: near_list(m.log_returns([50, 50, 50, 50]), [0.0, 0.0, 0.0])),
    ("telescoping", telescoping),
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
