# M4 persistent fake-intent journal

Verified11October2026:187identical source/installed checks,0failures/errors/skips, independent targeted review closed. Receipt: `artifacts/m4/fake_intent_journal.json`. This includes20native journal checks,60risk,28plan,28import-boundary and51domain checks.

One actual execution role owns the SQLite/WAL state. A logical intent/account has one immutable body and stable client identity. CHECKED/SUBMITTING is committed before one simulated attempt can be issued. Lost replies and404lookups preserve UNKNOWN and cannot cause another attempt. Broker event evidence is deduplicated globally and applied independently to order/cancellation intents. Contradictory cumulative fills retain the last accepted totals and latch uncertainty; ordinary repeated observations cannot clear an integrity conflict.

Four real Windows process-exit fixtures covered before attempt, after durable attempt, after acceptance in a separate persistent fake-broker database, and after acknowledgment commit. Restart retained the expected0or1acceptance and issued no second simulated attempt. Queued work became SKIPPED_RESTART; admission remained DISARMED/RECONCILING. These are bounded fixture receipts, not a complete M4 crash matrix.

Source archive `.cache/test-runs/m4-execution-contracts-20261011-01/journal-source01.zip` SHA256 `6e6dbc255212ec53d0b564b05997b258d014f4ef78c66f50591e53fb5a785ab7`; exact wheel/package/runtime identities are in the receipt. Passing native fixture copies were archived and hash-verified before removal. Failed prior fixtures remain preserved.

Still required: full deterministic broker/driver, explicit conflict reconciliation, owner-authenticated authority/calendar/input/reserve checks, mutual watchdog integration, old-execution-snapshot non-replay proof, and complete recovery matrix. No real account or transport capability was added. FullM4and financial acceptance remain false.
