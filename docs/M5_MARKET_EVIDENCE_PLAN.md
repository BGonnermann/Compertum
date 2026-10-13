# Encrypted private operational evidence

12 October 2026 UTC. Authorized offline M5 continuation. One new runtime module with protect, publish and execution-only historical open. Account evidence code and limits stay unchanged. No actual keys, outside requests or account actions.

- [x] Tests first: exact native round trips, interrupted publication, damaged bytes, manifest/ledger/context rejection, lease revocation, child-process restart, complete/incomplete collection shapes and semantic tampering.
- [x] Implement framed purpose-specific DPAPI envelope, bounded publication and historical reader.
- [x] Independent review (at most three passes), targeted repair and fresh tests.
- [x] Frozen source/package matching checks, exact semantic replays, storage receipt and roadmap update.

Only a live factory-created collection snapshot can be sealed. Bind project, account alias, task and collection UUID, execution generation, credential hash and snapshot hash. Encrypt metadata plus exact canonical snapshot with CPOMKT01 magic, OPERATIONAL_ONLY purpose and fixed data origin entropy. Allow 2 MiB snapshot plus 16 KiB framing/metadata; cipher maximum 3 MiB. Bind ciphertext length inside authenticated plaintext and require exact EOF.

Reconstruct each request and raw response observation, exact diagnostics, hashes, provider cursor sequence and recorded chronology. Recompute a captured aggregate from original bytes; preserve null aggregate and its recorded error instead of upgrading rejected output. Zero-record terminal failure and final unvalidated retained page remain legitimate incomplete evidence. Cursor completion never proves financial completeness.

Publish ciphertext only through exact records grants and pinned storage. Exact bytes are idempotent; conflict/staging/unindexed rename are refused. Opening requires unique exact PUBLISHED ledger linkage. Execution-private, redacted, nonserializable handle, owner revocation and mutable plaintext wipe. Reopened purpose remains OPERATIONAL_ONLY with HISTORICAL_ONLY use; no live collection, freshness, dispatch, research or financial authority. Immutable caller copies are not claimed erased.

Independent design inspection by /root/paper_contract_review informs this bounded design. New plaintext allowance accounts only for framing overhead; no existing cap is relaxed.

Verified in artifacts/m5/market_evidence.json. Reviewed plan identity retained in the receipt; completion marks added afterward.
