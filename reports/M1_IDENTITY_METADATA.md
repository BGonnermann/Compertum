# Identity and dated metadata

Current evidence contains13 distinct provider asset IDs and current active/tradable observations, retained from the previously approved connector envelopes. The raw HTTP responses were not supplied by that connector. SEC metadata independently matches12 current issuer symbols and supplies11 stock industry(SIC) classifications. These observations do not establish historical ID validity or historical tradability.

Three primary source notices establish relevant distinctions:
- Meta announced FB-to-META trading from9June2022, with unchanged CUSIP.
- Roundhill's older META-to-METV change belongs to a separate fund and remains excluded.
- ExxonMobil completed a holding-company reorganization on1July2026 with a one-for-one common-share exchange. Current provider XOM names the successor. Its current UUID is not assumed to identify the predecessor historically. Anticipated2July trading is retained as an expectation, not observed execution.

SPY exchange labels differ:provider ARCA,SEC NYSE. Both are retained without an unverified equivalence rule. JPMorgan's SEC response exceeded2MiB; its partial body remains rejected. A complete issuer business description supports a proposed Financials group but does not fill missing SIC/CIK observations.

A separately versioned dated sector proposal covers the12 stocks and marksSPY as a broad benchmark without a single sector. Group labels are explicit proposed policy, not certified GICS data or historical classifications. No runtime sector/risk policy was adopted. The proposal is concrete material for the later protocol gate.

Collection:20 direct requests;17 completeHTTP200,2HTTP403,1 incompleteHTTP200 at the unchanged body limit. Four unused requests are closed. No credentials, new broker/asset/account endpoints, prices, protected financial statements, installs or environment changes. Failed sources remain in the result and original bytes.

Fresh verification:205 focused checks passed in each source/wheel environment,30 new tests,zero failures/skips. Identity evidence and sector proposal reproduce byte-for-byte in both environments. Independent review and preservation/storage status are recorded in the closeout receipt. Product code unchanged; allocative native suites were not rerun.

Identity result:`data/identity-metadata-20261010-01/identity-evidence.json`, SHA256`0fbdd4558b48ab896083dd07325e73fc2022c115f5ff6128e41b23cfe298afc7`.
Sector proposal:`data/identity-metadata-20261010-01/sector-proposal.json`, SHA256`1bef4509b6489ca1f7f9cba3bf3207e396feb51354fdecde498a67debb02afb9`.
Receipt:`artifacts/m1/identity_metadata.json`.

Full M1 remains incomplete. Dividend inventory remains301/317linked,16unresolved(UNH14/XOM2),298date fills. Newly retained SEC metadata identifies exact historical filing-index URLs for a fresh bounded source pass. Continue there before treating the older dividend sources as exhausted. Warmup/realSnapshot depend on qualified inputs; protocol adoption and strategy execution remain closed.

Initial independent review reproduced malformed recognized fields and duplicate-key acceptance. Standalone connector dependency anchoring was also strengthened. Twelve new regressions first failed and then passed; original helper/tests and failures are preserved. Data values and artifact hashes are unchanged. Repair review closed both findings and receipt-binding concern; no material issue remains in the bounded scope.
