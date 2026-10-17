# Posted fee observations from original account activity

17 October 2026. This increment continues gate 2 of the approved local finish plan.
Declared-fee engineering is verified across 260 matching source and installed cases. Its three review rounds are closed.
Actual billing coverage, account applicability, unpaid liabilities, actions, risk, dispatch, and the combined rehearsal remain open.

## Verified result - 17 October 2026

Source and installed inventories each passed 238 distinct cases, with zero failures, errors, or skips.
Each contains 236 in-process cases and two native Windows stages. Both complete environment byte checks passed.
All three posted-fee review rounds are closed. Actual billing, liabilities, and action coverage remain unverified.
Continue M5_LOCAL_ECONOMIC_EVIDENCE_PLAN.md, then risk, durable dispatch and recovery, and the installed combined rehearsal.

## Intended behavior

Compare original observed cash with owned fills and retained USD fee activity.
Keep the observed cash unchanged. Count each original activity once.
Keep posted debits, posted credits, declared estimates, and unpaid liabilities separate.
A matching comparison does not prove that all fees have posted or that a credit reverses a particular debit.

The current activity parser preserves non-fill rows but reports them as unsupported.
The fee context calculates declared estimates from fills. It cannot explain an original posted fee debit.
The existing strict order comparison and position-cost methods must keep their present behavior.

## Source limits

The official [account activity documentation](https://docs.alpaca.markets/us/docs/account-activities) identifies `FEE` as a USD-denominated fee.
It defines `net_amount` as a signed cash amount. Its date can describe occurrence or settlement.
The [request reference](https://docs.alpaca.markets/us/reference/getaccountactivities-2) filters by record creation time.
These are distinct times. Do not place a date-only fee between exact fill timestamps.
Do not use a missing fee row or short final page to establish zero unpaid liability.
Do not classify `CFEE`, dividends, transfers, interest, or unknown activity as an equity fee.
Those records remain preserved by the existing collection and must refuse this narrower calculation.

## Calculation

Add `calculate_posted_fees` in `src/compertum/paper_posted_fees.py`.
Use the same bounded original inputs as `validate_fill_history`.
Accept only `FILL` and strict `FEE` rows. Check activity IDs across both kinds.
Require each fee's original ID, type, date, and signed `net_amount`.
The required fields are exactly `id`, `activity_type`, `date`, and `net_amount`.
Only `description` is optional. If present, it must be a string with at most 1024 UTF-8 bytes.
The activity type must be exactly `FEE`. Other fields refuse this narrow calculation.
Dates accept an exact `YYYY-MM-DD` or a UTC timestamp ending in `Z` with up to nine fractional digits.
Accept years 2000 through 2100. Retain the original date text.
Amounts accept a minus sign, up to nine integer digits, and up to twelve fractional digits.
Reject exponents, leading plus signs, leading zeroes, nonfinite values, and absolute amounts above 100,000,000.
Accept zero and negative zero as zero cash effects. Preserve their original text.
Reject malformed, oversized, duplicate, and unsupported records.
Retain date text without inventing an exact posting or execution time.
Treat a negative cash amount as a posted debit and a positive amount as a posted credit.
Do not assign a credit to a reversal, component, order, or execution without independent evidence.
Do not deduct a declared fee estimate a second time.

Reuse fill-history ownership and quantity checks on the original fill rows.
Keep its negative-intermediate-cash refusal. Do not move a fee credit before a purchase to make that purchase valid.
Add exact posted cash effects to the calculated fill balance.
Compare that result with the unchanged observed balance under the existing $0.01 tolerance.
Retain the original difference, gross debits, gross credits, and the resulting difference privately.
Use an independent bounded decimal context. Trap unexpected rounding.
Keep the 200-row and one MiB combined input bounds.

The result remains a blocked calculation. Actual total liability, complete billing coverage, and financial authority remain unknown.
Do not claim intra-day cash sufficiency from a date-only fee.
Always retain `FEE_POSTING_INTERVAL_UNVERIFIED`, including matching and empty totals.
Creation filters and fee dates do not establish when the account cash changed.
Preserve the original opening cash and observed cash separately in the private calculation.

## Original private context

Add `PaperReadOwner.posted_fee_context(subject, packet_id, activity_id)`.
Resolve its opening, account, portfolio, history, activity publication, and credential from existing original records.
Reuse `_capture_originals(..., allow_unsupported=True)` without changing that helper's behavior.
Let the new calculation refuse every unsupported activity itself.
Bind all original bytes, account identity, owner generation, and calculation bytes before and after callbacks.
Keep the result private, nonserializable, redacted, and single-use.
Recheck credentials, transactions, original identities, clocks, expiry, ownership, and health before proof completion.
Do not close borrowed account resources when this context closes.

Diagnostics may expose fixed statuses and counts. Do not expose amounts, descriptions, symbols, or account and order IDs.
Run the existing credential-reflection check on completed diagnostics.
Keep financial and transport authority false, even when the cash comparison matches.
The current comparison, position-cost, and declared-fee methods remain separate.

## Impact and verification

| File or behavior | Required work | Evidence |
| --- | --- | --- |
| New pure calculation | Implement bounded original fee effects | Exact arithmetic, signed amounts, dates, bounds, duplicate IDs, hostile decimal settings |
| New private context and owner method | Bind original records and single-use proofs | Substitution, callbacks, stale inputs, changed records, transactions, closure, borrowed resources, secrecy |
| Existing comparison and cost methods | Verify unchanged refusal and arithmetic | Focused existing original-context checks |
| Existing declared-fee component | Preserve its closed receipt and unchanged behavior | Explicit input comparison and affected checks |
| Native test helpers and control tests | Extend the admitted fresh folder with original invented fee rows | Two distinct source stages and the same two installed stages |
| README, checkpoint, reports, project map | Report actual results and remaining gates | Fresh receipts and all-page visual review |

Freeze exact cases, commands, inputs, and resource bounds before each run.
Run a focused failing case before implementation. Preserve every failed receipt.
Require matching distinct source and installed inventories, complete environment byte checks, and final independent review.
Use at most three review and repair rounds. Carry counters forward.
Design review 1/3 identified the timing, credit, and exact-schema requirements above. Code review 2 found the repaired parser limit. Final review 3 is clear; all three rounds are closed.
Test a backdated fee and a fee collected after the current cash observation. Both keep the posting-interval blocker.
Test opening cash 10, a purchase costing 20, and a fee credit 10. The unchanged fill check must refuse.
Test zero, negative zero, invalid dates, extra fields, cross-kind duplicate IDs, and cancelling debit/credit pairs.
Apply the combined input bounds before filtering any rows.

Native checks use invented account observations and local replies.
Use only the one admitted fresh folder at its original path, with its existing project and allocated reserve.
Preserve its stopped state before further use. Never resume either halted older folder.
Prove original posted activity reaches the new calculator and proof; restart must not restore freshness.
No test result establishes actual-account acceptance or authority for a broker action.

## Capacity and execution

Require fresh complete capacity admission before creating new test or evidence namespaces.
Proposed new holds are 128 MiB source scratch, 80 MiB installed test output, and 16 MiB installed-prefix growth.
The installed prefix is the existing isolated Python environment. Preserve its original runtime and dependencies.
Reserve eight MiB records and 64 MiB backups.
Retain the existing fresh-native 1072 MiB hold. Do not create another native folder.
Test scratch is capped at 14 GiB. Backups stay 21 GiB, and the total stays 50 GiB.
Published program limits, locked dependencies, CPU and RAM bounds, deadlines, and financial gates stay unchanged.
Keep one heavy job at a time and host memory floors of 16 GiB to start and 12 GiB to stop.
Keep maintenance measurement at 110 seconds within a 120-second job. Production scans stay at 30 seconds with 35-second freshness.

Verification is complete: 238 matching cases per environment, including two native stages, with complete byte checks.
Continue local economic evidence, current-input risk, durable dispatch and recovery, and the combined installed rehearsal.
