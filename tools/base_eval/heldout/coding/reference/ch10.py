def run_strategy(bars, strategy, cash, fee_per_share, min_fee, stop_pct):
    position = 0
    stop = None
    pending = None
    last_equity = cash
    equity = []
    fills = []
    for t, bar in enumerate(bars):
        if pending is not None:
            target = int(pending * last_equity / bars[t - 1]["close"])
            qty = target - position
            if qty != 0:
                price = bar["open"]
                cost = max(min_fee, abs(qty) * fee_per_share)
                cash -= qty * price + cost
                fills.append({"bar": t, "qty": qty, "price": price, "fee": cost, "reason": "target"})
                new = position + qty
                if new == 0:
                    stop = None
                elif position == 0 or (new > 0) != (position > 0):
                    if stop_pct is not None:
                        stop = price * (1 - stop_pct) if new > 0 else price * (1 + stop_pct)
                position = new
            pending = None
        if stop is not None and position != 0:
            exit_price = None
            if position > 0 and bar["low"] <= stop:
                exit_price = min(bar["open"], stop)
            elif position < 0 and bar["high"] >= stop:
                exit_price = max(bar["open"], stop)
            if exit_price is not None:
                qty = -position
                cost = max(min_fee, abs(qty) * fee_per_share)
                cash -= qty * exit_price + cost
                fills.append({"bar": t, "qty": qty, "price": exit_price, "fee": cost, "reason": "stop"})
                position = 0
                stop = None
        last_equity = cash + position * bar["close"]
        equity.append(last_equity)
        state = {"cash": cash, "position": position, "equity": last_equity}
        decision = strategy(t, bars[:t + 1], state)
        if decision is not None and t + 1 < len(bars):
            pending = decision
    return {"equity": equity, "fills": fills}
