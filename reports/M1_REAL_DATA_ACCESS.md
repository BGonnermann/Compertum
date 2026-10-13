# M1 real-data access check

9 October 2026 ET. The owner approved the bounded, read-only, $0 data-verification increment. Alpaca access works. The sampled data are not qualified for a real baseline or full M1 acceptance.

## What ran

33 serial connector requests used development dates in 2021 and 2023. No historical prices from the protected 2024-2025 period or reserved 2026 observations were requested. The probe used the existing connection without reading API keys. Current asset metadata are explicitly current, not historical eligibility evidence.

Requests were frozen before each batch. Original connector envelopes and actual receipt times are retained under `data/access-probe-20261009-01/`. These are the exact responses delivered by the connector, not the provider's original HTTP bodies. The checksum index is in `.cache/test-runs/m1-real-data-20261009-01/evidence-index.json`.

| Check | Measured result |
| --- | --- |
| Current watchlist asset identity/status | 13 of 13 returned active/tradable with distinct asset IDs |
| November daily sample | 52 of 52 expected rows across four sessions |
| Exchange calendar | Nine sessions matched the locked calendar, including an early close and the DST transition |
| Exact minute references | 100 of 104 returned: all 52 closing references and 48 of 52 entry references |
| Missing-minute confirmation | Each of the four gaps was also absent in a separate single-symbol request |
| Split evidence | NVDA 4-for-1 action effective 20 July 2021 returned; three surrounding daily bars retained |
| Corporate actions | 11 unique actions returned across the probes; completeness and first-known times remain unverified |
| Input-rejection regressions | 15 passed, zero failures/skips; 16 unrelated cases deselected |
| Saved-evidence checks | Six deliberately invalid cases rejected; actual sample structure, timestamps and request bindings checked |

## Confirmed minute gaps

All four are the required 09:35 New York entry reference on the explicit IEX feed:

| Session | Symbol |
| --- | --- |
| 20 November 2023 | UNH |
| 24 November 2023 | JNJ |
| 10 March 2023 | HD |
| 13 March 2023 | PG |

No other minute, daily price or feed was substituted. These observations establish gaps in this sample, not a claim that every possible IEX backtest is unusable. The sample cannot establish the complete execution-reference coverage required for the intended real-data fixture.

## What prevents the next dependent tasks

The connector's stock-bar tool exposes neither an adjustment selector nor page-token controls, and its returned payload does not expose adjustment or page-completion evidence. Corporate-action results also omit page tokens and first-known times. Prices retain more than two decimal places, but original upstream numeric precision is still unverified. The native request timeout and resource controls cannot be inspected through this connector. Do not infer them from a fast successful response.

Alpaca's underlying API documents explicit raw/split adjustment selection and pagination. Those features are absent from this connector's callable interface. See [historical bars](https://docs.alpaca.markets/us/reference/stockbars). A direct read-only connection or original raw export is needed before extending the strict input path around real-provider evidence.

Action queries use process dates. The November query alone did not cover later payments tied to November ex-dates. A separately frozen follow-up through December returned that additional evidence. No absent action was treated as zero. Completeness and historical availability remain unverified; the provider also warns that action publication can be delayed. See [corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1). The sampled NVDA split is consistent with [NVIDIA's 2021 announcement](https://nvidianews.nvidia.com/news/nvidia-announces-four-for-one-stock-split-pending-stockholder-approval-at-annual-meeting-set-for-june-3).

No direct connection was found in the five conventional environment-variable names checked, or in a project `.env` or `credentials` directory. Other credential locations were not searched. The owner has been asked whether an existing direct connection or raw export is available. This is a missing-access question, not a request to approve the same work again.

## Scope and next action

Read-only data authorization is granted. Confirm the existing direct connection or export location without putting key values in chat. Then verify original response precision, explicit raw/split adjustments, pagination and action provenance. Keep IEX gaps unresolved unless a separately adopted data profile supplies valid references. No silent feed change or paid upgrade is allowed.

Real-provider import, a sealed real snapshot, baseline replay and complete M1 acceptance remain blocked by these dependencies. No real data were admitted to the synthetic-only engine, no strategy protocol was sealed, and no real baseline was run. The small sample also lacks the 252-session warmup needed for a baseline; expanding collection before resolving the input contract would not fix the blocker.

Product source, tests and installed package are unchanged. The read-only validation script initially failed because the request manifest used short connector tool names while invocation records used fully qualified names. Normalizing only the fixed connector namespace repaired the audit; every argument remains compared exactly. The original script and correction receipt remain preserved.

New spending was $0. No account/position/order calls, broker writes, training, protected evaluation, Strata changes, further deletion, commit or publication occurred. Independent review and final storage/preservation checks are recorded in the final receipt.

## Requirement-to-evidence reconciliation

| M1 requirement | Evidence and remaining work |
| --- | --- |
| All 12 stocks plus SPY; feed/schema; normal/early-close/DST/split/missing-row cases | Current identities, 52 daily rows, nine sessions, split record and four individually confirmed gaps checked. Explicit IEX retained. Historical eligibility and full interval coverage remain unverified. |
| Raw and split-adjusted bars; complete pagination and source precision | Blocked: current connector exposes neither adjustment selection nor page completion or original HTTP bodies. |
| Exact minute execution/valuation references | All 52 sampled closing references returned; 48/52 entry references returned. The four missing cases above remain unresolved; no guessed fills. |
| Corporate-action coverage and knowledge | Eleven unique returned records checked. Full coverage, original lineage and historical first-known times remain unverified. Unknown actions are not zero actions. |
| Immutable snapshot and adopted protocol seal | Offline publication already verified. Real snapshot/import and owner adoption/sealing remain pending, dependent on qualified source evidence. |
| All three baseline horizons and reproducibility | Offline six normal/stress runs previously verified; current source still bound to those receipts. No qualified real baseline run. Sample lacks full warmup. |
| Pause/resume/stop preserving history | Previously verified offline, including 17/17 final native checks in both environments. No new runtime source changes or real run in this increment. |
| Duplicate row and wrong adjustment refusal | Included in the 15 fresh synthetic admission regressions. They confirm existing refusal, not real-provider support. |
| Future feature, overlapping label, missing fill, stale bar, train-on-final refusal, zero/cash qualification rejection | Existing component evidence remains retained; complete full-M1 mapping and real-provider integration checks are pending. No claim that the 15 focused cases cover this entire list. Reconcile every named case before full acceptance; do not query protected prices to test refusal. |
| $0 bounded reads and preserved authority | 33 serial development-only calls and original envelopes retained. No new plan, feed, permissions or spend. Connector-native timeout/resource enforcement remains unverified and is not a production ingestion receipt. |

All independent review actions are now addressed in this report, NEXT_STEP.md and CURRENT_CHECKPOINT.md. Final integrity/storage measurements are retained in artifacts/m1/real_data_access.json; no full-M1 pass is claimed.

Final preservation checks passed: 131 source files and the existing tracked default configuration are unchanged; all eight saved data files match their hashes; both Git indexes and seven preserved files match prior receipts. Native storage stayed within every unchanged category cap, with about 7.6 MiB scratch remaining before the small closeout receipts. The final storage check is retained as final-postflight.json.

The closeout verifier initially found that the older source manifest omitted the existing config/default.toml. It was corrected to verify that exact additional file against its tracked Git version, preserving the original failed log and script. No configuration, source, acceptance limit or test requirement changed.
