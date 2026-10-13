# Proposed M1 real-data protocol

Prepared 10 October 2026 from BUILD_SPEC v1.1 and the approved baseline/data plans. DRAFT: NOT ADOPTED, NOT SEALED, NOT EXECUTABLE. This makes the later choice reviewable; it neither qualifies missing facts nor authorizes strategy execution. Dataset/action/mapping/fee artifact hashes remain pending and must be supplied before final adoption. BUILD_SPEC remains the authoritative full policy.

| Item | Proposed setting |
| --- | --- |
| Universe | AAPL, MSFT, AMZN, GOOGL, META, NVDA, JPM, XOM, JNJ, PG, UNH, HD; benchmark SPY; no substitution |
| Historical claim | Present-day frozen watchlist, conditional historical research; no survivorship-free claim |
| Profile | Explicit historical SIP, raw execution/accounting plus tested split-consistent features; original request/response manifests and complete pagination |
| Development | 2016-2023 only, first 252 completed sessions for feature warmup; train 2016-2020/test 2021, train 2016-2021/test 2022, train 2016-2022/test 2023 |
| Excluded access | 2024-2025 protected, 2026 reserved; no prices or outcome inspection in this work |
| Identity | Provider ID with effective symbol/lifecycle mapping, historical eligibility evidence and coverage denominator; no assumption that current XOM successor UUID was historical |
| Sectors | Frozen dated `data/identity-metadata-20261010-01/sector-proposal.json`, hash 1bef4509b6489ca1f7f9cba3bf3207e396feb51354fdecde498a67debb02afb9; explicit grouping policy, not GICS |
| Eligibility | Active/tradable US stock; 252 complete feature sessions; prior raw close >= $5; prior 20-session mean SIP dollar volume >= $1 million; no unresolved halt/action/mapping/data issue |
| Availability | CURRENT_VINTAGE / SIMULATED_AVAILABILITY; actual retrieval retained, never backdated; daily/close mark proxy at next-session 09:25; minute reference at minute-end +15 minutes; documented action knowledge or explicit failure |
| Decision/entry | Prior completed daily features; immutable 09:25 New York information cutoff, 09:35 minute-open reference; session calendar handles early close/DST |
| Horizons | H=1,5,21 exchange sessions; exit 09:35 after H sessions; label availability at least next-session 09:25 after exit; no overlapping/unavailable training labels |
| Fitting | Predeclared annual 07:00 cutoff on first exchange session; expanding window, same-date assets grouped/purged; approved artifact ready before 09:25 or skip |
| Baseline | H * prior 21-session return /21; zero-return comparison; three H baselines in M1, eventual 12 variants fixed by BUILD_SPEC, M2 ridge work remains outside this task |
| Portfolio | $10,000 modeling cash; top three eligible names, 20% targets, 60% gross, 40% sector cap, whole shares, stable symbol ties, sell before buy, 1% sizing buffer |
| Risk | Existing 2% daily-loss and 10% drawdown halts, no automatic liquidation/reset; child min($2,000,1% prior dollar volume), six submission ceiling |
| Costs | Adverse 10bp/side base, 20bp stress, zero cash interest/financing; commissions/sell fees from dated verified schedule still required, never inherit synthetic zero fees as verified |
| Benchmark | 60% SPY/40% cash with synchronized H/costs/actions; full SPY and 60%-gross equal-weight watchlist diagnostics |
| Actions | Exact raw share/cash ledger; split basis/quantity changes, ex-date receivables, pay-date cash; unresolved actions quarantine; no assumed zero dividends |
| Reproducibility | Exact input hashes, rows, splits, trade decisions, IDs and integer quantities; atol=1e-10, rtol=1e-8; daily portfolio return difference <=1e-8; Decimal precision 28; all unchanged BUILD_SPEC thresholds |
| Coverage | >=99.5% expected daily rows per segment and 100% selected execution/held-action coverage; verified listing denominator; no price/label forward fill |

Real-adapter implementation contract: preserve synthetic-only readers unchanged; build a distinct provider snapshot with qualified actions, provider/effective mapping, sectors, simulated/actual availability and original evidence hashes. Validate bounded chunks under existing byte/row/session limits before constructing a real market tape. Do not set `provider=synthetic`, discard coverage issues or change financial status solely to reuse the existing engine. Retained sample engineering review is available now; qualified publication and simulator integration follow the viable complete input contract, per M1_REAL_DATA_PLAN and M1_ACTION_QUALIFICATION_PLAN.

Acceptance still required: publish the immutable qualified snapshot and separately approved protocol seal; run all three baseline horizons at base/stress costs; reproduce exact trades and allowed numeric differences; verify pause/resume/stop history. On real-provider inputs, reject/diagnose future features, overlapping labels, duplicate rows, wrong adjustment, missing fills, stale bars and train-on-final access. Cash candidate must fail strategy qualification without threshold changes. Independent review and clean source/wheel/native receipts complete the gate. Current sample checks do not substitute for these future full runs.

The final adoption packet must bind qualified dataset, action, mapping/eligibility, sector and fee evidence plus resolved implementation/environment versions. The owner gate comes from BUILD_SPEC sections 10 and 17; ask once that packet exists. Existing data access and routine preparation require no repeat approval. Financial/protected/paper actions remain subject to their separate authority.
