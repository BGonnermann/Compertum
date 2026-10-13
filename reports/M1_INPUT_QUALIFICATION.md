# M1 input qualification follow-up

10 October 2026 ET. **Two missing ExxonMobil declarations obtained. Real sample checks pass; full M1 remains incomplete.** Current receipt: `artifacts/m1/input_qualification_followup.json`; run `.cache/test-runs/m1-input-qualification-20261010-02`.

| Result | Verified evidence |
| --- | --- |
| Dividend reconciliation | 303 of 317 linked; four additional dates, 302 cumulative date fills; 14 UNH events remain unresolved |
| Original sources | Six direct public attempts; five complete HTTP 200 bodies; one archive-index deadline failure retained |
| Retained real sample | All 13 symbols; 55 raw daily and 104 raw minute rows; normal, early-close, DST, split and missing-price cases checked |
| Automated verification | 240 passed in source and 240 in installed wheel; zero final failures, errors or skips; 24 new checks |
| Actual outputs | Both new artifacts reproduce exactly across environments |
| Review | One independent reviewer; no material defect in the new helpers/results |
| Qualification | Rejected: payment/event gaps, unresolved conflict, incomplete action knowledge/coverage and historical eligibility/mapping |

The issuer sitemap exposed the missing XOM 2018-Q1 and 2019-Q1 declarations. Original bytes and exact requests are retained. 2019's literal `$0.82 cents` remains unknown as a raw amount; a separate source-bound unchanged-quarter chain supports the economic $0.82 interpretation. These links use unique declaration-to-record intervals; they do not independently establish provider ex-dates. No intraday availability is invented.

UnitedHealth's 14 unmatched events remain in [the ledger](M1_REMAINING_INPUTS.md). Its 2017-Q3 filing says March 10 was a payment date; the current history says March 21. Neither overrides the other. Sitemap, archived-source attempt, dated searches and relevant annual-meeting filings did not supply a reliable new binding or resolve that contradiction. Search failure does not prove that no source exists. Cached and secondary leads are discovery only; detailed provenance is retained in the run's `discovery.md`.

The real-input review consumes pinned original provider evidence, action inventory, metadata, economic reconciliation and sector proposal. It verifies all four minute sessions and exposes a deliberately removed execution row and rejects a wrong adjustment. Exact NVDA split normalization reproduces the prior result; a later-split fixture leaves it unchanged. Actual retrieval stays distinct from simulated historical availability. Only four consecutive daily sessions are present, far short of the required 252. Sample coverage does not establish complete 2016-2023 coverage.

Record dates, optional CUSIPs, SIC/GICS and exact original provider arrival are not universal qualification requirements. Record dates support the current association route. Current provider IDs do not prove historical continuity; required effective symbol mapping and then-available eligibility remain to qualify. XOM's 2026 successor cannot silently stand in for its predecessor. SPY exchange wording and absent JPM SIC do not automatically block the whole dataset. The sector table is a dated proposal.

The new helpers are verification workflows, not a real Snapshot adapter. Product source and environment are unchanged. Qualified real snapshot publication, 252-session warmup, real-provider simulator integration, protocol adoption, three real baseline horizons and their full deliberate-failure/control tests remain unfinished. The plan requires a viable input contract before full collection/integration; qualified records cannot be manufactured to bypass this dependency. [Prepared protocol draft](../docs/M1_REAL_PROTOCOL_DRAFT.md) records the proposed settings and later acceptance checks without adoption or sealing.

Verification retained expected red tests, two fixture-correction rounds and a transient storage scan deadline failure. First corrections handled omitted fields and duplicate identical prose; the remaining failure was a mutation that changed no bytes across an HTML newline. The corrected mutation asserts changed bytes and the final suites pass. The storage scan passed on one isolated retry with its five-second limit unchanged. Preservation and final measured storage are recorded in the receipt/postflight; earlier native acceptance is historical, not rerun here.

Next action: obtain a reliable dated UNH source containing explicit event terms sufficient to bind the 14 listed provider events, including an authoritative resolution of the March 2017 payment disagreement; retain/hash its original response, then rerun a new reconciliation and qualification version. Independently qualify applicable historical mapping, eligibility, action coverage/knowledge and dated fee inputs. Only then freeze full collection requests and implement/admit the real Snapshot adapter. Present the final concrete protocol for explicit adoption before any real strategy execution.

No new price requests, credential use, orders/account calls, paid sources, protected/reserved prices, deletions, commits, publication or Strata changes. $0 new spending.
