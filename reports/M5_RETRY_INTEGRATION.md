# M5 collection retry integration

14 October 2026. The prepared retry changes are integrated in master. Exact source/installed verification passed: 521 matching case IDs in each environment, zero failures, errors or skips in the accepted results. Independent closeout review cleared on pass 1 of 3, checking 52 evidence pins, both environment qualifications, installed modules and preserved fixtures.

The existing market collector now retries eligible HTTP responses with bounded waiting. It retains every attempt, advances a page only after a validated success, and preserves the original deadline, cutoff, queue priority and request limits. Version 2 encrypted evidence records the attempt chain; version 1 remains readable. Unclassified native transport failures are still terminal. No account, order or actual provider request was made.

## Current verification

The new product has 192 modules, with 496 frozen release files. Python 3.14.7 and all 38 dependencies remain unchanged. Both complete environments qualified against the corrected source archive. The exact selection contains 521 unique cases in each environment.

The first source run passed all 521 original assertions, but inspection found that the purported full-reserve test created metadata reservations only. The test was corrected to physically create and reopen the default non-sparse 1 GiB journal reserve. A subsequent run passed the other 520 cases but failed an overly strict comparison of Windows allocation sizes: allocation fell from 1,135,542,272 to 1,073,741,824 bytes after close. Both meet the requirement. The final assertion keeps capacity, unused bytes, sparse status and file size unchanged and independently requires at least 1 GiB physically allocated before and after restart.

Only that test function changed; all 495 other frozen files and every other function in its module match the preceding release. The retained 520 source results therefore have explicit byte/AST continuity. The corrected source case passed, and all 521 installed-package cases passed freshly against the final test release. The source total uses the 520 explicitly reconciled results plus that fresh corrected case; it does not count the failed predecessor.

The eight accepted groups took at most 48.692 seconds each, below the 120-second limit. Peak job memory was 785.813 MiB under the 4 GiB limit. Minimum observed free host memory was 47.863 GiB; commit headroom was 80.313 GiB. All child processes closed. Both actual reserve cases created and reopened a physically allocated, non-sparse 1 GiB file.

Final local receipt: `artifacts/m5/master_retry_verified.json`. The reconciliation command exited 0 without timeout, memory stop, namespace overflow or monitoring error. The first environment qualification invocation was rejected because it loaded the helper as an unapproved file; the established inline invocation passed unchanged validation. That failed command remains preserved.

## Preservation

The failed full-reserve fixture remains under `backups/m5-retry-source-reserve-failed-20261014-01/fixture`. Its original prefix was `.cache/test-runs/m5-retry-native-20261014-01/source_actual_reserve02-pytest/test_reopened_prior_generation0`. Every file byte and file/directory identity was verified unchanged. The original pytest convenience link remains stationary as a historical pointer. All failure logs and XML remain in the original tooling folder.

Windows refused a directory rename while descendant lock handles were held. The reviewed recovery recorded a brief unlock, performed one native rename, immediately reacquired both locks, then verified no unexpected process and exact identities/content. It does not claim continuous exclusion. No files were deleted and no runtime was resumed from backups. Passing source and installed reserve fixtures were preserved by the same checked native-rename procedure under `backups/m5-retry-source-reserve-passed-20261014-01/fixture` and `backups/m5-retry-installed-reserve-passed-20261014-01/fixture`.

Evidence lives in `.cache/test-runs/m5-retry-native-20261014-01`; detailed local receipts are excluded from Git. The review is bound to the final result in `artifacts/m5/master_retry_review.json`. Next is opening-baseline integration, including a genuine process/owner-generation restart check and compatibility tests. M3's missing installed Final audit, financial qualification and actual paper/M6 session gates remain open.
