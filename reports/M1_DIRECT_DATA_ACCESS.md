# Direct Alpaca data verification

9 October 2026 ET. The owner authorized using the existing Alpaca entries in Desktop/v20/.env. Direct read-only access succeeded. The file was unchanged, credential values were never copied, and a scan found no actual key values in the 135 evidence files inspected at the first audit. The final receipt records a fresh scan after closeout.

## Measured results

| Check | Result |
| --- | --- |
| Frozen requests | 22 logical requests, 28 HTTP pages; every response HTTP 200 |
| Endpoint scope | GET to data.alpaca.markets/v2/stocks/bars and /v1/corporate-actions only |
| Dates/feed | Development dates in 2021/2023; explicit IEX, USD and asof |
| Original responses | 38,665 exact uncompressed HTTP-body bytes retained with hashes and actual retrieval times |
| Adjustments/pagination | Explicit raw and split requests; all 22 chains ended with an observed null next_page_token; daily queries deliberately exercised multiple pages |
| Daily sample | 52/52 watchlist rows plus three split-case rows for each adjustment |
| Minute sample | 100/104 rows for each adjustment; the same four distinct missing IEX entry minutes |
| Calendar | Nine exchange sessions checked, including early close and DST cases |
| Actions | 11 returned records: nine dividends, one split and one merger; provider coverage and first-known times remain unverified |
| Client safety tests | 19 passed, zero failures/skips; fake credentials and no external requests |
| Native controls | One CPU thread, 1 GiB cap, assigned before execution, peak job memory 29,155,328 bytes; live collection 17.93 seconds; zero surviving processes |
| Deadline checks | Local process timeout passed; a separate local fake HTTP request was stopped by its ten-second request timer before the outer process deadline |

All four missing entry references are 09:35 New York: UNH on 2023-11-20, JNJ on 2023-11-24, HD on 2023-03-10, PG on 2023-03-13. Raw and split queries agree on these gaps. Previous individual connector rechecks also returned no row. No alternative minute, feed or invented price was substituted.

## New adjustment finding

The original split-adjusted NVDA responses are rounded. For 19 July 2021, raw close 751.07 becomes 18.78 while volume is multiplied by 40. Multiplying that returned price by 40 gives 751.20, not 751.07. On 20 July, raw close 186.055 becomes 18.61 with a volume factor of 10. The specified 2021 asof date did not limit the retrospective adjustment to the in-window 4:1 split.

Even the ratio between the two post-split closes differs: the adjusted ratio minus the raw ratio is approximately -0.0003598862. Thus successful raw/split requests do not establish the required invariant features. The current strict snapshot contract also checks consistent adjustment factors through the snapshot horizon; these provider values cannot simply be renamed into that contract. Keep original provider observations, preserve raw prices for accounting, and design/verify explicit normalization before admission. No tolerance was loosened and no data were admitted.

Alpaca documents adjustment selection separately from asof symbol mapping and complete page-token traversal. See [historical bars](https://docs.alpaca.markets/us/reference/stockbars). Complete pagination proves capture of the provider-returned records, not that every applicable corporate action exists in the source. Alpaca does not guarantee immediate action publication; first-known times remain absent here. See [corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1).

## Review, repairs and preservation

Independent review found no material client or evidence-binding defect. It identified the adjustment-rounding issue and corrected one overbroad action-completeness status. The final status is UNVERIFIED_PROVIDER_COVERAGE, including inside the requested dates. The original analysis is retained alongside the corrected version.

The first harmless native fixture exited before the Job accounting query reported zero active processes. The runner now observes the same bounded three-second drain used by the existing product runtime, still requiring zero active processes. Its success and timeout checks then passed. The failed command and original runner remain preserved. Live collection required no retries.

This is a one-off, bounded data probe. It does not qualify the future execution-owned credential transport or create a production fetch command. Runtime source, tests, original checkout and previous acceptance receipts remain preserved. New spending is $0. No account/order endpoint, training, protected/reserved price window, Strata change, commit, publication or further deletion was used.

## Remaining dependencies

The missing-access blocker is resolved. Full M1 remains incomplete because minute coverage, adjustment normalization and corporate-action coverage/knowledge are not qualified. The sample also lacks baseline warmup and no real protocol was adopted/sealed.

The owner has been asked to choose whether to test historical SIP access at $0 using the same existing key, or keep IEX and retain its gaps. The data plan requires this explicit profile choice. No answer has been assumed. Even a successful SIP sample would not itself resolve adjustment, action or full-M1 acceptance requirements.

After that choice, freeze the appropriate request manifest, verify the selected feed, complete the evidence-backed importer/normalization plan, and continue snapshot/protocol/baseline work only when their inputs qualify. The source credential file may be read for this authorized work without another credential-location question; never print its values.

Evidence: data/direct-probe-20261009-01/; .cache/test-runs/m1-direct-data-20261009-01/analysis.json, safety.xml, native Job receipts, independent-review.md and final-verification.json. Canonical receipt: artifacts/m1/direct_data_access.json. Current work: docs/CURRENT_CHECKPOINT.md and reports/NEXT_STEP.md.
