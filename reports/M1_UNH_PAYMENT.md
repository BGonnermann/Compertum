# UNH March 2017 dividend: resolved

**Reconciled payment date: March 21, 2017. Record date: March 10. Cash dividend: USD 0.625 per share.** The earlier quarantine is preserved as history; the new derivative fills the final missing UNH payment date.

## Evidence that resolves the discrepancy

1. [S&P Capital IQ announcement, published February 9, 2017](https://www.marketscreener.com/quote/stock/UNITEDHEALTH-GROUP-INC-14750/news/UnitedHealth-Group-Announces-Dividend-Payable-on-March-21-2017-35203882/): explicitly separates March 10 record and March 21 payment dates and states USD 0.625.
2. [UnitedHealth issuer archive](https://www.unitedhealthgroup.com/investors/archive.html): the Q1 2017 entry agrees with those terms.
3. [Hemsley Form 4, filed March 23, 2017](https://www.sec.gov/Archives/edgar/data/731766/000120919117022585/xslF345X03/doc4.xml): the March 21 transaction footnote identifies paid dividend equivalents on deferred and restricted stock units.
4. [Issuer 2017 proxy](https://www.unitedhealthgroup.com/content/dam/UHG/PDF/investors/2016/UNH-2017-Proxy-Notice-Shareholders.pdf), PDF page49 / printed45: Hemsley SERP deferred-stock-unit dividend equivalents are paid at the same rate and time as shareholder dividends.

The Form 4 reports a combined DSU/RSU transaction. It does not establish that all489.157 units are SERP units, and that quantity is not used to infer the cash dividend. The evidence supports the shareholder payable date; it is not a shareholder account settlement ledger.

## Contrary evidence and inference

The [Q2 10-Q](https://www.sec.gov/Archives/edgar/data/731766/000073176617000028/unh630201710-q.htm) and retained issuer Q3 10-Q both label March10 as Payment Date. Both observations remain in the new artifact, alongside the earlier quarantine and untouched provider original. March10 is expressly the record date in the dated announcement. A record-date substitution in the quarterly tables is the likely explanation, **an inference rather than a formal issuer correction**. No formal correction was found.

This is a narrow evidence-based adjudication for one event. General conflict rules and every other unresolved field remain unchanged. See [case policy](../docs/M1_UNH_PAYMENT_ADJUDICATION.md).

## Provenance and verification

The announcement and Form 4 were read successfully in the ordinary browser. Their retained excerpts explicitly identify current rendered DOM and model-mediated transcription. They are not relabeled as original HTTP responses or as 2017 retrievals. The separate direct requests returned HTTP403 and remain recorded as failures. The issuer proxy was retained as a complete HTTP200 PDF. Google presented a CAPTCHA; Bing located the dated announcement. A Fintel mirror presented a security check and was not used as evidence. An unrelated advertising redirect was left without interaction.

- 56 source checks passed; 56 installed-wheel checks passed; zero failures, errors or skips. These include16 new adjudication checks and40 prior alternative-source checks.
- Both actual artifacts reproduced byte-for-byte in the existing environments. Product source and environments are unchanged.
- New result SHA256: `bb26261d5d85dbd12fb0db3648f22dafc47a9a1e53891c38e85ab6278b7c5351`.
- New qualification SHA256: `ed643887fc4e53156d7d9db977bd2c5de802990adf9db6c66c170d69515de82a`.
- Bounded independent review clean:21 pinned inputs and fresh in-memory reproduction verified; no actionable defect.

All317 inventoried dividends remain associated. All14 missing UNH payment dates are now recovered:13 uncontested plus one adjudicated. Cumulative date fills:316. Two record-date and three declaration-date discrepancies remain recorded; four displayed-precision differences are unchanged.

**Full M1 is incomplete.** Remaining requirements: historical action coverage/knowledge, historical mapping/eligibility, dated fees, full252-session warmup, qualified real-provider integration, final protocol adoption and real baseline/control tests. No financial input acceptance, strategy execution or historical provider arrival was invented.

Run: `.cache/test-runs/m1-unh-payment-20261010-01`. Data: `data/unh-payment-20261010-01`. Receipt: `artifacts/m1/unh_payment.json`; final capacity/preservation check is separately retained. Existing limits unchanged. No spending, credentials, price requests, account/order actions, deletion, publication or Strata changes.
