# Fresh asset and quote inputs

Verified 2026-10-12T01:27:00.456851+00:00. Source and installed package each passed **488 identical checks**, including 48 fresh-input checks. Zero final failures, errors or skips. Independent review closed on pass 2 of 3. Receipt: [market_fresh.json](../artifacts/m5/market_fresh.json).

The execution owner now collects one ASSET response followed by one QUOTE response. Fixed endpoint checks, original response bytes, credential-envelope binding and private provenance are retained. The pair allows ten seconds per request and twenty seconds total, including setup and validation. It makes no retry. Partial failures stay incomplete.

Every private diagnostic access rechecks retained inputs and quote age. Exact 30-second validity and one-nanosecond expiry pass. Wall/elapsed clock disagreement over five seconds is rejected; age uses the later clock estimate. The actual observed wall time remains separate. A saved result describes its observation time and grants no continuing freshness or trading permission.

Three session dates, each replayed three times, produced identical fresh and stale artifacts in both environments: 2026-10-09, 2026-11-02 and 2026-11-27. Each lane used 18 native local HTTP requests. Prior history/action collection artifacts matched the previous package, current source and installed package exactly. Package matching verified 174 Python modules.

Review reproduced and repaired four failures: mutation during calculation/scanning and stalled/regressing elapsed clocks. Expected missing-module and review failures remain retained. The archive helper initially refused an incorrect scratch suffix; it was corrected to use the recorded command path. Completed passing fixtures were verified in three exact archives before duplicate loose copies were removed. Logs, failed tests and archive inventories remain under `.cache/test-runs/m5-market-fresh-20261012-01`.

Source archive SHA256: `2e924d4c646a602656d27f0a9a5ab2ec1d299dfe1dc1d7beb7aeebc58a572df0`. Wheel SHA256: `115ddbc081bde1b8f2027af6a42f3ec3f809003e608e84c0b378ef77af7e03c8`. Final storage scan: 4.740 seconds; retained namespace: 11,222,724 bytes, below 64 MiB. Available RAM: 8,001,671,168 bytes, below M3's unchanged 8 GiB floor.

These checks used invented credentials and local HTTP fixtures. Preflight regressions explicitly simulate reserve capacity and account replies. Actual paper/data TLS, full owner reserve acceptance, account authority and financial acceptance remain unverified. No real credentials, external requests, orders, publication or Strata changes occurred.

Next: execution-private composition of the same frozen history plan and current asset/quote pair, preserving the 09:25 validation cutoff and all financial deficiencies. Then shared request budgeting and remaining account/risk/reconciliation dependencies.
