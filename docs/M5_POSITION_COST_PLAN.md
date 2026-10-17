# Recorded-fill position costs

Status: the pure calculation is verified. Source and installed inventories each passed 102 matching cases.
Both complete environments and final review passed. Current original-record cost qualification remains open.

16 October 2026. This is a bounded gate 2 dependency under the approved local finish plan.
The owner authorized continuous local implementation, tests and repair.
That direction covers this routine design choice without another design-approval stop.
The completed calculator and private-context review counters remain unchanged.

## Existing behavior and selected change

The existing calculator binds attempts, orders, fills, holdings and cash.
It checks that position quantity, average price and cost agree internally.
It does not reconstruct the position cost from the recorded fills.

Add a separate pure `calculate_position_costs` function with the same keyword inputs.
Call the existing calculator without changing it.
Then reconstruct current position cost from those validated fills.

Purchases have an exact aggregate purchase cost before a partial sale.
A partial sale from a uniform-price holding can have an exact remaining cost.
After any sale, later different-price purchases must remain unsupported, including purchases after flattening.
This conservative restriction also applies across days. The inputs do not establish the broker's overnight processing state.
After mixed-price purchases, a partial sale must also remain unsupported.
Compare purchase prices numerically. Sale prices do not determine purchase cost.
A later full sale gives a zero current holding, but preserves that historical unsupported status.
For supported holdings, compare reconstructed cost with the original reported cost.
Refuse contradictory reported cost or average price.
Return bounded private calculations with false financial and transport authority.
Known unsupported histories include `UNSUPPORTED_FILL_COST_HISTORY` and the generic cost-coverage blocker.
Fee, action, original-record and native coverage remain unverified.

Alpaca documents different intraday and overnight cost methods.
This increment supports histories with directly determined costs instead of selecting an unverified broker method.
See [Alpaca's cost-method documentation](https://docs.alpaca.markets/us/docs/position-average-entry-price-calculation), checked 16 October 2026.

## Impact and verification

| Surface | Status | Required action |
| --- | --- | --- |
| New pure calculation and tests | Add | Freeze exact cases before implementation |
| Existing reconciliation calculator | Verify | Keep source unchanged; run its 71 compatibility cases |
| Private context, original producers and native controls | Unchanged | Reuse their unchanged 301-case component evidence; claim no new native behavior |
| Package and complete environments | Verify | Build and check matching installed bytes with unchanged locked dependencies |
| Reports, checkpoint and horizontal map | Update | State the supported histories and remaining coverage requirements |

Cover empty, buy, multiple purchases, uniform-price partial sale, full close,
same-price purchase after a sale, multiple symbols, unsupported partial sale and later flattening.
Cover different-price purchases after a sale, both before and after flattening.
An unsupported symbol must not hide a contradictory cost on another symbol.
Keep unsupported history after a complete closing order delivered through partial fills.
Test numerically equal prices, such as `10` and `10.00`.
Cover contradictory position cost, incorrect average price, malformed inputs,
missing or duplicate fills, changed asset identities and caller rounding changes.
Use hand-calculated expected costs and preserve inputs without mutation.

Use at most three review and repair rounds for this new increment.
Round 1 is the independent design and acceptance review.
Freeze selected test IDs, commands and source hashes before every test execution.
Use the same source and installed case inventories.
Complete environment checks must verify the new package and every locked dependency.

Private receipts use `artifacts/m5/position-cost-20261016-01`.
Propose a fresh 32 MiB namespace at `.cache/test-runs/m5-position-cost-20261016-01`.
Admit its full hold before any test or build.
Retain 120-second Jobs, four CPUs, 4 GiB RAM, 16 processes and the shared heavy-job lock.
Host memory floors stay 16 GiB at start and 12 GiB while running.
Scratch remains 12 GiB, backups 21 GiB and the total 50 GiB.
No native runtime, model server or actual broker operation is needed for this pure increment.

## Finish requirements

- [x] Complete the selected calculation and frozen cases.
- [x] Verify source and installed inventories, package bytes and complete environments.
- [x] Finish independent review within three rounds.
- [ ] Update reports and the project map, then synchronize the verified checkpoint.

The independent design review used round 1. Its method-dependence finding is incorporated above.
Round 2 findings are repaired. Final round 3 is clear. All three review rounds are used.

The final census passed in 78.4774 seconds. The two earlier failures remain preserved.
Then compose qualified cost, fee and action evidence with the existing private original-record context.
Risk, durable dispatch and the installed integrated rehearsal remain in the approved continuous scope.
