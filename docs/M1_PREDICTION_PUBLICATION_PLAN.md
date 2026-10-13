# Saved prediction publication implementation plan

Use executing-plans, primary implementation and one bounded independent review. Owner authorized autonomous execution and follow-up on9October2026. Follow BUILD_SPEC unchanged; no commits or publication. Execute after supervised replay receipts are frozen.

Goal: save three fixed prediction reports alongside the six trading replays, with the same immutable inputs, explicit stepping, bounded worker and restart behavior.

Design: keep existing six-unit runs unchanged. New runs with explicit scoring_as_of freeze a normalized UTC cutoff and a nine-unit format into inputs.json before hashing. Units0-5 remain the original H/cost replays; units6-8 are prediction H1/5/21 without duplicate cost variants. Every dispatch, result header, path, completion count and acceptance check uses the frozen typed unit schedule. Changed cutoff creates a new request identity and cannot replace an existing run.

Worker: extend the fixed registered template, preserving the same two inherited handles and no SQLite ownership. Prediction calls score_predictions with the frozen cutoff. A distinct small header binds method, horizon, cutoff, input hash, payload size/hash and synthetic status; use .prediction files. Parent verifies header and payload digest without loading numerical libraries or decoding bulk data. Publication and checkpoint acceptance retain owner-held grants and immutable artifacts.

Limits: new nine-unit runs use90seconds per attempt, two attempts/unit, including interrupted attempts. Eighteen attempts plus existing six-second cleanup allowance each consume at most1728seconds, below30minutes. Existing six-unit runs retain120seconds/attempt. Four CPU threads,4GiB RAM, one heavy worker,16MiB output/attempt and unchanged64MiB default/128MiB maximum aggregate bytes. Every incomplete reservation remains fully charged. No new dependency, network, account, Strata, real-data, training or financial capability.

- [x] Tests first: legacy six-unit compatibility, normalized cutoff/hash conflict, nine fixed units, wrong cutoff/horizon/input-hash rejection and three unique reports.
- [x] Extend SavedRuns and worker record/dispatch with frozen schedule; support existing synchronous library path without duplicating unit policy.
- [x] Native nine-unit completion matches pure replay/scorer bytes. Prediction-stage pause/crash preserves prior replay artifacts, second attempt and terminal/budget bounds. Installed-wheel results match source.
- [x] Independent review and at most three repair rounds; retain failed and passing receipts, exact source/wheel identities and final storage measurement. Update roadmap/handoff/progress.

Before each batch, check remaining5GiB scratch capacity. Use a fresh .cache/test-runs namespace. Preserve older archives, results and original project. Refuse new writes when the documented budget cannot fit; never delete evidence or raise limits to make tests pass.

9 October completion: implementation, review, source/wheel checks and all nine fresh reserve-backed recovery checks pass. All 502 current source test IDs reconcile to 491 unique passes and 11 Windows-inapplicable skips. The owner conditionally approved removal of two old test reserves; passing tests and matching backups were verified before removing exactly those two files. All required items in this component are complete. See reports/M1_PREDICTION_PUBLICATION.md. The 1728-second arithmetic is the maximum sum of admitted worker attempt reservations, including cleanup allowance; it is not a measurement of operator waiting or end-to-end interactive session duration.
