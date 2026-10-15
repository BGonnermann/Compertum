# Original-folder removal stopped before deletion

15 October 2026. **The approved removal attempt stopped during preflight. All four originals and all eight backup files plus their index remain unchanged. Zero entries were removed. The production storage-admission scan has not run.**

The owner accepted the historical-copy limits and master-only incoming-link scope, approved the four specific removals, and required helper review before execution. Independent source review cleared the corrected helper in round 2. The attempt then completed its full inspection but refused to begin removal because of an extra time-margin check in the helper.

## Why removal did not start

The fresh complete inspection took 60.8339889 seconds. The helper required the first removal to begin before 60 seconds, leaving ten seconds within the 70-second internal deadline. After its additional archive and original checks, that requirement failed with `INSUFFICIENT_TIME_BEFORE_FIRST_REMOVAL`.

I added this extra start condition while building the helper. The approved procedure already required a 70-second internal deadline, a 75-second parent deadline and durable records if work stopped partway through. The additional condition prevented the intended removal even though permissions and the measured capacity checks passed.

The child exited with code 1. The parent observed exit in 64.2673502 seconds, with a 58,089,472-byte peak under its one-CPU, 128 MiB Job limits. Zero children remained. The outer launch finished in 65.2017449 seconds without a timeout. No removal manifest, per-entry journal or removal-result file was created. The failure and every completed inspection record remain saved.

No automatic retry ran. The approved procedure prohibits automatic retries after failure. The remaining records allowance is also insufficient for another complete copy of the inspection and the full removal journals while preserving this failure.

## Independent proof of unchanged evidence

A separate read-only audit finished in 1.9627 seconds. It checked the complete member sets, identifiers, contents, creation and modification times, attributes, readable access rules and raw link records for all 1,827 original entries. All four roots, 1,098 files, 718 directories and 11 original links remained unchanged. Access times may reflect inspection.

The audit reopened and strictly verified the eight backup payloads and index. Their hashes and identifiers still match Stage A. It also verified the other 1,627 retained master links, all 711 frozen inputs, all 217 source and 217 installed program files, 65 original group reports and 112 receipt fingerprints. The coordinator bytes and full 1 GiB execution reserve remain unchanged. No other evidence was removed, and Strata stayed off.

Private evidence remains in `artifacts/m5/fixture-consolidation-execution-20261015-01/`. The refused attempt uses its original names and identifiers. Earlier review candidates, manifests, checks and failures remain there too.

| Saved record | SHA-256 |
| --- | --- |
| Frozen 711-file inputs | `e480f9fb40193544ab520467e61ca057108e846ce1c8c364f376f142f37e0edc` |
| Reviewed removal helper | `036cdd92b6aec62637ee78d012ac5e4ad785c4ca962c132c37f7fe6050638261` |
| Failed parent closure | `46523ebcf0fcfcda9860b6017f315ecf84b763aae95dbd7606b0077bd4ffa754` |
| Independent unchanged-original audit | `1e3fb48923ee9b3038c416be657d817ef268ca934daf26e01ce7e0cd0743aa45` |

These execution inputs bind the documentation at commit `00719a1a02f5e31d51267c6085d974d8772f4b82`. The later failure-report publication intentionally updates five status documents after the independent audit. It does not rewrite the attempt or its saved evidence.

## Current measured storage

The completed inspection found zero unreadable entries, unknown streams, unresolved links or incoming dependencies inside master. The owner has already accepted the master-only link scope. Links outside master remain outside this check.

| Storage group | Complete observed bytes | Category ceiling |
| --- | ---: | ---: |
| Backups | 21,474,314,208 | 21,474,836,480 |
| Scratch | 5,369,020,008 | 5,368,709,120 |
| Records | 1,130,611,896 | 5,368,709,120 |
| Data | 0 | 16,106,127,360 |
| Models | 0 | 5,368,709,120 |

Scratch remains **310,888 bytes over its limit**. The helper created no scratch files and did not use future deletion credit. The current backups still charge 1,179,648 bytes within the approved 1.5 MiB ceiling.

The actual coordinator database has no `reservations` table and therefore no reservation rows. The read-only preparation explicitly handles that state. The admission-check adapter now does the same and records table absence; it creates no schema or grant. That corrected adapter has not run its production scan.

The independent audit measured 10,520,288 charged bytes in the execution folder. Against the original 301,352-byte baseline, cumulative growth is 10,218,936 bytes, leaving 6,558,280 bytes within the original 16 MiB allowance. A further attempt needs room for another full inspection, a complete member list, per-entry intentions/results and closure evidence. Existing failed evidence must stay in place.

## Preserved stop and unexecuted admission check

`state/watchdog/halt.json` already contains the reason `STORAGE_UNHEALTHY`. Its bytes remain unchanged, with SHA-256 `b8ab6b68c7f7a514d518b9b8eba963060e58c5794fa156b264d8a9698142dca8`. The production watchdog treats an existing stop file as `RETAINED_WATCHDOG_HALT`.

The reviewed check distinguishes a current inventory/capacity result from ordinary admission blocked by this preserved stop. It evaluates the full records hold together with actual reservations in the unchanged capacity function. It uses one actual production scan, the unchanged five-second limit and the original volume callback. Removal did not complete, so this later check remains unexecuted. No stop file, permission, ownership or privilege changed.

## Verification and next decision

Thirteen in-memory removal checks passed, with zero failures or skips. The read-only native access check retained all 1,827 deletion-capable handles together and verified every original without making a removal call. A second native check verified all backups and 1,627 other links. The complete-record size check also passed. No product tests ran: zero passed, failed or skipped cases.

The initial 13 stub failures remain saved. Source review caught an oversized index read, incomplete combined records accounting and the preserved watchdog stop. A primary schema check caught an unconditional query against the absent reservation table. The source fixes and direct read-only checks passed before the approved attempt; their earlier versions and diagnostics remain intact.

The [bounded recovery proposal](../docs/FIXTURE_REMOVAL_RECOVERY_PROPOSAL.md) is prepared for a separate decision. It proposes one additional attempt and 8 MiB more cumulative execution records while retaining the existing 32 MiB folder ceiling and every category, CPU, memory, disk and scan limit. No further attempt is currently authorized by the no-retry procedure. The four-folder removal scope and accepted preservation limits do not need to be chosen again.

Ordinary work and clone updates remain stopped. Scanner experiment rounds 1 through 12 remain used; no round 13 occurred. Reader19 remains 34 drafts and zero executed cases, M5 requirements 2 through 5 remain open, and M6 remains zero of ten actual sessions.
