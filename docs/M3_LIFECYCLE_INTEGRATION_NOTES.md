# M3 lifecycle integration notes

Independent read-only review by /root/scope_audit, 10 October 2026. Implementation begins after the pure qualification component is freshly verified. No real final-period data or financial authority is included.

1. Add compact typed seal, shortlist and evaluation transaction methods on the evaluation-owned StateStore. Keep generic fixture transitions unable to authorize lifecycle actions. Bind protocol/data/runtime before a fresh development run; do not relabel M2 diagnostics.
2. Freeze all12 trials and at most one candidate per horizon with existing scorecard ordering. Require pinned independent development evidence, not caller booleans or a reviewer-name string.
3. Reuse consume_once(input/protocol/shortlist pins). Flush guard and SQLite mirror before opening/decoding holdout data or admitting computation. Same-transaction replay also needs the exact retained checkpoint/unit history.
4. Keep evaluation owner as the compact authority ledger. Use coordinator-mediated fixed numerical worker admission bound to its receipt; explicit handles and existing Job/output limits. Keep ordinary development guards and real capability denials.
5. Extend recovery closure to evaluation seals, shortlist, transaction, committed fits/results and audits. Existing _fixture_lineage covers coordinator fixture/AI only; consumed seals currently have checkpoint_id=None. Preserve sticky compromise and later consumption outside replaceable backups.
6. Add narrow synthetic commands through CLI, supervisor, domain capability map and both managed-owner allowlists. Use durable idempotent request/payload binding at the evaluation owner as well as coordinator. Reuse an independent experiment_auditor entry point and fresh locked-environment reruns. Return compact references, not numerical arrays or predictions, through RPC.

## Limits and necessary supporting repairs

- Evaluation owner256MiB/one core/one process; coordinator256MiB. Do not import or execute the numerical stack inline in these owners.
- Owner/public RPC64KiB/five seconds; registration allows at most16commands. Commit/enqueue and poll; no long blocking computation through RPC.
- launch_bounded and StorageManager require coordinator ownership. Evaluation owner cannot launch a child under its existing one-process Job.
- reserve_runtime_paths reserves consumption identity/head but not new numbered events. Reserve the exact event append path before consumption, or the watchdog correctly refuses unaccounted growth.
- SQLite/checkpoint16MiB, event64KiB, exported history1024rows; keep large reports in metered artifacts.
- Complete recovery grant64MiB. Bound closure of three databases plus artifacts within it; never raise the limit to fit a fixture.
- Reject lifecycle mutations while the remote checkpoint barrier is held.
- Convert component DataError into an appropriate RuntimeRefused at the owner boundary; serve_owner_once does not catch arbitrary component exceptions.
- A remote commit may precede local coordinator receipt; remote idempotence must survive that crash.

## Existing verification to extend

Consumption and recovery: tests/test_consumption.py, tests/test_recovery.py. Ownership and persistence: tests/test_persistence.py, tests/test_owner_channel.py, tests/windows/test_remote_owners.py. Commands: tests/windows/test_control.py, tests/test_coordinator.py, tests/test_cli.py. Actual barriers: tests/windows/test_recovery_barrier.py. Budgets and denials: tests/test_storage.py, tests/test_contracts.py.

Exact next action after arithmetic receipt: implement and verify the typed evaluation-owned protocol seal and immutable fresh-development binding first. Then shortlist/consumption/checkpoint bridge, fixed worker/audit route, native crash/recovery matrix and narrow operator commands. This note is a source-backed integration map, not completed implementation or milestone acceptance.


Origin verification refinement (read-only scope_audit review,10 October2026):

Current observe-origins.py proves Compertum Python-byte/wheel equality and actual resolved package locations only. Hashing dependency RECORD metadata does not hash installed payloads or prove those inventories match uv.lock. The preregistered lane contract must pin interpreter/base/root/package/lock/source/wheel expectations; a fixed bounded worker must stream-check actual dependency files and native DLLs against manifests tied to retained wheels with locked archive hashes (or equivalently verified installation receipts). Reject missing/mismatched or unexpected importable files, duplicate/editable wheel-lane distributions and escaping paths; honor documented wheel relocation.

Bind compact origin-manifest hashes to genuine native launch observations before Resume, including the actual base executable used by CreateProcessW. Worker startup returns resolved interpreter/prefix/package/critical-module origins for acceptance against the preregistered lane. Repeat on restart. Labels and caller flags confer no authority. Keep numerical imports out of256MiB owners; full manifests stay in metered artifacts, RPC carries compact pins, and heavy file checks stay within the existing120s/4GiB worker limits with bounded file/byte counts. Measure feasibility before acceptance.
