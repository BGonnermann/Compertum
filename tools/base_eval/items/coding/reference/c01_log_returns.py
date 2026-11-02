import math


def log_returns(prices):
    values = [float(p) for p in prices]
    if any(v <= 0 for v in values):
        raise ValueError("prices must be positive")
    return [math.log(b / a) for a, b in zip(values, values[1:])]
