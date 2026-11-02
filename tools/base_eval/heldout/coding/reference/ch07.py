def fill_price(order, bar):
    kind = order["type"]
    side = order["side"]
    if kind == "market":
        return bar["open"]
    level = order["price"]
    if kind == "limit" and side == "buy":
        return min(bar["open"], level) if bar["low"] < level else None
    if kind == "limit":
        return max(bar["open"], level) if bar["high"] > level else None
    if side == "buy":
        return max(bar["open"], level) if bar["high"] >= level else None
    return min(bar["open"], level) if bar["low"] <= level else None


def simulate(bars, orders, cash, fee):
    position = 0
    fills = []
    equity = []
    done = set()
    for t, bar in enumerate(bars):
        live = [
            i for i, o in enumerate(orders)
            if i not in done and o["bar"] < t and (o.get("expire") is None or o["expire"] >= t)
        ]
        markets = [i for i in live if orders[i]["type"] == "market"]
        others = [i for i in live if orders[i]["type"] != "market"]
        for i in markets + others:
            if i in done:
                continue
            order = orders[i]
            price = fill_price(order, bar)
            if price is None:
                continue
            qty = order["qty"] if order["side"] == "buy" else -order["qty"]
            cost = fee * order["qty"]
            cash -= qty * price + cost
            position += qty
            done.add(i)
            fills.append({"id": order["id"], "bar": t, "side": order["side"], "qty": order["qty"], "price": price, "fee": cost})
            group = order.get("oco")
            if group is not None:
                for j, other in enumerate(orders):
                    if other.get("oco") == group:
                        done.add(j)
        equity.append(cash + position * bar["close"])
    return {"fills": fills, "equity": equity, "cash": cash, "position": position}
