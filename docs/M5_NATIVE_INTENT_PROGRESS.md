# Native paper intents and confirmations

14 October 2026. Dependency after verified native presence. This is accepted local engineering; concrete account access and broker actions remain separately authorized. No start, dispatch, actual-write attempt, strategy arm or financial acceptance is enabled here.

## Dependency order

- [ ] Finish and publish presence increment13 with matching source/package evidence and final review.
- [ ] Add the account-only private input context required by cancellation. Verify its original evidence, current identity and freshness independently of market quotes or strategy conditions.
- [ ] Add immutable exact intent and confirmation records using native presence and the appropriate private input context.
- [ ] Complete matching source/package checks, review, evidence preservation and GitHub synchronization for each bounded increment.
- [ ] Continue ownership/economic/risk readers, then consumption, dispatch and reconciliation under the admission plan.

The independent design check found no missing user decision for these local components. Unavailable downstream evidence stays blocking. It does not authorize the later account or broker actions.

## Account-only input contract

Attach a private, nonserializable context to `PaperReadOwner`, separate from the existing combined account/market context. Resolve the authenticated subject and original published packet, coordinator manifest, native preflight, confirmation/alias, first-opening reference when present and original attempt history. Bind owner generation/instance and the exact live objects. Reuse original account-binding and evidence readers; accept no caller-supplied manifest, account identity, clock, approval flag or reconstructed diagnostic as proof.

The context reports observations and unresolved requirements. Successful reads add no records, network requests, attempts or quota use. Require current native account provenance for a confirmed context. Missing confirmation or ownership is an explicit blocker; corrupt originals refuse. Existing holdings/orders, negative cash, closed market and HALTED/DISARMED strategy admission do not prevent observing valid account evidence. The context must not claim that these observations establish ownership, cancellation permission, flatness, clean opening or safe sizing.

Cancellation does not require a market producer, quote, alpha features, strategy arm, AI or the09:35 strategy window. It still requires later exact target/ownership/reconciliation qualification, healthy execution/watchdog, durable journal, current presence, account binding and clock/calendar agreement. Do not apply the combined market context unchanged to CANCEL.

Recheck the original records after decryption and secrecy scanning, then credentials, health and final owner clocks. Keep the original30-second account observation age; context creation or inspection cannot renew it. Observed corruption, refusal, replacement, restart, changed identity/credentials or clock faults permanently close that context. Closing it does not close borrowed market resources or alter historical records. Stable bindings exclude changing diagnostic timestamps.

Minimum checks: valid confirmed and unconfirmed inputs; both identity substitutions; absent market producer; legitimate holdings/orders/closed session; original age boundary; missing/changed confirmation, alias, history, opening, packet and encrypted artifact; credential/health/owner/context replacement; late mutation or expiry during verification; nonrevival after restoration; private serialization/public-routing denial; no HTTP, journal/attempt or quota effects; affected combined-context compatibility. Use clearly labeled simulated account origins/clocks/reserve capacity.

Preparation14 keeps observed conditions separate from unresolved downstream requirements. The account-only diagnostic will expose `observed_deficiencies` and `unverified_requirements`, with all authority false. Quote/feed/liquidity/asset eligibility and a closed market are not blanket CANCEL prerequisites; negative cash and a nonempty opening remain visible observations. Ownership, target and economic reconciliation, confirmation, presence and exact authorization remain unresolved. Clock/calendar or native-origin faults remain visible and must be qualified by downstream admission. Draft tests and bounded helpers are in `.cache/test-runs/m5-account-context-20261014-14`; no14 test or product change has run yet. Final callbacks, durable reads and pure final age/object checks must precede a diagnostic return, including a final check of context ownership after snapshot construction.

## Exact record contract

Keep intent, confirmation and irreversible invalidation separate. An intent binds version/purpose, immutable ID, authenticated subject, project/account identity and credential hashes, owner generation/instance/component lifetime, exact operation and terms, original evidence references/hashes, original presence identity/hash, owner wall/monotonic creation times and fixed pre-start expiry. A confirmation binds that exact intent/hash, subject/account/purpose, original presence and owner-measured confirmation times. Confirmation never changes terms or extends expiry.

Use explicit atomic schema creation, bounded history, canonical size limits, checked insert/readback and request conflict detection. Duplicate requests return historical receipts; only uncached inspection reports current validity. Keep irreversible local invalidation independent of restored mutable rows. Missing issued records, ignored writes and late dependency changes cannot create or revive confirmation. Preserve historical records across restart without restoring current authority.

The start deadline is no later than original creation+60seconds, bound presence expiry and applicable operation/window limits. Account and quote freshness remain independently30seconds. Later presence cannot revive an older plan. Do not construct a timed transport exchange while waiting for confirmation: the eventual10-second request deadline starts after that wait.

| Purpose | Required distinction |
| --- | --- |
| CANCEL | Account-only context, exact target and original ownership/history references; no blanket quote or strategy gate |
| CLOSE_LONG | Account evidence plus fresh quote, liquidity/notional cap, reconciled owned quantity and bounded children; regular session; at most12 children/10minutes, ending earlier at close |
| Fixture buy/resting buy | Separate fixture purpose, one whole share/$250 exposure and applicable fixture evidence/window |
| Strategy | Separate candidate/version/protocol references and all strategy gates; fixture confirmation is insufficient |

All results remain BLOCKED with transport/financial authority false while required ownership/risk/consumption producers are missing. Preserve `PaperIntentJournal`, `PAPER_PREPARATION` identities and fake authority as their existing distinct types. The later actual-write record must update shared guard/history/recovery contracts together; that is outside this record-only increment.

Exact next action after presence publication: freeze and implement the account-only context acceptance inventory, then exact native intent/confirmation. Use the existing120second/4GiB/fourCPU/16process job limits,16/12GiB host gates, five-second storage scan and50GiB category budget. One heavy job, primary writer, one independent reviewer and at most three review/repair iterations per bounded increment. No Strata or scheduled work.
