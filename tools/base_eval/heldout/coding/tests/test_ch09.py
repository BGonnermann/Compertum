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

TASK_ID = "ch09"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'import math\n\n\ndef execute(bars, orders, cash, participation, spread_bps, impact_bps, fee_bps, min_fee):\n    remaining = {o["id"]: o["qty"] for o in orders}\n    position = 0\n    fills = []\n    equity = []\n    for t, bar in enumerate(bars):\n        volume = bar["volume"]\n        capacity = math.floor(participation * volume) if volume > 0 else 0\n        for o in orders:\n            left = remaining[o["id"]]\n            if o["bar"] >= t or left == 0 or capacity <= 0:\n                continue\n            size = min(abs(left), capacity)\n            sign = 1 if left > 0 else -1\n            bps = spread_bps / 2 + impact_bps * size / volume\n            price = bar["open"] * (1 + sign * bps / 10000)\n            fee = max(min_fee, size * price * fee_bps / 10000)\n            cash -= sign * size * price + fee\n            position += sign * size\n            remaining[o["id"]] = left - sign * size\n            capacity -= size\n            fills.append({"id": o["id"], "bar": t, "qty": sign * size, "price": price, "fee": fee})\n        equity.append(cash + position * bar["close"])\n    return {"fills": fills, "remaining": remaining, "cash": cash, "position": position, "equity": equity}\n'


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
    {"open": 20.0, "close": 20.2, "volume": 1000},
    {"open": 20.5, "close": 20.4, "volume": 2000},
    {"open": 20.3, "close": 20.6, "volume": 0},
    {"open": 20.8, "close": 21.0, "volume": 800},
    {"open": 21.1, "close": 21.3, "volume": 4000},
]


def run(sol, orders, cash=100000.0):
    return sol.execute(BARS, orders, cash, 0.25, 4.0, 20.0, 1.0, 1.0)


def tape(seed, n):
    rng = random.Random(seed)
    bars = []
    close = 30.0
    for _ in range(n):
        start = round(close * (1 + rng.gauss(0, 0.01)), 2)
        close = round(start * (1 + rng.gauss(0, 0.012)), 2)
        volume = 0 if rng.random() < 0.08 else rng.randrange(100, 5000)
        bars.append({"open": start, "close": close, "volume": volume})
    orders = [{"id": f"o{k}", "bar": rng.randrange(n), "qty": rng.choice([-1, 1]) * rng.randrange(50, 3000)} for k in range(15)]
    return bars, orders


def case_carry(sol, ref):
    out = run(sol, [{"id": "a", "bar": 0, "qty": 900}])
    want = [
        {"id": "a", "bar": 1, "qty": 500, "price": 20.5 * 1.0007, "fee": 500 * 20.5 * 1.0007 * 0.0001},
        {"id": "a", "bar": 3, "qty": 200, "price": 20.8 * 1.0007, "fee": 1.0},
        {"id": "a", "bar": 4, "qty": 200, "price": 21.1 * 1.0003, "fee": 1.0},
    ]
    same(out["fills"], want, "partial fills carried across bars")
    same(out["remaining"], {"a": 0}, "remaining")
    same(out["position"], 900, "position")


def case_priority(sol, ref):
    orders = [{"id": "a", "bar": 0, "qty": 400}, {"id": "b", "bar": 0, "qty": -300}]
    out = run(sol, orders)
    same([(f["id"], f["bar"], f["qty"]) for f in out["fills"]], [("a", 1, 400), ("b", 1, -100), ("b", 3, -200)], "capacity shared in list order")
    same(out["fills"][1]["price"], 20.5 * (1 - 0.0002 - 0.002 * 100 / 2000), "sell price")


def case_remaining(sol, ref):
    out = run(sol, [{"id": "big", "bar": 2, "qty": -5000}, {"id": "late", "bar": 4, "qty": 10}])
    same(out["remaining"], {"big": -3800, "late": 10}, "unfilled quantities")
    same([f["qty"] for f in out["fills"]], [-200, -1000], "fill sizes")


def case_equity(sol, ref):
    orders = [{"id": "a", "bar": 0, "qty": 700}, {"id": "b", "bar": 3, "qty": -300}]
    got, want = both(sol, ref, "execute", BARS, orders, 50000.0, 0.25, 4.0, 20.0, 1.0, 1.0)
    same(got["equity"], want["equity"], "equity marks")
    same(got, want, "execute")


def case_submit(sol, ref):
    out = run(sol, [{"id": "x", "bar": 1, "qty": 100}])
    same([(f["bar"], f["qty"]) for f in out["fills"]], [(3, 100)], "no fill on the submission bar or on zero volume")


def case_random(sol, ref):
    for seed, part in ((91, 0.1), (92, 0.25), (93, 0.5)):
        bars, orders = tape(seed, 40)
        got, want = both(sol, ref, "execute", bars, orders, 200000.0, part, 6.0, 30.0, 2.0, 1.5)
        same(got, want, f"execute seed {seed}")


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
