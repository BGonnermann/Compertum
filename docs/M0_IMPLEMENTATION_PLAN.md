# M0 implementation plan

> For agentic workers: use `superpowers:executing-plans` only after separate implementation authority. The primary agent implements and integrates this plan. A bounded independent reviewer may inspect completed work; do not run speculative explorers or parallel writers. Checkbox steps below are future work, not actions performed by this documentation task.

**Goal:** Establish a reproducible local workspace with authenticated single-owner processes, durable restart records, enforced resource boundaries, and usable subscription/manual and local AI proposal workflows. No orders or strategy acceptance.

**Architecture:** One native Windows Python package, a coordinator/supervisor and independent watchdog, plus bounded trusted fixture processes. Three owner-checked state stores and a protected-consumption guard support synthetic recovery tests. M0 uses no broker transport, real holdout, data pipeline, model training or portfolio engine.

**Tech stack:** Python 3.14.7, uv, local Git, argparse/TOML/SQLite/decimal, Windows APIs through ctypes, JSON Schema, HTTPX, and the research dependencies listed in the specification. Existing Strata is a read-only external dependency except for bounded model-only qualification requests; it is not installed, restarted or reconfigured.

**Spec:** [BUILD_SPEC.md](BUILD_SPEC.md), version 1.1, especially sections 3-7, 12 and M0 in section 16. The specification is authoritative. Record its actual SHA-256 and this plan's hash in implementation receipts.

## Global constraints

- New spending is $0. Approximately $300/month is reserve, never an automatic allocation or spending target.
- Native Windows 11; Ryzen 7 7700X; RTX 5070 Ti; 64 GB DDR5; plan within 1 TB total storage. Recheck capabilities rather than assume the earlier observations remain current.
- Prioritize existing OpenAI Pro 20x through March 2027; no API credits, new account permissions, login changes, paid APIs, purchased credits or renewals.
- Project storage cap is 50 GiB: 15 GiB data, 5 GiB quant models, 5 GiB scratch, 5 GiB records/logs/code, 20 GiB backups. The 1 GiB execution reserve is inside the 5 GiB records/logs/code category, not an additional allocation.
- One heavy deterministic job or one local inference request; at most 4 CPU threads, 4 GiB research RAM, no daily CPU-job wall-time cap per the 12 October owner amendment, 8 AI tasks and 40 AI requests/day. All retries count.
- Local AI requests have at most 16,384 input tokens, 2,048 output tokens and 120 seconds; use the exact qualified Strata model identity, not a guessed alias.
- No unbounded disk writes, arbitrary AI-generated code, credential inheritance, external repository, administrator elevation or power/security-setting changes.
- M0 starts disarmed and cannot enable any broker mutation, actual protected evaluation, strategy promotion, authenticated market-data fetch or M1 campaign.
- Do not implement sections 8-11's financial calculations in M0. Their timing/scoring/covariance tests belong to M1-M3. M0 records their protocol identities without producing financial results.
- Tests use a new, checked `.cache/test-runs/TEST_RUN_ID` namespace inside this workspace, charged to scratch; do not reuse or recursively clear unrelated directories. Scale disk/resource fault fixtures instead of filling the real volume. Preserve acceptance receipts before approved fixture cleanup.
- This document authorizes documentation only. Dependency downloads, package installation, Git initialization, source/tests/config creation and live local qualification occur only after later M0 implementation authority.

## Review focus

Each input class has an owning task and an explicit check below:

1. Duplicate starts, root aliases, stale metadata and PID reuse must never create another mutable owner. Task 3.
2. A valid Windows user pretending to be another application role must not receive writer capabilities. Task 3.
3. Library/temp/log growth and an unrelated disk writer must not consume reserved journal headroom. Task 5.
4. An older backup, missing consumption guard or partially delivered durable message must not reopen evaluation or repeat a broker side effect. Tasks 4 and 6.
5. Malformed/late AI responses, timeouts and provider loss must preserve tasks and leave ordinary trusted fixture work usable without AI. Tasks 7 and 8.

## Dependencies and expected outputs

| Task | Depends on | Independently reviewable output |
| --- | --- | --- |
| 1. Workspace/environment | Later implementation authority | Local source-control/environment receipts and compatible lock |
| 2. Contracts/configuration | 1 | Validated domain types, schemas and M0 capability matrix |
| 3. Single owners and IPC | 2 | Native ownership and authenticated-role test receipts |
| 4. State and durable events | 3 | Owner-checked state/event stores and consumption guard |
| 5. Resource/storage controls | 3, 4 | Job Object limits, byte reservations, watchdog storage checks |
| 6. Recovery sets | 4, 5 | Cross-store recovery manifest and rollback-safe restore fixtures |
| 7. Supervisor and terminal flow | 2-6 | Working M0 commands and durable offline fixture lifecycle |
| 8. AI proposal workflows | 5, 7 | Manual bridge, bounded Strata adapter and capability receipts |
| 9. M0 verification | 1-8 | Clean rerun, independent review and honest M0 acceptance report |

Execute in this order. Every task finishes its focused checks and repair before dependent work. Do not add M1 to make M0's result look complete.

## Task 1: Establish a reproducible local environment

Files to create after implementation authority: `AGENTS.md`, `.gitignore`, `pyproject.toml`, `.python-version`, `uv.lock`, `src/compertum/__init__.py`, and an environment-receipt helper at `tools/environment_receipt.py`. Existing requirements/spec/plan remain preserved. Use a standard `src` package layout; declare the inspected Python 3.14.7 interpreter and package entry point, with no source-build dependency workaround.

Interfaces: `collect_environment(project_root: Path) -> dict` returns observed tool/interpreter/dependency versions, OS/build, non-secret hardware/storage capabilities, source/document hashes and explicitly unknown fields. It writes only when the caller supplies an admitted receipt destination. The helper must not inspect auth files, dump environment variables or query an authenticated account.

- [ ] Read project guidance/current files and compare the preparation/spec hashes before writing source. Preserve unrelated changes.
- [ ] Initialize local Git without a remote. Add ignored rules for `.venv`, `.cache`, runtime state, data/artifacts/backups and local secret files. Track source, schemas, docs and the lock. Never stage secret values.
- [ ] Define the package/dependencies from BUILD_SPEC section 3. Include jsonschema and the Windows timezone/calendar dependencies; exclude PyTorch and a paid provider SDK. Use static project metadata and `setuptools.build_meta` for the local src package; lock setuptools/wheel in the development group as well as the runtime dependencies. Route uv cache under `.cache/uv` and charge it to scratch storage. If compatible third-party wheels cannot be resolved, retain the error receipt and stop environment activation; request an interpreter decision rather than silently installing 3.13.
- [ ] Resolve/install third-party wheels only after later implementation authority. Use the existing interpreter and disable managed downloads/source distributions. Install the local project separately with its already locked backend, without dependency resolution or build isolation; this permits packaging owned source without permitting third-party source-build fallback. [uv command contracts](https://docs.astral.sh/uv/reference/cli/).

Future commands, verified against the available uv help but not executed now:

```powershell
git init
uv lock --python 'C:\Program Files\Python314\python.exe' --no-managed-python --no-build --cache-dir .cache/uv
uv sync --locked --no-install-project --python 'C:\Program Files\Python314\python.exe' --no-managed-python --no-build --cache-dir .cache/uv
uv pip install --no-deps --no-build-isolation --editable . --python '.\.venv\Scripts\python.exe' --cache-dir .cache/uv
```

- [ ] Verify every specified dependency imports in `.venv`, capture resolved versions/lock hash and wheel identities, and reproduce them in a second fresh environment under the same project budget. Do not use Strata's environment. A mocked incompatible-wheel check must produce a blocked receipt without creating an active environment or changing the lock silently.
- [ ] Review only this task's diff; make a local commit using an existing configured Git identity. If identity is unavailable, retain a source hash/patch and record that decision pending; do not invent identity or modify global configuration.

Expected output: `artifacts/m0/environment.json`, dependency lock, source-control status and a clean-import receipt. These prove reproducibility/capability only. Setup/cache/environment bytes count toward the project cap even before runtime metering exists.

## Task 2: Define validated foundation contracts

Files: create `src/compertum/domain.py`, `src/compertum/config.py`, `config/default.toml`; create `schemas/task.v1.json`, `schemas/control_receipt.v1.json`, `schemas/artifact_manifest.v1.json`, `schemas/recovery_manifest.v1.json`, `schemas/ai_proposal.v1.json`; test in `tests/test_contracts.py` and `tests/test_config.py`.

Interfaces:

- `load_config(path: Path, project_root: Path) -> M0Config` parses TOML, validates exact defaults/paths and returns immutable resolved settings.
- `validate_record(schema_name: str, payload: dict) -> dict` rejects unknown schema versions, unknown fields, non-finite numbers, invalid UTC timestamps and out-of-root artifact paths.
- `TaskSpec` carries IDs, role/kind, immutable input/schema/code hashes, permissions, deadline, attempts and CPU/RAM/storage/AI budgets from section 6. Only `OFFLINE_FIXTURE`, `AI_PROPOSAL`, `AI_QUALIFICATION` and synthetic recovery fixture tasks are admitted by M0.
- `ControlReceipt` contains `request_id`, action, target, confirmed state/evidence label, process generation, UTC timestamps, exit code, reason and artifact references. A submitted request is not a confirmed effect.
- `ProcessIdentity` contains process-instance UUID, PID, creation FILETIME, operator SID and role. `OwnerLease` additionally contains project identity, generation and a private live handle; no capability/handle is serialized.
- `ArtifactManifest` and `RecoveryManifest` contain the lengths/hashes/lineage and complete recovery fields in BUILD_SPEC section 7. All schemas use `additionalProperties=false`.

- [ ] Write failure cases `test_reject_unknown_field_and_schema`, `test_reject_nonfinite_and_non_utc_time`, `test_reject_artifact_escape_and_reparse_target`, and `test_budget_cannot_increase_itself`. Assert explicit reasons, not just exceptions.
- [ ] Run them with `python -m pytest tests/test_contracts.py tests/test_config.py`; confirm missing behavior before adding the minimal parsers/types.
- [ ] Implement the signatures and frozen domain records. Explicitly distinguish `WAITING_FOR_OPERATOR`, active task time and its 24-hour manual deadline. Store money/budgets as integer bytes or decimal strings with declared units.
- [ ] Freeze an M0 capability matrix. Paper/data/evaluation/promotion actions return exit 3 `CAPABILITY_UNAVAILABLE` and never instantiate a transport; status uses `NOT_CONFIGURED` for broker state, not invented empty/flat positions.
- [ ] Rerun focused tests and inspect resolved defaults against the preserved $0/50 GiB/resource limits. Commit only task files after review.

Expected output: versioned schemas, `artifacts/m0/config.json` with no secrets, and a contract-test receipt. No real stock universe selection, data fetch or financial engine is needed.

## Task 3: Enforce single-owner startup and role-authenticated IPC

Files: create `src/compertum/runtime/__init__.py`, `identity.py`, `owners.py`, `ipc.py`; test in `tests/windows/test_ownership.py`, `tests/windows/test_ipc.py` and a bounded helper `tests/helpers/role_holder.py`. Windows-specific tests are mandatory on this target; a skipped native test remains unverified.

Interfaces:

- `resolve_project(root: Path) -> ProjectIdentity`, with canonical `root_path`, `project_id`, volume/root file identity and operator SID.
- `acquire_owner(project: ProjectIdentity, role: str) -> OwnerLease`, covering `supervisor`, `coordinator`, `evaluation`, `execution`, `watchdog` and `recovery` locks.
- `verify_prior_exit(previous: ProcessIdentity) -> ExitEvidence`; combine exclusive owner acquisition with a signaled verified prior handle, native verified absence, or verified creation-time mismatch at a reused PID. No PID-file-only, heartbeat-only or access-denied-as-absence evidence.
- `start_role_pipe(lease: OwnerLease, allowed_commands: frozenset[str]) -> RoleEndpoint` and `request(endpoint: RoleEndpoint, command: dict) -> ControlReceipt`.
- Peer registration binds OS-reported PID/creation time/SID, instance, role, project and generation. Private role capabilities use the bootstrap pipe; CLI/operator control rights never become writer rights.

- [ ] Write native tests for two synchronized starts of the same role: exactly one live exclusive owner, no second writable-state initialization. Before Task 4's stores exist, use a bounded initializer callback to observe this guard; later repeat against real stores. Repeat with path case differences, an existing root alias and restart overlap.
- [ ] Add a fixture where the owner thread stops but the process/handle remains live. Replacement must be refused. Metadata/PID alone cannot authenticate or terminate a reused-PID process; use the verified creation-time/exclusive-lock path only to prove the old instance ended. Access-denied identity checking fails closed. Repeat crash recovery after closing every retained parent process handle; verified absence must allow one conservative replacement, including the prior-boot/reclaimed-object fixture.
- [ ] Implement non-inherited `CreateFileW` share-zero owner handles and atomic separate role metadata. Handle root resolution via Windows final path/file identity. Do not use a PID file or thread-owned mutex as the authority.
- [ ] Implement local-only restricted named pipes, OS peer checks and private scoped capabilities. Tests `test_wrong_role_or_generation_denied`, `test_spoofed_pid_does_not_authenticate`, `test_cli_cannot_claim_writer`, and `test_unexpected_pipe_server_denied` must reject before dispatch. Replay of a completed request ID returns the existing receipt without repeating an effect.
- [ ] Verify a proved-dead owner can be replaced once, with a new generation and expired old capability. Use fixture holders for the future execution role, with no broker code/credentials. Run `python -m pytest tests/windows/test_ownership.py tests/windows/test_ipc.py` and commit reviewed files.

Expected output: `artifacts/m0/ownership.json` and `ipc.json`, recording native observations, process instances/generations and denied attempts without private capabilities. A simultaneous-start success assertion is based on observed live handles, not a mocked mutex response.

## Task 4: Persist owned state, durable messages and consumption guards

Files: create `src/compertum/persistence.py`, `src/compertum/events.py`, `src/compertum/consumption.py`, `schemas/consumption_event.v1.json`; test in `tests/test_persistence.py`, `tests/test_events.py`, `tests/test_consumption.py`.

Interfaces:

- `open_store(lease: OwnerLease, db_role: str) -> StateStore` maps coordinator to `research.sqlite`, evaluation to `evaluation.sqlite`, execution to `execution.sqlite`; wrong role/generation cannot write.
- `StateStore.commit_event(event: dict) -> EventReceipt` atomically persists event/outbox and affected local state. `accept_message(event: dict) -> EventReceipt` stores inbox/deduplication with the receiving transition.
- `StateStore.checkpoint(barrier_id: str, destination: Path) -> DbCheckpoint` reports snapshot hash, schema, source generation, pending events and high-water marks.
- `consume_once(lease: OwnerLease, seal_id: str, evaluation_id: str, inputs: dict) -> ConsumptionReceipt` appends/flushed guard evidence then mirrors it in the evaluation store. M0 invokes this only for synthetic seals without any holdout reader.
- `verify_consumption_guard(project: ProjectIdentity) -> GuardEvidence` distinguishes verified latest chain, missing/corrupt/uncertain status and consumed IDs. It never reconstructs unused authority from an older backup alone.

- [ ] Write checks for wrong-owner write denial, duplicate event/message delivery, crash between local commit and delivery, and a lost acknowledgement. Expected result is one transition with a retained pending receipt, not duplicate history.
- [ ] Create versioned DB schemas using WAL, `synchronous=FULL`, foreign keys and unique event/request IDs. Record task/attempt/checkpoint lineage and interrupted status. Broker-related tables may be schema-only; no broker request implementation is part of this task.
- [ ] Implement guard creation/append/head flushing and consumed-only-forward state. Tests must show no simulated protected-read callback runs when either guard or DB mirror fails. Guard tokens are synthetic IDs, not model/data access.
- [ ] Test a recovery boundary containing pending safe messages and a synthetic `BROKER_SIDE_EFFECT` message. Safe message deduplication works; the side-effect record is nonreplayable and never dispatched as a write.
- [ ] Run `python -m pytest tests/test_persistence.py tests/test_events.py tests/test_consumption.py`. Inspect real SQLite rows and guard files, then commit.

Expected output: empty/fixture-only owner stores, durable event/checkpoint receipts and `artifacts/m0/persistence.json`. State stores are initialized by their designated lease holders, not by an unrestricted coordinator writing all DBs.

## Task 5: Enforce process budgets and bounded storage independently

Files: create `src/compertum/runtime/jobs.py`, `src/compertum/storage.py`, `src/compertum/watchdog.py`; test in `tests/windows/test_jobs.py`, `tests/test_storage.py`, `tests/windows/test_storage_monitor.py`; helpers under `tests/helpers/` may only consume bounded resources in temporary test directories.

Interfaces:

- `launch_bounded(lease: OwnerLease, task: TaskSpec, argv: list[str]) -> JobHandle` launches only registered trusted fixture/template commands, suspended and assigned before resume.
- `reserve_bytes(task_id: str, category: str, maximum: int) -> StorageGrant` is serialized through the coordinator-owned reservation ledger.
- `open_artifact(grant: StorageGrant, relative_path: str) -> BoundedWriter`; `BoundedWriter.write(chunk: bytes)` checks before write and accepts at most 8 MiB chunks; `publish() -> ArtifactManifest` flushes/hashes/renames and transfers reserved bytes to retained usage.
- `sample_storage(project: ProjectIdentity) -> StorageObservation` records actual allocation/free capacity and monitoring time. `check_storage(observation, reservations) -> ControlReceipt` can only restrict admission.
- `create_journal_reserve(lease: OwnerLease, bytes: int) -> ReserveReceipt` and `release_journal_reserve(lease, bytes: int, incident_id: str)` require the execution role, even in a synthetic holder. No research borrower is admitted.

- [ ] Write failure tests for failed Job assignment/no resume, whole-child-tree termination on timeout, committed-memory excess and attempted breakaway. Use small bounded native fixtures; record child PIDs and actual exit, not only a reported timeout flag.
- [ ] Implement verified Job Object limits and wall deadlines. Set child thread/affinity limits and sanitize its environment; no arbitrary executable, secret-bearing environment or free network access. Local fixture defaults stay below the full 4 GiB/30-minute ceiling.
- [ ] Write storage tests for an output chunk crossing remaining capacity, simultaneous reservations, temp+final/copy accounting, WAL/log growth, abrupt worker death, duplicate publish, out-of-root/reparse targets and recount after restart. Crossing bytes must never be written. Do not silently raise caps or auto-delete failed evidence.
- [ ] Implement metered sinks/reservations and allocate/verify the real 1 GiB non-sparse reserve under the existing category budget during later authorized setup. Test reserve release/refill logic with small scaled fixture files first; full reserve verification records measured allocated bytes. Installation/env/cache/log files remain counted.
- [ ] Test independent disk growth: a separate fixture writer bypasses the artifact API within a small test namespace; watchdog detects actual growth within 5 s, refuses further research writes, and leaves the journal reserve inaccessible to that writer. Test a simulated free-space drop below 50 GiB without filling the real disk. Below 256 MiB reserve, failed flush or stale monitoring, broker capability remains blocked. Do not fill C: or alter OS quotas.
- [ ] Run `python -m pytest tests/windows/test_jobs.py tests/test_storage.py tests/windows/test_storage_monitor.py`, inspect actual bounded files/terminated children, and commit.

Expected output: `artifacts/m0/resources.json`, storage reservations/counters, verified journal-reserve receipt and disk-growth incident. Job limits and storage acceptance are separate evidence fields. Unsupported native enforcement is `CAPABILITY_UNAVAILABLE`, not a passing skip.

## Task 6: Publish and restore a consistent recovery set

Files: create `src/compertum/recovery.py`; test in `tests/test_recovery.py` and `tests/windows/test_recovery_barrier.py` using three fixture-owned DBs and small referenced artifacts.

Interfaces:

- `collect_recovery_set(project: ProjectIdentity, owners: list[RoleEndpoint], grant: StorageGrant) -> RecoveryManifest` requests a shared barrier, snapshots each store through its owner, captures pending events and pins the artifact closure.
- `validate_recovery_set(manifest_path: Path) -> RecoveryValidation` checks hashes, schema/generation consistency, messages and transitive references.
- `restore_recovery_set(manifest_path: Path, current_guard: GuardEvidence, destination: Path) -> RestoreReceipt` is permitted only under the exclusive recovery/restore owner handles with prior writers stopped. It stages new state, preserves current evidence, merges sticky consumption, invalidates arms/plans and never replays broker writes.

- [ ] Create a three-store barrier test with one pending event, one acknowledged event and a referenced artifact. Require verified matching high-water/deduplication records, not merely three individually valid SQLite files.
- [ ] Implement the 30-second checkpoint-barrier deadline, paused message delivery and publication only after every snapshot/required artifact validates. Missing owner/hash/artifact yields an incomplete receipt and no published recovery manifest. Release the barrier conservatively after failure.
- [ ] Implement staged restore with a restore-operation journal so a crash between individual DB replacements cannot advertise a mixed set as active. Preserve previous state; a restart must complete/abort the recorded recovery consistently before any writer admission. Guard evidence is never replaced by the selected backup.
- [ ] Add the rollback test: backup A has synthetic `SEAL_A=UNUSED`; later consume it under `EVAL_A`, persist the guard and make B. Restore A with the verified later guard: DB state must remain consumed, and a new evaluation request must fail. Remove/corrupt/unverify later evidence and restore A again: state must be `EVALUATION_COMPROMISED`, never unused. Original evaluation continuation requires matching ID/input/checkpoint, not a fresh request.
- [ ] Test pending safe-message replay once, nonreplayable broker-message retention, old armed/approved-plan state becoming invalid, missing/corrupt artifact rejection and backup budget exhaustion. No real protected data or account is used.
- [ ] Run `python -m pytest tests/test_recovery.py tests/windows/test_recovery_barrier.py`, read restored DB rows and manifests, then commit.

Expected output: `artifacts/m0/recovery.json`, complete synthetic recovery manifests and restore receipts. This proves the foundation's recovery semantics; M3/M4/M6 later repeat the relevant checks against their actual evaluator/execution/operating artifacts.

## Task 7: Connect the supervisor and M0 terminal commands

Files: create `src/compertum/coordinator.py`, `src/compertum/runtime/supervisor.py`, `src/compertum/cli.py`, `src/compertum/__main__.py`, `src/compertum/foundation.py`; test in `tests/test_cli.py`, `tests/windows/test_m0_lifecycle.py`, with one registered offline fixture worker under `tests/helpers/`.

Interfaces:

- `start_research(config: M0Config) -> ControlReceipt` attaches to or starts the unique supervisor/coordinator/watchdog; no execution transport is activated.
- `submit_fixture(task: TaskSpec) -> str` admits only the M0 fixture task kind and records its lease/attempt/resources/artifact/checkpoint. It is not a campaign runner.
- `get_status() -> dict`, `pause_research(reason: str) -> ControlReceipt`, `resume_research() -> ControlReceipt`, `stop_run(run_id: str) -> ControlReceipt`, and `shutdown_checkpoint() -> ControlReceipt` use authenticated IPC and their named stores.
- `run_foundation_suite(config: M0Config, offline: bool) -> ControlReceipt` returns a foundation receipt, never a strategy score.

- [ ] Write lifecycle tests for confirmed pause within 30 s, restart from a matching fixture checkpoint, mismatched hash refusal, interrupted attempt retention and duplicate request deduplication. The fixture produces a small canonical deterministic artifact; assert its hash from independent expected bytes after restart.
- [ ] Implement 5-second heartbeats, 30-second task leases, mutual role/storage health checks and conservative admission. Default broker status is `NOT_CONFIGURED`, strategy state `NOT_EVALUATED`, order admission `DISARMED`. Do not fake monitoring of an execution process that is not active.
- [ ] Implement only M0-supported commands: `doctor --read-only`, `start --mode research --config config/default.toml`, `status`, research pause/resume/stop, `shutdown --checkpoint`, AI commands after Task 8, and `foundation check --suite m0 --offline`. The foundation command is a trusted local fixture orchestration check. Other spec commands must fail explicitly with exit 3 and no side effect.
- [ ] Test doctor/status read-only behavior against the real file inventory; invocation must not create an environment, configure/login to a provider or allocate the journal reserve. Doctor may probe approved loopback health without invoking inference. Test `start --mode supervised-paper`, `data fetch`, `evaluate final` and paper/order verbs are unavailable in M0.
- [ ] Run the M0 terminal walkthrough in two terminals: start/attach/status, offline fixture, pause/checkpoint/resume, bounded stop and shutdown. Verify the original worker state/artifacts and one owner, then run `python -m pytest tests/test_cli.py tests/windows/test_m0_lifecycle.py` and commit.

Expected output: readable terminal status, `artifacts/m0/lifecycle.json` and preserved fixture history. AI outage must not prevent this deterministic suite from completing.

## Task 8: Qualify proposal-only AI workflows

Files: create `src/compertum/ai/__init__.py`, `manual.py`, `strata.py`, `qualification.py`; create `tests/test_ai_manual.py`, `tests/test_ai_strata_contract.py`, `tests/windows/test_ai_timeout.py`, and small sanitized fixtures under `tests/fixtures/ai/`.

Interfaces:

- `export_subscription_task(task: TaskSpec) -> ArtifactManifest` contains only admitted sanitized development/fixture inputs and the expected response schema.
- `import_proposal(task_id: str, response_path: Path, metadata: dict) -> ControlReceipt` validates schema/provenance/deadline/budget, retains the original and returns a proposal without executing code/tools.
- `probe_strata(base_url: str) -> CapabilityReceipt`, `request_proposal(task: TaskSpec, messages: list[dict]) -> ProposalReceipt`, and `qualify_strata(suite: str) -> QualificationReceipt` permit only the recorded loopback endpoint, approved request dialect, bounded messages and no MCP.
- `provider_status() -> dict` reports subscription access/quota unknown when unobserved; local health/capability and evidence time are separate fields.

- [ ] Write manual bridge tests for protected-sentinel/out-of-bundle read denial, secret-shaped input denial without printing the value, schema/unknown-field rejection, response mismatch/24-hour expiry, and no executable side effects. Export/import a synthetic subscription packet to prove the bridge without claiming an actual hosted model response.
- [ ] Implement the bridge and manual waiting clock. Existing operator-controlled ChatGPT/Codex use remains the primary provider. Do not read auth stores, log in, seed tokens, configure an API or enable automatic Codex execution. Any optional automatic adapter remains disabled pending the separately verified permissions/billing gates.
- [ ] Write deterministic local-server tests for malformed JSON, injected tool request, context/input/output limits, HTTP failure, timeout, retry ceiling and task-context isolation. Use HTTPX with environment proxy inheritance disabled; no non-loopback request or actual tool execution is possible. At most one transport retry/provider and one schema-repair request/task fit inside the declared attempts/requests.
- [ ] Implement client-side schema/token validation and qualified fallback. If the shared server is busy/unreachable, record pending/unavailable; do not restart it or steal/cancel another user's request. After a timed-out owned request, stop new local dispatch until its completion/idle state is verified; do not issue a global cancellation against unknown requests.
- [ ] Under later implementation authority, run the bounded live worker-v1 suite against the existing idle Strata endpoint: JSON object, math-domain check, forced fictional tool proposal, second-turn response using a dispatcher-supplied fixture result, and two isolated task contexts. No offered function has a real filesystem/broker effect. Test context overflow/malformed/timeout recovery primarily with the deterministic server and preflight rejection. Record native cancellation/owned-timeout behavior separately; if not established, mark that capability unverified and keep affected autonomous tasks disabled.
- [ ] Record model/engine/context/serving-slot, binary/model/tokenizer/template/config hashes with secret fields excluded, exact prompts/responses/settings/latency/usage when available. Hash existing weight files in place; do not download/copy them. A smoke test alone must not claim the full qualification gate passed.
- [ ] Prove both AI providers unavailable pauses only AI-dependent dispatch while the Task 7 offline suite/heartbeat/persistence continues. Run `python -m pytest tests/test_ai_manual.py tests/test_ai_strata_contract.py tests/windows/test_ai_timeout.py`; inspect provider receipts and commit.

Expected output: `artifacts/m0/ai/manual_bridge.json`, sanitized original packets/responses, and `artifacts/m0/ai/strata_worker_v1.json`. Manual hosted usage/expiry/quota stays pending unless actually observed. Tested, pending and unavailable capabilities remain distinct.

## Task 9: Verify M0 and publish an honest acceptance receipt

Files: create `tools/verify_m0.py` and `tests/test_m0_receipt.py`; produce runtime verification records and `reports/M0_ACCEPTANCE.md` only during the later implementation task. Review the new source against BUILD_SPEC/M0 scope before executing the full gate.

Interfaces: `verify_m0(project_root: Path) -> M0AcceptanceReceipt` runs the required native/offline checks, records exact commands/exit codes/artifact hashes/environment and assigns each condition `VERIFIED_PASS`, `VERIFIED_FAIL`, `UNVERIFIED` or `PENDING_EXTERNAL_TIME`. It cannot change capability flags to hide missing evidence.

- [ ] Confirm the implementation contains no broker transport/credential reader, real evaluator/data collector, promotion bypass, external repository or paid provider configuration. Check the actual command/module graph, not only a no-orders configuration flag.
- [ ] Run the entire M0 test suite once in the locked environment, then reproduce the offline foundation artifact and schema/state behavior in a second clean environment. Repeat only after a material repair/failure.

Future acceptance commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp .cache/test-runs/TEST_RUN_ID
.\.venv\Scripts\python.exe -m compertum doctor --read-only --json
.\.venv\Scripts\python.exe -m compertum foundation check --suite m0 --offline --json
.\.venv\Scripts\python.exe tools/verify_m0.py
```

- [ ] Independently inspect singleton/authentication, Job assignment, disk growth and pre-consumption-backup restore evidence. The primary agent repairs material findings and reruns affected checks. No reviewer writes shared product/state while the primary is integrating.
- [ ] Reconcile outputs against all M0 obligations in the matrix below, inspect file/status inventories and issue one acceptance report. No observed candidate/trading result exists in M0.
- [ ] Finish M0 only after required gates pass. If native isolation/storage/local qualification cannot be verified, report `M0_BLOCKED` with the exact failed/unverified condition and preserve unaffected work. Never label a skipped test or missing Strata capability as passed.

Expected output: `artifacts/m0/acceptance.json`, reproducibility/review receipts and `reports/M0_ACCEPTANCE.md`. Report `ENGINEERING_FOUNDATIONS_READY` only when supported, always `STRATEGY_NOT_EVALUATED` and `PAPER_DISABLED`. State the next milestone as M1 without starting it or asking to perform already unauthorized external work.

## M0 acceptance matrix

| Gate | Required evidence | Owning tasks |
| --- | --- | --- |
| Compatible isolated environment | Actual lock/import/second-environment receipts; source/document versions preserved | 1, 9 |
| Contracts and no-order capability | Invalid inputs rejected; unavailable financial commands cannot instantiate transport; no fabricated broker state | 2, 7, 9 |
| One owner and verified roles | Native simultaneous-start/overlap/root-alias/peer tests; new generation invalidates old capability | 3, 7 |
| Durable records/messages | Real DB/event/attempt/checkpoint inspection; duplicate delivery once | 4, 7 |
| Processes and storage | Assignment-before-resume, actual child exits, crossing write refused, independent growth incident, verified reserved bytes | 5 |
| Recovery cannot unconsume | Complete manifest/artifact/message closure; old backup keeps consumed status or compromises seal when latest evidence unavailable | 4, 6 |
| Deterministic operation without AI | Offline trusted fixture hash agrees across restart/clean rerun; status/watchdog remains operational | 7, 8, 9 |
| Subscription-first/manual bridge | Sanitized export/import, honest manual provenance/wait/usage status, no new auth/API configuration | 8 |
| Qualified bounded local fallback | Recorded live model-only checks plus deterministic denial/timeout/isolation tests; any missing capability blocks its automatic use | 8, 9 |
| Scope and audit | Independent review and full M0 reconciliation; no M1-M6 product implementation or strategy claim | 9 |

## Decisions and capability gates retained

The specification's proposed defaults are sufficient to prepare M0. Exact package pins await wheel resolution during authorized setup. A different Python interpreter, altered model/server configuration, more storage, a backup location outside this workspace, subscription login/permissions, or paid usage requires its own concrete decision/authority. Free Alpaca entitlement/actions/quotes, universe/benchmark adoption and paper limits remain later-milestone gates. None is a reason to access credentials or implement trading in M0.

The first inspection's provider/hardware observations are dated evidence, not a fresh run of this plan. Native enforcement and fallback capabilities can produce a blocked result. No financial acceptance criterion is weakened to accommodate a tool/setup failure. Implementation is not started by writing or reviewing this plan.
