# M4 operator authority

11 October 2026. Verified local deterministic fake component; full M4 and financial acceptance remain incomplete.

Source and installed package each passed261 identical test IDs, with zero failures/errors and3explicit non-Windows-only skips. Each includes one actual-process, actual1GiBreserve case covering authenticated public control, lost reply/reconnect deduplication, checkpoint barriers, disarmed restart, new session supervision and halt. Small fixtures separately test native clock/health expiry, profile binding, ignored/corrupt writes and request replay. No operator command submits an order.

Frozen334files: source SHA256 e3f35790d3f98b2f5846ca32c145eb03e1954e04cfcd0d8942ba7e560338e6b9. Wheel SHA256 ede1548e1d6cc6fe1c2f99d9e7238b8cc03c2e3acabb85b936a7164116ddbede. All134 installed Python files plus configuration/schema/lock match. Independent authority review and subsequent snapshot repair review closed.

A native installed test found saved WAL snapshots creating unreserved journal files when read. The targeted repair switches only the saved copy to DELETE mode before fsync/hash; live owner databases retain WAL/FULL. The new native regression first reproduced the defect, then passed. Relevant persistence/recovery checks and both full restart paths pass after repair. No watchdog rule or capacity limit changed.

Evidence: artifacts/m4/operator_authority.json; .cache/test-runs/m4-operator-authority-20261011-01/authority-source03.*, authority-wheel03.*, authority-source03.json/zip, snapshot-review01.json; .cache/test-runs/m4-operator-native-20261011-01/operator-source02.* and operator-wheel02.*.

Preservation and capacity: both passing full-reserve fixtures were archived with every byte checked before disposable copies were removed. The failed installed fixture was moved intact into backups/failed-fixtures-20261011-01, with failure logs/XML retained in place and every hash/link verified. Earlier closed241pass/3skip fixtures were similarly preserved under backups/closed-fixtures-20261011-01 after the active small namespace exceeded64MiB. That failure remains recorded; its final measured size is53,138,832bytes. Restoration mappings are in failed-relocation01.json and closed-relocation01.json. All global category limits remain unchanged.

Next: docs/M4_PLAN_OWNER_INTEGRATION.md. Reserve the exact broker/attempt paths, then implement execution-owned observations and immutable plan approval/start. Bounded serial dispatch and full current-source recovery follow. No full M4, M5 or M6 acceptance is claimed.