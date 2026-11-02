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

TASK_ID = "ch02"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'import math\n\n\ndef asset_returns(closes, dividends):\n    return [(closes[t] + dividends[t]) / closes[t - 1] - 1 for t in range(1, len(closes))]\n\n\ndef portfolio_returns(closes, dividends, weights, cost_bps):\n    symbols = sorted(weights)\n    rets = {s: asset_returns(closes[s], dividends[s]) for s in symbols}\n    rate = cost_bps / 10000\n    steps = len(closes[symbols[0]]) - 1\n    equity = 1.0 - rate * sum(abs(weights[s]) for s in symbols)\n    previous = 1.0\n    out = []\n    for t in range(steps):\n        gross = sum(weights[s] * rets[s][t] for s in symbols)\n        value = equity * (1 + gross)\n        turnover = 0.0\n        for s in symbols:\n            drifted = weights[s] * (1 + rets[s][t]) / (1 + gross)\n            turnover += abs(weights[s] - drifted)\n        value -= value * turnover * rate\n        out.append(value / previous - 1)\n        previous = value\n        equity = value\n    return out\n\n\ndef summary(net_returns, periods_per_year):\n    m = len(net_returns)\n    equity = [1.0]\n    for r in net_returns:\n        equity.append(equity[-1] * (1 + r))\n    mean = sum(net_returns) / m\n    sd = math.sqrt(sum((r - mean) ** 2 for r in net_returns) / (m - 1))\n    sharpe = mean / sd * math.sqrt(periods_per_year) if sd > 0 else 0.0\n    peak = equity[0]\n    worst = 0.0\n    for value in equity:\n        peak = max(peak, value)\n        worst = max(worst, (peak - value) / peak)\n    return {\n        "total_return": equity[-1] - 1,\n        "cagr": equity[-1] ** (periods_per_year / m) - 1,\n        "vol": sd * math.sqrt(periods_per_year),\n        "sharpe": sharpe,\n        "max_drawdown": worst,\n    }\n'


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


def market(seed, symbols, n):
    rng = random.Random(seed)
    closes = {}
    dividends = {}
    for s in symbols:
        path = [rng.uniform(20, 200)]
        divs = [0.0]
        for t in range(1, n):
            path.append(round(path[-1] * (1 + rng.gauss(0.0003, 0.015)), 4))
            divs.append(round(path[-1] * 0.01, 4) if rng.random() < 0.08 else 0.0)
        closes[s] = path
        dividends[s] = divs
    return closes, dividends


def case_assets(sol, ref):
    got = sol.asset_returns([10.0, 10.5, 10.2, 10.8], [0.0, 0.0, 0.3, 0.0])
    same(got, [0.05, 0.0, 10.8 / 10.2 - 1], "asset_returns with a dividend")
    same(sol.asset_returns([10.0, 9.0], [5.0, 0.0]), [-0.1], "dividend on bar 0 is ignored")


def case_initial(sol, ref):
    got = sol.portfolio_returns({"A": [10.0, 10.0, 10.0]}, {"A": [0.0, 0.0, 0.0]}, {"A": 1.0}, 25.0)
    same(got, [-0.0025, 0.0], "first return includes the purchase cost")


def case_dividend(sol, ref):
    closes = {"A": [20.0, 20.5, 20.0, 21.0]}
    dividends = {"A": [0.0, 0.0, 0.5, 0.0]}
    got = sol.portfolio_returns(closes, dividends, {"A": 0.6}, 0.0)
    same(got, [0.015, 0.0, 0.03], "dividend counted once")


def case_drift(sol, ref):
    closes = {"A": [100.0, 110.0, 99.0, 105.0], "B": [50.0, 49.0, 51.0, 52.0]}
    dividends = {"A": [0.0] * 4, "B": [0.0] * 4}
    got, want = both(sol, ref, "portfolio_returns", closes, dividends, {"A": 0.5, "B": 0.5}, 20.0)
    same(got, want, "two-asset rebalance costs")


def case_short(sol, ref):
    closes = {"A": [40.0, 41.0, 39.5, 42.0, 43.0], "B": [80.0, 78.0, 79.0, 81.5, 80.0], "C": [5.0, 6.0, 7.0, 8.0, 9.0]}
    dividends = {"A": [0.0, 0.0, 0.4, 0.0, 0.0], "B": [0.0, 0.0, 0.0, 0.0, 1.0], "C": [0.0] * 5}
    got, want = both(sol, ref, "portfolio_returns", closes, dividends, {"A": 0.8, "B": -0.3}, 10.0)
    same(got, want, "long and short weights with cash and an unused symbol")


def case_summary(sol, ref):
    rets = [0.01, -0.02, 0.015, 0.005]
    got, want = both(sol, ref, "summary", rets, 252)
    same(got["total_return"], 1.01 * 0.98 * 1.015 * 1.005 - 1, "total_return")
    same(got, want, "summary")


def case_firstloss(sol, ref):
    got = sol.summary([-0.1, 0.05, 0.02], 12)
    same(got["max_drawdown"], 0.1, "max_drawdown when the first return is a loss")


def case_flat(sol, ref):
    got = sol.summary([0.01, 0.01], 4)
    same(got, {"total_return": 0.0201, "cagr": 1.0201 ** 2 - 1, "vol": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}, "summary with zero deviation")


def case_random(sol, ref):
    for seed, weights, cost in ((11, {"X": 0.5, "Y": 0.4, "Z": -0.2}, 15.0), (12, {"X": 1.0, "Z": 0.25}, 5.0)):
        closes, dividends = market(seed, ["X", "Y", "Z"], 90)
        got, want = both(sol, ref, "portfolio_returns", closes, dividends, weights, cost)
        same(got, want, f"portfolio_returns seed {seed}")
        got, want = both(sol, ref, "summary", want, 252)
        same(got, want, f"summary seed {seed}")


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
