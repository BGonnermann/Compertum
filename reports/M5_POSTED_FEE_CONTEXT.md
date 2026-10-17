# Original posted USD fee observations

17 October 2026. Posted-fee engineering is locally verified. The approved local finish plan remains incomplete.
USD means US dollars.

## Verified result

| Inventory | Source passes | Installed passes |
| --- | ---: | ---: |
| New pure calculation | 57 | 57 |
| New private context | 39 | 39 |
| Existing compatibility cases | 140 | 140 |
| Native Windows lifecycle cases | 2 | 2 |
| Distinct total | 238 | 238 |

Both final inventories have zero failures, errors, and skips. Both complete environment byte checks passed.
Do not add the separate declared-fee 260-case or current-cost 53-case inventories; their compatibility cases overlap.

The calculation retains original opening cash, observed cash, dates, descriptions, and signed USD fee rows.
It reports debits, credits, and their cash effect. It does not infer a reversal or an unpaid balance.
Unsupported activities and duplicate original IDs refuse. A later fee credit cannot fund an earlier unaffordable purchase.
Matching and empty totals retain the posting-interval and liability blockers.

The private context binds original opening, account, history, portfolio, and encrypted activity records.
A proof checks its original private records before use. It can be used once.
It checks original bytes, credentials, owner identities, transactions, clocks, expiry, and health around callbacks.
Diagnostics redact private values. Proofs are single-use, and borrowed account resources remain available after closure.

Code review 2 found a real size defect. The old parser rejected valid new inputs above 65,536 bytes.
The new calculation now has its own one MiB parser. The existing parser's limit is unchanged.
The passing boundary case retains 200 fees with 400-byte descriptions, an exact debit of 4, and unchanged original inputs.
Repeated reconstruction passes. Malformed JSON, duplicate keys, excessive depth, nonfinite values, and oversized arguments refuse.
Final independent review 3/3 is clear. All posted-fee rounds are closed; older counters were not reset.

## Native evidence and preservation

Four separately frozen Jobs passed: original capture and restart in source, then the same two cases when installed.
They use real Windows owners and transport with invented account observations and local replies.
The account-origin substitution is confined to test helpers. Activity provenance remains loopback fixture evidence.
Each original run records seven local requests and zero actual-account calls. Restart records no requests and restores no freshness.
Every accepted Job observed exit with zero remaining children.

Before the first attempt, all 85 original runtime files and 113 entries matched the prior preservation inventory.
The first posted-fee native source attempt failed: zero passes, one failure, zero errors or skips.
Its separate stopped-runtime archive preserves 89 files and 119 entries.
Archive SHA-256: `31636c967e2efdadc04b1c37897142f8b7b0cc90ceed84449cdb3d1bbe6151d5`.
The original cause remains unproven. Database copies show normal startup disarming and published activity.
The test helper ran expensive proof work during publication acknowledgement. It now leaves that acknowledgement passive.
Three explicit status calls perform context creation, proof preparation, and single-use verification.
The first repaired source run measured these phases at 2.7880, 1.6311, and 0.0860 seconds.
The five-second owner-exchange limit remains unchanged. Safe timing records contain no request or reply payloads.
Only three test files changed. The 236 valid in-process cases in each environment were reused.
The installed package and all 232 product files remain unchanged by this helper repair.
The same project, original path, and fully allocated one GiB reserve remain in use.
After verification, the stopped runtime archive contains 151 files and 197 entries.
Archive size: 13,185,513 bytes. SHA-256: `3b38ed9c6585934613bdc8abcf3d2092b6ee13984dd2242ea3e1cbd2e1e693a1`.
The runtime has no watchdog halt. Both older failed runtimes and retained halts remain intact.
No actual order, cancellation, close, account change, or Strata start occurred.

## Storage and reproducibility

The source run retained 69,812,224 bytes of test output. The original installed-output hold was 67,108,864 bytes.
The corrected measurement counts pytest links without following them. Its first failed diagnostic remains preserved.
A fresh complete census admitted 80 MiB installed output and a 208 MiB installed-output parent before those tests.
Its parent Job passed in 58.3002 seconds with zero remaining children.
After all admitted holds, that census left 802,361,000 scratch bytes and 622,475,296 backup bytes.
Those are measurements at admission, not a new production scan.
The longest installed case batch took 113.4748 seconds under the unchanged 120-second limit.
Its remaining margin was 6.5252 seconds. Do not treat this result as a wide timing margin.

Test scratch stays 14 GiB, backups 21 GiB, and total storage 50 GiB. No additional native folder or reserve was created.
The published program configuration, production scan rules, dependencies, interpreter, CPU, memory, deadlines, and financial limits are unchanged.
The release contains 232 package files: 229 previous files are unchanged, one owner gains one method, and two modules are new.
The exact case inventory freezes 635 source and test inputs. Source and installed package bytes match the retained release.
The original source archive retains the failed helper. A separate checked three-file archive supplies the repaired test helpers.
Its exact file hashes, archive hash, and old-to-new input comparison are recorded in `posted-native-helper-repair02-impact.json`.

Wheel SHA-256: `92d9a58fdf036c50db920550fcaf8560c7a19be48e26d282f12a8ad80b9f7866`.
Source archive SHA-256: `b1d87db03a82ef605e7ede2bb14a0a0cd29b2cc4c58fe78d477b0a18b1203c77`.

Private receipts remain local under `artifacts/m5/posted-fees-20261017-01`.
The stopped runtime archive remains under `backups/m5-posted-fees-20261017-01`.
These private outputs, environments, and credentials are excluded from Git.

## Preserved failed test attempts

| Attempt | Pass | Fail | Error | Skip | Meaning |
| --- | ---: | ---: | ---: | ---: | --- |
| posted-red01-source | 0 | 1 | 0 | 0 | Expected missing pure module |
| posted-red02-source | 0 | 1 | 0 | 0 | Expected missing owner method |
| posted-source-part01 | 0 | 3 | 0 | 0 | Incorrect test expectation for original cash text |
| posted-review2-red01-source | 0 | 1 | 0 | 0 | Expected reproduction of the 64 KiB parser defect |

These attempts remain failed. They are not counted in the final passing inventory.
The source cash-text test now checks the unchanged original `100000.00` value.
The separate failed output diagnostic executed no product cases and changed no program limit.
One six-case installed batch reached its unchanged 120-second deadline. Its process group closed in 121.6002 seconds with zero remaining children.
No case from that interrupted batch entered the passing inventory.
The remaining 60 cases used 22 fresh batches of at most three cases. The 176 valid installed passes were reused.
Code, original inputs, dependencies, resource limits, and financial gates did not change for this repair.

## Remaining local work

Actual billing, account applicability, unpaid liabilities, reversal links, posting intervals, and complete action coverage remain unverified.
Fee dates and activity creation filters do not establish cash posting time.
See the [activity contract](https://docs.alpaca.markets/us/docs/account-activities) and [creation filters](https://docs.alpaca.markets/us/reference/getaccountactivities-2).

Next, implement [local fixture economic evidence](../docs/M5_LOCAL_ECONOMIC_EVIDENCE_PLAN.md). Its design review 1 is complete.
Use original complete fixture accrual, payment, reversal, and action records. Keep actual-account qualification separate.
Then finish current-input risk, durable dispatch and recovery, and the installed combined rehearsal.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.

## Project map and saved-record checks

The horizontal PDF has nine reviewed pages, 90 function groups, 81 navigation links, and 90 source notes.
Visual review found a clipped footer and damaged roadmap separators. Both were corrected before final review.
The PDF retains the current live Hub work and its separate 51 source and 47 browser checks.
The exact map hash and all-page review receipt remain in the local evidence folder.
The existing Hub reader correctly reads the new saved checkpoint, counts, next plan, report, and map.
Its first isolated import failed because the test environment lacked the Windows user-profile path.
The corrected isolated check passed. This repair changed no Hub code and added no product test cases.
