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

TASK_ID = "ch08"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'def run_portfolio(days, orders, cash, half_spread_bps, commission_bps, borrow_rate):\n    half = half_spread_bps / 10000\n    rate = commission_bps / 10000\n    positions = {}\n    fills = []\n    records = []\n    for t, day in enumerate(days):\n        prices = day["prices"]\n        for order in orders:\n            if order["day"] != t - 1:\n                continue\n            symbol = order["symbol"]\n            qty = order["target"] - positions.get(symbol, 0)\n            if qty == 0:\n                continue\n            base = prices[symbol]["open"]\n            price = base * (1 + half) if qty > 0 else base * (1 - half)\n            commission = abs(qty) * price * rate\n            cash -= qty * price + commission\n            positions[symbol] = positions.get(symbol, 0) + qty\n            fills.append({"day": t, "symbol": symbol, "qty": qty, "price": price, "commission": commission})\n        for symbol, amount in day.get("dividends", {}).items():\n            cash += positions.get(symbol, 0) * amount\n        for symbol, qty in positions.items():\n            if qty < 0:\n                cash -= -qty * prices[symbol]["close"] * borrow_rate / 360\n        value = cash + sum(qty * prices[s]["close"] for s, qty in positions.items())\n        held = {s: q for s, q in positions.items() if q != 0}\n        records.append({"cash": cash, "equity": value, "positions": held})\n    return {"fills": fills, "days": records}\n'


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


DAYS = [
    {"prices": {"A": {"open": 50.0, "close": 51.0}, "B": {"open": 20.0, "close": 19.5}}},
    {"prices": {"A": {"open": 52.0, "close": 53.0}, "B": {"open": 19.0, "close": 18.8}}, "dividends": {"A": 0.5}},
    {"prices": {"A": {"open": 53.5, "close": 52.0}, "B": {"open": 18.5, "close": 18.0}}, "dividends": {"B": 0.2}},
    {"prices": {"A": {"open": 52.5, "close": 54.0}, "B": {"open": 18.2, "close": 18.4}}},
]


def tape(seed, n, symbols):
    rng = random.Random(seed)
    level = {s: rng.uniform(20, 120) for s in symbols}
    days = []
    for _ in range(n):
        prices = {}
        dividends = {}
        for s in symbols:
            start = round(level[s] * (1 + rng.gauss(0, 0.01)), 2)
            level[s] = round(start * (1 + rng.gauss(0, 0.015)), 2)
            prices[s] = {"open": start, "close": level[s]}
            if rng.random() < 0.1:
                dividends[s] = round(level[s] * 0.005, 3)
        day = {"prices": prices}
        if dividends:
            day["dividends"] = dividends
        days.append(day)
    orders = [{"day": rng.randrange(n), "symbol": rng.choice(symbols), "target": rng.choice([-150, -60, -20, 0, 0, 25, 80, 200])} for _ in range(35)]
    return days, orders


def case_fill(sol, ref):
    out = sol.run_portfolio(DAYS, [{"day": 0, "symbol": "A", "target": 100}], 10000.0, 5.0, 10.0, 0.0)
    same(out["fills"], [{"day": 1, "symbol": "A", "qty": 100, "price": 52.026, "commission": 5.2026}], "buy fill")
    same(out["days"][0], {"cash": 10000.0, "equity": 10000.0, "positions": {}}, "day 0 record")
    same(out["days"][1], {"cash": 4842.1974, "equity": 10142.1974, "positions": {"A": 100}}, "dividend on the fill day")


def case_short(sol, ref):
    out = sol.run_portfolio(DAYS, [{"day": 0, "symbol": "B", "target": -200}], 10000.0, 5.0, 10.0, 0.03)
    same(out["fills"][0]["price"], 18.9905, "short sale price")
    cash1 = 10000.0 + 200 * 18.9905 - 200 * 18.9905 * 0.001 - 200 * 18.8 * 0.03 / 360
    same(out["days"][1]["cash"], cash1, "cash after borrow fee")
    cash2 = cash1 - 200 * 0.2 - 200 * 18.0 * 0.03 / 360
    same(out["days"][2]["cash"], cash2, "short pays the dividend")
    same(out["days"][2]["equity"], cash2 - 200 * 18.0, "equity of a short")


def case_targets(sol, ref):
    orders = [{"day": 0, "symbol": "A", "target": 50}, {"day": 0, "symbol": "A", "target": 30}, {"day": 1, "symbol": "A", "target": 30}]
    got, want = both(sol, ref, "run_portfolio", DAYS, orders, 10000.0, 2.0, 1.0, 0.02)
    same([(f["day"], f["qty"]) for f in got["fills"]], [(1, 50), (1, -20)], "targets use the updated position")
    same(got, want, "target orders")


def case_flat(sol, ref):
    orders = [{"day": 0, "symbol": "A", "target": 100}, {"day": 1, "symbol": "A", "target": 0}, {"day": 3, "symbol": "B", "target": 10}]
    out = sol.run_portfolio(DAYS, orders, 10000.0, 0.0, 0.0, 0.0)
    expect(out["days"][2]["positions"] == {} and out["days"][3]["positions"] == {}, f"positions must omit zero holdings, got {brief(out['days'][2]['positions'])}")
    same(len(out["fills"]), 2, "order on the last day is not filled")
    same(out["days"][3]["equity"], 10000.0 - 5200.0 + 50.0 + 5350.0, "equity after a round trip")


def case_borrow(sol, ref):
    orders = [{"day": 0, "symbol": "A", "target": -50}, {"day": 0, "symbol": "B", "target": 120}]
    got, want = both(sol, ref, "run_portfolio", DAYS, orders, 5000.0, 0.0, 0.0, 0.05)
    same(got, want, "borrow fee on the close")


def case_random(sol, ref):
    for seed in (81, 82, 83):
        days, orders = tape(seed, 40, ["X", "Y", "Z"])
        got, want = both(sol, ref, "run_portfolio", days, orders, 25000.0, 3.0, 5.0, 0.04)
        same(got, want, f"run_portfolio seed {seed}")


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
