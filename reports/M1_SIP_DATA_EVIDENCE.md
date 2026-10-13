# M1 SIP evidence and exact split normalization

9 October 2026 ET. **The approved SIP sample and supporting data component are verified. Full M1 is not complete.** The owner-approved V20 credentials worked; no further credential or feed decision is pending.

## Measured result

Twenty frozen logical requests returned 26 HTTP 200 pages, with original bytes, explicit raw/split settings and terminal pagination retained. Each adjustment has 52/52 daily watchlist rows, three NVIDIA split-case rows, and 104/104 exact minute references. SIP fills all four IEX gaps: UNH November 20, JNJ November 24, HD March 10 and PG March 13, 2023, at 09:35 New York. Normal sessions, the November early close and the March daylight-saving transition validate against the locked calendar.

The collection ran in the existing Windows Job wrapper with one CPU thread and a 1 GiB memory cap: 16.64 seconds, peak 29,274,112 bytes, no remaining processes, no storage overrun. The client made market-data GET requests only. The original V20 file was unchanged and its values were not copied to project files. Client safety checks: 19 passed. The native success/process/HTTP-deadline fixtures from the preceding direct probe remain historical evidence; they were not rerun or presented as fresh here. This one-off probe does not qualify the future execution-owned credential transport.

## Implementation and verification

`src/compertum/data/alpaca.py` adds a bounded, pure evidence reader. It verifies exact request types and values, response hashes, status, receipt timing, page/token links, expected calendar rows, OHLC and numeric bounds. Missing rows remain explicit; duplicates, mixed feeds and protected-price dates are rejected. Normalization revalidates the original bytes before using immutable rows, so a forged in-memory row set is refused.

Split normalization uses exact fractions from raw prices and share quantities. Only declared events effective inside the normalization interval and available by the declared cutoff contribute. Future splits cannot change the earlier output. Missing/future required action knowledge refuses normalization. Provider-adjusted observations remain separate: in the actual SIP sample, July 21/20 raw-close ratio is 3235/3102, while the provider-rounded split-close ratio is 1941/1861. No tolerance was loosened.

NVIDIA's [May 21 announcement](https://nvidianews.nvidia.com/news/nvidia-announces-four-for-one-stock-split-pending-stockholder-approval-at-annual-meeting-set-for-june-3) describes the conditional four-for-one split and July 20 trading date. Its [June 7 SEC filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581021000075/nvda-20210603.htm) confirms the required authorized-share amendment was approved June 3. The [filing index](https://www.sec.gov/Archives/edgar/data/1045810/000104581021000075/0001045810-21-000075-index.html) distinguishes June 7 publication from June 4 acceptance. For this engineering example, we declare June 8 at 00:00 New York as a conservative publication bound. This is an explicit proxy, not exact first-known time, provider availability, or historical Compertum receipt.

- Source regression set: **135 passed**, zero failures/skips. Includes all 49 new importer cases plus unchanged synthetic data, baseline and prediction checks.
- Installed-wheel component set: **80 passed**, zero failures/skips.
- Actual retained sample: **318 rows validated in both environments**, no missing rows. Input, action-lineage and normalized-output hashes match exactly.
- Independent review: two boundary findings reproduced and repaired; narrow follow-up reports no remaining findings. Original failures remain retained. The actual sample also exposed a holiday handling issue, now covered by Thanksgiving/weekend tests; JSON object ordering was corrected separately.
- Final environment comparison initially counted the local project twice because the source import path exposes its setuptools metadata alongside the installed package. The corrected check requires exactly that one duplicate; all 39 unique package/version identities and the full package hash match. No dependency or interpreter was changed.
- No full-suite rerun or new native-runtime acceptance is claimed. Existing runtime files, specification, lock and prior acceptance evidence are preserved. Only the new reader and its new test module extend product/test source.

The output is explicitly `REAL_DATA_ENGINEERING_DIAGNOSTIC`, with `financial_accepted=false`, unknown action coverage and historical availability. It is not a Snapshot and is rejected by the existing synthetic snapshot validator.

## Remaining M1 dependencies

The independent action review found partial corroboration for the economic terms of all 11 sampled records. Six dividend ex-dates and the split due-bill date remain uncorroborated in the inspected official sources. A terminal page token does not establish complete provider coverage. See [action review](M1_ACTION_EVIDENCE.md).

A real strategy snapshot still needs comprehensive action/mapping/eligibility evidence, dated sector metadata, full 252-session warmup, and integration with the strict real-provider contract. The proposed real protocol needs explicit owner adoption before sealing under BUILD_SPEC sections 10 and 17. Data engineering checks do not waive these requirements. No real snapshot, protocol seal, strategy run, protected evaluation or M2-M6 completion is claimed.

Current evidence: [machine receipt](../artifacts/m1/sip_data_evidence.json), [checkpoint](../docs/CURRENT_CHECKPOINT.md), [remaining work](NEXT_STEP.md). Original and derived observations: `data/sip-probe-20261009-01`; verification scripts, logs, wheel and source archive: `.cache/test-runs/m1-sip-data-20261009-01`. Spending stayed $0.
