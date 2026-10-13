# Independent causal prediction and fit audit

49 source and49 installed-package tests passed, zero failures/errors/skips. All48 artifacts match exactly:12 candidate results,12 prediction audits and24 accounting audits, covering3,720 daily portfolio records. Independent review closed with no remaining material finding.

The audit binds expected candidate/year/windows/as-of separately from the result. It independently reconstructs the original252-session asset/SPY features, split-only price labels, source/revision hashes, complete12-symbol coverage, same-date missing-label purge and annual07:00 cutoff purge. Original source rows drive training-only scaling and a separate ridge normal-equation solve. Independent serving, recorded serving, error metrics, rank ties, zero/momentum comparisons and contribution gates agree under unchanged tolerances. Hand equations and exact cutoff equality/late-revision cases pass.

Five review false passes were reproduced and repaired: small reported training perturbations amplified by scaling; changed fixed configuration; numeric strings; inconsistent momentum comparison; changed recorded rank ties. Failed logs remain. Test-only fixture repairs corrected string conversion, numerical hand comparison, a corruption too small to violate the declared tolerance, and a missing row that broke snapshot completeness. Requirements and thresholds were not changed.

This is partial-window synthetic evidence. Actual arrival accuracy, fit activation, financial qualification, exact strategy trade policy/intervals, native auditor identity, clean locked campaign reruns and complete-history/shortlist authority remain unverified. No candidate is promoted. Next: independent policy/interval audit, then the complete native campaign and lifecycle integration.

Receipt: artifacts/m3/prediction_audit.json. Source archive, exact artifacts and verification files: .cache/test-runs/m3-prediction-audit-20261010-01. Storage/category/namespace checks passed; original checkout, lock, build spec and prior receipts are preserved.
