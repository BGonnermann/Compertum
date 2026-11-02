import importlib
import io
import json
import os
import sys
import threading

TASK = "c10_order_book"
LIMIT = 10.0


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def as_tuples(trades):
    return [tuple(t) for t in trades]


def empty_book(m):
    book = m.OrderBook()
    return book.best_bid() is None and book.best_ask() is None


def resting(m):
    book = m.OrderBook()
    a = as_tuples(book.submit("b1", "buy", 99, 5))
    b = as_tuples(book.submit("s1", "sell", 101, 5))
    return a == [] and b == [] and book.best_bid() == 99 and book.best_ask() == 101


def resting_price(m):
    book = m.OrderBook()
    book.submit("s1", "sell", 100, 5)
    trades = as_tuples(book.submit("b1", "buy", 102, 3))
    return trades == [("b1", "s1", 100, 3)] and book.best_ask() == 100 and book.best_bid() is None


def price_priority(m):
    book = m.OrderBook()
    book.submit("s1", "sell", 101, 2)
    book.submit("s2", "sell", 100, 2)
    trades = as_tuples(book.submit("b1", "buy", 101, 5))
    want = [("b1", "s2", 100, 2), ("b1", "s1", 101, 2)]
    return trades == want and book.best_bid() == 101 and book.best_ask() is None


def time_priority(m):
    book = m.OrderBook()
    book.submit("s1", "sell", 100, 2)
    book.submit("s2", "sell", 100, 2)
    first = as_tuples(book.submit("b1", "buy", 100, 3))
    second = as_tuples(book.submit("b2", "buy", 100, 1))
    return (first == [("b1", "s1", 100, 2), ("b1", "s2", 100, 1)]
            and second == [("b2", "s2", 100, 1)]
            and book.best_ask() is None and book.best_bid() is None)


def partial_queue(m):
    book = m.OrderBook()
    book.submit("s1", "sell", 100, 5)
    book.submit("s2", "sell", 100, 5)
    book.submit("b1", "buy", 100, 2)
    trades = as_tuples(book.submit("b2", "buy", 100, 4))
    return trades == [("b2", "s1", 100, 3), ("b2", "s2", 100, 1)] and book.best_ask() == 100


def sell_side(m):
    book = m.OrderBook()
    book.submit("b1", "buy", 99, 1)
    book.submit("b2", "buy", 100, 1)
    trades = as_tuples(book.submit("s1", "sell", 98, 3))
    want = [("b2", "s1", 100, 1), ("b1", "s1", 99, 1)]
    return trades == want and book.best_ask() == 98 and book.best_bid() is None


def no_cross(m):
    book = m.OrderBook()
    book.submit("s1", "sell", 101, 5)
    trades = as_tuples(book.submit("b1", "buy", 100, 50))
    return trades == [] and book.best_bid() == 100 and book.best_ask() == 101


def exact_fill(m):
    book = m.OrderBook()
    book.submit("s1", "sell", 100, 5)
    trades = as_tuples(book.submit("b1", "buy", 100, 5))
    return trades == [("b1", "s1", 100, 5)] and book.best_bid() is None and book.best_ask() is None


def cancel_order(m):
    book = m.OrderBook()
    book.submit("s1", "sell", 100, 1)
    book.submit("s2", "sell", 100, 1)
    book.submit("s3", "sell", 102, 1)
    first = book.cancel("s1")
    trades = as_tuples(book.submit("b1", "buy", 100, 1))
    again = book.cancel("s1")
    unknown = book.cancel("zzz")
    gone = book.cancel("s3")
    return (first is True and trades == [("b1", "s2", 100, 1)] and again is False
            and unknown is False and gone is True and book.best_ask() is None)


def bad_input(m):
    book = m.OrderBook()
    return (raises(lambda: book.submit("x1", "hold", 100, 1))
            and raises(lambda: book.submit("x2", "buy", 100, 0))
            and raises(lambda: book.submit("x3", "sell", 0, 1)))


CHECKS = [
    ("empty book", empty_book),
    ("resting", resting),
    ("resting price", resting_price),
    ("price priority", price_priority),
    ("time priority", time_priority),
    ("partial queue", partial_queue),
    ("sell side", sell_side),
    ("no cross", no_cross),
    ("exact fill", exact_fill),
    ("cancel", cancel_order),
    ("bad input", bad_input),
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
