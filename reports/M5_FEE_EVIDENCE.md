# Fee evidence and declared calculation

11 October 2026. **299 matching source and installed-wheel checks passed**, including 61 focused fee checks. Zero final failures, errors or skips. Review closed on pass 2 of 3; all 166 installed modules match frozen source. Receipt: artifacts/m5/fee_evidence.json.

The new fee calculator retains immutable source documents, declarations and execution batches. It calculates exact quantities and principal, applies each declared minimum/cap, aggregates to the declared billing scope, then rounds. Per-order caps and daily rounding are separate. Missing or overlapping schedules produce no complete fee total. Malformed or oversized inputs are rejected before hashing or sorting.

Two public Alpaca PDFs were fetched without credentials and retained under data/m5-fee-evidence-20261011-01. The disclosure-library PDF is revised 1 October 2026; the alternate URL serves a version revised 17 September. Their equity TAF rates differ. Original bytes and source findings are preserved; the current PDF's rate and aggregation tables were visually checked. Sources: [library schedule](https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf), [alternate schedule](https://files.alpaca.markets/disclosures/BrokFeeSched.pdf), [disclosure index](https://alpaca.markets/disclosures).

Both declarations replayed three times with identical source/wheel hashes. For two invented one-share sales at $100, their declared totals are $0.02 and $0.03. Supplying both overlapping declarations produces an explicit conflict and no total. The dates and direct-retail commission assumption in this demonstration are declared scenarios; this is not proof of this account's fee schedule. Actual billed fees, account applicability, daily fill completeness and order-lifetime completeness remain unverified. No current provider rate is a product default. Five previous 2023 fee calculations remain exact.

Review reproduced and repaired validation occurring after schedule hashing. All initial failures remain in logs. The final storage scan first exceeded its unchanged five-second deadline. Two earlier completed test folders (260 passing checks each, three inapplicable platform skips each) were archived and byte-verified; only duplicate loose copies were removed. The archive retains 1,352 files, and original test logs/results remain. Final scan passed in 4.425 seconds.

Source archive SHA256: `a41ab5748767affd238da38bf71f4943b01738727698af0bc25ddc8d3b3870a1`. Wheel SHA256: `5f0cc50a2af0285023a0afc16dd5991ba14c3032e4f52b5137a51e213d1fd3e3`. Namespace: 4,152,223 bytes of 64 MiB; source documents/metadata: 296,322 bytes of 8 MiB. Available RAM: 8,100,564,992 bytes; M3 still requires 8,589,934,592.

No credentials, account reads or order requests were used. M5's actual walkthrough and M6's ten supervised sessions remain incomplete. Next: bounded current action/halt observations, preserving explicit coverage and freshness gaps.
