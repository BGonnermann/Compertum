# Saved-run retry policy correction

Final reconciliation found that the saved-run library allowed three attempts per replay, exceeding BUILD_SPEC section6's two-attempt limit. It also allowed deterministic data errors to be retried. Both behaviors are corrected. No acceptance threshold was lowered.

Each fixed replay now allows at most two attempts total. An I/O interruption or abrupt owner loss remains eligible for explicit resume. Invalid data, exhausted output budgets and unknown computation exceptions mark the run FAILED and refuse resume. No automatic retries or parameter changes occur. The API remains a synchronous library; supervised worker resource enforcement and terminal integration are still pending.

Verification evidence is in `.cache/test-runs/m1-run-policy-20261009-01`; final measured counts and identities are in `artifacts/m1/run_policy.json`. Red tests retain the original failures: `RUN_INTERRUPTED` instead of `RUN_ATTEMPT_BOUND`, and two deterministic failures returning `RUN_INTERRUPTED` instead of `RUN_FAILED`. The independent saved-run reviewer found no further material issues after repair.

Final checks: 14 source tests and 14 installed-wheel tests passed. Four real Windows crash/stop tests passed in each environment. All final checks had zero failures and zero skips. Eighteen recovered outputs match across source and wheel, with each also compared to an uninterrupted replay. The source and wheel package hashes match. Exact command arguments and durations are retained in `commands.jsonl`; JUnit files are `source-final.xml`, `wheel-final.xml`, `native-source.xml` and `native-wheel.xml`.

Checkout: `C:\Users\bgonn\Desktop\Compertum-development`, repository `BrennanCompertum/Compertum`, branch `local/m0-development`, published base `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781`. Current implementation remains uncommitted and unpublished; the receipt and source archive identify the tested changes.

The original saved-run and prediction receipts and source archives remain unchanged. Their test counts describe their respective source stages. This correction receives a separate source identity, wheel, source archive, logs, JUnit files and receipt. Prior run identities cannot silently accept changed code.

Python remains 3.14.7 with the existing 39 distinct locked distributions. Builds and installation use existing tools offline. No Strata request, external data, trading, training, spending, publishing or service launch is part of this repair. Full M1 and financial acceptance remain incomplete.
