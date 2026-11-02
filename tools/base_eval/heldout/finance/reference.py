import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path


def find_root(f, lo, hi):
    flo = f(lo)
    fhi = f(hi)
    if flo * fhi > 0:
        raise ValueError("no sign change")
    for _ in range(400):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm == 0:
            return mid
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def irr_of(flows):
    return find_root(lambda r: sum(c / (1 + r) ** t for t, c in enumerate(flows)), -0.95, 10.0)


def xirr_of(rows):
    d0 = rows[0][0]
    return find_root(lambda r: sum(c / (1 + r) ** ((d - d0).days / 365) for d, c in rows), -0.95, 10.0)


def bond_price(y, coupon, periods, redemption=100.0, freq=2):
    k = y / freq
    c = coupon / freq
    return sum(c / (1 + k) ** t for t in range(1, periods + 1)) + redemption / (1 + k) ** periods


def bond_yield(price, coupon, periods, redemption=100.0, freq=2):
    return find_root(lambda y: bond_price(y, coupon, periods, redemption, freq) - price, -0.5, 2.0)


def irr_salvage():
    flows = [-4250, -1100, 900, 1750, 2300, 1980 + 600]
    ans = irr_of(flows) * 100
    wrong = [
        irr_of([-4250, -1100, 900, 1750, 2300, 1980]) * 100,
        irr_of([-4250, 1100, 900, 1750, 2300, 2580]) * 100,
        irr_of([1980 + 600, 2300, 1750, 900, -1100, -4250]) * 100,
    ]
    return ans, wrong


def irr_semiannual():
    flows = [-2.00, -0.50, 0.45, 0.48, 0.52, 0.55, 0.60, 0.60, 0.62 + 0.80]
    r = irr_of(flows)
    ans = ((1 + r) ** 2 - 1) * 100
    r0 = irr_of(flows[:-1] + [0.62])
    wrong = [2 * r * 100, ((1 + r0) ** 2 - 1) * 100, r * 100]
    return ans, wrong


def xirr_memo():
    rows = [
        (date(2024, 1, 15), -1_000_000),
        (date(2024, 6, 30), -250_000),
        (date(2024, 11, 2), 120_000),
        (date(2025, 3, 31), 300_000),
        (date(2025, 9, 15), 450_000),
        (date(2026, 2, 28), 700_000),
    ]
    ans = xirr_of(rows) * 100
    with_memo = sorted(rows + [(date(2024, 3, 1), -500_000)])
    wrong = [
        xirr_of(with_memo) * 100,
        irr_of([c for _, c in rows]) * 100,
    ]
    return ans, wrong


def xirr_nav():
    rows = [
        (date(2022, 2, 10), -5000),
        (date(2022, 9, 30), -3200),
        (date(2023, 5, 15), -2600),
        (date(2023, 12, 20), 1150),
        (date(2024, 8, 1), -1400),
        (date(2025, 3, 31), 2900),
        (date(2025, 11, 14), 3350),
    ]
    full = rows + [(date(2026, 6, 30), 9800)]
    ans = xirr_of(full) * 100
    wrong = [xirr_of(rows) * 100, xirr_of([(d, abs(c)) if c < 0 and d == date(2024, 8, 1) else (d, c) for d, c in full]) * 100]
    return ans, wrong


def ytm_series():
    ans = bond_yield(94.21, 5.25, 18) * 100
    wrong = [5.25 / 94.21 * 100, bond_yield(97.85, 4.80, 24) * 100]
    return ans, wrong


def yield_worst():
    ytm = bond_yield(108.40, 7.5, 24)
    ytc = bond_yield(108.40, 7.5, 8, redemption=103.0)
    ans = min(ytm, ytc) * 100
    wrong = [ytm * 100, bond_yield(108.40, 7.5, 8, redemption=100.0) * 100, 7.5 / 108.40 * 100]
    return ans, wrong


def days_360(d1, d2):
    a = min(d1.day, 30)
    b = d2.day
    if a == 30 and b == 31:
        b = 30
    return 360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (b - a)


def clean_price():
    last = date(2026, 1, 15)
    settle = date(2026, 4, 20)
    nxt = date(2026, 7, 15)
    accrued_days = days_360(last, settle)
    remaining = days_360(settle, nxt)
    w = remaining / 180
    k = 0.059 / 2
    c = 7.0 / 2
    n = 11
    dirty = sum(c / (1 + k) ** (t - 1 + w) for t in range(1, n + 1)) + 100 / (1 + k) ** (n - 1 + w)
    accrued = c * accrued_days / 180
    ans = dirty - accrued
    wrong = [dirty, dirty + accrued]
    return ans, wrong


def invoice_amount():
    last = date(2026, 3, 1)
    settle = date(2026, 7, 14)
    nxt = date(2026, 9, 1)
    period = (nxt - last).days
    accrued_days = (settle - last).days
    w = (nxt - settle).days / period
    k = 0.053 / 2
    c = 4.75 / 2
    n = 9
    dirty = sum(c / (1 + k) ** (t - 1 + w) for t in range(1, n + 1)) + 100 / (1 + k) ** (n - 1 + w)
    accrued = c * accrued_days / period
    face = 5_000_000
    ans = dirty / 100 * face
    wrong = [(dirty - accrued) / 100 * face, (dirty - accrued + 4.75 * accrued_days / period) / 100 * face]
    return ans, wrong


def loan_balance():
    p = 412_500.0
    j = 0.066 / 12
    n = 300
    pmt = p * j / (1 - (1 + j) ** -n)
    k = 37
    ans = p * (1 + j) ** k - pmt * ((1 + j) ** k - 1) / j
    p2 = 286_000.0
    j2 = 0.071 / 12
    n2 = 240
    pmt2 = p2 * j2 / (1 - (1 + j2) ** -n2)
    wrong = [
        p * (1 - k / n),
        p2 * (1 + j2) ** k - pmt2 * ((1 + j2) ** k - 1) / j2,
        p - pmt * k,
    ]
    return ans, wrong


def loan_prepay():
    p = 250_000.0
    j = 0.054 / 12
    n = 180
    pmt = p * j / (1 - (1 + j) ** -n)
    bal = p
    total = 0.0
    month = 0
    while bal > 1e-9:
        month += 1
        interest = bal * j
        total += interest
        if bal + interest <= pmt:
            bal = 0.0
        else:
            bal = bal + interest - pmt
        if month == 24:
            bal -= 30_000
    ans = total
    wrong = [pmt * n - p, (pmt * n - p) - 30_000]
    return ans, wrong


def npv_terminal():
    r = 0.095
    g = 0.025
    fcf = [12.0 * 1.08 ** (t - 1) for t in range(1, 6)]
    pv = sum(f / (1 + r) ** t for t, f in enumerate(fcf, start=1))
    tv = fcf[-1] * (1 + g) / (r - g)
    ans = -140 + pv + tv / (1 + r) ** 5
    wrong = [
        -140 + pv + fcf[-1] / (r - g) / (1 + r) ** 5,
        -140 + pv + tv / (1 + r) ** 6,
        -140 + sum(12.0 * 1.08 ** t / (1 + r) ** t for t in range(1, 6)) + 12.0 * 1.08 ** 5 * (1 + g) / (r - g) / (1 + r) ** 5,
    ]
    return ans, wrong


def lease_value():
    r = 0.08
    g = 0.045
    rent = 2.4
    pv = sum(rent * (1 + g) ** t / (1 + r) ** t for t in range(20))
    sale = 15 * rent * (1 + g) ** 20 / (1 + r) ** 20
    ans = pv + sale
    arrears = sum(rent * (1 + g) ** (t - 1) / (1 + r) ** t for t in range(1, 21))
    wrong = [arrears + sale, pv, pv + 15 * rent * (1 + g) ** 19 / (1 + r) ** 20]
    return ans, wrong


def wacc_market():
    shares = 104.0 - 20.0
    e = shares * 23.50
    db = 600 * 0.82
    dl = 150.0
    pf = 2.0 * 52.0
    kp = 3.90 / 52.0
    ke = 0.041 + 1.15 * 0.055
    t = 0.24
    v = e + db + dl + pf
    ans = (e * ke + db * 0.068 * (1 - t) + dl * 0.062 * (1 - t) + pf * kp) / v * 100
    no_shield = (e * ke + db * 0.068 + dl * 0.062 + pf * kp) / v * 100
    e2 = 104.0 * 23.50
    v2 = e2 + db + dl + pf
    issued = (e2 * ke + db * 0.068 * (1 - t) + dl * 0.062 * (1 - t) + pf * kp) / v2 * 100
    v3 = e + 600 + dl + pf
    face = (e * ke + 600 * 0.068 * (1 - t) + dl * 0.062 * (1 - t) + pf * kp) / v3 * 100
    return ans, [no_shield, issued, face]


def wacc_dividend():
    price = bond_price(0.071, 2.5, 8, freq=1)
    d = 400 * price / 100
    e = (62.0 - 14.0) * 32.00
    ke = 1.80 * 1.04 / 32.00 + 0.04
    kd = 0.071 * (1 - 0.25)
    ans = (e * ke + d * kd) / (e + d) * 100
    face = (e * ke + 400 * kd) / (e + 400) * 100
    ke0 = 1.80 / 32.00 + 0.04
    d0 = (e * ke0 + d * kd) / (e + d) * 100
    e2 = 62.0 * 32.00
    issued = (e2 * ke + d * kd) / (e2 + d) * 100
    coupon = (e * ke + d * 0.025 * 0.75) / (e + d) * 100
    return ans, [face, d0, issued, coupon]


def eps_convertible():
    ni = 48_600 / 1000
    pref = 3_600 / 1000
    basic_sh = 30.0
    options = 2.4 * (1 - 25 / 40)
    conv_sh = 80_000_000 / 1000 * 25 / 1e6
    conv_int = 80.0 * 0.04 * (1 - 0.25)
    ans = (ni - pref + conv_int) / (basic_sh + options + conv_sh)
    wrong = [
        (ni - pref + conv_int) / (basic_sh + options + conv_sh + 1.0),
        (ni - pref + conv_int) / (basic_sh + 2.4 + conv_sh),
        (ni - pref) / basic_sh,
        (ni - pref + 80.0 * 0.04) / (basic_sh + options + conv_sh),
        (ni - pref) / (basic_sh + options + conv_sh),
    ]
    return ans, wrong


def eps_antidilution():
    ni = 120.0
    pref = 6.0
    basic = 2 * (50 + 6 * 9 / 12 - 4 * 3 / 12)
    options = 4.0 * (1 - 20 / 32)
    ans = (ni - pref) / (basic + options)
    wrong = [
        ni / (basic + options + 4.0),
        (ni - pref) / basic,
        (ni - pref) / ((50 + 6 * 9 / 12 - 4 * 3 / 12) + options),
        (ni - pref) / (2 * (50 + 6 - 4) + options),
    ]
    return ans, wrong


def dupont_change():
    ni = {2026: 512, 2025: 498}
    ni_total = {2026: 547, 2025: 529}
    eq = {2026: 2780, 2025: 2690, 2024: 2450}
    eq_total = {2026: 3010, 2025: 2905, 2024: 2640}
    roe = {y: ni[y] / ((eq[y] + eq[y - 1]) / 2) for y in (2026, 2025)}
    ans = (roe[2026] - roe[2025]) * 100
    end = (ni[2026] / eq[2026] - ni[2025] / eq[2025]) * 100
    tot = {y: ni_total[y] / ((eq_total[y] + eq_total[y - 1]) / 2) for y in (2026, 2025)}
    mixed = (ni[2026] / ((eq_total[2026] + eq_total[2025]) / 2) - ni[2025] / ((eq_total[2025] + eq_total[2024]) / 2)) * 100
    return ans, [end, (tot[2026] - tot[2025]) * 100, mixed, -ans]


def dupont_counterfactual():
    ebit = {2026: 6270, 2025: 5640}
    interest = {2026: 910, 2025: 620}
    tax = {2026: 1233, 2025: 1054}
    eq = {2026: 21900, 2025: 20800, 2024: 19950}
    ebt = {y: ebit[y] - interest[y] for y in ebit}
    ni = {y: ebt[y] - tax[y] for y in ebit}
    roe26 = ni[2026] / ((eq[2026] + eq[2025]) / 2)
    ib = {y: ebt[y] / ebit[y] for y in ebit}
    ans = roe26 * ib[2025] / ib[2026] * 100
    wrong = [roe26 * 100, ni[2026] / eq[2026] * ib[2025] / ib[2026] * 100, roe26 * ib[2026] / ib[2025] * 100]
    return ans, wrong


def fcfe_statement():
    ni = 18_640
    da = 7_215
    capex = 11_980
    sale = 1_140
    borrow = 6_500
    repay = 4_200
    div = 5_000
    nwc26 = 16_320 + 12_050 + 1_240 - 8_930 - 3_410
    nwc25 = 13_880 + 12_610 + 1_105 - 8_210 - 3_180
    dnwc = nwc26 - nwc25
    fcfe = ni + da - capex + sale - dnwc + borrow - repay
    ans = fcfe / 1000
    cash = (9_410 - 7_150)
    std = 2_000 - 2_400
    wrong = [
        (fcfe - cash) / 1000,
        (fcfe - div) / 1000,
        (fcfe - sale) / 1000,
        (fcfe + std) / 1000,
        (fcfe + 2 * dnwc) / 1000,
    ]
    return ans, wrong


def fcfe_fcff():
    ebit = 412.0 - 248.6 - 81.2 - 18.5
    t = 0.23
    fcff = ebit * (1 - t) + 18.5 - 27.3 - 4.1
    ans = fcff - 9.6 * (1 - t) + 15.0 - 9.0
    wrong = [fcff - 9.6 + 6.0, fcff - 9.6 * (1 - t) + 15.0, fcff, ans + 2 * 4.1]
    return ans, wrong


def fifo_lifo():
    begin = [(4000, 12.00)]
    buys = [(6000, 12.80), (5000, 13.60), (7000, 14.25)]
    sold = 17_500

    def cogs(lots, units):
        total = 0.0
        for q, c in lots:
            take = min(q, units)
            total += take * c
            units -= take
            if units == 0:
                break
        return total

    lots = begin + buys
    fifo = cogs(lots, sold)
    lifo = cogs(list(reversed(lots)), sold)
    ans = lifo - fifo
    lots2 = lots + [(3000, 14.90)]
    wrong = [cogs(list(reversed(lots2)), sold) - cogs(lots2, sold), fifo - lifo + 0.0]
    return ans, wrong


def cash_cycle():
    rev = 1284.0
    cogs_lifo = 842.0
    ar = {2026: 176.0, 2025: 158.0}
    inv = {2026: 131.0, 2025: 124.0}
    ap = {2026: 98.0, 2025: 90.0}
    res = {2026: 41.0, 2025: 22.0}
    cogs = cogs_lifo - (res[2026] - res[2025])
    fifo_inv = {y: inv[y] + res[y] for y in inv}
    dso = (ar[2026] + ar[2025]) / 2 / rev * 365
    dio = (fifo_inv[2026] + fifo_inv[2025]) / 2 / cogs * 365
    dpo = (ap[2026] + ap[2025]) / 2 / cogs * 365
    ans = dso + dio - dpo
    lifo = dso + (inv[2026] + inv[2025]) / 2 / cogs_lifo * 365 - (ap[2026] + ap[2025]) / 2 / cogs_lifo * 365
    end = ar[2026] / rev * 365 + fifo_inv[2026] / cogs * 365 - ap[2026] / cogs * 365
    plus = cogs_lifo + (res[2026] - res[2025])
    wrong_sign = dso + (fifo_inv[2026] + fifo_inv[2025]) / 2 / plus * 365 - (ap[2026] + ap[2025]) / 2 / plus * 365
    return ans, [lifo, end, wrong_sign, dso + dio + dpo]


def constant_currency():
    lc = {"EUR": (412.0, 436.5), "GBP": (188.0, 193.4), "JPY": (31.20, 33.85), "USD": (520.0, 548.0)}
    rate = {"EUR": (1.082, 1.145), "GBP": (1.271, 1.318), "JPY": (151.4, 143.2), "USD": (1.0, 1.0)}

    def usd(cur, amount, r):
        if cur == "JPY":
            return amount * 1000 / r
        return amount * r

    rep25 = sum(usd(c, lc[c][0], rate[c][0]) for c in lc)
    rep26 = sum(usd(c, lc[c][1], rate[c][1]) for c in lc)
    cc26 = sum(usd(c, lc[c][1], rate[c][0]) for c in lc)
    ans = (cc26 / rep25 - 1) * 100
    wrong = [(rep26 / rep25 - 1) * 100, (sum(lc[c][1] for c in lc) / sum(lc[c][0] for c in lc) - 1) * 100]
    return ans, wrong


def fx_impact():
    cad = (254.0, 271.5)
    brl = (615.0, 702.0)
    eur = (96_400 / 1000, 104_800 / 1000)
    cad_r = (1.352, 1.388)
    brl_r = (4.99, 5.62)
    eur_r = (1.082, 1.145)
    rep26 = cad[1] / cad_r[1] + brl[1] / brl_r[1] + eur[1] * eur_r[1]
    cc26 = cad[1] / cad_r[0] + brl[1] / brl_r[0] + eur[1] * eur_r[0]
    ans = rep26 - cc26
    rep26b = cad[1] / cad_r[1] + brl[1] / brl_r[1] + 104_800 * eur_r[1]
    cc26b = cad[1] / cad_r[0] + brl[1] / brl_r[0] + 104_800 * eur_r[0]
    rep25 = cad[0] / cad_r[0] + brl[0] / brl_r[0] + eur[0] * eur_r[0]
    wrong = [-ans, rep26b - cc26b, cad[1] * cad_r[1] + brl[1] * brl_r[1] + eur[1] / eur_r[1]
             - (cad[1] * cad_r[0] + brl[1] * brl_r[0] + eur[1] / eur_r[0]), rep26 - rep25]
    return ans, wrong


def brinson_selection():
    wb = [0.24, 0.20, 0.13, 0.12, 0.18, 0.13]
    wp = [0.28, 0.18, 0.15, 0.09, 0.20, 0.10]
    rp = [9.4, 3.1, 5.6, -2.4, 4.8, 1.9]
    rb = [7.8, 4.0, 6.2, -4.1, 4.3, 2.2]
    ans = sum(b * (p - q) for b, p, q in zip(wb, rp, rb))
    wrong = [
        sum(w * (p - q) for w, p, q in zip(wp, rp, rb)),
        sum(w * (q - p) for w, p, q in zip(wb, rp, rb)),
        sum(w * p for w, p in zip(wp, rp)) - sum(b * q for b, q in zip(wb, rb)),
    ]
    return ans, wrong


def brinson_allocation():
    wp = [0.14, 0.22, 0.19, 0.16, 0.12, 0.17]
    wb = [0.10, 0.26, 0.17, 0.18, 0.11, 0.18]
    rb = [2.6, 12.8, 5.9, 6.6, 5.3, -0.9]
    rp = [3.2, 11.5, 6.4, 7.1, 4.9, -1.8]
    total_b = sum(b * r for b, r in zip(wb, rb))
    ans = (wp[0] - wb[0]) * (rb[0] - total_b)
    total_p = sum(w * r for w, r in zip(wp, rp))
    wrong = [(wp[0] - wb[0]) * rb[0], (wp[0] - wb[0]) * (rp[0] - total_b), (wp[0] - wb[0]) * (rb[0] - total_p)]
    return ans, wrong


def twr_chain():
    v0 = 20.0
    before = [19.10, 31.40, 28.90, 32.60]
    flows = [10.0, -4.0, 2.5]
    start = v0
    growth = 1.0
    for i, v in enumerate(before):
        growth *= v / start
        if i < len(flows):
            start = v + flows[i]
    ans = (growth - 1) * 100
    net = sum(flows)
    simple = (before[-1] - v0 - net) / v0 * 100
    dietz = (before[-1] - v0 - net) / (v0 + 10.0 * 0.75 - 4.0 * 0.5 + 2.5 * 0.25) * 100
    signs = [10.0, 4.0, 2.5]
    start = v0
    g2 = 1.0
    for i, v in enumerate(before):
        g2 *= v / start
        if i < 3:
            start = v + signs[i]
    return ans, [simple, dietz, (g2 - 1) * 100]


def mwr_solve():
    v0 = 50.0
    flows = [(0.25, 12.0), (0.5, -6.0), (0.75, 9.0)]
    vend = 70.2

    def f(r):
        return -v0 - sum(c / (1 + r) ** t for t, c in flows) + vend / (1 + r)

    ans = find_root(f, -0.5, 1.0) * 100
    before = [52.3, 63.0, 60.1, 70.2]
    start = v0
    g = 1.0
    for i, v in enumerate(before):
        g *= v / start
        if i < 3:
            start = v + flows[i][1]
    simple = (vend - v0 - 15.0) / v0 * 100

    def f2(r):
        return -v0 - sum(c / (1 + r) ** (4 * t) for t, c in flows) + vend / (1 + r) ** 4

    quarterly = find_root(f2, -0.5, 1.0) * 400
    return ans, [(g - 1) * 100, simple, quarterly]


TE_PORT = [1.82, -0.64, 2.31, 0.47, -1.95, 3.12, 0.88, -0.21, 1.54, -2.36, 2.07, 0.95]
TE_TOTAL = [1.45, -0.32, 1.98, 0.71, -1.42, 2.65, 1.10, -0.48, 1.21, -1.88, 1.66, 1.02]
TE_PRICE = [1.43, -0.34, 1.41, 0.69, -1.44, 2.07, 1.08, -0.50, 0.66, -1.90, 1.64, 0.43]


def tracking_error():
    active = [p - b for p, b in zip(TE_PORT, TE_TOTAL)]
    ans = statistics.stdev(active) * math.sqrt(12)
    wrong = [
        statistics.pstdev(active) * math.sqrt(12),
        statistics.stdev([p - b for p, b in zip(TE_PORT, TE_PRICE)]) * math.sqrt(12),
        statistics.stdev(active),
        statistics.stdev(active) * 12,
    ]
    return ans, wrong


IR_PORT = [0.94, 1.37, -0.58, 2.11, -1.26, 0.73, 1.65, -0.42, 0.18, 2.44, -0.87, 1.09]
IR_BENCH_BP = [71, 102, -105, 228, -141, 49, 147, 15, -12, 262, -98, 84]


def information_ratio():
    active = [p - b / 100 for p, b in zip(IR_PORT, IR_BENCH_BP)]
    mean = statistics.mean(active)
    ans = mean * 12 / (statistics.stdev(active) * math.sqrt(12))
    wrong = [
        mean * 12 / (statistics.pstdev(active) * math.sqrt(12)),
        mean / statistics.stdev(active),
        (math.prod(1 + p / 100 for p in IR_PORT) - math.prod(1 + b / 10000 for b in IR_BENCH_BP)) * 100 / (statistics.stdev(active) * math.sqrt(12)),
    ]
    return ans, wrong


def convexity_estimate():
    y = 0.052
    cfs = [4.5, 4.5, 4.5, 4.5, 104.5]
    price = sum(c / (1 + y) ** t for t, c in enumerate(cfs, start=1))
    mac = sum(t * c / (1 + y) ** t for t, c in enumerate(cfs, start=1)) / price
    mod = mac / (1 + y)
    conv = sum(t * (t + 1) * c / (1 + y) ** (t + 2) for t, c in enumerate(cfs, start=1)) / price
    dy = 0.012
    ans = (-mod * dy + 0.5 * conv * dy ** 2) * 100
    wrong = [-mod * dy * 100, (-mac * dy + 0.5 * conv * dy ** 2) * 100, (-mod * dy + conv * dy ** 2) * 100]
    return ans, wrong


def portfolio_duration():
    bonds = [
        (40_000 * 1000, 92.50, 6.8, 58.0),
        (25.0 * 1_000_000, 108.20, 3.1, 12.0),
        (15_500_000, 99.10, 11.4, 165.0),
    ]
    dy = -0.0065
    ans = sum(f * p / 100 * (-d * dy + 0.5 * c * dy ** 2) for f, p, d, c in bonds)
    wrong = [
        sum(f * (-d * dy + 0.5 * c * dy ** 2) for f, p, d, c in bonds),
        sum(f * p / 100 * (-d * dy) for f, p, d, c in bonds),
        sum(f * p / 100 * (-d * dy - 0.5 * c * dy ** 2) for f, p, d, c in bonds),
    ]
    return ans, wrong


def parity_arbitrage():
    s, k, t, r = 48.20, 50.0, 0.5, 0.04
    c, p = 3.10, 4.60
    per_share = (s - c + p) * math.exp(r * t) - k
    ans = per_share * 20 * 100
    wrong = [per_share * math.exp(-r * t) * 2000, ((s - c + p) * (1 + r * t) - k) * 2000, per_share * 20]
    return ans, wrong


def parity_dividend():
    s, k, t, r = 72.40, 70.0, 0.75, 0.05
    div, td = 1.35, 4 / 12
    c, p = 7.85, 3.20
    fair = s - div * math.exp(-r * td) - k * math.exp(-r * t)
    ans = abs((c - p) - fair) * 1500
    fair0 = s - k * math.exp(-r * t)
    wrong = [abs((c - p) - fair0) * 1500, abs((c - p) - fair) * 1500 * math.exp(r * t), abs((c - p) - (s - div - k * math.exp(-r * t))) * 1500]
    return ans, wrong


def futures_fair():
    s, r = 64.00, 0.048
    t = 150 / 365
    divs = [(40, 1.20), (130, 0.90)]
    pv = sum(d * math.exp(-r * day / 365) for day, d in divs)
    ans = (s - pv) * math.exp(r * t)
    wrong = [
        s * math.exp(r * t),
        (s - pv - 1.05 * math.exp(-r * 190 / 365)) * math.exp(r * t),
    ]
    return ans, wrong


def index_arbitrage():
    s = 4812.60
    q = 0.016
    r_eff = 0.052
    t = 119 / 365
    fair = s * math.exp(-q * t) * (1 + r_eff) ** t
    market = 4905.00
    ans = (market - fair) * 50 * 12
    wrong = [
        (market - s * math.exp((r_eff - q) * t)) * 600,
        (market - s * (1 + r_eff) ** t) * 600,
        (market - s * math.exp(-q * t) * (1 + r_eff) ** (119 / 360)) * 600,
    ]
    return ans, wrong


def ear_cheapest():
    a = (1 + 0.072 / 12) ** 12 - 1
    b = (1 + 0.0735 / 2) ** 2 - 1
    c = math.exp(0.0705) - 1
    proceeds = 100_000 * (1 - 0.070 * 9 / 12)
    d = (100_000 / proceeds) ** (12 / 9) - 1
    e = (1 + 0.0715 / 365) ** 365 - 1
    rates = [a, b, c, d, e]
    ans = min(rates) * 100
    wrong = [d * 100, 7.05, a * 100, e * 100]
    return ans, wrong


def ear_fee():
    growth = (1 + 0.09 / 365) ** (365 * 2)
    proceeds = 1 - 0.015
    ans = math.log(growth / proceeds) / 2 * 100
    wrong = [math.log(growth) / 2 * 100, (math.log(growth) / 2 - math.log(proceeds)) * 100, ((growth / proceeds) ** 0.5 - 1) * 100]
    return ans, wrong


def pension_cola():
    q = 1.055 ** 0.25 - 1
    pv = sum(9600 * 1.02 ** k / (1 + q) ** (4 * k + m) for k in range(25) for m in range(4))
    ans = pv
    no_cola = sum(9600 / (1 + q) ** n for n in range(100))
    arrears = pv / (1 + q)
    qn = 0.055 / 4
    nominal = sum(9600 * 1.02 ** k / (1 + qn) ** (4 * k + m) for k in range(25) for m in range(4))
    return ans, [no_cola, arrears, nominal]


def pbo_value():
    final = 84_000 * 1.03 ** 25
    benefit = 0.016 * 12 * final
    annuity = benefit * (1 - 1.046 ** -22) / 0.046
    ans = annuity / 1.046 ** 25
    abo = 0.016 * 12 * 84_000 * (1 - 1.046 ** -22) / 0.046 / 1.046 ** 25
    due = ans * 1.046
    total_service = 0.016 * 37 * final * (1 - 1.046 ** -22) / 0.046 / 1.046 ** 25
    return ans, [abo, due, total_service]


FUNCS = {
    "fh01": irr_salvage,
    "fh02": irr_semiannual,
    "fh03": xirr_memo,
    "fh04": xirr_nav,
    "fh05": ytm_series,
    "fh06": yield_worst,
    "fh07": clean_price,
    "fh08": invoice_amount,
    "fh09": loan_balance,
    "fh10": loan_prepay,
    "fh11": npv_terminal,
    "fh12": lease_value,
    "fh13": wacc_market,
    "fh14": wacc_dividend,
    "fh15": eps_convertible,
    "fh16": eps_antidilution,
    "fh17": dupont_change,
    "fh18": dupont_counterfactual,
    "fh19": fcfe_statement,
    "fh20": fcfe_fcff,
    "fh21": fifo_lifo,
    "fh22": cash_cycle,
    "fh23": constant_currency,
    "fh24": fx_impact,
    "fh25": brinson_selection,
    "fh26": brinson_allocation,
    "fh27": twr_chain,
    "fh28": mwr_solve,
    "fh29": tracking_error,
    "fh30": information_ratio,
    "fh31": convexity_estimate,
    "fh32": portfolio_duration,
    "fh33": parity_arbitrage,
    "fh34": parity_dividend,
    "fh35": futures_fair,
    "fh36": index_arbitrage,
    "fh37": ear_cheapest,
    "fh38": ear_fee,
    "fh39": pension_cola,
    "fh40": pbo_value,
}


def run_checks(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = {it["id"]: it for it in data["items"]}
    failures = 0
    if set(items) != set(FUNCS):
        print("ID MISMATCH", sorted(set(items) ^ set(FUNCS)))
        failures += 1
    for key, fn in FUNCS.items():
        ans, wrongs = fn()
        stored = items[key]["grading"]["answer"]
        match = abs(stored - ans) <= 1e-9 * max(abs(ans), 1e-12)
        margins = [abs(w - ans) / abs(ans) for w in wrongs]
        margin_ok = all(m > 0.01 for m in margins)
        status = "OK" if match and margin_ok else "FAIL"
        if status == "FAIL":
            failures += 1
        wtxt = ", ".join(f"{w:.6g} ({m * 100:.2f}%)" for w, m in zip(wrongs, margins))
        print(f"{key} {status} answer={ans:.10g} stored={stored:.10g} match={match} min_margin={min(margins) * 100:.2f}% wrong=[{wtxt}]")
    print(f"items={len(FUNCS)} failures={failures}")
    return failures


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent / "items.json")
    sys.exit(1 if run_checks(target) else 0)
