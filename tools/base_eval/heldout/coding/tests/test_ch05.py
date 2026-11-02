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

TASK_ID = "ch05"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'def run_ledger(prices, targets, cash, commission_rate):\n    position = 0\n    avg_cost = 0.0\n    realized = 0.0\n    fees = 0.0\n    rows = []\n    for t, price in enumerate(prices):\n        qty = targets[t] - position\n        if qty != 0:\n            fee = abs(qty) * price * commission_rate\n            cash -= qty * price + fee\n            fees += fee\n            new = position + qty\n            if position == 0 or (position > 0) == (qty > 0):\n                avg_cost = (avg_cost * abs(position) + price * abs(qty)) / abs(new)\n            else:\n                closed = min(abs(qty), abs(position))\n                sign = 1 if position > 0 else -1\n                realized += (price - avg_cost) * closed * sign\n                if new == 0:\n                    avg_cost = 0.0\n                elif (new > 0) != (position > 0):\n                    avg_cost = price\n            position = new\n        rows.append({\n            "cash": cash,\n            "position": position,\n            "avg_cost": avg_cost,\n            "realized": realized,\n            "unrealized": (price - avg_cost) * position,\n            "fees": fees,\n            "equity": cash + position * price,\n        })\n    return rows\n\n\ndef summary(rows, prices):\n    trades = 0\n    turnover = 0.0\n    previous = 0\n    for row, price in zip(rows, prices):\n        qty = row["position"] - previous\n        if qty != 0:\n            trades += 1\n            turnover += abs(qty) * price\n        previous = row["position"]\n    return {\n        "final_equity": rows[-1]["equity"],\n        "total_fees": rows[-1]["fees"],\n        "trades": trades,\n        "turnover": turnover,\n    }\n'


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


def tape(seed, n):
    rng = random.Random(seed)
    prices = [100.0]
    targets = [0]
    for _ in range(n - 1):
        prices.append(round(prices[-1] * (1 + rng.gauss(0, 0.02)), 2))
        targets.append(targets[-1] if rng.random() < 0.4 else rng.choice([-30, -20, -10, -5, 0, 5, 10, 15, 25, 40]))
    return prices, targets


def case_long(sol, ref):
    rows = sol.run_ledger([100.0, 110.0], [10, 0], 1000.0, 0.0)
    same(rows[0], {"cash": 0.0, "position": 10, "avg_cost": 100.0, "realized": 0.0, "unrealized": 0.0, "fees": 0.0, "equity": 1000.0}, "row after buying")
    same(rows[1], {"cash": 1100.0, "position": 0, "avg_cost": 0.0, "realized": 100.0, "unrealized": 0.0, "fees": 0.0, "equity": 1100.0}, "row after selling")


def case_short(sol, ref):
    rows = sol.run_ledger([100.0, 95.0, 90.0], [-10, -10, 0], 1000.0, 0.0)
    same(rows[1]["unrealized"], 50.0, "unrealized on a short")
    same(rows[2]["realized"], 100.0, "realized on a short")
    same(rows[2]["cash"], 1100.0, "cash after covering")


def case_cross(sol, ref):
    rows = sol.run_ledger([100.0, 120.0, 110.0, 100.0], [10, -5, -5, 0], 0.0, 0.0)
    same(rows[1]["realized"], 200.0, "realized when crossing zero")
    same(rows[1]["avg_cost"], 120.0, "avg_cost of the new short")
    same(rows[2]["unrealized"], 50.0, "unrealized on the new short")
    same(rows[3]["realized"], 300.0, "realized after covering")


def case_fees(sol, ref):
    rows = sol.run_ledger([50.0, 52.0, 51.0], [100, 40, 0], 10000.0, 0.001)
    same([r["fees"] for r in rows], [5.0, 8.12, 10.16], "cumulative fees")
    same(rows[2]["cash"], 10000.0 - 5000.0 + 3120.0 + 2040.0 - 10.16, "cash after fees")


def case_average(sol, ref):
    rows = sol.run_ledger([10.0, 12.0, 11.0, 13.0], [100, 300, 150, 150], 5000.0, 0.0)
    same(rows[1]["avg_cost"], (1000.0 + 2400.0) / 300, "weighted avg_cost")
    same(rows[2]["avg_cost"], (1000.0 + 2400.0) / 300, "avg_cost unchanged after a partial sale")
    same(rows[2]["realized"], (11.0 - 3400.0 / 300) * 150, "realized on a partial sale")
    same(rows[3]["unrealized"], (13.0 - 3400.0 / 300) * 150, "unrealized")


def case_idle(sol, ref):
    rows = sol.run_ledger([10.0, 11.0, 12.0], [0, 0, 0], 500.0, 0.01)
    same([r["equity"] for r in rows], [500.0, 500.0, 500.0], "equity without trades")
    same(sol.summary(rows, [10.0, 11.0, 12.0]), {"final_equity": 500.0, "total_fees": 0.0, "trades": 0, "turnover": 0.0}, "summary without trades")


def case_summary(sol, ref):
    prices, targets = tape(41, 40)
    rows = ref["run_ledger"](prices, targets, 5000.0, 0.0005)
    got, want = both(sol, ref, "summary", rows, prices)
    same(got, want, "summary of a ledger")


def case_random(sol, ref):
    for seed, rate in ((42, 0.0), (43, 0.001), (44, 0.0025)):
        prices, targets = tape(seed, 80)
        got, want = both(sol, ref, "run_ledger", prices, targets, 10000.0, rate)
        same(got, want, f"run_ledger seed {seed}")


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
