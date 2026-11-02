import copy
import importlib
import io
import json
import math
import os
import random
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TASK_ID = "ch01"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'import math\n\n\ndef signals(prices, lookback):\n    n = len(prices)\n    out = [0] * n\n    for t in range(lookback, n):\n        diff = prices[t] - prices[t - lookback]\n        out[t] = (diff > 0) - (diff < 0)\n    return out\n\n\ndef run_backtest(prices, lookback, cost_bps):\n    sig = signals(prices, lookback)\n    n = len(prices)\n    equity = [1.0] * n\n    positions = [0] * n\n    trades = 0\n    prev = 0\n    for t in range(1, n):\n        pos = sig[t - 1]\n        r = prices[t] / prices[t - 1] - 1\n        cost = abs(pos - prev) * cost_bps / 10000\n        equity[t] = equity[t - 1] * (1 + pos * r - cost)\n        positions[t] = pos\n        if pos != prev:\n            trades += 1\n        prev = pos\n    peak = equity[0]\n    worst = 0.0\n    for value in equity:\n        peak = max(peak, value)\n        worst = max(worst, (peak - value) / peak)\n    return {\n        "positions": positions,\n        "equity": equity,\n        "trades": trades,\n        "total_return": equity[-1] - 1,\n        "max_drawdown": worst,\n    }\n\n\ndef stats(equity, periods_per_year):\n    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity))]\n    m = len(rets)\n    mean = sum(rets) / m\n    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (m - 1))\n    sharpe = mean / sd * math.sqrt(periods_per_year) if sd > 0 else 0.0\n    return {\n        "cagr": (equity[-1] / equity[0]) ** (periods_per_year / m) - 1,\n        "vol": sd * math.sqrt(periods_per_year),\n        "sharpe": sharpe,\n    }\n'


def close_to(got, want):
    if want is None:
        return got is None
    if isinstance(want, (bool, str)):
        return got == want
    if isinstance(want, (int, float)):
        if isinstance(got, bool) or not isinstance(got, (int, float)):
            return False
        return math.isclose(got, want, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    if isinstance(want, dict):
        if not isinstance(got, dict):
            return False
        return all(key in got and close_to(got[key], want[key]) for key in want)
    if isinstance(want, (list, tuple)):
        if not isinstance(got, (list, tuple)) or len(got) != len(want):
            return False
        return all(close_to(g, w) for g, w in zip(got, want))
    return got == want


def brief(value):
    text = repr(value)
    return text if len(text) <= 240 else text[:240] + "..."


def same(got, want, label):
    if not close_to(got, want):
        raise AssertionError(f"{label}: got {brief(got)}, expected {brief(want)}")


def expect(flag, label):
    if not flag:
        raise AssertionError(label)


def both(sol, ref, name, *args):
    want = ref[name](*copy.deepcopy(args))
    data = copy.deepcopy(args)
    got = getattr(sol, name)(*data)
    expect(data == args, f"{name} changed its input arguments")
    return got, want


def timed(func, *args):
    box = {}

    def work():
        try:
            box["value"] = func(*args)
        except BaseException as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(LIMIT)
    if thread.is_alive():
        return None, "time limit of 10 s exceeded"
    return box.get("value"), box.get("error")


def walk(seed, n, start=100.0):
    rng = random.Random(seed)
    prices = [start]
    for _ in range(n - 1):
        prices.append(round(prices[-1] * (1 + rng.gauss(0.0005, 0.02)), 4))
    return prices


def case_window(sol, ref):
    prices = [10.0, 11.0, 10.5, 10.5, 12.0, 11.0, 11.5]
    same(sol.signals(list(prices), 1), [0, 1, -1, 0, 1, -1, 1], "signals lookback 1")
    same(sol.signals(list(prices), 3), [0, 0, 0, 1, 1, 1, 1], "signals lookback 3")
    for lookback in (2, 4, 6):
        got, want = both(sol, ref, "signals", prices, lookback)
        same(got, want, f"signals lookback {lookback}")


def case_tiny(sol, ref):
    same(sol.signals([5.0, 6.0], 3), [0, 0], "signals when lookback exceeds the data")
    out = sol.run_backtest([5.0], 1, 10.0)
    same(out["equity"], [1.0], "equity for one price")
    same(out["positions"], [0], "positions for one price")
    same(out["max_drawdown"], 0.0, "max_drawdown for one price")


def case_timing(sol, ref):
    out = sol.run_backtest([100.0, 110.0, 99.0, 99.0, 120.0], 1, 0.0)
    same(out["positions"], [0, 0, 1, -1, 0], "positions")
    same(out["equity"], [1.0, 1.0, 0.9, 0.9, 0.9], "equity")
    same(out["trades"], 3, "trades")


def case_costs(sol, ref):
    out = sol.run_backtest([100.0, 110.0, 99.0, 99.0, 120.0], 1, 10.0)
    same(out["equity"], [1.0, 1.0, 0.899, 0.897202, 0.896304798], "equity with 10 bps cost")
    same(out["total_return"], -0.103695202, "total_return")
    same(out["max_drawdown"], 0.103695202, "max_drawdown")


def case_holding(sol, ref):
    prices = [100.0, 101.0, 102.5, 103.0, 104.2, 105.0, 106.1]
    got, want = both(sol, ref, "run_backtest", prices, 1, 50.0)
    same(got["trades"], 1, "trades while the signal stays long")
    same(got["equity"], want["equity"], "equity while the signal stays long")


def case_flip(sol, ref):
    prices = [50.0, 52.0, 49.0, 53.0, 48.0, 55.0, 47.0]
    got, want = both(sol, ref, "run_backtest", prices, 1, 25.0)
    same(got["positions"], want["positions"], "positions with flips")
    same(got["equity"], want["equity"], "equity with flips")
    same(got["max_drawdown"], want["max_drawdown"], "max_drawdown with flips")


def case_drawdown(sol, ref):
    prices = [100.0, 120.0, 150.0, 140.0, 160.0, 170.0, 130.0, 135.0, 180.0]
    got, want = both(sol, ref, "run_backtest", prices, 2, 0.0)
    expect(want["max_drawdown"] > 0, "test design: drawdown expected")
    same(got["max_drawdown"], want["max_drawdown"], "max_drawdown after a peak above 1")
    same(got["total_return"], want["total_return"], "total_return")


def case_random(sol, ref):
    for seed, lookback, cost in ((1, 3, 7.5), (2, 5, 0.0), (3, 10, 20.0)):
        prices = walk(seed, 120)
        got, want = both(sol, ref, "run_backtest", prices, lookback, cost)
        same(got, want, f"run_backtest seed {seed}")


def case_stats(sol, ref):
    equity = [2.0, 2.2, 2.1, 2.4, 2.3]
    got, want = both(sol, ref, "stats", equity, 252)
    same(got, want, "stats with equity starting at 2.0")
    curve = ref["run_backtest"](walk(7, 60), 4, 5.0)["equity"]
    got, want = both(sol, ref, "stats", curve, 52)
    same(got, want, "stats on a backtest curve")


def case_flat(sol, ref):
    same(sol.stats([1.0, 2.0, 4.0], 2), {"cagr": 3.0, "vol": 0.0, "sharpe": 0.0}, "stats with zero deviation")


def main():
    saved = os.dup(1)
    sink = os.open(os.devnull, os.O_WRONLY)
    os.dup2(sink, 1)
    os.dup2(sink, 2)
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    cases = [(name, func) for name, func in list(globals().items()) if name.startswith("case_") and callable(func)]
    failures = []
    passed = 0
    try:
        oracle = {}
        exec(ORACLE, oracle)
        sol, error = timed(importlib.import_module, "solution")
        for name, func in cases:
            if error is not None or sol is None:
                failures.append(f"{name}: solution import failed: {error}"[:500])
                continue
            value, problem = timed(func, sol, oracle)
            if problem is None:
                passed += 1
            else:
                failures.append(f"{name}: {problem}"[:500])
    except BaseException as exc:
        failures.append(f"harness error: {type(exc).__name__}: {exc}"[:500])
    line = json.dumps({"id": TASK_ID, "passed": passed, "total": len(cases), "failures": failures})
    os.write(saved, (line + "\n").encode("utf-8"))
    os._exit(0)


if __name__ == "__main__":
    main()
