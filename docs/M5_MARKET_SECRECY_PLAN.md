# Private market exchange and reply qualification

12October2026UTC. Authorized offline M5 increment. One private runtime module and focused tests; no actual keys,external calls,public route,persistence,grants,account UUID or packet driver.

Prepare an immutable execution-owned context pinned to exact plan/request/action arguments,protected credential object and ciphertext hash,lease/generation/process identity. Revalidate before every use; register revocation; deny construction,serialization and access after close. Bound retention to four contexts per owner,each with at most64KiB plan,64KiB request,64KiB reply and8KiB diagnostic (under1MiB). Context lifetime ends explicitly or with owner disposal. Clearing immutable Python references is not secure erasure.

Dispatch through one private factory that opens the pinned envelope and constructs the exact native data GET. One attempt per context. Real-profile headers derive solely from the envelope;loopback sends a fixed invented header and must say credentials were not sent. Qualification binds exact native object/result identity,request bytes/hash,plan hash,lease,GET,target,origin and verified handle closure. Caller-supplied raw replies remain UNVERIFIED; caller flags cannot confer native provenance. Transport timestamps remain declared observations; no real TLS qualification is inferred from offline tests.

Scan original raw JSON bytes,decoded keys/values,plan/request and final diagnostic for literal,escaped,Base64 and URL-safe key/secret reflections before returning evidence or hashes. Existing secrecy JSON parser is discarded; use original bytes with existing MarketObservation/CurrentActionPage Decimal parsing and exact nanosecond bounds. Reject malformed/duplicate/nonfinite/oversized/deep JSON with fixed errors. Error HTTP objects may retain refused observations; no retry/financial/entitlement/coverage grant. Never normalize raw bytes. Qualification does not validate aggregate completeness or economic eligibility.

Checklist:
- [x] Tests first: secret variants/locations,immutable context and wrong owner/envelope,Decimal/nanoseconds,malformed bodies,status types,native/injected/substituted provenance,revocation and concurrency.
- [x] Implement bounded context,owned dispatch,secrecy qualification and private reply; preserve existing adapters/parsers.
- [x] Independent review maximum3passes,repair concrete findings.
- [x] Freeze/build/install; matching focused/regression IDs and exact invented replay; storage/receipt/checkpoint.

Design supported by bounded independent inspection from /root/paper_contract_review. Concrete provenance gap: the low-level adapter alone cannot prove which envelope supplied headers; this context must own their creation.
