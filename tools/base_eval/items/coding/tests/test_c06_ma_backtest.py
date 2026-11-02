import importlib
import io
import json
import math
import os
import sys
import threading

TASK = "c06_ma_backtest"
LIMIT = 10.0

HAND = [10, 11, 12, 11, 10, 12, 13]
SERIES = [100 + (t * 7) % 13 - 6 + t // 4 for t in range(60)]


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


def curve(prices, short, long, bps):
    sums = [0]
    for p in prices:
        sums.append(sums[-1] + p)
    held = [0] * len(prices)
    for t in range(1, len(prices)):
        u = t - 1
        if u >= long - 1:
            fast = (sums[u + 1] - sums[u + 1 - short]) / short
            slow = (sums[u + 1] - sums[u + 1 - long]) / long
            held[t] = 1 if fast > slow else 0
    out = [1.0]
    for t in range(1, len(prices)):
        move = prices[t] / prices[t - 1] - 1
        out.append(out[-1] * (1 + held[t] * move - bps / 1e4 * abs(held[t] - held[t - 1])))
    return out


def matches(got, want):
    equity, total = got
    return near_list(equity, want) and near(total, want[-1] - 1.0)


def hand_cost(m):
    a = 11 / 12 - 0.001
    want = [1.0, 1.0, 1.0, a, a * 10 / 11, a * 10 / 11 * 0.999, a * 10 / 11 * 0.999]
    return matches(m.ma_backtest(list(HAND), 2, 3, 10), want)


CHECKS = [
    ("hand no cost", lambda m: matches(m.ma_backtest(list(HAND), 2, 3, 0), [1.0, 1.0, 1.0, 11 / 12, 10 / 12, 10 / 12, 10 / 12])),
    ("hand cost", hand_cost),
    ("hand total", lambda m: near(m.ma_backtest(list(HAND), 2, 3, 0)[1], -1 / 6)),
    ("length", lambda m: len(list(m.ma_backtest(list(SERIES), 3, 7, 5)[0])) == len(SERIES)),
    ("too short", lambda m: matches(m.ma_backtest([10, 11, 12], 2, 5, 10), [1.0, 1.0, 1.0])),
    ("constant", lambda m: matches(m.ma_backtest([10] * 8, 2, 4, 25), [1.0] * 8)),
    ("series", lambda m: matches(m.ma_backtest(list(SERIES), 3, 7, 5), curve(SERIES, 3, 7, 5))),
    ("short one", lambda m: matches(m.ma_backtest(list(SERIES), 1, 2, 20), curve(SERIES, 1, 2, 20))),
    ("order", lambda m: raises(lambda: m.ma_backtest(list(HAND), 3, 3, 0)) and raises(lambda: m.ma_backtest(list(HAND), 4, 2, 0))),
    ("short zero", lambda m: raises(lambda: m.ma_backtest(list(HAND), 0, 3, 0))),
    ("empty", lambda m: raises(lambda: m.ma_backtest([], 2, 3, 0))),
    ("bad price", lambda m: raises(lambda: m.ma_backtest([10, 11, 0, 12], 2, 3, 0))),
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
