import math


def affordable(cash, price, commission, min_commission, limit):
    best = min(limit, max(0, math.floor(cash / price)))
    while best > 0 and best * price + max(min_commission, best * commission) > cash:
        best -= 1
    return best


def run_backtest(bars, orders, cash, commission, min_commission, slippage_bps, max_position):
    queue = {}
    for order in orders:
        queue.setdefault(order["bar"] + 1, []).append(order["qty"])
    slip = slippage_bps / 10000
    position = 0
    fills = []
    daily = []
    for t, bar in enumerate(bars):
        for qty in queue.get(t, []):
            if position + qty > max_position:
                qty = max_position - position
            elif position + qty < -max_position:
                qty = -max_position - position
            if qty == 0:
                continue
            price = bar["open"] * (1 + slip) if qty > 0 else bar["open"] * (1 - slip)
            fee = max(min_commission, abs(qty) * commission)
            if qty > 0 and qty * price + fee > cash:
                qty = affordable(cash, price, commission, min_commission, qty)
                if qty == 0:
                    continue
                fee = max(min_commission, qty * commission)
            cash -= qty * price + fee
            position += qty
            fills.append({"bar": t, "qty": qty, "price": price, "commission": fee})
        daily.append({"bar": t, "cash": cash, "position": position, "equity": cash + position * bar["close"]})
    return {"fills": fills, "daily": daily}
