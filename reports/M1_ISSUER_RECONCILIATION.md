# M1 issuer reconciliation

Updated 10 October 2026 ET. The bounded issuer-evidence workflow is verified. Full M1 remains incomplete.

The new derived evidence fills 201 absent dividend dates across the retained provider inventory. It adds three SPY distributions missing from that inventory and uses State Street's exact amount for the June 2020 difference. Original provider responses, issuer files and every disagreement remain unchanged.

| Evidence | Result |
| --- | --- |
| Public file collection | 24 serial requests: 19 HTTP 200, two 302 redirects, two 403 responses and one 406. Failed/redirect responses retained; no credentials used. Web research and factual extracts are separately labeled. |
| Extracted issuer observations | 236: 224 history rows across AAPL, HD, JNJ, JPM, MSFT, SPY and UNH; four dated announcement observations; eight NVIDIA tax-form payment observations. |
| Event association | 211 observations associated, including three issuer-only SPY rows. They link to 206 distinct provider dividends. Twenty observations use a unique declaration-to-record interval; that association does not independently prove the provider ex-date. |
| Derived field changes | 201 filled record/pay dates, one exact SPY amount replacement and 12 economic fields for the three missing SPY records. Total 214 distinct field changes. |
| Source disagreements | Five exact comparisons retained. Four MSFT XLSX values display as $0.56 under their explicit two-decimal currency format. UNH's dated announcement supports provider payment on 28 June 2022; its current history says 29 June. Separate interpretation file explains all five. |
| Verification | 118 source checks and 118 installed-wheel checks passed, zero failures/skips. Includes 27 focused issuer checks and 91 existing provider/action checks. Actual reconciliation and interpretation files reproduce byte-for-byte. |
| Review | One independent reviewer; corrected an Exxon timestamp description and completed a targeted recheck. No remaining material findings in the reviewed scope. |

SPY's 32 development-period distributions now have source-backed economic terms, including the December 2023 distribution payable 31 January 2024. This resolves the economic omission without a further provider query. It does not establish historical announcement timing.

MSFT's raw XML contains 0.56000000000000005 in four cells. The separate interpretation checks each cell's actual number format and records its displayed 0.56. The original exact comparison is preserved; no blanket rounding tolerance was introduced. For UNH, the [dated issuer announcement](https://www.unitedhealthgroup.com/newsroom/2022/2022-06-08-unh-shareholder-meeting-board-actions.html) supports 28 June. The retained web fact extract is not represented as an original HTTP response.

P&G's April 2016 release says its payment is on or after 16 May, so only a lower bound is recorded. NVIDIA's two retrospective tax forms establish eight payment dates and a common-stock identifier, but lack amounts, ex-dates and record dates. All eight stay unbound because the provider records lack corresponding payment dates. Exxon explicitly corrected a record date from 9 to 10 February 2017; its displayed timestamp and HTML datetime attribute disagree, and that discrepancy is retained.

## Remaining input requirements

- 111 provider dividend records have no issuer association: NVDA 32, PG 31, UNH 17 and XOM 31. The UNH history supplies partial facts for those 17, but association remains unverified. Do not infer an ex-date or count an absent event as zero.
- Among the original 317 provider dividends, 64 record dates and 65 payment dates remain absent after the supported fills. The original 165 missing provider CUSIPs remain missing. Source identity claims are kept separately; no historical eligibility was inferred from them.
- The 163 declaration-date observations are source claims, including duplicate corroboration of two events. Exact historical provider arrival remains unavailable. BUILD_SPEC permits documented announcement/knowledge evidence where available; exact provider arrival is not an invented additional prerequisite. A complete usable timing convention still needs sufficient source evidence and protocol adoption.
- Historical listing/tradability, unresolved mappings and dated sector metadata are not established by these dividend sources. The original action inventory's unrelated META ETF and six acquirer-only mergers remain classified as before.
- The 252-session warmup, qualified real Snapshot, explicit owner protocol adoption, three-horizon real baselines and full M1 acceptance remain. Financial admission stays false.

Direct collection reached its predeclared 24-request bound. Failed source access and unavailable facts are explicit limitations; this report does not claim the remaining records cannot be found elsewhere. Next evidence work must target the recorded gaps under a new frozen manifest, not repeat unchanged requests. Keep existing credential/feed authority; no renewed routine permission is needed.

## Reproduction and preservation

Working scripts/tests, commands, initial failures, review and archive are in `.cache/test-runs/m1-issuer-reconciliation-20261010-01`. Data and source receipts are in `data/issuer-reconciliation-20261010-01`. The canonical receipt is [issuer_reconciliation.json](../artifacts/m1/issuer_reconciliation.json). Product source and both locked Python environments are unchanged. No allocative native suite was rerun; this work adds an offline evidence workflow, not runtime behavior.

The first storage preflight hit the unchanged five-second scan deadline; the unchanged repeat passed at 3.960 seconds. Initial Apple decimal/month parsing failures are retained and corrected with focused checks. The workbook inspection's initial protocol-relative URL failure and the no-request follow-up failure are also retained. No failed command is counted as a pass.

New spending remains $0. No credentials, account/order calls, protected price queries, seals, strategy execution, training, Strata changes, commits, publication or deletion in this increment. See [checkpoint](../docs/CURRENT_CHECKPOINT.md) and [reconciliation policy](../docs/M1_ISSUER_RECONCILIATION_POLICY.md).
