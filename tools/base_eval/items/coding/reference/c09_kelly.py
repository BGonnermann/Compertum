def kelly_binary(p, b):
    if not 0 <= p <= 1:
        raise ValueError("p must be in [0, 1]")
    if not b > 0:
        raise ValueError("b must be positive")
    return p - (1.0 - p) / b


def kelly_continuous(mu, sigma, risk_free=0.0):
    if not sigma > 0:
        raise ValueError("sigma must be positive")
    return (mu - risk_free) / (sigma * sigma)
