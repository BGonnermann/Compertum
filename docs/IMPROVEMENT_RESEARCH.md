# Improvement research - 2 November 2026

Status: findings for the owner. Owner, 2 November 2026: "in the background run auto research on our system. Find ways to improve it."
A read-only research agent studied the code, documents and results, and published literature. It changed no file, ran no engine, sweep
or provider call, and opened no price data and no ledger. Items marked "owner" change the judge, the gate, the scorer, the vault, the data
tiers or spending, and need the owner's approval.

## Ranked findings

1. Test against the benchmark, not against zero (owner). `deflation.py` deflates the raw strategy Sharpe ratio against 0; "beats the
   baseline" compares point estimates only. On french49 the equal-weight benchmark alone has a Sharpe ratio of 0.85, and ew_trend passed
   with +0.25% a year over it. Fix: deflate active returns (strategy minus benchmark), or test the Sharpe difference (Ledoit and Wolf, 2008).
2. Excess returns over the risk-free rate, and cash earning it (owner). `metrics()` uses raw returns, and flat periods earn 0. The French
   factor file has the daily T-bill rate.
3. Realistic costs and timing (owner for the scorer). Costs by era (Jones, 2002: one-way commissions near 0.9% in 1974); count weight
   drift as turnover; a one-day execution-lag check, because stale industry prices flatter daily trend rules; tradability before 1998.
4. Move the firm from single-asset 0/1 timing to portfolio weights on the long French panel (owner: a new candidate type).
5. Confirmed in the code: `tasks.market_brief` says "synthetic and closed" on real markets. Fix the brief; hide real dates from the roles.
   The models know market history, so a vault pass by an AI-written strategy cannot rule out memory (arXiv 2504.14765). Forward paper
   trading is the only clean test for those.
6. Treat published anomaly families as replications: French VALIDATION (1973 to 2003) lies inside the samples where industry and stock
   momentum were found (Moskowitz and Grinblatt, 1999; Jegadeesh and Titman, 1993). Effects decay after publication (McLean and Pontiff, 2016).
7. A real-data bench inside French TRAIN (1926 to 1973, split into an inner train and an inner test); no VALIDATION or vault rows (owner).
8. GEPA ranks prompts only on that bench, never on real VALIDATION (owner: run start).
9. More free data: French 5 factors, momentum and reversal factors, other portfolio sets; FRED rates; Open Source Asset Pricing
   (Chen and Zimmermann). Keep each vintage's hash ("Noisy Factors").
10. Information, not rules, for the firm: lessons for the Researcher, library TRAIN statistics, an originality check (ask the owner: it
    touches the no-steering rule of 29 October).
11. Overfitting diagnostics beside the gate: probability of backtest overfitting on TRAIN, SPA or Romano-Wolf, effective trial count.
12. VALIDATION results per decade (diagnostic).
13. Engineering: measure the 120-second sandbox deadline on 12,824 TRAIN rows; numpy loops in `library_multi`; tests for drift turnover,
    the brief and the lag check.

## Not to do

1. Do not open the french-v1 vault for xs_momentum or ew_trend before items 1 to 3 are fixed and the candidates are fixed in writing.
   A vault test is final and the vault holds 12 candidates.
2. No more single-symbol runs or sweeps on the 2016 to 2023 Alpaca markets, and no GEPA ranking on real VALIDATION.
3. Do not lower the DSR minimum; do not use the unlicensed CRSP copy or Yahoo scraping.

Uncertain in the report: the average T-bill rate, the exact McLean and Pontiff figures, how much stale prices inflate ew_trend.
Sources: McLean and Pontiff (2016), arXiv 2504.14765, arXiv 2512.23847, AlphaAgent (arXiv 2502.16789), Jones (2002), Open Source Asset
Pricing (Federal Reserve), Geczy and Samonov (SSRN 2292544), "Noisy Factors" (ECGI); from memory: Ledoit and Wolf (2008), Harvey, Liu and
Zhu (2016), Bailey et al. (2017), Sullivan, Timmermann and White (1999), Welch and Goyal (2008).
