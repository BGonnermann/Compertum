# Original grant consumption and owner-bound market capture

14 October 2026. **291 identical checks passed in each source and installed-package environment**, with zero failures, errors or skips and all child processes closed. This local component records original grant-consumption observations and resolves capture inputs directly from their execution owner. Encrypted lineage publication and its native restart/ACK integration remain pending. No full M5 or financial acceptance; M6 remains0/10 actual supervised sessions.

## Behavior

Each newly started market job now saves an immutable UTC/monotonic consumption observation in the same execution transaction as its irreversible consumed state. The original exclusive60-second predicate is rechecked immediately before that transaction. Both writes must be verified and committed before producer construction. Ignored writes roll back both changes. Constructor failure retains the committed evidence; repeated start never dispatches twice. The existing grant v1/job v1 schemas stay unchanged.

An internal capture operation accepts a trusted subject, job and expected grant hash. It resolves the original FRESH/HISTORY records and their consumption proofs itself, then captures and reconstructs the original bytes. It rechecks those records, health and credentials after capture. Older consumed records without proofs stay readable; they cannot satisfy the new evidence claim. No timestamp is inferred or backfilled. Historical reconstruction never restores freshness or transport authority.

Live clock/health/credential refusals invalidate unusable FRESH resources. Invalid identities and missing legacy proofs do not revoke an otherwise usable view. If cleanup cannot be confirmed, the retained producer continues to block replacement and checkpointing. Original consumption records remain unchanged.

## Verification

| Cases | Source | Installed |
| --- | ---: | ---: |
| New consumption contracts/storage |29|29|
| New owner-bound capture |21|21|
| Existing grant/record contracts |116|116|
| Existing market owners |30|30|
| Existing publication/transfer/routing |50|50|
| Existing owner FRESH and capture foundation |45|45|
| Total distinct cases |291|291|

These checks use native Windows ownership, DPAPI and loopback WinHTTP where applicable, with invented provider data. Owner recreation is exercised in-process; this is not a new multi-process lineage restart claim. Capture adds no HTTP request or storage reservation. Both complete environments qualified with unchanged Python/dependencies. Release09 freezes525 inputs and201 exact product modules. Maximum accepted job83.835640seconds; peak226406400bytes. Existing120-second/4GiB/fourCPU limits, host memory gates, storage caps and deadlines remain unchanged. Strata was not started.

Initial missing-feature regressions:29 contract and16 owner failures, zero errors/skips. Review1 found missing refusal cleanup; the added regression run produced16 passes and5 failures, zero errors/skips. The correction passed all21 owner cases. Implementation review2/3 is CLEAR; final aggregate review3/3 is CLEAR. All failed evidence and exact input versions remain preserved.

## Local receipts

Source namespace N=`.cache/test-runs/m5-market-native-20261014-01`; installed namespace O=`.cache/test-runs/m5-lineage-package-20261014-01`. Detailed local evidence stays outside Git.

- Aggregate: `artifacts/m5/market_consumption_pair_verified.json`, SHA256 `19b5bea29cc05ae58ddf27ff3e9e45abc350140ae41d6f93fb7a0e1eb9e1ec94`.
- Release: `N/release09.json`, SHA256 `3c9ca72af49af584da92274a28d57f19bb4940f955cde9b732fe3b09b237ba2c`.
- Source archive: `N/source09.zip`, SHA256 `944cf445b6ef4ed1ae4b14059faae0629b16641f2b2cfe9e899cc7485949daa5`.
- Wheel: `N/wheels09/compertum-0.0.1-py3-none-any.whl`, SHA256 `d0ac47064f105591267b956a94d153850ff15330cd6b1524ea55595836f82e0b`.
- Environment manifests/proofs: `N/market09-{source,wheel}-manifest.json`, `N/qualify-{source,wheel}09.log`; exact bindings are in the aggregate.
- Accepted plans: `plan_ownerlineage_final09.json`, `plan_consumption_{final,contracts,owners,publication,integration}09.json`; identical hashes in both namespaces.
- Retained inputs: all48 plans/554 exact source blobs in `N/iteration-sources09.zip`, SHA256 `59c852de3f0a57e38e72f48b7e8d94622ab5767e6b80a866616314d161de6da2`; no missing input.

No failed runtime identity was resumed or reset. Existing preserved full-reserve fixtures remain untouched; this increment created no additional1GiB fixture. Actual provider/account/order requests remain0.

Next: [encrypted publication and recovery](../docs/M5_MARKET_LINEAGE_PUBLICATION_PLAN.md), including separate capture identity, genuine coordinator reservation,32KiB transfer, manifest-before-ACK persistence and historical reopening. Full durable lineage remains incomplete until that contract is verified.
