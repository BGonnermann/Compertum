# Independent recorded-fill accounting

36 source and36 installed-package checks passed, zero failures/errors/skips. Six reports reproduce byte-for-byte. Independent review closed with no material finding. A hand-built ledger reconciles buy2 at100, split2:1, unpaid dividend4, sell4 at55: cash10019.58 + receivable4 = NAV10023.58, total price costs0.42.

The separate audit reconstructs cash, positions, total basis, dividend claims/payments, adverse fills, turnover, entry/post-fill/close observations, risk halts and financial metrics using original synthetic prices/actions. It does not call the replay ledger or its metrics implementation. Existing scalar and daily-return tolerances are unchanged. Raw references, zero fees and discrete identities are exact.

Three intentional false passes were reproduced then repaired: tiny raw-price changes, nonzero declared-zero fees, and opposing recorded-NAV deviations that exceeded the daily-return tolerance. All red logs remain. Storage/category/namespace checks passed. Original checkout, build spec, lock and prior evidence are preserved.

This component grants no strategy selection, causal/model provenance, native auditor, clean rerun, shortlist or financial approval. Next: independent candidate feature/label/training/serving audit, complete development history and bounded auditor process.

Receipt: artifacts/m3/accounting_audit.json. Exact source and verification files: .cache/test-runs/m3-accounting-audit-20261010-01.
