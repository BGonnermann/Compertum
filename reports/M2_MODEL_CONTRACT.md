# M2 synthetic model fitting

109 source checks and109 installed-wheel checks passed, zero failures/errors/skips:39 model checks and70 covariance regressions. All27 synthetic fits (nine ridge configurations across three annual cutoffs) reproduce exactly. An independent normal-equation calculation differs by at most2.8e-17; the declared parity tolerance remains1e-12.

The fixed registry contains12 strategy IDs. Training uses only rows available at the07:00 New York annual cutoff, with whole-date purging when any asset is affected. Exact decision/entry/label timing, selected revision identity and row hashes are retained. Scaling uses training rows only. Plain immutable artifacts contain the fixed solver/configuration and locked library versions; no pickle or financial admission is involved. Row/batch serving matches the fitted pipeline.

Initial tests exposed a holiday-handling mismatch; using the locked calendar's first-session lookup repaired it. Independent review found no remaining material defect. [Receipt](../artifacts/m2/model_contract.json) retains source, raw arrays, commands and comparison results. These are invented engineering fixtures, not real strategy training or completed M2 scorecards.

Next: causal feature assembly and campaign integration. Financial input qualification and protocol sealing remain open.
