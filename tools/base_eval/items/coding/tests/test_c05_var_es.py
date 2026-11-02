import importlib
import io
import json
import math
import os
import sys
import threading

TASK = "c05_var_es"
LIMIT = 10.0

TWENTY = [0.012, -0.034, 0.005, -0.021, 0.018, -0.002, 0.009, -0.045, 0.027, -0.011,
          0.003, -0.016, 0.022, -0.007, 0.001, -0.029, 0.014, 0.006, -0.004, 0.010]
HUNDRED = [((i * 37) % 101 - 50) / 1000 for i in range(100)]
SEVEN = [0.02, -0.03, 0.01, -0.05, 0.04, -0.01, 0.0]
TIES = [-0.05, -0.05, -0.05, 0.01, 0.02, 0.0, -0.01, 0.03, 0.01, 0.02]


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def tail(rets, k):
    worst = sorted(rets)[:k]
    return -worst[-1], -sum(worst) / k


def pair(got, want):
    var, es = got
    return near(var, want[0]) and near(es, want[1])


CHECKS = [
    ("twenty", lambda m: pair(m.var_es(list(TWENTY), 0.9), tail(TWENTY, 2))),
    ("hundred", lambda m: pair(m.var_es(list(HUNDRED), 0.95), tail(HUNDRED, 5))),
    ("default alpha", lambda m: pair(m.var_es(list(HUNDRED)), tail(HUNDRED, 5))),
    ("worst only", lambda m: pair(m.var_es(list(HUNDRED), 0.99), tail(HUNDRED, 1))),
    ("at least one", lambda m: pair(m.var_es(list(TWENTY[:10]), 0.99), tail(TWENTY[:10], 1))),
    ("ceiling", lambda m: pair(m.var_es(list(SEVEN), 0.75), tail(SEVEN, 2))),
    ("all gains", lambda m: pair(m.var_es([0.01, 0.02, 0.03, 0.04], 0.5), (-0.02, -0.015))),
    ("ties", lambda m: pair(m.var_es(list(TIES), 0.8), (0.05, 0.05))),
    ("empty", lambda m: raises(lambda: m.var_es([], 0.95))),
    ("bad alpha", lambda m: raises(lambda: m.var_es(list(TWENTY), 1.0)) and raises(lambda: m.var_es(list(TWENTY), 0.0))),
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
