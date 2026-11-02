class OrderBook:
    def __init__(self):
        self.bids = []
        self.asks = []
        self.seq = 0

    def submit(self, order_id, side, price, qty):
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        if qty <= 0 or price <= 0:
            raise ValueError("price and qty must be positive")
        buying = side == "buy"
        other = self.asks if buying else self.bids
        trades = []
        while qty > 0 and other:
            rest = other[0]
            rest_price = rest[4]
            if (buying and rest_price > price) or (not buying and rest_price < price):
                break
            fill = min(qty, rest[3])
            if buying:
                trades.append((order_id, rest[2], rest_price, fill))
            else:
                trades.append((rest[2], order_id, rest_price, fill))
            qty -= fill
            rest[3] -= fill
            if rest[3] == 0:
                other.pop(0)
        if qty > 0:
            self.seq += 1
            own = self.bids if buying else self.asks
            key = -price if buying else price
            own.append([key, self.seq, order_id, qty, price])
            own.sort(key=lambda e: (e[0], e[1]))
        return trades

    def cancel(self, order_id):
        for book in (self.bids, self.asks):
            for i, entry in enumerate(book):
                if entry[2] == order_id:
                    del book[i]
                    return True
        return False

    def best_bid(self):
        return self.bids[0][4] if self.bids else None

    def best_ask(self):
        return self.asks[0][4] if self.asks else None
