# Alpaca exact-ID check

10 October 2026 ET. **Alpaca returned all 14 missing UNH dividend events, but supplied no additional fields.** The new original JSON records exactly match the earlier inventory. Every record includes amount and ex-date but omits payment and record dates. This is a source-data omission, not a parser loss.

One GET to the documented market-data corporate-actions endpoint used the 14 exact event IDs. HTTP 200; 2,402-byte original response; terminal pagination; all requested IDs and symbols verified. The current [official API reference](https://docs.alpaca.markets/us/reference/corporateactions-1) documents ID lookup and excludes combining IDs with date/symbol/quality filters. The earlier eight annual inventory requests and three SPY rechecks had not exercised this route. No broader date filter, price query or broker/account endpoint was used.

The request succeeded, but it did not resolve any missing economic fact. Coverage remains 303/317 linked dividends, with 14 UNH event/payment gaps and the previously retained source contradiction. Other mapping/eligibility/action knowledge/coverage dependencies are unchanged. We cannot claim that every possible Alpaca service was exhausted; this receipt covers the current market-data endpoint's original inventory and exact-ID retrieval only.

Verification: 13 focused checks passed in source and 13 in installed-wheel environments; zero failures/errors/skips. All eight original inventory body hashes verify, and all 14 new records match originals field-for-field using exact decimal parsing. The native Job ran with one CPU and a 1-GiB limit, exited successfully with no child left. Existing V20 key was loaded privately, unchanged and not copied/logged. No spending, financial action, source/environment change, deletion, commit or publication.

Evidence: `data/alpaca-ids-20261010-01/comparison.json`; receipt `artifacts/m1/alpaca_id_check.json`; run `.cache/test-runs/m1-alpaca-ids-20261010-01`. The initial storage scan exceeded its unchanged five-second deadline; isolated retry passed. Final capacity/preservation results are in the receipt/postflight.

Next evidence needed is a reliable dated source providing the UNH payment terms and an unambiguous event binding, with resolution of the March 2017 payment disagreement. Repeating the same Alpaca filters is not expected to fill fields absent in both verified responses. Full M1 and financial acceptance remain incomplete.
