# Four passed test folders preserved

15 October 2026. **Stage A is complete. Eight backup files and their index passed independent verification. All four original folders remain intact. Zero files were removed.**

The owner approved a one-time maintenance exception with no new scratch files, followed by archive creation and verification. Independent source review cleared the helper and launch controls in round 2 of 3 before the job ran. This approval does not cover removal, administrator access or security changes.

## Copies and unchanged originals

The destination is `backups/fixture-consolidation-20261015-01` inside master. Each row has a `.contents.tar.gz` file and a `.properties.json.gz` file with the stated prefix. The ninth file is `index.json`.

All original paths below begin with `.cache/test-runs/`.

| Original folder | Backup prefix | Compressed contents | Compressed properties | Combined allocated bytes |
| --- | --- | ---: | ---: | ---: |
| `m3-pair-validation-repair-20261013-01/source_native01-pytest` | `root-00` | 818,049 | 48,145 | 868,352 |
| `m3-review-health-20261013-01/installed_native11_r2-pytest` | `root-01` | 113,230 | 16,119 | 131,072 |
| `m3-review-health-20261013-01/source_native11_r2-pytest` | `root-02` | 112,886 | 16,060 | 131,072 |
| `m3-pair-validation-repair-20261013-01/source_green01-pytest` | `root-05` | 23,812 | 13,082 | 40,960 |
| Total | Eight payload files | 1,067,977 | 93,406 | 1,171,456 |

The complete measured backup charge, including the index, destination directory and any increase in its parent directory, is **1,179,648 bytes**. This leaves 393,216 bytes within the approved 1,572,864-byte ceiling. The index contains 4,050 logical bytes. Its SHA-256 is `e479b5b150ccc4fb0769ada11bc1c713789b4ba615847ae3b95f220e85640af0`.

The helper checked every expected archive name, file length, file hash, empty directory, frozen inventory and fresh properties record. It rejected duplicate or extra members, damaged checksums, incomplete compressed streams and trailing data. It closed and reopened every output through checked Windows handles. An independent process then reopened and checked all eight payloads and the index again. Neither check extracted files or recreated links.

All 1,827 original entries remained present: 1,098 files, 718 directories and 11 links. Their contents, native identifiers, creation and modification times, attributes, readable owners, groups, access rules and raw link records matched. Access times may reflect inspection. The copies preserve historical evidence under the owner's choice. They do not promise missing audit rules, original Windows file identities or a runnable environment.

## Fresh capacity and bounded execution

The job obtained a new complete snapshot before writing. It counted 110,705 files, 29,334 directories and 1,638 links in master. All retained links were readable, with zero incoming dependencies on the selected roots and zero unresolved chains. Incoming links outside master remain unproved. The actual coordinator database had zero reservation rows and no sidecar journals; its bytes stayed unchanged. The real 1 GiB execution reserve remained fully allocated and unchanged.

Starting backups used 21,473,134,560 bytes. Adding the actual archive charge gives 21,474,314,208 bytes, leaving 522,272 bytes below the 20 GiB category ceiling. Before writing, the helper instead charged the full 1.5 MiB maximum, leaving 129,056 bytes. It also held the preparation's 8 MiB allowance, 2 MiB for publication and one cumulative 16 MiB execution allowance under records. No future deletion credit was used.

The fresh scratch measurement was exactly 5,369,020,008 bytes, still 310,888 bytes over its 5 GiB limit. There were zero outstanding scratch reservations. The helper refused a larger starting measurement or any new scratch reservation. All helper output, temporary paths and receipts used backups or records, with bytecode writes disabled. Its zero-scratch-growth result describes its own writes, not a second whole-category census after completion. Ordinary admission and requested-clone updates remain stopped.

The native Windows Job used one CPU and a 128 MiB memory limit. It exited with code 0 in 59.788703 seconds under the 75-second parent deadline. Peak Job memory was 55,275,520 bytes. Process exit was observed and zero children remained. The outer launch took 60.7029702 seconds without a timeout. Host memory stayed above the required stop threshold. The reviewed launch checks found no competing research or model job. They permitted the separately identified idle website server.

The independent reopen check completed in 1.2368011 seconds under its ten-second internal deadline. Its parent observed exit code 0 in 1.8796861 seconds. The check matched all 471 frozen inputs, including 217 source and 217 installed program files, plus 65 original reports and 112 historical receipt fingerprints. Product code, interpreter and dependencies were unchanged. Strata remained off.

## Validation and retained failures

Fifteen in-memory format and limit checks passed, with zero failures or skips. One native allocation check passed, with zero failures or skips. These are archive-helper checks. No product tests ran: zero passed, failed or skipped cases. The four folders' 26 passing cases remain historical results.

The initial nine-check stub run had eight expected failures and one pass. Its output remains saved. The first native check incorrectly expected unused preallocation to remain after file closure; Windows reduced it. That failed check and its fixture remain saved. The corrected check proved initial allocation, refusal before crossing the write limit, preserved bytes and bounded final allocation. No failed real archive attempt occurred, and no attempt label was replaced.

The source review's first round required a competing-process check, an exact scratch baseline, separate reporting for partial files and a current input manifest. The second round cleared those repairs. Every earlier review, manifest and check remains in the same evidence folder.

## Saved evidence and stop

Private execution evidence is `artifacts/m5/fixture-consolidation-execution-20261015-01/`. It contains the owner approval, reviewed source fingerprints, complete snapshot, maintenance allowance, original properties, archive hashes and process-exit records. Backups and detailed local evidence remain outside Git.

| Record | SHA-256 |
| --- | --- |
| Frozen 471-file input manifest | `8c396479237ce270f7985cc9ce1cb53612ff1f70dc8ac61d5437af8ad5da0841` |
| Archive helper, `tools/fixture_archive.py` | `ebf5ccf066a71672811b6cddab219f090d69306e02cb495dd71775967f4fdcef` |
| Child result, `archive-result.json` | `4039688694a4289243ff2ed9f06571b5277e83dc00c75b9926fc825eeb8617c4` |
| Native parent closure, `stage-a-closure.json` | `d28486f8333a38ccbb3ab9f00947c4556f302386498d1ca6a5af2514db51af5c` |
| Independent verification, `independent-verification.json` | `5b955917c2dc863334442f8d6cf8bcad35fd9c777043e939ff09b1f4926f1c50` |

The approved procedure had SHA-256 `1bcc8d42524a45514c6f17e9ebd09fdb0aac5bbcd29954b1d17159c7b0ea37a8` at master commit `793e8a68ca8eaff152852f8fabe44d29531ff2b1`. The completion update changes documentation intentionally after independent verification; it does not change that frozen execution record.

Work stops before Stage B. Removal requires separate approval naming these four roots and the verified copies, accepting the historical-copy limits and addressing the master-only incoming-link scope. The [execution procedure](../docs/FIXTURE_CONSOLIDATION_EXECUTION_PROCEDURE.md) retains those requirements. It supplies no current removal authority.

No production scanner check ran. Scanner experiment rounds 1 through 12 remain used. Reader19 remains 34 drafts and zero executed cases. M5 requirements 2 through 5 remain open; M6 remains zero of ten actual supervised sessions. The requested clone stays at `e903f8d20600fc6233105a83c0383634207adfb2` while scratch admission is blocked.
