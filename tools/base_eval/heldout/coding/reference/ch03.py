import math


def zscores(series, window):
    out = [None] * len(series)
    for t in range(window - 1, len(series)):
        chunk = series[t - window + 1:t + 1]
        mean = sum(chunk) / window
        var = sum((x - mean) ** 2 for x in chunk) / (window - 1)
        if var > 0:
            out[t] = (series[t] - mean) / math.sqrt(var)
    return out


def trade_spread(a, b, hedge, window, entry_z, exit_z, cost):
    spread = [x - hedge * y for x, y in zip(a, b)]
    z = zscores(spread, window)
    n = len(spread)
    positions = [0] * n
    pnl = [0.0] * n
    pos = 0
    for t in range(n):
        if t > 0:
            pnl[t] = pos * (spread[t] - spread[t - 1])
        new = pos
        if z[t] is not None:
            if new == 1 and z[t] >= -exit_z:
                new = 0
            elif new == -1 and z[t] <= exit_z:
                new = 0
            if new == 0:
                if z[t] > entry_z:
                    new = -1
                elif z[t] < -entry_z:
                    new = 1
        pnl[t] -= abs(new - pos) * cost
        pos = new
        positions[t] = pos
    cumulative = []
    total = 0.0
    for x in pnl:
        total += x
        cumulative.append(total)
    return {
        "spread": spread,
        "z": z,
        "positions": positions,
        "pnl": pnl,
        "cumulative": cumulative,
    }
