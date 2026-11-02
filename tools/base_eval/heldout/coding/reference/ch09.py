import math


def execute(bars, orders, cash, participation, spread_bps, impact_bps, fee_bps, min_fee):
    remaining = {o["id"]: o["qty"] for o in orders}
    position = 0
    fills = []
    equity = []
    for t, bar in enumerate(bars):
        volume = bar["volume"]
        capacity = math.floor(participation * volume) if volume > 0 else 0
        for o in orders:
            left = remaining[o["id"]]
            if o["bar"] >= t or left == 0 or capacity <= 0:
                continue
            size = min(abs(left), capacity)
            sign = 1 if left > 0 else -1
            bps = spread_bps / 2 + impact_bps * size / volume
            price = bar["open"] * (1 + sign * bps / 10000)
            fee = max(min_fee, size * price * fee_bps / 10000)
            cash -= sign * size * price + fee
            position += sign * size
            remaining[o["id"]] = left - sign * size
            capacity -= size
            fills.append({"id": o["id"], "bar": t, "qty": sign * size, "price": price, "fee": fee})
        equity.append(cash + position * bar["close"])
    return {"fills": fills, "remaining": remaining, "cash": cash, "position": position, "equity": equity}
