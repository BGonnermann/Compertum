# Mathematics for accurate research and trading - 2 November 2026

Owner question: "What mathematics do we need to be accurate in our research and trading? can it just be imbeded into the engine or produced by another engine thats fast and built in C++ or rust? or possibly even a small neural network."
A read-only research agent answered it. It changed no file and ran no engine, provider or model. Scratch scripts: session scratchpad `math/` (gate.py, power2.py, fwer.py, pure.py, vec.py).

## Short answer

- The scoring mathematics already exists in the engine and is mostly correct and fast. One deflated Sharpe ratio takes 2 ms, and one panel score takes under 1 s; model requests take minutes per cycle.
- Formula speed and precision do not limit accuracy. Two things do: weak signals, and a few statistical assumptions in the judge.
- C++ or Rust would not improve accuracy and would save under 1% of run time. NumPy is already compiled code.
- A small neural network must never be the judge. In the sandbox it is a possible candidate model, but weak on 49 industry series.

## What a candidate must show to pass the vault (computed from `deflation.py`)

french-v1 has about 5,130 vault sessions. The observed annual information ratio (IR) a candidate needs is 0.365 at N=1, 0.55 at N=3 and 0.73 at N=12.
Chance that a true IR passes at N=12: IR 0.3 gives 2.5%, 0.5 gives 15%, 0.75 gives 53%, and 1.0 gives 89%.
Today's panel candidates beat equal weight by 0.05% to 0.9% a year. That is an IR of about 0.05 to 0.3 (estimate), so their pass chance is about 0 to 3%. The firm needs stronger signals, not more exact arithmetic.

## Has, weak, lacks

Has, and checked against the published formulas:
- the deflated and probabilistic Sharpe ratios (`deflation.py`);
- excess returns over the T-bill rate, era costs, drift turnover, next-session attribution and the lag check (`market.py`, `library_multi.py`);
- the lookahead and reproduction checks (`audit.py`);
- a block bootstrap (`modeling/qualification.py`) and covariance gates (`mathematics/covariance.py`). The engine does not use these two.
Weak or possibly wrong (owner items):
1. Vault false-pass rate. The vault's N starts at 1 and grows by one per vault candidate. Over 12 candidates with zero skill, the chance of at least one false pass is about 8.1%; with N=12 for every candidate it would be 0.56% (computed, iid returns).
2. Serial correlation is ignored. Standard errors assume iid daily returns. A lag-1 autocorrelation of 0.1 inflates the t-statistic by about 1.11, which raises a false pass from 5% to about 6.8% (estimate). Fix: an autocorrelation-robust standard error (Newey-West or Lo 2002), first as a diagnostic.
3. Delisting bias in `sp500-pit`: a held stock without a next close earns 0, so its delisting loss is never charged. This flatters reversal rules. It does not reach a vault today.
4. `library_multi.causal` uses the weaker perturbation (already an owner item).
5. Determinism. Float64 is precise enough: the sum order of 20,518 returns moved the result by 4.4e-16. That still breaks the exact `score_recomputed` check, so any rewrite must keep the order of operations, or the owner must allow a tolerance.
Lacks:
- a 2x-cost stress check in the engine gate;
- a minimum-track-record or power report;
- an effective trial count for correlated trials;
- probability of backtest overfitting (PBO) on TRAIN, and per-decade VALIDATION results (`IMPROVEMENT_RESEARCH.md` items 11 and 12);
- candidate-side mathematics in the sandbox: shrunk covariance, risk parity, minimum variance, long-only projection, volatility scaling, no-trade bands, ridge regression and rolling statistics.

## Where each piece should live

- Judge (sealed Python with NumPy, owner changes only): scoring, costs, deflation, trials and the Auditor, plus new diagnostics. Milliseconds to seconds. No native component is needed.
- Sandbox maths for candidates. Option (a): a trusted plain-Python helper file in each job folder, which needs no install but changes what the firm sees (bench exam, no-steering rule). Option (b): a pinned NumPy readable by the sandbox, with one BLAS thread for reproducible reruns; it changes the interpreter or the sealed `sandbox.py`. Both are owner decisions.
- A learned model only as a candidate strategy in the sandbox, never as the judge.

## Speed measured on this host (49 assets x 20,518 sessions; system Python 3.14.7; NumPy 2.5.4, one thread)

| Task | Plain Python | NumPy | Speedup |
|---|---|---|---|
| Rolling 60-session volatility | 0.354 s | 0.022 s | 16x |
| Shrunk covariance + minimum variance, monthly (977 solves) | 36.9 s | 0.065 s | 570x |
| Ridge regression, about 500k rows | 3.25 s | 0.027 s | 120x |
| Small neural network (MLP 10-16-1), about 100k rows | 2.57 s per epoch | 1.27 s per 100 epochs | about 200x |
| Block bootstrap, 10,000 draws | 4.23 s | 0.33 s | 13x |
A daily minimum-variance rule in plain Python would take about 780 s, against the 120 s sandbox deadline (estimate). This is the real speed problem, and NumPy or a helper file solves it.

## Recommended plan

1. Now: give the power table above to the owner, and to the Director as a fact.
2. Owner: decide the vault N rule (8% against 0.56% false-pass chance over 12 candidates).
3. Owner: add judge diagnostics first: a robust IR t-statistic, a 2x-cost stress result, per-decade VALIDATION results and a power report.
4. Owner: add candidate-side maths (a helper file or a pinned single-thread NumPy), then a panel bench exam.
5. Owner: mark `sp500-pit` as research-only until delisting returns are modelled, and strengthen `library_multi.causal`.
6. Not now: C++ or Rust components, a neural-network judge or filter.
7. Any rewrite (NumPy, Rust or C++) must reproduce scores bit for bit, or the owner first allows a tolerance.
