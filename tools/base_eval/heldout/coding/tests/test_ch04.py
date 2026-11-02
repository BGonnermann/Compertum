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

TASK_ID = "ch04"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'import math\n\n\ndef leverage(returns, window, target_vol, periods_per_year, max_leverage):\n    n = len(returns)\n    out = [0.0] * n\n    for t in range(window, n):\n        chunk = returns[t - window:t]\n        mean = sum(chunk) / window\n        var = sum((x - mean) ** 2 for x in chunk) / (window - 1)\n        vol = math.sqrt(var * periods_per_year)\n        if vol == 0:\n            out[t] = max_leverage\n        else:\n            out[t] = min(max_leverage, target_vol / vol)\n    return out\n\n\ndef strategy_returns(returns, window, target_vol, periods_per_year, max_leverage, financing_rate):\n    lev = leverage(returns, window, target_vol, periods_per_year, max_leverage)\n    out = []\n    for t, r in enumerate(returns):\n        borrow = max(0.0, lev[t] - 1) * financing_rate / periods_per_year\n        out.append(lev[t] * r - borrow)\n    return out\n\n\ndef drawdowns(returns):\n    equity = [1.0]\n    for r in returns:\n        equity.append(equity[-1] * (1 + r))\n    peak = equity[0]\n    worst = 0.0\n    longest = 0\n    current = 0\n    for value in equity:\n        if value >= peak:\n            peak = value\n            current = 0\n        else:\n            current += 1\n            longest = max(longest, current)\n        worst = max(worst, 1 - value / peak)\n    return {"equity": equity, "max_drawdown": worst, "longest": longest}\n'


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


def noise(seed, n, scale=0.01):
    rng = random.Random(seed)
    return [round(rng.gauss(0.0004, scale), 6) for _ in range(n)]


def case_basic(sol, ref):
    rets = [0.01, -0.02, 0.015, 0.003, -0.007, 0.012]
    got, want = both(sol, ref, "leverage", rets, 3, 0.1, 252, 3.0)
    same(got[:3], [0.0, 0.0, 0.0], "leverage before the first full window")
    same(got, want, "leverage window 3")


def case_lookahead(sol, ref):
    rets = noise(31, 40)
    base = sol.leverage(list(rets), 10, 0.15, 252, 4.0)
    changed = list(rets)
    changed[-1] = 0.25
    after = sol.leverage(changed, 10, 0.15, 252, 4.0)
    same(after[-1], base[-1], "leverage at bar t must not use the return of bar t")


def case_periods(sol, ref):
    rets = noise(32, 30, 0.04)
    got, want = both(sol, ref, "leverage", rets, 12, 0.12, 12, 5.0)
    same(got, want, "leverage with 12 periods per year")


def case_zero(sol, ref):
    got = sol.leverage([0.0, 0.0, 0.0, 0.0, 0.0], 3, 0.1, 252, 2.5)
    same(got, [0.0, 0.0, 0.0, 2.5, 2.5], "zero volatility gives max_leverage")
    got = sol.leverage([0.001, -0.001, 0.001, 0.002], 3, 10.0, 252, 1.75)
    same(got[3], 1.75, "leverage capped at max_leverage")


def case_financing(sol, ref):
    rets = noise(33, 50, 0.004)
    got, want = both(sol, ref, "strategy_returns", rets, 10, 0.1, 252, 3.0, 0.05)
    expect(max(ref["leverage"](rets, 10, 0.1, 252, 3.0)) > 1, "test design: leverage above 1 expected")
    same(got, want, "financing on leverage above 1")
    rets = noise(34, 50, 0.03)
    got, want = both(sol, ref, "strategy_returns", rets, 10, 0.1, 252, 3.0, 0.05)
    expect(max(ref["leverage"](rets, 10, 0.1, 252, 3.0)) < 1, "test design: leverage below 1 expected")
    same(got, want, "no financing below leverage 1")


def case_first(sol, ref):
    got = sol.drawdowns([-0.1, 0.05])
    same(got["equity"], [1.0, 0.9, 0.945], "equity starts at 1.0")
    same(got["max_drawdown"], 0.1, "max_drawdown from the starting value")
    same(got["longest"], 2, "longest drawdown")


def case_duration(sol, ref):
    rets = [0.1, -0.05, -0.05, 0.2, -0.1, 0.01, 0.01, 0.01, 0.2, -0.01]
    got, want = both(sol, ref, "drawdowns", rets)
    same(got["longest"], 4, "longest drawdown length")
    same(got, want, "drawdowns")


def case_empty(sol, ref):
    same(sol.drawdowns([]), {"equity": [1.0], "max_drawdown": 0.0, "longest": 0}, "drawdowns of no returns")


def case_random(sol, ref):
    for seed, window, target, periods, cap, rate in ((35, 20, 0.1, 252, 2.0, 0.04), (36, 6, 0.2, 52, 4.0, 0.08)):
        rets = noise(seed, 200, 0.012)
        got, want = both(sol, ref, "strategy_returns", rets, window, target, periods, cap, rate)
        same(got, want, f"strategy_returns seed {seed}")
        got, want = both(sol, ref, "drawdowns", want)
        same(got, want, f"drawdowns seed {seed}")


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
