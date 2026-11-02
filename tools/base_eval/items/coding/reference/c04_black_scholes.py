import math


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def d_terms(s, k, t, r, sigma, kind):
    if kind not in ("call", "put"):
        raise ValueError("kind must be call or put")
    if s <= 0 or k <= 0 or t <= 0 or sigma <= 0:
        raise ValueError("s, k, t and sigma must be positive")
    root = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r + sigma * sigma / 2.0) * t) / root
    return d1, d1 - root


def bs_price(s, k, t, r, sigma, kind):
    d1, d2 = d_terms(s, k, t, r, sigma, kind)
    disc = k * math.exp(-r * t)
    if kind == "call":
        return s * norm_cdf(d1) - disc * norm_cdf(d2)
    return disc * norm_cdf(-d2) - s * norm_cdf(-d1)


def bs_delta(s, k, t, r, sigma, kind):
    d1, _ = d_terms(s, k, t, r, sigma, kind)
    if kind == "call":
        return norm_cdf(d1)
    return norm_cdf(d1) - 1.0
