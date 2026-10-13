# Offline M1 data component implementation plan

> For agentic workers: use superpowers:executing-plans. The owner approved this scope and delegated routine execution decisions on 9 October 2026. Primary agent implements; one independent reviewer at completion. No commits or publication.

Goal: validate synthetic daily/minute/action data, select only information available at a decision cutoff, and publish immutable reproducible snapshots using M0 storage ownership.

Architecture: pure bounded JSON validation and calendar calculations in compertum.data; snapshot publication through the existing StorageManager. No network client, provider authentication, model invocation or new runtime process. This is a library component with meaningful source and installed-wheel tests, not an active research service.

Tech stack: locked Python3.14.7; stdlib Decimal/zoneinfo/hashlib; existing exchange-calendars. No lock changes.

Spec: reports/NEXT_STEP.md and BUILD_SPEC sections7,8,16. The owner's latest instruction approves routine design and planning for this component, superseding earlier M0-only and routine review pauses.

## Constraints and decisions

- Synthetic fixtures only. Never claim verified provider coverage, M1 completion or a strategy result.
- Keep 09:25 New York decision cutoff and 09:35 minute entry reference. Include last regular-session minute and actual exchange early closes/DST.
- Input is bounded UTF-8 JSON, maximum1MiB/1024 bars. Explicit asset/session coverage binds missing-row checks. One current revision per row; no invented historical revision stream.
- Each feature session requires raw and split-adjusted daily bars, its raw close-minute reference, and the next session's raw09:35 reference for every declared asset. Daily aggregation remains explicitly PROVIDER_DAILY.
- Store actual retrieval/first-seen/admission separately from simulated historical availability. Daily availability earliest next-session09:25; raw minutes earliest minute-end plus15minutes. Feature selection uses only the preceding session and available simulated revisions. Minute references never enter feature selection.
- Split adjustment factors derive from declared split actions effective after a bar through the snapshot's last feature session. Check all OHLC fields and adjusted volume. Unknown corporate-action knowledge is diagnostic and cannot support financial acceptance.
- Decimal strings preserve price precision. Stable sorting/canonical numeric forms and JSON produce deterministic content hashes independent of input order.
- Publish originals, accepted snapshot or rejection receipt under an admitted task's artifacts directory through StorageManager. Unsafe secret-shaped input receives a hash-only rejection; never retain secrets. No overwrites. Identical repeats verify retained bytes before returning the same receipt; corrections create new identities.
- Historical M0 receipts and source bundle remain unchanged. Test scratch is a new checked .cache/test-runs directory; no new1GiB reserve fixture. Keep50GiB project/5GiB scratch caps.

## Task1: pure records and timing

Files: src/compertum/data/__init__.py, calendar.py, snapshot.py; tests/test_data_snapshot.py.
Interfaces: session_times(session_date)->SessionTimes; validate_snapshot(raw:bytes)->Snapshot; feature_rows(snapshot,execution_session)->tuple[dict,...]. Snapshot holds immutable canonical bytes, hash and diagnostic labels.

- [x] Write failing tests for normal/DST/early-close timing, duplicate JSON keys/rows, missing records, mixed feed/adjustment, nonfinite/impossible prices, future feature or late revision, and strict synthetic provenance.
- [x] Run these tests and retain RED evidence before implementation.
- [x] Implement strict field/type validation, immutable snapshot, declared coverage and feature-cutoff checks.
- [x] Verify hand-computed split adjustments, dividends/action dates and unknown action knowledge diagnostics.
- [x] Verify shuffled input yields identical normalized bytes/hash; corrected values produce a new identity.

## Task2: admitted immutable publication

Files: src/compertum/data/publication.py; tests/test_data_publication.py.
Interfaces: publish_snapshot(storage,task_id,raw,maximum_bytes)->receipt. Require coordinator-owned StorageManager; use actual bounded writers and verified reads for idempotence.

- [x] Add failing native tests for original/rejection retention, repeated publication, corruption refusal, sensitive-input hash-only rejection and aggregate output limit.
- [x] Implement publication through existing grants and manifests without changing M0 storage caps or shared databases outside owner scope.
- [x] Run native tests in a fresh small project fixture; preserve every failed artifact.

## Task3: review and reproduction

- [x] Run focused source checks and relevant M0 contracts/storage/ownership regressions.
- [x] Build a new project wheel with existing locked tools. Preserve prior wheel and environment evidence; install the new wheel offline/no-deps into the existing isolated reproduction environment.
- [x] Run the same new component tests against the installed wheel with source imports disabled, and compare deterministic snapshot hash.
- [x] Obtain one bounded independent read-only review; repair material issues and rerun affected checks. Three review/repair iterations maximum, then report any actual blocker.
- [x] Record exact commands, pass/fail/skip counts, hashes, source identity and limits in artifacts/m1 and reports/M1_OFFLINE_DATA.md. Update README and progress. No provider, broker, strategy or full-M1 acceptance claim.

## Review focus

- Unknown/extra keys and malformed timestamps must fail closed, not be silently dropped.
- Duplicate semantic timestamps/numeric representations must not evade uniqueness or change snapshot hashes.
- A future entry/close reference in a full snapshot must never be returned as a feature.
- Unknown actions and omitted/mixed adjustment rows must not look financially verified.
- Interrupted or corrupted publication must preserve evidence and refuse a false success.

Completion: 131 source/regression passes; 38 installed-wheel passes; exact snapshot/feature hash agreement; independent review cleared repairs. Runtime outputs remain SYNTHETIC. The completed recovery regression briefly exceeded scratch capacity; all128 fixture files were preserved in the verified backup-category archive and all budgets restored. See artifacts/m1/offline_data.json.
