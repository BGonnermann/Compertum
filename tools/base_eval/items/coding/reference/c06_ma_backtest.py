def ma_backtest(prices, short, long, cost_bps):
    data = [float(p) for p in prices]
    if not data:
        raise ValueError("empty prices")
    if any(p <= 0 for p in data):
        raise ValueError("prices must be positive")
    if short < 1 or long <= short:
        raise ValueError("need 1 <= short < long")
    n = len(data)
    signal = [0] * n
    for t in range(long - 1, n):
        fast = sum(data[t - short + 1:t + 1]) / short
        slow = sum(data[t - long + 1:t + 1]) / long
        signal[t] = 1 if fast > slow else 0
    cost = cost_bps / 10000.0
    equity = [1.0]
    held = 0
    for t in range(1, n):
        pos = signal[t - 1]
        ret = data[t] / data[t - 1] - 1.0
        equity.append(equity[-1] * (1.0 + pos * ret - cost * abs(pos - held)))
        held = pos
    return equity, equity[-1] - 1.0
