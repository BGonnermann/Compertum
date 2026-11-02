import importlib
import io
import json
import math
import os
import sys
import threading

TASK = "c08_bond_duration"
LIMIT = 10.0


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def annuity(face, coupon_rate, ytm, years, freq):
    n = round(years * freq)
    c = face * coupon_rate / freq
    y = ytm / freq
    if y == 0:
        return c * n + face
    return c * (1 - (1 + y) ** -n) / y + face * (1 + y) ** -n


def durations(face, coupon_rate, ytm, years, freq):
    n = round(years * freq)
    c = face * coupon_rate / freq
    y = ytm / freq
    flows = [c] * n
    flows[-1] += face
    weights = [f * (1 + y) ** -(i + 1) for i, f in enumerate(flows)]
    mac = sum((i + 1) * w for i, w in enumerate(weights)) / sum(weights) / freq
    return mac, mac / (1 + y)


def pair(got, want):
    mac, mod = got
    return near(mac, want[0]) and near(mod, want[1])


CASE = (1000, 0.06, 0.08, 5, 2)
MONTHLY = (1000, 0.06, 0.07, 30, 12)


def zero_coupon(m):
    price = m.bond_price(1000, 0.0, 0.08, 5, 2)
    mac, mod = m.bond_duration(1000, 0.0, 0.08, 5, 2)
    return near(price, 1000 / 1.04 ** 10) and near(mac, 5.0) and near(mod, 5.0 / 1.04)


def zero_yield(m):
    price = m.bond_price(100, 0.04, 0.0, 3, 1)
    mac, mod = m.bond_duration(100, 0.04, 0.0, 3, 1)
    return near(price, 112.0) and near(mac, 324 / 112) and near(mod, 324 / 112)


CHECKS = [
    ("par price", lambda m: near(m.bond_price(100, 0.05, 0.05, 10, 2), 100.0)),
    ("par duration", lambda m: pair(m.bond_duration(100, 0.05, 0.05, 10, 2), durations(100, 0.05, 0.05, 10, 2))),
    ("zero coupon", zero_coupon),
    ("discount price", lambda m: near(m.bond_price(*CASE), annuity(*CASE))),
    ("discount duration", lambda m: pair(m.bond_duration(*CASE), durations(*CASE))),
    ("annual", lambda m: near(m.bond_price(100, 0.07, 0.05, 3, 1), 7 / 1.05 + 7 / 1.05 ** 2 + 107 / 1.05 ** 3) and pair(m.bond_duration(100, 0.07, 0.05, 3, 1), durations(100, 0.07, 0.05, 3, 1))),
    ("zero yield", zero_yield),
    ("monthly", lambda m: near(m.bond_price(*MONTHLY), annuity(*MONTHLY)) and pair(m.bond_duration(*MONTHLY), durations(*MONTHLY))),
    ("half year", lambda m: near(m.bond_price(100, 0.04, 0.06, 2.5, 2), annuity(100, 0.04, 0.06, 2.5, 2))),
    ("bad periods", lambda m: raises(lambda: m.bond_price(100, 0.05, 0.05, 2.25, 2)) and raises(lambda: m.bond_duration(100, 0.05, 0.05, 2.25, 2))),
    ("bad freq", lambda m: raises(lambda: m.bond_price(100, 0.05, 0.05, 2, 0))),
]


def run_one(target):
    box = {}

    def body():
        try:
            box["value"] = target()
        except BaseException as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=body, daemon=True)
    worker.start()
    worker.join(LIMIT)
    if worker.is_alive():
        return None, "timeout"
    return box.get("value"), box.get("error")


def main():
    real = sys.stdout
    sys.stdout = io.StringIO()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    failures = []
    passed = 0
    module, error = run_one(lambda: importlib.import_module("solution"))
    if error:
        failures.append(f"import: {error}"[:200])
    else:
        for name, check in CHECKS:
            ok, error = run_one(lambda c=check: c(module))
            if error is None and ok is True:
                passed += 1
            else:
                failures.append(f"{name}: {error or 'wrong result'}"[:200])
    line = {"id": TASK, "passed": passed, "total": len(CHECKS), "failures": failures}
    real.write(json.dumps(line) + "\n")
    real.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
