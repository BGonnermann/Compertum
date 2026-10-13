# Clean campaign admission: implementation notes

Next dependency after native startup verification; local synthetic engineering only.

- Embed one bounded canonical environment manifest and its preregistration binding in a versioned campaign input, outside the fixed trial definition and mathematical folds. Preserve the whole20MiB input limit; overhead reduces usable space. v1 remains diagnostic.
- Campaign and unit-audit workers read the existing primary campaign handle in a stdlib-only startup gate. Reviews read their existing request plus its first campaign evidence handle. No additional inherited handles or larger16MiB review request:104 input/105 total handle limits remain unchanged.
- Move the bounded handle reader out of campaign_worker so startup does not import numerical modules. Pass verified bytes to the numerical stage without re-reading exhausted handles. One owner closes each handle.
- Bind expected environment pins through coordinator tickets, evaluation admission, saved state, native admission, audit source requests and review registration/current checks. The evaluator reads committed registrations independently. Missing proof cannot downgrade a registered run. Preregister both lane/run/seal/environment IDs and common mathematical input pins before either run exists.
- Unit auditors initially use their campaign registered lane. Cross-environment unit auditing is rejected until separately registered transport exists; source/wheel runs each get their own audit.
- Full input/frame hashes differ between lanes because environment provenance differs. Preserve those hashes and histories. Compare exact deterministic mathematical payloads, common data/definition/holdout pins and explicit failure/skip outcomes. Matching failures stay failed.
- Full manifests remain metered artifacts. Native receipts keep compact pins within1536B identity/2048B receipt bounds. Actual environment verification remains in fixed120s/4GiB/4core workers, outside256MiB owners and64KiB/5s RPC.
- A trusted clean-launch path starts the existing Supervisor with fresh cache policy before Python; ordinary foreground startup cannot retrospectively claim that observation. Reuse existing ownership and persistence.

Assumptions: retained exact dependency archives and current trusted Python installation define pinned local environments; hash consistency does not authenticate a hostile same-user process. No real protected data, broker action or financial qualification is admitted.

Read-only bounded design review: scope_audit. Exact next implementation: bounded immutable environment manifest and its fixtures, followed by embedded campaign transport and owner preregistration. Freeze controls before complete paired63-unit campaigns.

Bounded manifest review follow-up: pin pyvenv.cfg and disallow system-site packages; pin source egg-info metadata and the exact source tree, including refusal of unlisted pyd/sourceless bytecode. Generated installed RECORD is explicitly not original wheel evidence. Re-derive embedded payload entries from the pinned wheel archives and match every selected dependency to uv.lock, so fabricated entries cannot retain a legitimate archive hash. Keep the entire nested environment manifest within4MiB and all scans inside one worker deadline. Registration remains separate from byte observation.

Concrete transport sequencing (preparation; not implemented):

1. Freeze the common v1 mathematical campaign bytes and digest, common protocol/data/holdout/runtime pins, pair UUID and distinct run/seal/environment IDs. Pair registration commits these plus both expected manifest artifact hashes before either saved campaign exists. Pair hash must not contain the later full campaign hash, avoiding a circular digest.
2. Wrap that same mathematical input in a v2 campaign with the lane's manifest and compact pair binding. Preserve the definition/trial hashes; enforce the existing20MiB total and run byte budget after adding metadata. Read validation reconstructs the same exact envelope.
3. Keep full manifests as metered immutable artifacts. Owners validate compact registrations and bounded manifest structure; only workers scan actual dependency bytes. Do not put multi-megabyte manifests into the64KiB RPC or run numerical imports/full payload scans in256MiB owners.
4. Prefer running each lane under a clean launch of the existing Supervisor in its registered environment; its existing fixed worker launch then uses that same environment. Avoid adding an arbitrary alternate-executable route. Source and wheel runs retain distinct histories and seals in the registered pair.
5. Preserve the existing startup proof contract. Add versioned compact environment evidence in native identity/output framing only if it still fits the unchanged1536B native identity,2048B receipt and4096B frame limits. Bind expected pins before Resume, compare observed pins on acceptance/reuse, and reject removal/downgrade for registered clean runs.
6. Before foreground integration, verify that campaign preparation reaches the existing Supervisor without importing numerical libraries or doing archive/payload scans inside its256MiB owner budget. Current development_seals.create_campaign lazily calls numerical build_campaign; its fixture success alone does not establish foreground memory feasibility.
