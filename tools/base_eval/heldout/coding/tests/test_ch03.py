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

TASK_ID = "ch03"
LIMIT = 10.0
REL_TOL = 1e-9
ABS_TOL = 1e-6
ORACLE = 'import math\n\n\ndef zscores(series, window):\n    out = [None] * len(series)\n    for t in range(window - 1, len(series)):\n        chunk = series[t - window + 1:t + 1]\n        mean = sum(chunk) / window\n        var = sum((x - mean) ** 2 for x in chunk) / (window - 1)\n        if var > 0:\n            out[t] = (series[t] - mean) / math.sqrt(var)\n    return out\n\n\ndef trade_spread(a, b, hedge, window, entry_z, exit_z, cost):\n    spread = [x - hedge * y for x, y in zip(a, b)]\n    z = zscores(spread, window)\n    n = len(spread)\n    positions = [0] * n\n    pnl = [0.0] * n\n    pos = 0\n    for t in range(n):\n        if t > 0:\n            pnl[t] = pos * (spread[t] - spread[t - 1])\n        new = pos\n        if z[t] is not None:\n            if new == 1 and z[t] >= -exit_z:\n                new = 0\n            elif new == -1 and z[t] <= exit_z:\n                new = 0\n            if new == 0:\n                if z[t] > entry_z:\n                    new = -1\n                elif z[t] < -entry_z:\n                    new = 1\n        pnl[t] -= abs(new - pos) * cost\n        pos = new\n        positions[t] = pos\n    cumulative = []\n    total = 0.0\n    for x in pnl:\n        total += x\n        cumulative.append(total)\n    return {\n        "spread": spread,\n        "z": z,\n        "positions": positions,\n        "pnl": pnl,\n        "cumulative": cumulative,\n    }\n'


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


def pair(seed, n):
    rng = random.Random(seed)
    b = [50.0]
    noise = 0.0
    for _ in range(n - 1):
        b.append(round(b[-1] * (1 + rng.gauss(0, 0.01)), 4))
    a = []
    for x in b:
        noise = 0.6 * noise + rng.gauss(0, 0.8)
        a.append(round(1.5 * x + 10 + noise, 4))
    return a, b


def case_window(sol, ref):
    series = [1.0, 2.0, 4.0, 7.0, 11.0, 16.0]
    got = sol.zscores(list(series), 3)
    same(got[:2], [None, None], "first window - 1 values are None")
    same(got[2], (4.0 - 7.0 / 3.0) / math.sqrt(7.0 / 3.0), "z at the first full window")
    got, want = both(sol, ref, "zscores", series, 4)
    same(got, want, "zscores window 4")


def case_flat(sol, ref):
    got = sol.zscores([5.0, 5.0, 5.0, 6.0], 3)
    same(got, [None, None, None, (6.0 - 16.0 / 3.0) / math.sqrt(1.0 / 3.0)], "zero variance gives None")


def case_long(sol, ref):
    a = [10.0, 10.5, 10.2, 10.4, 8.0, 8.5, 9.6, 10.1, 10.3]
    b = [0.0] * len(a)
    got, want = both(sol, ref, "trade_spread", a, b, 2.0, 4, 1.2, 0.3, 0.0)
    expect(1 in want["positions"], "test design: long position expected")
    same(got, want, "long trade")


def case_short(sol, ref):
    a = [10.0, 10.2, 10.1, 10.3, 12.5, 11.0, 10.2, 10.0, 9.9]
    b = [0.0] * len(a)
    got, want = both(sol, ref, "trade_spread", a, b, 1.0, 4, 1.2, 0.3, 0.0)
    expect(-1 in want["positions"] and 1 not in want["positions"], "test design: short only")
    same(got["positions"], want["positions"], "short positions")
    same(got["pnl"], want["pnl"], "short pnl")


def case_flip(sol, ref):
    a = [10.0, 10.5, 10.2, 10.4, 8.0, 13.0, 11.0, 10.0, 10.5]
    b = [0.0] * len(a)
    got, want = both(sol, ref, "trade_spread", a, b, 0.0, 4, 1.2, 0.3, 0.0)
    expect(want["positions"][4] == 1 and want["positions"][5] == -1, "test design: flip expected")
    same(got["positions"], want["positions"], "flip from long to short on one bar")


def case_costs(sol, ref):
    a = [10.0, 10.5, 10.2, 10.4, 8.0, 13.0, 11.0, 10.0, 10.5]
    b = [1.0] * len(a)
    got, want = both(sol, ref, "trade_spread", a, b, 0.5, 4, 1.2, 0.3, 0.05)
    same(got, want, "costs on position changes")


def case_hedge(sol, ref):
    a, b = pair(21, 80)
    got, want = both(sol, ref, "trade_spread", a, b, 1.5, 10, 1.0, 0.25, 0.02)
    same(got["spread"], want["spread"], "spread with hedge 1.5")
    same(got["z"], want["z"], "z with hedge 1.5")


def case_random(sol, ref):
    for seed, window, entry, leave, cost in ((22, 8, 1.0, 0.2, 0.01), (23, 15, 1.5, 0.0, 0.0), (24, 5, 0.8, 0.5, 0.03)):
        a, b = pair(seed, 150)
        got, want = both(sol, ref, "trade_spread", a, b, 1.5, window, entry, leave, cost)
        same(got, want, f"trade_spread seed {seed}")


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
