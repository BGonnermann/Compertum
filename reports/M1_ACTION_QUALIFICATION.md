# M1 action evidence: qualification result

The action reader works on the retained inventory; that inventory is not sufficient for an accepted real snapshot. All outputs remain engineering diagnostics. Existing credential and SIP access are verified and require no renewed approval.

## Observed inventory

Eight successful authenticated GET requests cover process years 2016-2023, all action types, data_quality=all, region=us, the frozen 12-stock/SPY watchlist and the issuer-confirmed FB alias. The eight terminal pages contain 329 unique actions: 317 cash dividends, four forward splits, two name changes, five cash mergers and one stock merger. Original bytes, hashes, dates and complete request/page bindings are retained.

165 records lack CUSIPs, 165 lack record dates and 169 lack payable dates. None supplies verified historical provider arrival or first-known time. Current retrieval time is preserved and is never backdated. Missing fields are explicit, not inferred from process date.

The identity diagnostic has 157 matches to the declared table, 165 unknowns, one symbol/identity conflict and six counterparty-only mergers. Most declarations originate in the same provider inventory and are not independent historical eligibility evidence. A matching CUSIP/alias does not establish tradability, historical sector or action knowledge.

## Issuer reconciliation

The [State Street historical distributions workbook](https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx), linked on its [distribution page](https://www.ssga.com/us/en/institutional/resources/documents/etf-dividend-distributions), supplies 32 SPY ex-date observations for 2016-2023. Original 581,242-byte workbook SHA-256: b162dd17027d1128f2209e312b0f634960daa78319dafe0ab821ab0b7e77ce23. This current historical file verifies economic terms, not publication dates or historical receipt.

Comparison yields 14 complete declared-field matches, 14 incomplete provider records, three missing provider records and one exact amount conflict. No matching subset establishes full coverage.

| Ex-date | Issuer amount/share | Record date | Payable date | Retained provider result |
| --- | ---: | --- | --- | --- |
| 2016-03-18 | 1.049604 | 2016-03-22 | 2016-04-29 | Missing |
| 2018-06-15 | 1.245568 | 2018-06-18 | 2018-07-31 | Missing |
| 2020-06-19 | 1.366242 | 2020-06-22 | 2020-07-31 | 1.3662419: exact difference 0.0000001 |
| 2023-12-15 | 1.906073 | 2023-12-18 | 2024-01-31 | Missing from frozen 2016-2023 process windows |

Three additional frozen SPY-only year requests reproduce all nine corresponding provider records exactly. They confirm the 2016/2018 omissions and 2020 amount conflict are not removed by isolating the symbol. The amount difference is tiny; it remains unresolved rather than being rounded away. December 2023 needs later process-window closure; this increment makes no 2024-2026 authenticated action queries. Total authenticated attempts: 11, all HTTP200, below the original 40-attempt ceiling. Two serial native jobs share the original aggregate time/request/body budgets; each is confined to one CPU and 1GiB, with no surviving child.

## Ticker identity and merger direction

[Meta Platforms' May 31, 2022 announcement](https://investor.atmeta.com/investor-news/press-release-details/2022/Meta-Platforms-Inc.-to-Change-Ticker-Symbol-to-META-on-June-9/default.aspx) establishes FB-to-META on June 9 with unchanged CUSIP. The earlier META-to-METV record belongs to Roundhill, supported by its [January 14 SEC supplement](https://www.sec.gov/Archives/edgar/data/1683471/000089418922000256/meta497etickerchange.htm) and [fund details](https://www.roundhillinvestments.com/etf/metv/), CUSIP 53656F417. It is excluded from Meta Platforms' lineage.

The five cash mergers and DEN-to-XOM stock merger identify watchlist companies as acquirers. Existing acquirer shares are not converted as if they were acquiree shares. Missing economic dates in name-change provider records remain explicit; process dates do not substitute for issuer effective dates.

## Verification and next dependency

Verification passed: 177 source/regression tests and 122 installed-wheel tests, zero final failures/skips; 42 new action cases and 22 separate client safety passes. Actual inventory and SPY outputs match byte-for-byte across both Python3.14.7 environments with the same39 unique locked distributions. Independent review is complete after the identity fix and a final depth16 normalization guard. The latter has a retained failing boundary test followed by passing checks. The full allocative suite was not rerun: this additive data module was checked against relevant data, simulation and prediction regressions within the unchanged scratch budget. See artifacts/m1/action_qualification.json for source/archive/environment, preservation and storage evidence. Retained failures include the expected missing-module red test, the malformed identity regression, and an issuer-extraction assertion corrected to compare numeric zero exactly (the workbook contains 0.000000).

The qualified-input contract is not yet satisfied. Complete held-position action terms, identities and documented knowledge are required before collecting the full warmup into a real Snapshot. Historical eligibility and dated sectors remain unverified. Protocol adoption under BUILD_SPEC sections10/17 is a separate gate before seal and real strategy execution. No claim of full M1 or financial acceptance follows from these diagnostics.

Data: data/action-coverage-20261009-01. Commands, tests, scripts and review: .cache/test-runs/m1-action-coverage-20261009-01. Original checkout, earlier receipts and observations are preserved. No spending, account/order requests, protected prices, training, Strata changes, publishing or deletion.
