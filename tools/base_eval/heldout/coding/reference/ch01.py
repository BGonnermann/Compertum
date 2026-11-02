import math


def signals(prices, lookback):
    n = len(prices)
    out = [0] * n
    for t in range(lookback, n):
        diff = prices[t] - prices[t - lookback]
        out[t] = (diff > 0) - (diff < 0)
    return out


def run_backtest(prices, lookback, cost_bps):
    sig = signals(prices, lookback)
    n = len(prices)
    equity = [1.0] * n
    positions = [0] * n
    trades = 0
    prev = 0
    for t in range(1, n):
        pos = sig[t - 1]
        r = prices[t] / prices[t - 1] - 1
        cost = abs(pos - prev) * cost_bps / 10000
        equity[t] = equity[t - 1] * (1 + pos * r - cost)
        positions[t] = pos
        if pos != prev:
            trades += 1
        prev = pos
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return {
        "positions": positions,
        "equity": equity,
        "trades": trades,
        "total_return": equity[-1] - 1,
        "max_drawdown": worst,
    }


def stats(equity, periods_per_year):
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity))]
    m = len(rets)
    mean = sum(rets) / m
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (m - 1))
    sharpe = mean / sd * math.sqrt(periods_per_year) if sd > 0 else 0.0
    return {
        "cagr": (equity[-1] / equity[0]) ** (periods_per_year / m) - 1,
        "vol": sd * math.sqrt(periods_per_year),
        "sharpe": sharpe,
    }
