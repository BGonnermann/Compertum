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

TASK_ID = "ch10"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'def run_strategy(bars, strategy, cash, fee_per_share, min_fee, stop_pct):\n    position = 0\n    stop = None\n    pending = None\n    last_equity = cash\n    equity = []\n    fills = []\n    for t, bar in enumerate(bars):\n        if pending is not None:\n            target = int(pending * last_equity / bars[t - 1]["close"])\n            qty = target - position\n            if qty != 0:\n                price = bar["open"]\n                cost = max(min_fee, abs(qty) * fee_per_share)\n                cash -= qty * price + cost\n                fills.append({"bar": t, "qty": qty, "price": price, "fee": cost, "reason": "target"})\n                new = position + qty\n                if new == 0:\n                    stop = None\n                elif position == 0 or (new > 0) != (position > 0):\n                    if stop_pct is not None:\n                        stop = price * (1 - stop_pct) if new > 0 else price * (1 + stop_pct)\n                position = new\n            pending = None\n        if stop is not None and position != 0:\n            exit_price = None\n            if position > 0 and bar["low"] <= stop:\n                exit_price = min(bar["open"], stop)\n            elif position < 0 and bar["high"] >= stop:\n                exit_price = max(bar["open"], stop)\n            if exit_price is not None:\n                qty = -position\n                cost = max(min_fee, abs(qty) * fee_per_share)\n                cash -= qty * exit_price + cost\n                fills.append({"bar": t, "qty": qty, "price": exit_price, "fee": cost, "reason": "stop"})\n                position = 0\n                stop = None\n        last_equity = cash + position * bar["close"]\n        equity.append(last_equity)\n        state = {"cash": cash, "position": position, "equity": last_equity}\n        decision = strategy(t, bars[:t + 1], state)\n        if decision is not None and t + 1 < len(bars):\n            pending = decision\n    return {"equity": equity, "fills": fills}\n'


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
    {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
    {"open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0},
    {"open": 102.0, "high": 104.0, "low": 95.0, "close": 96.0},
    {"open": 94.0, "high": 97.0, "low": 93.0, "close": 96.5},
    {"open": 97.0, "high": 99.0, "low": 96.0, "close": 98.0},
    {"open": 98.0, "high": 99.0, "low": 97.0, "close": 98.5},
]


def plan(table):
    def decide(t, history, state):
        return table.get(t)
    return decide


def tape(seed, n):
    rng = random.Random(seed)
    bars = []
    close = 60.0
    for _ in range(n):
        start = round(close * (1 + rng.gauss(0, 0.012)), 2)
        close = round(start * (1 + rng.gauss(0, 0.02)), 2)
        high = round(max(start, close) * (1 + abs(rng.gauss(0, 0.008))), 2)
        low = round(min(start, close) * (1 - abs(rng.gauss(0, 0.008))), 2)
        bars.append({"open": start, "high": high, "low": low, "close": close})
    return bars


def signal(t, history, state):
    bar = history[-1]
    if t % 4 == 3:
        return None
    move = (bar["close"] - bar["open"]) / bar["open"]
    return max(-0.9, min(0.9, round(move * 40, 3)))


def case_history(sol, ref):
    seen = []

    def watch(t, history, state):
        seen.append((t, len(history), history[-1] == BARS[t], dict(state)))
        return 0.5 if t == 0 else None

    sol.run_strategy(BARS, watch, 10000.0, 0.01, 1.0, None)
    same([s[0] for s in seen], list(range(6)), "strategy called once per bar")
    expect(all(s[1] == s[0] + 1 for s in seen), "history must hold bars 0..t only")
    expect(all(s[2] for s in seen), "last history bar must be the current bar")
    same(seen[0][3], {"cash": 10000.0, "position": 0, "equity": 10000.0}, "state at bar 0")
    same(seen[1][3], {"cash": 4949.0, "position": 50, "equity": 10049.0}, "state at bar 1")


def case_sizing(sol, ref):
    out = sol.run_strategy(BARS, plan({0: 0.5}), 10000.0, 0.01, 1.0, None)
    same(out["fills"], [{"bar": 1, "qty": 50, "price": 101.0, "fee": 1.0, "reason": "target"}], "target fill at the next open")
    same(out["equity"], [10000.0, 10049.0, 4949.0 + 4800.0, 4949.0 + 4825.0, 4949.0 + 4900.0, 4949.0 + 4925.0], "equity marks")


def case_resize(sol, ref):
    out = sol.run_strategy(BARS, plan({0: 0.5, 1: 0.8, 3: 0.0}), 10000.0, 0.02, 1.0, None)
    same([(f["bar"], f["qty"]) for f in out["fills"]], [(1, 50), (2, 28), (4, -78)], "resizing uses equity and close at the decision bar")


def case_stop(sol, ref):
    out = sol.run_strategy(BARS, plan({1: 1.0}), 10000.0, 0.01, 1.0, 0.05)
    same([(f["bar"], f["qty"], f["price"], f["reason"]) for f in out["fills"]], [(2, 98, 102.0, "target"), (2, -98, 96.9, "stop")], "stop on the entry bar")
    same(out["equity"][-1], 10000.0 - 98 * 102.0 - 1.0 + 98 * 96.9 - 1.0, "equity after the stop")


def case_gap(sol, ref):
    out = sol.run_strategy(BARS, plan({0: 0.5}), 10000.0, 0.01, 1.0, 0.06)
    same([(f["bar"], f["qty"], f["price"]) for f in out["fills"]], [(1, 50, 101.0), (3, -50, 94.0)], "stop fills at a gap-down open")


def case_short(sol, ref):
    out = sol.run_strategy(BARS, plan({2: -0.5}), 10000.0, 0.01, 1.0, 0.03)
    same([(f["bar"], f["qty"], f["price"], f["reason"]) for f in out["fills"]], [(3, -52, 94.0, "target"), (3, 52, 96.82, "stop")], "short entry truncates toward zero and stops out")


def case_flip(sol, ref):
    got, want = both(sol, ref, "run_strategy", BARS, plan({0: 0.5, 1: -0.5}), 10000.0, 0.01, 1.0, 0.1)
    same([(f["bar"], f["qty"], f["reason"]) for f in got["fills"]], [(1, 50, "target"), (2, -99, "target")], "flip re-arms the stop")
    same(got, want, "flip run")


def case_last(sol, ref):
    out = sol.run_strategy(BARS, plan({5: 1.0}), 10000.0, 0.01, 1.0, None)
    same(out["fills"], [], "decision on the last bar is ignored")
    same(out["equity"], [10000.0] * 6, "flat equity")


def case_random(sol, ref):
    for seed, stop in ((101, None), (102, 0.03), (103, 0.015)):
        bars = tape(seed, 60)
        got, want = both(sol, ref, "run_strategy", bars, signal, 50000.0, 0.005, 1.0, stop)
        same(got, want, f"run_strategy seed {seed}")


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
