import importlib
import io
import json
import math
import os
import statistics
import sys
import threading

TASK = "c02_sharpe_ratio"
LIMIT = 10.0

RETS = [0.01, -0.02, 0.015, 0.003, -0.007, 0.012, 0.0, 0.021, -0.011, 0.005]
LOSERS = [-0.01, 0.004, -0.012, -0.003, 0.002, -0.008]


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def expected(rets, rf, periods):
    excess = [r - rf for r in rets]
    return statistics.mean(excess) / statistics.stdev(excess) * math.sqrt(periods)


CHECKS = [
    ("defaults", lambda m: near(m.sharpe_ratio(list(RETS)), expected(RETS, 0.0, 252))),
    ("risk free", lambda m: near(m.sharpe_ratio(list(RETS), 0.0002), expected(RETS, 0.0002, 252))),
    ("monthly", lambda m: near(m.sharpe_ratio(list(RETS), 0.0, 12), expected(RETS, 0.0, 12))),
    ("keywords", lambda m: near(m.sharpe_ratio(list(RETS), periods_per_year=52, risk_free=0.001), expected(RETS, 0.001, 52))),
    ("negative", lambda m: near(m.sharpe_ratio(list(LOSERS)), expected(LOSERS, 0.0, 252))),
    ("two points", lambda m: near(m.sharpe_ratio([0.01, 0.03]), 0.02 / math.sqrt(2e-4) * math.sqrt(252))),
    ("empty", lambda m: raises(lambda: m.sharpe_ratio([]))),
    ("single", lambda m: raises(lambda: m.sharpe_ratio([0.01]))),
    ("zero std", lambda m: raises(lambda: m.sharpe_ratio([0.25, 0.25, 0.25, 0.25]))),
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
