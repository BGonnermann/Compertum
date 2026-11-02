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

TASK_ID = "ch07"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'def fill_price(order, bar):\n    kind = order["type"]\n    side = order["side"]\n    if kind == "market":\n        return bar["open"]\n    level = order["price"]\n    if kind == "limit" and side == "buy":\n        return min(bar["open"], level) if bar["low"] < level else None\n    if kind == "limit":\n        return max(bar["open"], level) if bar["high"] > level else None\n    if side == "buy":\n        return max(bar["open"], level) if bar["high"] >= level else None\n    return min(bar["open"], level) if bar["low"] <= level else None\n\n\ndef simulate(bars, orders, cash, fee):\n    position = 0\n    fills = []\n    equity = []\n    done = set()\n    for t, bar in enumerate(bars):\n        live = [\n            i for i, o in enumerate(orders)\n            if i not in done and o["bar"] < t and (o.get("expire") is None or o["expire"] >= t)\n        ]\n        markets = [i for i in live if orders[i]["type"] == "market"]\n        others = [i for i in live if orders[i]["type"] != "market"]\n        for i in markets + others:\n            if i in done:\n                continue\n            order = orders[i]\n            price = fill_price(order, bar)\n            if price is None:\n                continue\n            qty = order["qty"] if order["side"] == "buy" else -order["qty"]\n            cost = fee * order["qty"]\n            cash -= qty * price + cost\n            position += qty\n            done.add(i)\n            fills.append({"id": order["id"], "bar": t, "side": order["side"], "qty": order["qty"], "price": price, "fee": cost})\n            group = order.get("oco")\n            if group is not None:\n                for j, other in enumerate(orders):\n                    if other.get("oco") == group:\n                        done.add(j)\n        equity.append(cash + position * bar["close"])\n    return {"fills": fills, "equity": equity, "cash": cash, "position": position}\n'


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
    {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"open": 100.5, "high": 102.0, "low": 98.0, "close": 101.0},
    {"open": 99.0, "high": 100.0, "low": 96.0, "close": 97.0},
    {"open": 97.5, "high": 103.0, "low": 97.0, "close": 102.5},
    {"open": 104.0, "high": 105.0, "low": 101.0, "close": 103.0},
]


def order(ident, bar, side, qty, kind, price=None, **extra):
    item = {"id": ident, "bar": bar, "side": side, "qty": qty, "type": kind}
    if price is not None:
        item["price"] = price
    item.update(extra)
    return item


def tape(seed, n):
    rng = random.Random(seed)
    bars = []
    close = 50.0
    for _ in range(n):
        start = round(close * (1 + rng.gauss(0, 0.012)), 2)
        close = round(start * (1 + rng.gauss(0, 0.015)), 2)
        high = round(max(start, close) * (1 + abs(rng.gauss(0, 0.006))), 2)
        low = round(min(start, close) * (1 - abs(rng.gauss(0, 0.006))), 2)
        bars.append({"open": start, "high": high, "low": low, "close": close})
    orders = []
    for k in range(40):
        bar = rng.randrange(n)
        kind = rng.choice(["market", "limit", "stop"])
        side = rng.choice(["buy", "sell"])
        ref_price = bars[bar]["close"]
        price = None if kind == "market" else round(ref_price * (1 + rng.uniform(-0.03, 0.03)), 2)
        extra = {}
        if rng.random() < 0.4:
            extra["expire"] = bar + rng.randrange(1, 6)
        if rng.random() < 0.3:
            extra["oco"] = f"g{rng.randrange(6)}"
        orders.append(order(f"o{k}", bar, side, rng.randrange(1, 50), kind, price, **extra))
    return bars, orders


def case_market(sol, ref):
    out = sol.simulate(BARS, [order("m", 0, "buy", 10, "market")], 2000.0, 0.01)
    same(out["fills"], [{"id": "m", "bar": 1, "side": "buy", "qty": 10, "price": 100.5, "fee": 0.1}], "market fill at the next open")
    same(out["equity"], [2000.0, 2000.0 - 0.1 + 5.0, 2000.0 - 0.1 - 35.0, 2000.0 - 0.1 + 20.0, 2000.0 - 0.1 + 25.0], "equity marks")
    same(out["position"], 10, "final position")
    same(out["cash"], 2000.0 - 1005.0 - 0.1, "final cash")


def case_through(sol, ref):
    out = sol.simulate(BARS, [order("a", 0, "buy", 5, "limit", 98.0)], 1000.0, 0.0)
    same([(f["bar"], f["price"]) for f in out["fills"]], [(2, 98.0)], "buy limit needs a low below the limit")
    out = sol.simulate(BARS, [order("b", 1, "buy", 5, "limit", 100.0)], 1000.0, 0.0)
    same([(f["bar"], f["price"]) for f in out["fills"]], [(2, 99.0)], "buy limit fills at a better open")


def case_gap(sol, ref):
    orders = [order("e", 0, "buy", 10, "market"), order("s", 1, "sell", 10, "stop", 99.5)]
    out = sol.simulate(BARS, orders, 2000.0, 0.0)
    same([(f["id"], f["bar"], f["price"]) for f in out["fills"]], [("e", 1, 100.5), ("s", 2, 99.0)], "sell stop fills at a gap-down open")


def case_buystop(sol, ref):
    orders = [order("x", 2, "buy", 3, "stop", 103.5), order("y", 2, "buy", 4, "stop", 102.5)]
    out = sol.simulate(BARS, orders, 2000.0, 0.02)
    same([(f["id"], f["bar"], f["price"]) for f in out["fills"]], [("y", 3, 102.5), ("x", 4, 104.0)], "buy stop prices")


def case_expire(sol, ref):
    out = sol.simulate(BARS, [order("t", 0, "sell", 2, "limit", 102.5, expire=2)], 1000.0, 0.0)
    same(out["fills"], [], "expired limit order")
    out = sol.simulate(BARS, [order("t", 0, "sell", 2, "limit", 102.5, expire=3)], 1000.0, 0.0)
    same([(f["bar"], f["price"]) for f in out["fills"]], [(3, 102.5)], "limit order fills on its expire bar")


def case_oco(sol, ref):
    orders = [
        order("e", 0, "buy", 10, "market"),
        order("tp", 1, "sell", 10, "limit", 102.5, oco="x"),
        order("sl", 1, "sell", 10, "stop", 97.5, oco="x"),
    ]
    out = sol.simulate(BARS, orders, 2000.0, 0.0)
    same([(f["id"], f["bar"], f["price"]) for f in out["fills"]], [("e", 1, 100.5), ("sl", 2, 97.5)], "one-cancels-other bracket")
    same(out["position"], 0, "flat after the bracket")
    orders = [
        order("e", 1, "sell", 4, "market"),
        order("tp", 2, "buy", 4, "limit", 97.2, oco="y"),
        order("sl", 2, "buy", 4, "stop", 102.8, oco="y"),
    ]
    out = sol.simulate(BARS, orders, 2000.0, 0.0)
    same([(f["id"], f["bar"], f["price"]) for f in out["fills"]], [("e", 2, 99.0), ("tp", 3, 97.2)], "first triggered order in list order wins")


def case_sequence(sol, ref):
    orders = [order("L", 0, "buy", 5, "limit", 101.0), order("M", 0, "sell", 5, "market")]
    out = sol.simulate(BARS, orders, 1000.0, 0.0)
    same([(f["id"], f["price"]) for f in out["fills"]], [("M", 100.5), ("L", 100.5)], "market orders fill before other orders")


def case_submit(sol, ref):
    out = sol.simulate(BARS, [order("n", 1, "buy", 5, "limit", 99.0)], 1000.0, 0.0)
    same([(f["bar"], f["price"]) for f in out["fills"]], [(2, 99.0)], "no fill on the submission bar")


def case_random(sol, ref):
    for seed in (71, 72, 73):
        bars, orders = tape(seed, 50)
        got, want = both(sol, ref, "simulate", bars, orders, 10000.0, 0.005)
        same(got, want, f"simulate seed {seed}")


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
