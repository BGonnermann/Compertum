# Private reconciliation context

16 October 2026. This is the next gate 2 increment after the verified pure
accounting calculator. It does not include risk, dispatch or actual orders.

Add `PaperReadOwner.reconciliation_context(subject, packet_id, activity_id)`
with keyword-only arguments. Resolve the existing private account context.
Do not recreate missing current evidence from historical publication.
Require the same subject, packet, account, credential, immutable opening and
complete retained-history bindings as the published native activity record.
Read complete native attempts from the external guard, including attempts
missing from an older database. Use current original portfolio observations.

Return a private nonserializable context with `diagnostic()` and `close()`.
Its internal single-use proof must recheck original records and artifact bytes
after callbacks. Check original clocks and health last. Closing the wrapper
must not close its borrowed account context. Refuse caller transactions before
callbacks. Corrupt evidence, replacement, expiry and identity changes must
permanently invalidate the wrapper. Diagnostics must hide account IDs, cash,
order IDs and credentials.

Matching original arithmetic can describe ownership observations. Keep fee
liabilities, corporate actions, full position costs, risk and consumption
explicitly unverified. Loopback evidence must remain labelled as local test
evidence. No new public command or broker-write capability is added.

## Frozen acceptance cases

Cover a valid empty published traversal, unpublished or failed traversal,
foreign subject/packet/account, missing current context, replaced context,
changed activity record, changed manifest bytes, changed opening, changed
complete history, same-alias credential replacement, expiry and clock gaps.
Cover late invalidation during decryption and final proof checking. Verify
privacy, serialization refusal, no extra GETs, caller-transaction preservation
and borrowed-context closure behavior. Add genuine nonempty owned-order cases
only from supported native retained records and exact activity observations.

Freeze exact case IDs, input hashes and commands before every execution.
Use the existing simulated 64 KiB reserve for labelled in-process checks.
Run matching source and installed cases and complete environment checks.
Use at most three evidence-led review and repair rounds for this new increment.
The completed calculator's three used rounds remain closed.

Native integration acceptance requires fresh Windows observations and verified
process ownership. Reuse only the passing runtime at its original path:
`.cache/test-runs/native-activity-20261016-02/native-shared`.
Keep its original project identity and fully allocated 1 GiB reserve.
The failed fixture, its halt and the master stop must remain unchanged.

Verify current owner locks and archive the complete stopped runtime before
starting it. Preserve database files with their journal files. Verify archive
contents against original hashes and record original Windows file identities.
Admit a 16 MiB backup allowance and a fresh 32 MiB installed-test namespace.
Keep the existing passing runtime's 1056 MiB ceiling. Put new logs and receipts
outside that runtime. Use new task, packet and activity identities.

Collect current loopback observations after each start. Record new owner
generations without replacing earlier evidence or restoring old freshness.
Recheck preserved immutable evidence after execution. Reuse the existing
isolated installed prefix and unchanged dependencies. No reserve is moved,
released or used as scratch. The earlier fresh-fixture proposal is preserved
in the private execution records.
