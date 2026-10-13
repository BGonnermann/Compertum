# Alternative UNH dividend sources

10 October 2026 ET. **Recovered explicit ex/payment pairs for all 14 missing UNH events. Thirteen uncontested payment dates are now recorded in a separate evidence version. One March2017 payment remains quarantined.** The 317/317 count means events have source associations, not that every event or the complete dataset is financially qualified.

Original HTTP200 HTML is retained from [Morningstar](https://lt.morningstar.com/1c6qh1t6k9/stockreport/default.aspx?ClientFund=0&CurrencyId=CAD&Id=0P000005NU&SecurityToken=0P000005NU%5D3%5D0%5DE0EXG%24XNYS&tab=1&vw=div), [StockScan](https://stockscan.io/stocks/UNH/dividend-history) and [DividendHistory](https://dividendhistory.org/payout/UNH/). Each target ex-date appears once in each table; all three give the same payment date. These are current published vendor observations; underlying feed independence and historical arrivals are unknown. Morningstar explicitly labels row currency USD despite the CAD URL parameter. Its day/month format is parsed separately from StockScan's month/day format.

The issuer archive now binds through the explicit alternative ex/payment pair plus exact issuer cash. Four Morningstar amounts display0.63 where the provider, other tables and issuer report0.625. Original displays remain separate; exact Morningstar cash and its rounding method are not inferred. Two record-date and three declaration-date disagreements stay visible. Only payable dates are filled; original provider values are never replaced.

| Provider ex-date | Corroborated payment date | Disposition |
| --- | --- | --- |
| 2016-03-09 | 2016-03-22 | Separate payment-date fill |
| 2016-06-15 | 2016-06-28 | Separate payment-date fill |
| 2016-09-07 | 2016-09-20 | Separate payment-date fill |
| 2016-11-30 | 2016-12-13 | Separate payment-date fill |
| 2017-03-08 | 2017-03-21 | Quarantined: filed payment differs |
| 2017-06-15 | 2017-06-27 | Separate payment-date fill |
| 2017-09-07 | 2017-09-19 | Separate payment-date fill |
| 2017-11-30 | 2017-12-12 | Separate payment-date fill |
| 2018-03-08 | 2018-03-20 | Separate payment-date fill |
| 2018-06-15 | 2018-06-26 | Separate payment-date fill |
| 2018-09-06 | 2018-09-18 | Separate payment-date fill |
| 2018-11-30 | 2018-12-13 | Separate payment-date fill |
| 2019-03-08 | 2019-03-19 | Separate payment-date fill |
| 2019-06-14 | 2019-06-25 | Separate payment-date fill |

The March2017 issuer filing reports payment on March10; current issuer history and all three tables say March21. A cached February24,2017 [Becker's report](https://www.beckerspayer.com/payer/quarterly-shareholder-payouts-for-the-big-5-payers/) also describes March21 and links the original issuer announcement. Direct Becker retrieval returned403. The original issuer URL redirects to the general newsroom. Two exact archive-availability lookups returned no snapshot. The retained issuer2017 annual report confirms quarterly amounts on PDFpage32/printedpage30, visually checked, but does not resolve the payment date. No global source-absence claim is made.

Verification: **293 source and293 installed-wheel tests passed**, zero final failures/errors/skips. This includes40 new alternate-source checks and retained real-sample checks: all13 symbols, early close, DST, exact split normalization and missing-price behavior. Both artifacts reproduce byte-for-byte. Independent review found no actionable defect. Expected red failure for the absent helper is retained; focused tests then passed. A report-writer quoting error is retained and corrected separately; it did not affect product code or evidence. The initial storage scan exceeded the unchanged five-second deadline; isolated retry and pretest scan passed. Final capacity/preservation is in separate postflight.

Collection used11 serial bounded public requests: six HTTP200, three403, one301 and one connection error. Only complete correctly identified bodies support admitted observations. No credentials, account/broker/order requests, spending, new price query, product source/environment change, deletion or publication occurred. PDF extraction used the existing bundled runtime; project interpreter and dependencies did not change.

**Full M1 remains incomplete.** Revised qualification rejects financial use. One payment conflict, complete action coverage/knowledge and historical mapping/eligibility remain unresolved; applicable dated fees still need verification. The sample has four consecutive daily sessions. Full252-session warmup and provider-snapshot/simulator integration follow a viable input contract. Explicit protocol adoption is required before real strategy tests. These engineering passes do not replace dependent acceptance tests.

Evidence: `data/alternate-sources-20261010-01/alternate-evidence.json` and `real-input-review.json`. Receipt: `artifacts/m1/alternate_sources.json`. Run: `.cache/test-runs/m1-alternate-sources-20261010-01`. Prior source bodies and receipts remain immutable.

Next exact evidence action: retain a genuinely new original issuer declaration, exchange notice or correction explaining the March2017 discrepancy, then rerun immutable reconciliation and qualification. Qualify remaining historical action/mapping/eligibility and dated fee evidence. Repeating current sources cannot establish missing facts. No date guessing, ticker removal, threshold change or automatic protocol adoption.
