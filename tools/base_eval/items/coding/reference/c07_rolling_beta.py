def rolling_beta(asset, market, window):
    if len(asset) != len(market):
        raise ValueError("length mismatch")
    if window < 2:
        raise ValueError("window must be at least 2")
    n = len(asset)
    out = [None] * n
    for t in range(window - 1, n):
        a = [float(x) for x in asset[t - window + 1:t + 1]]
        m = [float(x) for x in market[t - window + 1:t + 1]]
        mean_a = sum(a) / window
        mean_m = sum(m) / window
        cov = sum((x - mean_a) * (y - mean_m) for x, y in zip(a, m)) / (window - 1)
        var = sum((y - mean_m) ** 2 for y in m) / (window - 1)
        out[t] = None if var == 0.0 else cov / var
    return out
