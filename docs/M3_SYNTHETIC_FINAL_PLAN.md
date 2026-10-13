# M3 synthetic final transaction

Local generated-data engineering only. Real protected readers remain unavailable.

- [x] Bind a built-in generated recipe to the presealed holdout manifest. The fixture has partial training/scoring windows; financial evidence counts remain unmet.
- [x] Evaluation owner writes PREPARE_FINAL with fixed plan/initial checkpoint before consumption. Evaluation IDs are unique across seals.
- [x] Verify exact consumption guard and SQLite mirror before any batch work. Resume only the original ID and retained checkpoint; missing journal fails closed.
- [ ] Preserve attempts, terminal state and result pins in the append-preserved seal journal. Reserve all remaining attempt/terminal and live invalidation slots before consumption.
- [x] Empty shortlist consumes once and records NO_CANDIDATE_QUALIFIES without generating or reading prices.
- [ ] Nonempty batch runs fixed yearly fits/evaluations in existing bounded jobs, with no intermediate results returned to workers or coordinator proposals. No arbitrary paths, rows, metrics or candidate choices.
- [ ] Extend recovery artifact/lineage closure, operator controls, source/wheel/native acceptance and bounded independent review.

The current numerical development entry points explicitly refuse 2024+ rows. Preserve those guards. A final numerical path must accept only the fixed generator and journal-bound batch; a synthetic label on arbitrary rows is not provenance. Existing 120-second/4-thread/4-GiB worker and all storage limits remain unchanged. A failed or timed-out fixture remains unverified.

Reviewed ordering: durable initial checkpoint -> consumption event/head -> exact mirror verification -> durable attempt -> first generation/read -> complete bounded batch -> durable terminal result. Exact terminal readback cannot redispatch. Older database snapshots never reset the current journals.


## Current verification
final-transaction-green01:70 passes; final-crash01:37 passes; final-native01:19 passes. Counts overlap. Actual separate evaluation owner completes empty batch in0.269878sec,peak33124352B under268435456B; restart and barrier verified. Campaign worker receipts remain explicitly simulated. Nonempty dispatch/attempts/results, complete recovery closure, source/wheel and full campaigns remain unverified. Bounded review is running.

Resource scan resources04 failed5sec deadline with disposable test copies present; archived/byte-verified/removed both passing batches; resources05 passed4.690871sec. AvailableRAM8563376128B below8GiB worker floor. Original limits retained.

Review closed:4 red regressions reproduced missing/advanced consumption reservation and silently ignored PREPARE/COMPLETE mirror writes. Retry now checks the current next event grant; journal mirror SQL reads are bounded and exact readback is required. final-review-green01:80passes including real native RPC. Reviewed source frozen in R/final-source01.zip/json (268files); offline wheel built. Install01 failed because wrapper TEMP directory was absent; wrapper repaired, install02 passed with the same wheel. Consolidated source/package matrix in progress; exact next action: poll PTY92790, inspect XML, archive passing copy, then installed-wheel same IDs. No native final full-campaign acceptance yet.

## Nonempty batch implementation decision

Bounded independent review recommends a new presealed recipe with complete2024/2025 exchange calendars and the existing four-symbol synthetic fixture (AAPL,MSFT,JPM,SPY). Keep the12-stock denominator and missing-symbol omissions. Generate one continuous market with252warmup sessions,45initial training sessions and both full scoring years;2025 expands training from the same fixed initial start through2024. Exact symbols/sectors, price formula, availability and calendar version must be pinned in the recipe before the fresh source/wheel pair. Current31-session recipe has no nonempty execution implementation and cannot be reused under the new recipe.

Preserve public development-date guards. Extract only necessary private common cutoff, timing, date-purge and estimator arithmetic. The numerical final entrypoint accepts the owner-derived plan and generates inputs internally; no user paths/rows or allow-protected flag. Reuse replay/feature/prediction arithmetic through a narrow internal serving hook. Keep explicit fit provenance and all purged dates, no intermediate annual feedback.

Use qualification.py unchanged: compound yearly returns rather than concatenate reset NAV levels; offset annual checkpoint and completed-interval identities, retaining halt/boundary semantics. Compact shared data/fits instead of six embedded candidate reports; retain costs10/20, raw decisions/fills/predictions/omissions and bootstrap evidence. Verify worst-case3ridge batch against120sec/4GiB/16MiB with no budget changes. Full universe, full training coverage, financial acceptance and independent final audit remain unverified.

Versioned replay: new seals use fixed recipe v2. Journal replay derives the recipe solely from the presealed hash and preserves v1 plan/checkpoint bytes. v1 remains readable, including empty terminal records, but cannot enter nonempty generation. The closed generator loads validated snapshots through Dec30 and appends only its eight fixed Dec31 daily/close rows. Canonical terminal bytes, base market and recipe hashes bind the result; no2026price rows, unchanged16MiB input limit.

11October2026 active verification: recipe/market/source fit increments passed; full generated batch initially exceeded16MiB at20,312,149bytes. Fixed-path columnar tables preserve every JSON value and expanded hash; encoded cap remains16MiB, decoder expansion bounded32MiB and200000records, numerical processes only. Current full-batch roundtrip and arithmetic checks passed in green02; table-column mutation failure reproduced and corrected,8refusal regressions pass. Review found missing recorded-NAV return comparison and malformed-runtime/nil-ID admission;4red regressions fixed. Combined broad audit command timed out150seconds and stays unverified; run split suites, no enlarged limit. Next: reviewer closeout, frozen source/package split matrix and exact result reproduction; then owner attempt/result/recovery integration. No complete M3/native batch/financial claim.

## Durable nonempty continuation contract, 11 October

Next coherent increment: strict append-preserved START_FINAL_BATCH, INTERRUPT_FINAL_BATCH and TERMINATE_FINAL_BATCH transitions. These are journal contracts only until the native launcher and evaluation-owner validation are connected. Their inputs must bind the consumed plan, initial checkpoint, attempt ordinal, TaskSpec, exact reserved output and native identity. Two attempts share 120 seconds of active elapsed time. A retained interruption permits only the second attempt; a terminal rejection, stop, exhausted budget or completed publication never redispatches. No numerical decoding in owners.

Acceptance order: transition regressions first, journal replay/headroom integration, independent review, then native dispatch/result/recovery controls. Four reserved slots cover START1/INTERRUPT1/START2/TERMINAL2. Compute remaining capacity after the proposed transition; retain all live-seal invalidation slots. An interrupted attempt must have a proved exited process; missing proof keeps it non-resumable. Terminal publication must reference an immutable, streamed-verified frame and current native exit evidence.

Native mapping reviewed: add a generated-final mode to runtime/jobs.py and runtime/campaign_worker.py; keep campaign_worker as the registered template; verify committed coordinator TaskSpec/reservation and owner START both before launch and before Resume. Existing private synthetic_protocol RPC is already authenticated and barrier-gated. Extend supervisor tick/pause/shutdown and full recovery export/validation/restore, including current journals and final artifact closure. A small final controller owns this integration. Do not infer admission from the pure journal contract or generated output.
