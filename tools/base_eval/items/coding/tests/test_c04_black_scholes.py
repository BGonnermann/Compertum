import importlib
import io
import json
import math
import os
import sys
import threading

TASK = "c04_black_scholes"
LIMIT = 10.0

ATM = (100, 100, 1.0, 0.05, 0.2)
HULL = (42, 40, 0.5, 0.1, 0.2)
OTM = (50, 60, 0.5, 0.03, 0.35)


def near(got, want, rel=1e-6, tol=1e-9):
    return math.isclose(float(got), float(want), rel_tol=rel, abs_tol=tol)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def parity(m):
    s, k, t, r, sigma = OTM
    call = m.bs_price(s, k, t, r, sigma, "call")
    put = m.bs_price(s, k, t, r, sigma, "put")
    return near(call, 1.9928527569834316) and near(call - put, s - k * math.exp(-r * t))


def delta_gap(m):
    call = m.bs_delta(*OTM, "call")
    put = m.bs_delta(*OTM, "put")
    return near(call, 0.29035857177697644) and near(call - put, 1.0)


CHECKS = [
    ("atm call", lambda m: near(m.bs_price(*ATM, "call"), 10.450583572185565)),
    ("atm put", lambda m: near(m.bs_price(*ATM, "put"), 5.573526022256971)),
    ("atm call delta", lambda m: near(m.bs_delta(*ATM, "call"), 0.6368306511756191)),
    ("atm put delta", lambda m: near(m.bs_delta(*ATM, "put"), -0.3631693488243809)),
    ("hull call", lambda m: near(m.bs_price(*HULL, "call"), 4.759422392871528)),
    ("hull put", lambda m: near(m.bs_price(*HULL, "put"), 0.8085993729000958)),
    ("parity", parity),
    ("delta gap", delta_gap),
    ("bad kind", lambda m: raises(lambda: m.bs_price(*ATM, "straddle")) and raises(lambda: m.bs_delta(*ATM, "straddle"))),
    ("zero sigma", lambda m: raises(lambda: m.bs_price(100, 100, 1.0, 0.05, 0.0, "call"))),
    ("zero time", lambda m: raises(lambda: m.bs_price(100, 100, 0.0, 0.05, 0.2, "put"))),
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
