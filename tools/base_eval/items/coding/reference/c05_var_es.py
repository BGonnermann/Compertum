import math


def var_es(returns, alpha=0.95):
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    losses = sorted((-float(r) for r in returns), reverse=True)
    n = len(losses)
    if n == 0:
        raise ValueError("empty input")
    k = max(1, math.ceil((1 - alpha) * n - 1e-9))
    tail = losses[:k]
    return tail[-1], sum(tail) / k
