# Supervised research cycle implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for primary-agent implementation. Steps use checkboxes for tracking.

**Goal:** Complete one native synthetic campaign, verify its results, save an AI assessment and revised proposal, then stop for owner review.

**Architecture:** Add a coordinator-owned cycle controller around the existing research, unit-audit, and campaign-review controllers.
Keep numerical execution and artifact ownership in those existing components.
Use the manual AI exchange for feedback and preserve immutable links between the evidence, assessment, and revised proposal.

**Tech Stack:** Existing Python environment, SQLite, JSON schemas, Windows Job Objects, and pytest. No new dependency or service.

**Spec:** `docs/superpowers/specs/2026-10-19-supervised-research-cycle-design.md`, approved by the owner in this conversation.

## Global constraints

- Work in master. Preserve existing dirty work, runtime identities, failed attempts, and evidence.
- The primary agent implements and integrates. Use one independent reviewer at a time; no parallel writers.
- Keep new spending at $0. Strata, broker actions, paid data, services, and protected evaluation remain excluded.
- Keep twelve variants, the 63-unit schedule, financial checks, and existing worker limits unchanged.
- Keep source-test jobs at 120 seconds, one CPU, and 4 GiB. Capacity jobs retain 128 MiB.
- Keep native worker deadlines at 120 seconds, CPU limits at four, and worker memory at 4 GiB.
- Use one heavy job at a time and the existing 16/12 GiB verification host-memory floors.
- Keep 50 GiB total storage and current category and folder ceilings. No cleanup-check bypass or unrelated process termination.
- Keep the manual response deadline at 86,400 seconds and the encoded packet ceiling at 131,072 bytes.
- Actual numerical results come only from existing workers. Never fabricate completion, failures, or dependency skips in acceptance evidence.
- Distinguish source, simulated, native, installed-package, financial, and supervised-session results.
- Use plain English. Keep instructions within 20 words and other project sentences within 25 words where practical.
- Commit verified local checkpoints without staging unrelated work. Publication remains a separate owner boundary.
- Use at most three repair/review rounds per failure class. Preserve every consumed attempt.

## Proposed acceptance-run allowance

This is a new foreground test envelope. It does not alter existing source-test wrappers or production limits.
Plan approval authorizes this envelope only after fresh capacity admission and independent preparation review.

| Bound | Exact proposed value |
| --- | --- |
| Full native cycle envelope | 1,800 seconds, including startup, numerical work, audits, and process cleanup |
| Aggregate process memory | 4 GiB for the complete test process tree |
| CPU affinity | One available logical processor for the envelope and inherited children |
| Active process count | At most 16; no breakaway; kill on job close |
| Native numerical and audit jobs | Existing 120-second deadlines and existing process/output limits |
| Host-memory floors | 16 GiB at admission; 12 GiB during execution |
| Fresh acceptance folder | 128 MiB, inside the unchanged 448 MiB local-economics namespace |
| Preparation folder | At most 4 MiB, also inside that namespace |
| New verification receipts | At most 1 MiB total, inside the existing 2 MiB history-verification evidence folder |
| New attempts | One smoke attempt and one full-cycle attempt initially; distinct reviewed repair attempts only |
| Automatic retries | Zero for the acceptance envelope; existing transient-attempt records remain intact |

The 128 MiB acceptance ceiling includes inputs, outputs, databases, staging files, review artifacts, and feedback records.
The campaign's own allowance must not exceed that folder ceiling. Existing per-write reservations still apply.
Do not claim that capacity is available until a complete fresh census passes.
Cleanup may be necessary. If existing folders cannot fit these holds, stop dependent jobs and present the measured shortfall.
Do not reduce an emergency reserve, change a fixture identity, or install a new environment to force admission.
Any additional wheel or environment artifact must fit these bounds; otherwise report that prerequisite separately.
The native identity check must pass with actual observed identities. Do not patch identity functions in the acceptance run.

The cycle envelope exits before manual feedback. Waiting for assessment holds no worker lease or CPU reservation.
A later bounded feedback import reopens the same saved evidence without restarting campaign execution.
No background service or scheduled continuation is included.

## File responsibilities

| File | Responsibility |
| --- | --- |
| `src/compertum/ai/cycle_record.py` | Bounded cycle records, transitions, immutable bindings, and durable dispatch intents |
| `src/compertum/ai/cycle.py` | One foreground cycle; use existing controllers for all work |
| `src/compertum/ai/cycle_feedback.py` | Development packet, assessment validation, and revised-proposal linkage |
| `src/compertum/coordinator.py` | Exact authenticated owner-facing cycle control entry point |
| `src/compertum/ai/manual.py` | Honest current-session provenance and existing manual import/export reuse |
| `src/compertum/domain.py` | Register the new record schemas and owner-facing receipt actions |
| `schemas/research_cycle.v1.json` | Durable cycle record contract |
| `schemas/research_assessment.v1.json` | Evidence-bound assessment contract |
| `schemas/research_revision_link.v1.json` | Immutable cycle-to-assessment-to-proposal link |
| `tools/prepare_research_cycle.py` | Fresh bounded jobs, source fingerprints, and capacity requirements |
| `tools/run_research_cycle_acceptance.py` | Foreground native acceptance driver and bounded result receipt |
| `tests/helpers/research_cycle_fixture.py` | Shared synthetic inputs and real native fixture setup |
| `tests/helpers/research_cycle_restart.py` | Separate owner lifetimes for interruption tests |
| `tests/test_research_cycle.py` | Control, continuation, pause, cancellation, and duplicate tests |
| `tests/test_research_cycle_feedback.py` | Packet, assessment, provenance, and revision tests |
| `tests/windows/test_research_cycle_native.py` | Real approved-start smoke and native acceptance assertions |

Do not modify `runtime/supervisor.py` or transport allowlists merely to expose the feature.
The foreground driver owns polling and supervision during the engineering run.
An explicit check must prevent a cycle from competing with direct research or review control.
If enforcing that ownership needs a small existing-controller change, add its exact file and test before editing it.

## Review focus

1. A crash after durable dispatch intent must not replay a unit whose launch remains uncertain.
2. A valid receipt from another campaign, owner, or changed environment must not satisfy this cycle.
3. A pause between completed work and the next dispatch must prevent that dispatch.
4. Oversized or protected feedback content must fail without truncation or widening the manual packet limit.
5. A partial feedback import must recover its original records without creating a second proposal or executing one.

## Task 1: Preserve inputs and prepare a real native start check

**Files:** Create `tools/prepare_research_cycle.py`, `tests/helpers/research_cycle_fixture.py`, and `tests/windows/test_research_cycle_native.py`.

**Interfaces:** `prepare(label: str) -> job manifest`; `native_fixture(root: Path) -> owned fixture resources`.
The fixture must provide the existing registered campaign, controller, seal owner, and exact approval records.

- [ ] Save fingerprints for current source, tests, preparation tools, and relevant historical receipts before any edits.
- [ ] Prepare exact-path cleanup for eligible passing files. Preserve the active-Python refusal when other Python work remains active.
- [ ] Prepare fresh capacity and source-test labels derived from the reviewed start wrappers. Never reuse a consumed label.
- [ ] Build the native fixture from `test_native_seals.state` and existing prepared-campaign/environment builders.
- [ ] Verify actual environment manifests and registration bindings. Do not reuse mocked manifests from source fixtures as native evidence.
- [ ] Write `test_approved_start_runs_real_worker_once`: require one real exit receipt, checked output, and no second dispatch from a repeated request.
- [ ] Assert actual process assignment, native execution identity, exit observation, and zero remaining children.
- [ ] Run the smoke test within the existing 120-second test envelope after preparation review and capacity admission.
- [ ] If it fails, retain the failure and diagnose within the fixed limits. Independent source tasks may proceed after their own admission.

Commands after creating the tool:
`python -B tools/prepare_research_cycle.py capacity01`, then its generated bounded wrapper with kind `capacity`.
`python -B tools/prepare_research_cycle.py native-smoke01`, then its generated bounded wrapper with kind `native-smoke`.
Here and below, `python` means `.cache/clean-env-m0/Scripts/python.exe`; never change that interpreter silently.

The preparation tool writes `run_bounded.py` in `.cache/test-runs/m5-local-economics-20261017-01/research-cycle-preparation01`.
Its invocation is `python -B <preparation-folder>/run_bounded.py <label> <kind>`.
Use kind `source` for `cycle-records01`, `cycle-control01`, `cycle-feedback01`, and `cycle-revision01`.
Use kind `native-cycle` for `native-cycle01` and kind `feedback-import` for `feedback-import01`.
These are distinct initial labels. Repair attempts increment their suffix and preserve the original generated files.
Source and feedback-import kinds retain the 120-second envelope. Only native-cycle uses the proposed 1,800-second envelope.

Success means the complete smoke job passes. A simulated launch or partial child result is insufficient.

## Task 2: Durable cycle approval and dispatch ownership

**Files:** Create `ai/cycle_record.py`, `schemas/research_cycle.v1.json`, and `tests/test_research_cycle.py`; modify coordinator and domain registration.

**Interfaces:**
`Coordinator.control_research_cycle(decision, payload, *, cycle: ResearchCycleController) -> dict`.
`CycleRecords(storage)` owns only cycle records under the existing coordinator lease.
`CycleRecords.status(cycle_id: str) -> dict`; `CycleRecords.transition(cycle_id: str, expected_hash: str, change: dict) -> dict`.

Use at most 32 cycle records per fixture, each at most 65,536 encoded bytes.
Bind cycle ID, run ID, registration request, first-start request, prepared input hash, plan hash, seal, fixed schedule hash, and output allowance.
Also bind original operator, owner generation, cycle deadline, scorecard task ID, and aggregate-audit task ID.
Use existing durable request receipts; do not create a competing authentication mechanism.
Cycle approval is `RUN_FIXED_SYNTHETIC_CYCLE`. It does not reinterpret `START_FIRST_RESEARCH_UNIT` as whole-cycle permission.
Allowed operations are approve, status, pause, stop, and resume. Resume must bind the exact paused state hash and remaining deadline.
An expired deadline cannot be reset by resume. An unresolved dispatch intent cannot be resumed as an unstarted unit.

- [ ] Write refusal tests for absent approval, mismatched operator/generation, changed inputs, occupied dispatch ownership, and expired deadlines.
- [ ] Write `test_duplicate_cycle_request_has_one_record` and `test_second_cycle_cannot_claim_same_run`.
- [ ] Verify failure before implementation, then add the minimal record validation and coordinator entry point.
- [ ] Persist approval and ownership before any action. Use explicit compare-and-write state transitions under the coordinator lease.
- [ ] On construction after restart, preserve original bindings and enter paused or blocked state without dispatch.
- [ ] Verify all new cases through `cycle-records01` and existing registration/start/contract regressions.
- [ ] Review and commit only the verified task files, preserving prior dirty changes.

## Task 3: Continue the fixed campaign and run its audits

**Files:** Create `ai/cycle.py`; extend `tests/test_research_cycle.py` and `tests/helpers/research_cycle_restart.py`.

**Interfaces:**
`ResearchCycleController(coordinator, storage, *, research, auditor, reviews)`.
`control(decision, payload) -> dict`; `tick() -> None`; `status(cycle_id: str) -> dict`; `close() -> None`.
Use `ResearchController.control(run_id, request_id, operation)` and `tick()` for numerical work.
Use `AuditorController` and `AuditRuns.register(task, run, unit)` for required unit audits.
Use `CampaignReviewController` and `ReviewRuns.register(task, run, kind)` for `scorecard`, then `aggregate`.

Persist the next dispatch intent before invoking a controller. Bind it to the exact saved history position and deterministic task ID.
Only a verified completed result or genuine existing terminal outcome advances the schedule.
Require all unit audits needed by `audit_history.collect_units` before registering the aggregate review.
Use fresh audit processes and existing author/auditor separation checks. Do not treat a scorecard alone as an audit.

- [ ] Write `test_tick_dispatches_only_after_checked_exit` and `test_cycle_retains_all_63_outcomes_and_12_variants`.
- [ ] Write tests for pause before dispatch, cancellation during preparation, failed cleanup, failed unit audit, and changed seal.
- [ ] Write `test_restart_after_dispatch_intent_never_replays_uncertain_launch` using two actual owner lifetimes.
- [ ] Verify failure, implement the controller, then run `cycle-control01` under the bounded source wrapper.
- [ ] Poll existing controllers cooperatively. Recheck health, capacity, owner identity, pause, and deadline before each new action.
- [ ] Stop at blocked or uncertain effects. Preserve attempt history and require explicit checked resume.
- [ ] Enter `WAITING_FOR_ASSESSMENT` only after verified campaign, scorecard, unit audits, and aggregate audit.
- [ ] Verify zero active children before releasing cycle execution ownership. Review and commit the verified task files.

## Task 4: Export development evidence and validate an assessment

**Files:** Create `ai/cycle_feedback.py`, `schemas/research_assessment.v1.json`, and `tests/test_research_cycle_feedback.py`.

**Interfaces:**
`export_feedback(cycle_id: str, task: TaskSpec, *, cycle, bridge) -> artifact manifest`.
`validate_assessment(raw: bytes, *, cycle_record: dict, packet: dict) -> dict`.

Publish a development summary at `artifacts/runs/{feedback_task_id}/input/development-evidence.json` through metered storage.
The summary is at most 65,536 bytes. The complete encoded manual packet must remain within 131,072 bytes.
Include every variant and all 63 outcome statuses, actual attempts, source hashes, checked scorecard metrics, and audit references.
Use compact summaries with references to immutable local artifacts. Refuse an oversized summary; never silently omit failures.
Call `ManualBridge.export_subscription_task` with that exact allowed input and hash.
Keep its existing daily task/request checks and 86,400-second manual deadline.

The assessment has a 32,768-byte ceiling and `additionalProperties: false`.
Require cycle ID, original proposal ID/hash, evidence hash, prompt hash, conclusion, observations, limitations, and next-test explanation.
Conclusions are `SUPPORTED`, `CONTRADICTED`, or `INCONCLUSIVE`; all remain development-only.
Each observation names an artifact hash contained in the packet. Financial acceptance and execution authority remain false.

- [ ] Write tests for missing audit, changed evidence, foreign campaign references, all failed outcomes retained, and unknown observation hashes.
- [ ] Write `test_packet_overflow_refuses_without_truncation` and `test_protected_or_secret_text_is_rejected`.
- [ ] Write expiry tests proving that assessment import cannot bypass the manual task deadline.
- [ ] Verify failure, implement the bounded exporter and validator, then pass `cycle-feedback01` and manual/history regressions.
- [ ] Review and commit the verified task files.

## Task 5: Save the real assessment and revised proposal without execution

**Files:** Extend `ai/cycle_feedback.py` and `ai/manual.py`; create `schemas/research_revision_link.v1.json`; extend feedback tests.

**Interfaces:**
`import_feedback(cycle_id: str, assessment_raw: bytes, proposal_path: Path, metadata: dict, *, cycle, bridge) -> dict`.

Keep the primary response as the existing `AIProposal` schema. The assessment is a separate bounded response artifact from the same task.
Validate both against the same prompt and evidence before final publication.
Use `ManualBridge.import_proposal` for the revised proposal. Do not hand-edit its receipt or bypass its limits.
Add provenance `CURRENT_CODEX_SESSION` to the existing metadata validation without widening provider capabilities.
Record model label honestly, `usage_status=UNKNOWN`, and `operator_reports_hosted_response=False` for this provenance.
Never label current-session output `SYNTHETIC_FIXTURE` or claim an observed hosted API call.

The revision link has a 16,384-byte ceiling and binds the cycle, original proposal, evidence, assessment, revised proposal, and their hashes.
Persist an import intent before partial effects. Identical recovery reuses retained records; conflicting content fails.
Only publish `AWAITING_OWNER_REVIEW` after every linked artifact verifies.

- [ ] Write tests for valid current-session provenance, unchanged existing provenance behavior, foreign proposal tasks, and changed assessment hashes.
- [ ] Write `test_partial_feedback_import_recovers_one_proposal` at each artifact/receipt boundary.
- [ ] Write `test_revision_stays_proposal_only_and_creates_no_campaign` with database and controller assertions.
- [ ] Verify failure, implement the minimal import/link path, then pass `cycle-revision01` and proposal/history regressions.
- [ ] Review and commit the verified task files.

## Task 6: Complete the real supervised acceptance cycle

**Files:** Create `tools/run_research_cycle_acceptance.py`; extend native tests and the prepared bounded-job tool.

**Interfaces:** `run_acceptance(job_manifest: Path) -> bounded acceptance receipt`.
Use exact frozen source/environment hashes, the fixed full synthetic fixture, explicit first-start approval, and separate cycle approval.
Retain real registration and native seal checks. Do not patch identity, health, launch, audit, or acceptance functions.

- [ ] Prepare the exact 1,800-second envelope and its output bindings. Independently review all resource and cleanup checks.
- [ ] Recheck source identity, host memory, storage admission, native identity, and absence of competing research jobs.
- [ ] Run `native-cycle01` once. Preserve actual worker outputs, failures, dependency skips, audit records, and process-tree exit receipts.
- [ ] Require all 63 scheduled outcomes to resolve through real execution or genuine existing dependency rules.
- [ ] Require checked scorecard, required unit audits, and aggregate audit. A failure leaves acceptance incomplete.
- [ ] Exit the foreground native envelope cleanly at `WAITING_FOR_ASSESSMENT`; preserve the original runtime folder and identities.
- [ ] Read only the exported sanitized packet in this Codex session. Write its actual assessment and revised proposal within the declared bounds.
- [ ] Import them through `import_feedback` in a distinct bounded foreground job using the original evidence and existing recovery checks.
- [ ] Verify final `AWAITING_OWNER_REVIEW`, one linked revised proposal, no next campaign, and zero active or pending work.
- [ ] Report exact source, native, and simulated counts separately. No installed-package or financial acceptance claim is implied.

If any required native prerequisite fails, stop dependent execution and finish independent admitted source work.
Do not run a substitute simulated acceptance cycle or silently grant another outer-job attempt.

## Task 7: Final review, cleanup, and delivery

**Files:** Update `README.md`, `docs/CURRENT_CHECKPOINT.md`, and `docs/AI_RUNNER_CONNECTION_PLAN.md`.
Create `reports/SUPERVISED_RESEARCH_CYCLE_20261019.md` and the compact execution checklist.
Refresh the external project map under `docs/PROJECT_MAP_REFRESH.md`.

- [ ] Reconcile every design acceptance criterion with saved evidence. Mark any unmet criterion explicitly.
- [ ] Run one independent review of the integrated change. Repair evidence-backed defects within the stated round limit.
- [ ] Run only regressions needed by those repairs. Verify final source fingerprints and whole-job closures.
- [ ] Clean eligible passing fixtures using existing retention checks. Preserve the accepted cycle evidence and original runtime.
- [ ] Record blocked cleanup without stopping unrelated Python processes or weakening checks.
- [ ] Refresh all affected diagrams, inspect nine rendered pages, and verify all navigation links.
- [ ] Save a verified local checkpoint. Do not publish without the required owner authority.
- [ ] Deliver the assessment, revised proposal, report, exact counts, resource usage, and remaining operating restrictions.

## Self-review and handoff

The seven tasks cover native start, durable continuation, every required audit, feedback, revision, final stopping, and evidence retention.
All five review-focus conditions have explicit tests above.
The selected execution method is primary-agent implementation with one independent reviewer, following `AGENTS.md`.
The owner must review this plan before implementation under the writing-plans skill.
The material new allowance is the 1,800-second foreground native envelope; existing worker and storage ceilings remain unchanged.
