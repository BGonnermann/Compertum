# Encrypted historical paper-read evidence

11 October 2026. Authorized offline integration, invented credentials/replies only. $0, no account access, no new journal/schema, unchanged financial and resource gates. Primary writes; one bounded reviewer, maximum three review/repair passes.

Capture a terminal owned read packet under the existing owner mutex. Retain its exact plan, each prepared request/private context, original response bytes, qualified parsed bytes, terminal status and execution generation. Check all new metadata, including packet/task IDs and derived filename, for credential reflections before hashing/persistence. Incomplete and aborted packets remain incomplete/aborted.

Use one length-framed current-user DPAPI envelope, with a separate read-evidence purpose and project/alias/task/packet binding. Fixed bounds: 2MiB plaintext, 3MiB ciphertext, at most13 replies, 64KiB each raw/parsed frame. Factor only the native copy/wipe routine; the existing credential wrapper retains8192byte input/output caps. Authenticate framing, counts, hashes, exact EOF, request order/private identity and terminal shape before exposing any data. Historical reading needs DPAPI, not account keys or live transport; it neither creates a live packet nor restores authority/freshness.

Publish only ciphertext through the existing coordinator records grant/BoundedWriter at artifacts/runs/<task>/paper-read-<packet>.bin. Exact retained ciphertext/manifest is idempotent; resealing is randomized and conflicts. Retain failed staging/publication states, do not guess recovery. Published encrypted evidence participates in existing backup lineage; the RUNTIME credential slot remains excluded. Private read buffers are execution-lease scoped; mutable buffers are wiped, but arbitrary Python immutable copies cannot be guaranteed erased.

- [x] Admit fresh64MiB checked namespace and bounded design review.
- [x] Regression-first native envelope, context/privacy/bounds and framed historical loader.
- [x] Existing bounded artifact publication, retry/conflict/interruption/path/lineage checks.
- [x] Review, source/package regressions, exact native reopen evidence and durable receipt/checkpoint.

Supporting source changes: native credential crypto helper only; private qualified-read object retains request and parsing logic shared with historical validation. Existing native-owner start/poll/cancel/opaque ciphertext transfer follows after this component. No actual credential command or account grant yet.

Review repair: metadata frame64KiB (retains597order-row deficiencies), plan/request frames8KiB, raw/parsed64KiB. Maximum41frames occupy1,884,402bytes including headers, below unchanged2MiB plaintext cap. Native DPAPI accepts trailing input; the authenticated fixed-width native ciphertext-length field is filled by a bounded second seal, whose output length must match. Historical load now requires the exact PUBLISHED manifest from the pinned coordinator ledger. Credential-slot ledger pinning is shared, preserving its reservation checks.
