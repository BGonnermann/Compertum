def period_count(face, years, freq):
    if isinstance(freq, bool) or not isinstance(freq, int) or freq < 1:
        raise ValueError("freq must be a positive int")
    if face <= 0 or years <= 0:
        raise ValueError("face and years must be positive")
    raw = years * freq
    count = round(raw)
    if count < 1 or abs(raw - count) > 1e-9:
        raise ValueError("years * freq must be a whole number")
    return count


def present_values(face, coupon_rate, ytm, years, freq):
    count = period_count(face, years, freq)
    coupon = face * coupon_rate / freq
    rate = ytm / freq
    flows = []
    for i in range(1, count + 1):
        cash = coupon + (face if i == count else 0.0)
        flows.append((i, cash / (1.0 + rate) ** i))
    return flows


def bond_price(face, coupon_rate, ytm, years, freq):
    return sum(pv for _, pv in present_values(face, coupon_rate, ytm, years, freq))


def bond_duration(face, coupon_rate, ytm, years, freq):
    flows = present_values(face, coupon_rate, ytm, years, freq)
    price = sum(pv for _, pv in flows)
    macaulay = sum((i / freq) * pv for i, pv in flows) / price
    return macaulay, macaulay / (1.0 + ytm / freq)
