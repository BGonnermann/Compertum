# M5 market-owner repair

14 October 2026. The market-owner integration and its targeted recovery repair now pass the frozen source/package checks. Full M5 acceptance remains open.

## What changed

A valid busy-checkpoint reply closed healthy owner connections when it unwound nested recovery scopes. That caused a retained watchdog halt and prevented the next healthy generation. Validated, acknowledged refusal replies now preserve those connections. Malformed replies, wrong identities, transport errors and local failures still retire them. Recovery also requires the exact barrier-release acknowledgement and always closes its local snapshot connection.

The native test now records bounded startup observations outside the monitored runtime. It checks connection usability after the busy reply, lets the existing fixture deadline end that generation, verifies restart, and sends the deliberately forbidden command last. This proves controlled fixture termination and restart. It does not claim arbitrary crash recovery or successful checkpoint shutdown while FRESH views remain live.

## Fresh verification

| Frozen group | Source passed | Installed passed |
| --- | ---: | ---: |
| Calendar/import | 5 | 5 |
| Market integration | 216 | 216 |
| Account/related compatibility | 125 | 125 |
| Recovery-refusal regressions | 12 | 12 |
| Applicable owner-channel contracts | 35 | 35 |
| Actual native market lifecycle | 1 | 1 |
| **Total matching cases** | **394** | **394** |

All accepted runs have zero failures, errors or skips and zero remaining children. An additional 11 native remote-owner tests passed using source-backed child helpers; they are not installed-package evidence. One explicitly cloud-only owner-channel test was excluded before execution and is not counted as a native pass. Injected channel/refusal observations are simulated component evidence.

Both complete environments qualified against release07 with unchanged Python and dependency versions. The release contains 519 frozen inputs and 198 product modules. The native lifecycle took 83.110369 seconds from source and 82.806330 seconds installed. Maximum accepted Job memory was 400,207,872 bytes. The 120-second deadline, memory admission and process/resource limits were unchanged. Strata stayed off.

Each native lane created a real non-sparse 1 GiB reserve. Three loopback HISTORY requests were published despite a deliberately lost ACK reply. Restart recovered the same manifest without another HTTP request. Two FRESH requests supplied the composition; advancing fixture time made its age checks stale. A later restart invalidated completed FRESH authority, recovered HISTORY without recollection and rejected a public private-transfer request. Actual provider requests: zero.

The aggregate verifier passed in 6.343244 seconds under the unchanged full storage admission scan. It checked exact reviewed plans, matching case sets, source/wheel bytes, both environment qualifications, process closure, native receipts, preserved failures and input archives. Receipt: `artifacts/m5/market_owner_repair_pair_verified.json`, SHA `86c3fad24e6486347a0332eb821e727ea7a343f26b97c6da6a11d906a6452ac7`.

## Preservation and earlier failures

Accumulated passing fixture directories caused the storage-scan deadline failures. Under existing cleanup permission, 52 closed passing fixture roots were archived and verified before their temporary copies were removed. The archive retains 22,355 files, 11,368 directories and 1,212 link records. No failed fixture was selected. The full production scan then passed in 3.576421 seconds with its five-second limit unchanged.

All six failed native attempts remain recorded. Attempts 02–06 and both passing process07 fixtures were preserved by native rename, with every file byte and file/directory identity verified. Their historical paths remain historical; these copies are not resumed runtimes. Failed regression reproductions, earlier exhausted review rounds and three failed aggregate attempts remain intact. The new input archive retains 537 exact blobs for every repair plan, with no missing input.

Local evidence namespace: `.cache/test-runs/m5-market-native-20261014-01`. Source archive SHA `c9c60a889c77710594d012c12155731675513117e23156c4e0f6d011cfcb7533`; wheel SHA `53637580b197fa3aabeb48aab2fa9860eb7ce3f285853aa8755a9162032e679f`; repair-input archive SHA `53cbe305102d46f129170d780035136212a580c60103906740009b7154beca80`. Detailed runtime files, environments and backups stay outside Git.

## Remaining work

Final independent aggregate review is CLEAR3/3. It verified all 85 referenced artifacts, the exact case inventories and 537 retained source blobs across 28 plans. Review receipt: `artifacts/m5/market_owner_repair_review.json`.

The next local implementation is [durable FRESH/composed lineage](../docs/M5_MARKET_LINEAGE_PLAN.md), followed by journal/grant/risk/supervision integration and M6 semantic readers. Financial qualification, actual account/order authority and the supervised walkthrough remain separate gates. M6 remains at zero of ten actual supervised market sessions. M3's lost installed Final-audit receipt remains terminally blocked.
