import math


def sharpe_ratio(returns, risk_free=0.0, periods_per_year=252):
    excess = [float(r) - risk_free for r in returns]
    n = len(excess)
    if n < 2:
        raise ValueError("need at least 2 returns")
    mean = sum(excess) / n
    var = sum((x - mean) ** 2 for x in excess) / (n - 1)
    if var == 0.0:
        raise ValueError("zero standard deviation")
    return mean / math.sqrt(var) * math.sqrt(periods_per_year)
