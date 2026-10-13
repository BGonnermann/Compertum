# Real-data engineering replay verified

All six predeclared baseline replays completed: holding periods1/5/21 sessions, each at10/20basis points per side. Every result matches byte-for-byte between source and the installed wheel. 141 checks passed in each environment, with zero failures or skips.

The inputs cover13symbols,252warmup sessions and43sample sessions. Seven documented dividends are applied. Dividends payable after the sample remain in economic NAV as receivables; the equal-weight diagnostic retains$10.21. No pre-sample SPY entitlement is created. Sell-fee cash debits use an explicitly declared historical regulatory-rate scenario.

Independent review verified22source pins, all six result hashes, and cash/position/dividend/fee/NAV accounting across30portfolios and1,290daily records. The raw/split audit checked4,953pairs. NVIDIA adjusted prices contain rounding differences up to$0.05 at original price scale; adjusted observations are retained but excluded from features and execution. Raw observations determine historical eligibility and fills.

Both native jobs used one CPU core, a1GiB memory limit and a120second deadline; each completed in under13seconds with no remaining process. Cash control failed the unchanged400-observation,30-completed-interval and defined-Sharpe requirements. No strategy threshold was reduced.

This is REAL_ENGINEERING_DIAGNOSTIC evidence. Full M1 remains incomplete. Action completeness, the no-effective-split assumption, historical operational eligibility and actual Alpaca customer-fee conventions remain unqualified. Provider saved-run/lifecycle integration is the next local task; no financial or broker admission is granted.

[Receipt](../artifacts/m1/real_engineering_replay.json) | [Scenario](../data/real-replay-scenario-20261010-01/scenario.json) | [Source bindings](../data/real-replay-scenario-20261010-01/bounded-bindings.json) | [Checkpoint](../docs/CURRENT_CHECKPOINT.md).