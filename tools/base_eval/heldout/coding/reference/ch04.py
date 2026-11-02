import math


def leverage(returns, window, target_vol, periods_per_year, max_leverage):
    n = len(returns)
    out = [0.0] * n
    for t in range(window, n):
        chunk = returns[t - window:t]
        mean = sum(chunk) / window
        var = sum((x - mean) ** 2 for x in chunk) / (window - 1)
        vol = math.sqrt(var * periods_per_year)
        if vol == 0:
            out[t] = max_leverage
        else:
            out[t] = min(max_leverage, target_vol / vol)
    return out


def strategy_returns(returns, window, target_vol, periods_per_year, max_leverage, financing_rate):
    lev = leverage(returns, window, target_vol, periods_per_year, max_leverage)
    out = []
    for t, r in enumerate(returns):
        borrow = max(0.0, lev[t] - 1) * financing_rate / periods_per_year
        out.append(lev[t] * r - borrow)
    return out


def drawdowns(returns):
    equity = [1.0]
    for r in returns:
        equity.append(equity[-1] * (1 + r))
    peak = equity[0]
    worst = 0.0
    longest = 0
    current = 0
    for value in equity:
        if value >= peak:
            peak = value
            current = 0
        else:
            current += 1
            longest = max(longest, current)
        worst = max(worst, 1 - value / peak)
    return {"equity": equity, "max_drawdown": worst, "longest": longest}
