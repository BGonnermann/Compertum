def run_portfolio(days, orders, cash, half_spread_bps, commission_bps, borrow_rate):
    half = half_spread_bps / 10000
    rate = commission_bps / 10000
    positions = {}
    fills = []
    records = []
    for t, day in enumerate(days):
        prices = day["prices"]
        for order in orders:
            if order["day"] != t - 1:
                continue
            symbol = order["symbol"]
            qty = order["target"] - positions.get(symbol, 0)
            if qty == 0:
                continue
            base = prices[symbol]["open"]
            price = base * (1 + half) if qty > 0 else base * (1 - half)
            commission = abs(qty) * price * rate
            cash -= qty * price + commission
            positions[symbol] = positions.get(symbol, 0) + qty
            fills.append({"day": t, "symbol": symbol, "qty": qty, "price": price, "commission": commission})
        for symbol, amount in day.get("dividends", {}).items():
            cash += positions.get(symbol, 0) * amount
        for symbol, qty in positions.items():
            if qty < 0:
                cash -= -qty * prices[symbol]["close"] * borrow_rate / 360
        value = cash + sum(qty * prices[s]["close"] for s, qty in positions.items())
        held = {s: q for s, q in positions.items() if q != 0}
        records.append({"cash": cash, "equity": value, "positions": held})
    return {"fills": fills, "days": records}
