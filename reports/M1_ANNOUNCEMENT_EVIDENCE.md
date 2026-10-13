# Dated dividend announcements

20 dated issuer releases are reconciled. The comparison adds 13 ExxonMobil links and 26 missing dates, and corroborates seven NVIDIA raw cash amounts. Full M1 remains incomplete.

| Result | Verified value |
| --- | --- |
| Provider dividends with issuer links | 285 of 317 |
| Still without issuer links | 32: UNH 14, XOM 18 |
| Cumulative missing date fields supplied separately | 298 |
| Remaining original missing record / payment dates | 16 / 16 |
| Original missing CUSIPs | 165 |
| NVIDIA raw amounts confirmed in this pass | 7 |
| NVIDIA amount differences still unresolved | 15 |
| Focused checks | 151 source; 151 installed wheel; no final failures or skips |

The 20 releases cover 13 ExxonMobil events in 2016-2019 and seven NVIDIA events in 2016-2017. All new comparisons reproduce exactly in both unchanged Python 3.14.7 environments. Product source is unchanged. The broad allocative native suite was not rerun.

## Interpretation limits

Five ExxonMobil releases combine a dollar sign with the word 'cents'. Their raw observations retain an unknown amount. Separate economic interpretations use the unambiguous 2018 second-quarter release plus explicit unchanged-quarter statements, or the 2019 second- and third-quarter filing tables. Both filing tables were extracted and visually inspected on PDF page 12. Later filings corroborate amounts retrospectively; they do not establish what was known on the announcement date. No exact historical timestamp is invented.

The seven NVIDIA releases explicitly state $0.115 or $0.14. Those values agree with the original provider cash amounts. Three corresponding history values cannot be inverted exactly because they are rounded. The original 22 history conflicts remain preserved; seven now have separate source-backed raw cash resolutions. This does not prove the vendor history's normalization convention.

All new ex dates remain provider claims. Unique association does not establish a complete identity/lifecycle history or financial qualification.

## Collection and failures

24 direct public requests used the frozen allowance. 22 returned complete HTTP 200 bodies. Two HTML filings returned HTTP 200 but exceeded the unchanged 2 MiB body limit; their partial bodies and failure receipts are preserved and rejected as usable sources. Smaller official PDF representations succeeded. No credentials or account endpoints were used.

Initial checks found a test expectation that omitted trailing whitespace in retained HTML. The expectation was corrected to the actual raw text. Both initial runs (145 passed, one failed) remain saved; extractor and result bytes were unchanged. The subsequent review found a misattributed XOM Q4 source and context-sensitive cents division. Both were reproduced and repaired. The original implementation and immutable result remain preserved. Final repaired runs each passed all 151 checks, including 24 announcement checks and 127 earlier regressions.

Independent repair review verified both findings resolved, unchanged economic values and exact v2 reproduction. Fresh preservation and storage checks are recorded in the closeout receipt.

## Remaining work

Resolve the remaining 18 XOM issuer links and 15 NVIDIA cash differences using dated primary sources. The 14 older UNH declarations remain a source gap. Then finish symbol/provider identity, lifecycle/tradability and a frozen dated sector table; collect 252 warmup sessions and integrate a qualified real Snapshot. Explicit protocol adoption is still required before sealing and real baseline execution.

No deletion, new spending, product or environment change, real strategy run, publication or Strata change occurred.

Data: `data/announcement-evidence-20261010-01`. Workflow and command receipts: `.cache/test-runs/m1-announcement-evidence-20261010-01`. Current v2 result SHA-256: `567b38ada2c6790f5ff5d061eef4f9d50c517c7761ff45c3553fd48e50bf4493`. The superseded v1 remains immutable. Canonical closeout: `artifacts/m1/announcement_evidence.json`.
