import math


def asset_returns(closes, dividends):
    return [(closes[t] + dividends[t]) / closes[t - 1] - 1 for t in range(1, len(closes))]


def portfolio_returns(closes, dividends, weights, cost_bps):
    symbols = sorted(weights)
    rets = {s: asset_returns(closes[s], dividends[s]) for s in symbols}
    rate = cost_bps / 10000
    steps = len(closes[symbols[0]]) - 1
    equity = 1.0 - rate * sum(abs(weights[s]) for s in symbols)
    previous = 1.0
    out = []
    for t in range(steps):
        gross = sum(weights[s] * rets[s][t] for s in symbols)
        value = equity * (1 + gross)
        turnover = 0.0
        for s in symbols:
            drifted = weights[s] * (1 + rets[s][t]) / (1 + gross)
            turnover += abs(weights[s] - drifted)
        value -= value * turnover * rate
        out.append(value / previous - 1)
        previous = value
        equity = value
    return out


def summary(net_returns, periods_per_year):
    m = len(net_returns)
    equity = [1.0]
    for r in net_returns:
        equity.append(equity[-1] * (1 + r))
    mean = sum(net_returns) / m
    sd = math.sqrt(sum((r - mean) ** 2 for r in net_returns) / (m - 1))
    sharpe = mean / sd * math.sqrt(periods_per_year) if sd > 0 else 0.0
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return {
        "total_return": equity[-1] - 1,
        "cagr": equity[-1] ** (periods_per_year / m) - 1,
        "vol": sd * math.sqrt(periods_per_year),
        "sharpe": sharpe,
        "max_drawdown": worst,
    }
