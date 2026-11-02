def max_drawdown(values):
    data = [float(v) for v in values]
    if not data:
        raise ValueError("empty input")
    if any(v <= 0 for v in data):
        raise ValueError("values must be positive")
    peak_value = data[0]
    peak_index = 0
    best = 0.0
    best_peak = 0
    best_trough = 0
    for i, v in enumerate(data):
        if v > peak_value:
            peak_value = v
            peak_index = i
        drawdown = 1.0 - v / peak_value
        if drawdown > best:
            best = drawdown
            best_peak = peak_index
            best_trough = i
    return best, best_peak, best_trough
