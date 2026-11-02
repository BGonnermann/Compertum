def run_ledger(prices, targets, cash, commission_rate):
    position = 0
    avg_cost = 0.0
    realized = 0.0
    fees = 0.0
    rows = []
    for t, price in enumerate(prices):
        qty = targets[t] - position
        if qty != 0:
            fee = abs(qty) * price * commission_rate
            cash -= qty * price + fee
            fees += fee
            new = position + qty
            if position == 0 or (position > 0) == (qty > 0):
                avg_cost = (avg_cost * abs(position) + price * abs(qty)) / abs(new)
            else:
                closed = min(abs(qty), abs(position))
                sign = 1 if position > 0 else -1
                realized += (price - avg_cost) * closed * sign
                if new == 0:
                    avg_cost = 0.0
                elif (new > 0) != (position > 0):
                    avg_cost = price
            position = new
        rows.append({
            "cash": cash,
            "position": position,
            "avg_cost": avg_cost,
            "realized": realized,
            "unrealized": (price - avg_cost) * position,
            "fees": fees,
            "equity": cash + position * price,
        })
    return rows


def summary(rows, prices):
    trades = 0
    turnover = 0.0
    previous = 0
    for row, price in zip(rows, prices):
        qty = row["position"] - previous
        if qty != 0:
            trades += 1
            turnover += abs(qty) * price
        previous = row["position"]
    return {
        "final_equity": rows[-1]["equity"],
        "total_fees": rows[-1]["fees"],
        "trades": trades,
        "turnover": turnover,
    }
