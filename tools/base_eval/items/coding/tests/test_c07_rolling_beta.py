import importlib
import io
import json
import math
import os
import statistics
import sys
import threading

TASK = "c07_rolling_beta"
LIMIT = 10.0

MARKET = [0.010, -0.004, 0.007, 0.012, -0.009, 0.003, -0.006, 0.015, 0.001, -0.011]
ASSET = [0.014, -0.010, 0.006, 0.020, -0.012, 0.001, -0.004, 0.019, 0.006, -0.017]


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def same_beta(got, want):
    got = list(got)
    if len(got) != len(want):
        return False
    for g, w in zip(got, want):
        if w is None:
            if g is not None:
                return False
        elif g is None or not near(g, w):
            return False
    return True


def expected(asset, market, window):
    out = [None] * len(asset)
    for t in range(window - 1, len(asset)):
        a = asset[t - window + 1:t + 1]
        m = market[t - window + 1:t + 1]
        var = statistics.variance(m)
        out[t] = None if var == 0 else statistics.covariance(a, m) / var
    return out


def flat_window(m):
    market = [0.01, 0.02, 0.0, 0.0, 0.0, 0.03, -0.01]
    asset = [0.02, 0.01, 0.005, -0.002, 0.004, 0.05, -0.02]
    return same_beta(m.rolling_beta(asset, market, 3), expected(asset, market, 3))


CHECKS = [
    ("prefix", lambda m: same_beta([None if x is None else 0.0 for x in m.rolling_beta(list(ASSET), list(MARKET), 4)],[None] * 3 + [0.0] * 7)),
    ("window four", lambda m: same_beta(m.rolling_beta(list(ASSET), list(MARKET), 4), expected(ASSET, MARKET, 4))),
    ("window two", lambda m: same_beta(m.rolling_beta(list(ASSET), list(MARKET), 2), expected(ASSET, MARKET, 2))),
    ("beta two", lambda m: same_beta(m.rolling_beta([2 * x + 0.001 for x in MARKET], list(MARKET), 5), [None] * 4 + [2.0] * 6)),
    ("beta minus", lambda m: same_beta(m.rolling_beta([-x for x in MARKET], list(MARKET), 3), [None] * 2 + [-1.0] * 8)),
    ("full window", lambda m: same_beta(m.rolling_beta(list(ASSET), list(MARKET), 10), expected(ASSET, MARKET, 10))),
    ("long window", lambda m: same_beta(m.rolling_beta(list(ASSET), list(MARKET), 11), [None] * 10)),
    ("mismatch", lambda m: raises(lambda: m.rolling_beta(ASSET[:9], list(MARKET), 3))),
    ("window one", lambda m: raises(lambda: m.rolling_beta(list(ASSET), list(MARKET), 1))),
    ("flat window", flat_window),
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
