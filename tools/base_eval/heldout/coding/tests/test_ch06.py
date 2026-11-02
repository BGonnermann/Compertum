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

TASK_ID = "ch06"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'import math\n\n\ndef affordable(cash, price, commission, min_commission, limit):\n    best = min(limit, max(0, math.floor(cash / price)))\n    while best > 0 and best * price + max(min_commission, best * commission) > cash:\n        best -= 1\n    return best\n\n\ndef run_backtest(bars, orders, cash, commission, min_commission, slippage_bps, max_position):\n    queue = {}\n    for order in orders:\n        queue.setdefault(order["bar"] + 1, []).append(order["qty"])\n    slip = slippage_bps / 10000\n    position = 0\n    fills = []\n    daily = []\n    for t, bar in enumerate(bars):\n        for qty in queue.get(t, []):\n            if position + qty > max_position:\n                qty = max_position - position\n            elif position + qty < -max_position:\n                qty = -max_position - position\n            if qty == 0:\n                continue\n            price = bar["open"] * (1 + slip) if qty > 0 else bar["open"] * (1 - slip)\n            fee = max(min_commission, abs(qty) * commission)\n            if qty > 0 and qty * price + fee > cash:\n                qty = affordable(cash, price, commission, min_commission, qty)\n                if qty == 0:\n                    continue\n                fee = max(min_commission, qty * commission)\n            cash -= qty * price + fee\n            position += qty\n            fills.append({"bar": t, "qty": qty, "price": price, "commission": fee})\n        daily.append({"bar": t, "cash": cash, "position": position, "equity": cash + position * bar["close"]})\n    return {"fills": fills, "daily": daily}\n'


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


BARS = [
    {"open": 10.0, "high": 10.8, "low": 9.7, "close": 10.5},
    {"open": 11.0, "high": 11.6, "low": 10.9, "close": 11.2},
    {"open": 11.5, "high": 11.9, "low": 10.8, "close": 11.0},
    {"open": 12.0, "high": 12.6, "low": 11.8, "close": 12.4},
]


def tape(seed, n):
    rng = random.Random(seed)
    bars = []
    close = 40.0
    for _ in range(n):
        start = round(close * (1 + rng.gauss(0, 0.01)), 2)
        close = round(start * (1 + rng.gauss(0, 0.015)), 2)
        bars.append({"open": start, "high": max(start, close) + 0.3, "low": min(start, close) - 0.3, "close": close})
    orders = [{"bar": rng.randrange(n), "qty": rng.choice([-1, 1]) * rng.randrange(1, 300)} for _ in range(30)]
    return bars, orders


def case_nextopen(sol, ref):
    out = sol.run_backtest(BARS, [{"bar": 0, "qty": 50}], 10000.0, 0.01, 1.0, 10.0, 1000)
    same(out["fills"], [{"bar": 1, "qty": 50, "price": 11.011, "commission": 1.0}], "fill at the next open with slippage and minimum commission")
    same(out["daily"][0], {"bar": 0, "cash": 10000.0, "position": 0, "equity": 10000.0}, "bar 0 record")
    same(out["daily"][1], {"bar": 1, "cash": 9448.45, "position": 50, "equity": 9448.45 + 50 * 11.2}, "bar 1 record")


def case_last(sol, ref):
    out = sol.run_backtest(BARS, [{"bar": 3, "qty": 10}], 1000.0, 0.01, 1.0, 0.0, 100)
    same(out["fills"], [], "order on the last bar is not filled")
    same([d["equity"] for d in out["daily"]], [1000.0] * 4, "equity without fills")


def case_commission(sol, ref):
    out = sol.run_backtest(BARS, [{"bar": 1, "qty": 500}], 100000.0, 0.01, 1.0, 0.0, 1000)
    same(out["fills"], [{"bar": 2, "qty": 500, "price": 11.5, "commission": 5.0}], "per-share commission above the minimum")


def case_sell(sol, ref):
    out = sol.run_backtest(BARS, [{"bar": 0, "qty": -40}], 1000.0, 0.01, 1.0, 10.0, 100)
    same(out["fills"], [{"bar": 1, "qty": -40, "price": 10.989, "commission": 1.0}], "short sale fill")
    same(out["daily"][3]["equity"], 1000.0 + 40 * 10.989 - 1.0 - 40 * 12.4, "equity of a short")


def case_limits(sol, ref):
    orders = [{"bar": 0, "qty": 80}, {"bar": 0, "qty": 50}, {"bar": 1, "qty": -300}, {"bar": 1, "qty": -10}]
    got, want = both(sol, ref, "run_backtest", BARS, orders, 100000.0, 0.01, 1.0, 0.0, 100)
    same([f["qty"] for f in got["fills"]], [80, 20, -200], "quantities clipped to the position limit")
    same(got, want, "position limit run")


def case_cash(sol, ref):
    out = sol.run_backtest(BARS, [{"bar": 0, "qty": 200}], 1000.0, 0.01, 1.0, 10.0, 1000)
    same([f["qty"] for f in out["fills"]], [90], "buy reduced to the affordable quantity")
    same(out["daily"][1]["cash"], 1000.0 - 90 * 11.011 - 1.0, "cash after a reduced buy")


def case_feecash(sol, ref):
    out = sol.run_backtest(BARS, [{"bar": 0, "qty": 90}], 991.5, 0.01, 1.0, 10.0, 1000)
    same([f["qty"] for f in out["fills"]], [89], "commission counts in the cash check")
    out = sol.run_backtest(BARS, [{"bar": 0, "qty": 5}], 0.5, 0.01, 1.0, 0.0, 1000)
    same(out["fills"], [], "no fill when nothing is affordable")


def case_order(sol, ref):
    orders = [{"bar": 2, "qty": -30}, {"bar": 0, "qty": 20}, {"bar": 0, "qty": -5}]
    got, want = both(sol, ref, "run_backtest", BARS, orders, 5000.0, 0.02, 2.0, 5.0, 1000)
    same([(f["bar"], f["qty"]) for f in got["fills"]], [(1, 20), (1, -5), (3, -30)], "fill order")
    same(got, want, "unsorted orders")


def case_random(sol, ref):
    for seed, cash in ((61, 20000.0), (62, 3000.0), (63, 50000.0)):
        bars, orders = tape(seed, 60)
        got, want = both(sol, ref, "run_backtest", bars, orders, cash, 0.005, 1.5, 5.0, 400)
        same(got, want, f"run_backtest seed {seed}")


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
