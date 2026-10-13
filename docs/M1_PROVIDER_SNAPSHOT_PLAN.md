# Real-provider snapshot implementation

Bounded extension of the existing evidence reader. The owner's autonomous roadmap instruction supplies routine implementation authority; no additional design confirmation is required. The synthetic reader and its admission path remain unchanged.

- [x] Add tests for a distinct provider snapshot built from revalidated BarEvidence chunks. Preserve exact raw prices, raw/split observations, full pagination lineage, actual receipt times, calendar times and explicit current-vintage simulated availability.
- [x] Enforce the frozen 13-symbol universe, SIP profile, 252-session warmup, development-only dates, consistent asof, byte/row/session bounds and duplicate rejection across chunks. Report missing rows against the complete calendar rather than filling them or excluding their symbols.
- [x] Keep the snapshot diagnostic until action, identity, adjustment and fee evidence are separately bound and qualified. Its type must not pass synthetic admission. Snapshot construction is not protocol adoption or financial acceptance.
- [x] Run red/green focused tests plus existing provider/snapshot regressions. Run retained real envelopes through the adapter after the frozen warmup/reference collection.
- [ ] Complete the qualified contract and real replay integration as the next dependent increment; retain failure cases and review findings.

Scope: src/compertum/data/provider_snapshot.py and tests/test_provider_snapshot.py only for the first code increment. Tests use a fresh checked run namespace; no dependency changes. No fee-policy guess or current-asset assertion grants historical qualification. Three repair iterations per failure class.