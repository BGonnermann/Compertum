# Native paper-read integration

11 October 2026. Offline component verified. Actual account access and M5 acceptance remain pending.

- 746 matching passing test IDs in each environment: 745 regression passes plus one full native process test. Zero final failures or errors. One non-Windows refusal test is inapplicable on Windows and is not counted as verification.
- Independent review closed after three passes. Four reproduced defects were repaired: lost observed HTTP status, oversized durable summaries, ciphertext metadata recovery after a failed write, and unfinished publication after restart.
- Separate Windows processes used the actual allocated 1 GiB journal reserve. Six local HTTP reads produced encrypted evidence spanning multiple transfer chunks. A deliberately lost start reply did not repeat the reads. Restart retained the published result with zero new reads. Cancellation stopped a stalled request after one read.
- Grants bind operator, owner generation, plan, credential slot and reserved storage. They are consumed durably before the first GET. Restart does not replay them. Ciphertext remains with execution until verified durable publication acknowledgment.

Source archive: .cache/test-runs/m5-read-owner-20261011-01/owner-source02.zip, SHA256 8fcb47d082ed466cd8889d8ca2bcd5ef1db825d40eec4b0843d0303b8c1f5c34. Installed wheel SHA256 5874acd6d47c34e9abc8d0f3b0f7efe7150dc58280fbac5502dcaaea836fe948. All 156 installed Python modules match. Exact commands, XML hashes, native receipts and review hashes: artifacts/m5/read_owner.json.

Two native setup failures remain documented. Provisioning moved to a separate process to release native ownership; the initial execution store is now initialized before restart so its consumption guard exists. Product ownership and recovery checks were unchanged. Successful final source/package fixtures both cover normal shutdown and restart.

Storage admission initially exceeded its unchanged five-second limit. Generated test directories were compacted into fully verified, lossless archives; original failure logs and receipts remain. The two failed-tree duplicate cleanup receipts are failed-duplicate-cleanup01.json and failed-native-cleanup02.json in the read-owner test namespace. This preserved evidence and brought admission below five seconds. Final scan: 4.8384424 seconds, 13,973,598,640 bytes total project storage, 216,448,475,136 bytes free.

The native server used loopback HTTP with invented test credentials. Real Alpaca TLS, real credentials, account identity and financial conclusions remain unverified. M3 remains resource-blocked: observed available RAM 8,199,114,752 bytes, below the unchanged 8,589,934,592-byte floor. Next: reconcile remaining offline paper-write and M6 evidence work, then complete each independent requirement before requesting any concrete account scope.
