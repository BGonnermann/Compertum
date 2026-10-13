"""Boundary checks: malformed records must never become admitted tasks."""
import copy
import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "0199c3b4-1200-7000-8000-000000000001"
HASH = "a" * 64


@pytest.fixture
def domain():
    return importlib.import_module("compertum.domain")


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


def task():
    return {
        "schema_version": "1", "record_type": "TaskSpec",
        "task_id": TASK_ID, "parent_task_id": None, "campaign_id": None,
        "role": "experiment_runner", "kind": "OFFLINE_FIXTURE",
        "created_at": "2026-10-08T20:00:00Z",
        "deadline_at": "2026-10-08T20:30:00Z",
        "input_hashes": [HASH], "code_sha256": HASH, "lock_sha256": HASH,
        "output_schema_sha256": HASH, "model_identity": None,
        "acceptance_checks": ["fixture hash agrees"],
        "permissions": {
            "tools": ["trusted_fixture"], "filesystem_bundle": ["artifacts/fixture-input"],
            "output_directory": f"artifacts/runs/{TASK_ID}/attempt-001",
            "network_destinations": [], "protected_data": False,
            "broker": False, "shell": False,
        },
        "budget": {"cpu_threads": 4, "ram_bytes": 4294967296,
                   "output_bytes": 2147483648, "wall_seconds": 1800,
                   "max_attempts": 2, "ai_requests": 0, "gpu_training": False,
                   "input_tokens": 0, "output_tokens": 0, "request_deadline_seconds": 0},
        "clock": {"state": "REGISTERED", "active_elapsed_seconds": 0, "active_started_at": None,
                  "manual_wait_started_at": None, "manual_deadline_at": None,
                  "process_lease_id": None, "cpu_reserved": False},
    }


def assert_denied(domain, payload, root, reason, schema="task.v1"):
    with pytest.raises(domain.ContractError) as caught:
        domain.validate_record(schema, payload, project_root=root)
    assert caught.value.reason == reason


def test_reject_unknown_field_and_schema(domain, workspace):
    payload = task()
    payload["enable_orders"] = True
    assert_denied(domain, payload, workspace, "UNKNOWN_FIELD")
    assert_denied(domain, task(), workspace, "UNKNOWN_SCHEMA", "task.v2")
    payload = task()
    payload["schema_version"] = "2"
    assert_denied(domain, payload, workspace, "UNKNOWN_SCHEMA_VERSION")


def test_reject_nonfinite_and_non_utc_time(domain, workspace):
    for value in (float("nan"), float("inf"), float("-inf")):
        payload = task()
        payload["clock"]["active_elapsed_seconds"] = value
        assert_denied(domain, payload, workspace, "NONFINITE_NUMBER")
    for value in ("2026-10-08T20:00:00", "2026-10-08T20:00:00-04:00",
                  "2026-02-30T20:00:00Z"):
        payload = task()
        payload["created_at"] = value
        assert_denied(domain, payload, workspace, "INVALID_UTC_TIMESTAMP")


@pytest.mark.parametrize("path", ["../escape", "/tmp/escape", "C:/escape", "a/../../b",
                                      "a\\b", "a:stream", "CON/file", "artifacts/name."])
def test_reject_artifact_escape(domain, workspace, path):
    payload = task()
    payload["permissions"]["output_directory"] = path
    assert_denied(domain, payload, workspace, "ARTIFACT_ESCAPE")


def test_reject_artifact_escape_and_reparse_target(domain, workspace):
    target = workspace / "real"
    target.mkdir()
    (workspace / "alias").symlink_to(target, target_is_directory=True)
    payload = task()
    payload["permissions"]["filesystem_bundle"] = ["alias/input"]
    assert_denied(domain, payload, workspace, "REPARSE_TARGET")
    with pytest.raises(domain.ContractError) as caught:
        domain.validate_record("task.v1", task())
    assert caught.value.reason == "PROJECT_ROOT_REQUIRED"


@pytest.mark.parametrize("field,value", [("cpu_threads", 5), ("ram_bytes", 4294967297),
                                         ("output_bytes", 2147483649), ("wall_seconds", 1801),
                                         ("max_attempts", 3), ("ai_requests", 1),
                                         ("gpu_training", True)])
def test_task_cannot_expand_its_budget(domain, workspace, field, value):
    payload = task()
    payload["budget"][field] = value
    assert_denied(domain, payload, workspace, "BUDGET_EXCEEDED")


def test_no_admission_of_financial_kind_or_permissions(domain, workspace):
    payload = task()
    payload["kind"] = "PAPER_ORDER"
    assert_denied(domain, payload, workspace, "CAPABILITY_UNAVAILABLE")
    for field in ("broker", "shell", "protected_data"):
        payload = task()
        payload["permissions"][field] = True
        assert_denied(domain, payload, workspace, "PERMISSION_DENIED")


def test_role_cannot_smuggle_network_or_output_namespace(domain, workspace):
    payload = task()
    payload["permissions"]["network_destinations"] = ["http://127.0.0.1:8080"]
    assert_denied(domain, payload, workspace, "PERMISSION_DENIED")
    payload = task()
    payload["permissions"]["output_directory"] = "state/research.sqlite"
    assert_denied(domain, payload, workspace, "PERMISSION_DENIED")


def test_record_freezes_nested_inputs_and_returns_detached_copy(domain, workspace):
    payload = task()
    record = domain.TaskSpec(payload, project_root=workspace)
    payload["budget"]["cpu_threads"] = 99
    assert record.task_id == TASK_ID
    assert record.payload["budget"]["cpu_threads"] == 4
    with pytest.raises(TypeError):
        record.payload["budget"]["cpu_threads"] = 9
    with pytest.raises(FrozenInstanceError):
        record.payload = {}
    exported = record.to_payload()
    exported["budget"]["cpu_threads"] = 8
    assert record.payload["budget"]["cpu_threads"] == 4


def test_manual_wait_has_separate_24_hour_deadline_without_cpu_lease(domain, workspace):
    payload = task()
    payload.update(role="research_proposer", kind="AI_PROPOSAL", deadline_at=None,
                   model_identity={"provider": "manual_subscription", "model_label": "operator supplied", "sha256": None})
    payload["permissions"]["tools"] = []
    payload["budget"].update(cpu_threads=1, ram_bytes=268435456, wall_seconds=1200,
                              ai_requests=8, input_tokens=16384, output_tokens=2048,
                              request_deadline_seconds=120)
    payload["clock"].update(state="WAITING_FOR_OPERATOR",
                              manual_wait_started_at="2026-10-08T20:00:00Z",
                              manual_deadline_at="2026-10-09T20:00:00Z")
    assert domain.validate_record("task.v1", payload, project_root=workspace)["deadline_at"] is None
    for mutation in ({"cpu_reserved": True}, {"process_lease_id": TASK_ID},
                     {"manual_deadline_at": "2026-10-10T20:00:00Z"}):
        broken = copy.deepcopy(payload)
        broken["clock"].update(mutation)
        assert_denied(domain, broken, workspace, "INVALID_TASK_CLOCK")


def test_submitted_control_is_not_confirmed_effect(domain, workspace):
    payload = {"schema_version": "1", "record_type": "ControlReceipt", "request_id": TASK_ID,
               "action": "pause_research", "target": "research", "state": "SUBMITTED",
               "evidence_label": "UNVERIFIED", "confirmed": False, "generation": 1,
               "requested_at": "2026-10-08T20:00:00Z", "observed_at": None,
               "exit_code": None, "reason": "awaiting owner acknowledgement", "artifacts": []}
    assert domain.ControlReceipt(payload, project_root=workspace).to_payload()["confirmed"] is False
    payload["confirmed"] = True
    assert_denied(domain, payload, workspace, "UNCONFIRMED_EFFECT", "control_receipt.v1")


def test_live_owner_lease_cannot_be_serialized(domain):
    identity = domain.ProcessIdentity(TASK_ID, 10, 133000000000000000, "S-1-5-21-1-2-3-1001", "coordinator")
    lease = domain.OwnerLease(HASH, 1, identity, object())
    with pytest.raises(domain.ContractError) as caught:
        lease.to_payload()
    assert caught.value.reason == "PRIVATE_CAPABILITY"


def test_capability_matrix_cannot_arm_broker(domain):
    for action in ("paper.arm", "paper.start", "paper.cancel", "paper.close", "data.fetch",
                   "evaluate.final", "promote", "unknown.action"):
        decision = domain.capability_for(action)
        assert (decision.exit_code, decision.status, decision.broker_state) == (3, "CAPABILITY_UNAVAILABLE", "NOT_CONFIGURED")
    with pytest.raises(TypeError):
        domain.M0_CAPABILITIES["paper.arm"] = "AVAILABLE"


def test_resumed_ai_clock_excludes_prior_manual_wait(domain, workspace):
    payload = task()
    payload.update(role="research_proposer", kind="AI_PROPOSAL",
                   deadline_at="2026-10-09T20:15:00Z",
                   model_identity={"provider": "manual_subscription", "model_label": "operator supplied", "sha256": None})
    payload["permissions"]["tools"] = []
    payload["budget"].update(cpu_threads=1, ram_bytes=268435456, wall_seconds=1200,
                              ai_requests=8, input_tokens=16384, output_tokens=2048,
                              request_deadline_seconds=120)
    payload["clock"].update(state="ACTIVE", active_elapsed_seconds=300,
                              active_started_at="2026-10-09T20:00:00Z",
                              process_lease_id=TASK_ID, cpu_reserved=True)
    assert domain.validate_record("task.v1", payload, project_root=workspace)["deadline_at"] == "2026-10-09T20:15:00Z"
    payload["deadline_at"] = "2026-10-09T20:15:01Z"
    assert_denied(domain, payload, workspace, "INVALID_TASK_CLOCK")


def test_ai_critic_still_uses_small_adapter_and_sanitized_bundle(domain, workspace):
    payload = task()
    payload.update(role="mathematical_checker", kind="AI_PROPOSAL",
                   deadline_at="2026-10-08T20:20:00Z",
                   model_identity={"provider": "manual_subscription", "model_label": "operator supplied", "sha256": None})
    payload["permissions"]["tools"] = []
    payload["budget"].update(wall_seconds=1200, ai_requests=8, input_tokens=16384,
                              output_tokens=2048, request_deadline_seconds=120)
    assert_denied(domain, payload, workspace, "BUDGET_EXCEEDED")
    payload["budget"].update(cpu_threads=1, ram_bytes=268435456)
    payload["permissions"]["filesystem_bundle"] = ["artifacts/evaluations/private"]
    assert_denied(domain, payload, workspace, "PERMISSION_DENIED")


def artifact():
    return {"schema_version": "1", "record_type": "ArtifactManifest", "artifact_id": TASK_ID,
            "project_id": HASH, "task_id": TASK_ID, "run_id": None, "parent_artifact_ids": [],
            "path": "artifacts/fixtures/result.json", "size_bytes": 10, "sha256": HASH,
            "created_at": "2026-10-08T20:00:02Z", "kind": "OFFLINE_FIXTURE",
            "lineage": {"source_bundle_sha256": HASH, "code_sha256": HASH, "config_sha256": HASH,
                        "environment_sha256": HASH, "input_hashes": [HASH]},
            "command": {"argv": ["trusted_fixture"], "exit_code": 0,
                        "started_at": "2026-10-08T20:00:00Z", "ended_at": "2026-10-08T20:00:01Z",
                        "stdout_artifact_id": None, "stderr_artifact_id": None,
                        "resource_use": {"cpu_wall_seconds": 1, "peak_committed_bytes": 1024, "written_bytes": 10}},
            "audit_references": []}


def recovery():
    return {"schema_version": "1", "record_type": "RecoveryManifest", "recovery_set_id": TASK_ID,
            "project_id": HASH, "created_at": "2026-10-08T20:00:01Z", "code_sha256": HASH,
            "environment_sha256": HASH, "config_sha256": HASH, "complete": False,
            "barrier": {"barrier_id": TASK_ID, "started_at": "2026-10-08T20:00:00Z", "completed_at": None},
            "writers": [], "snapshots": [], "messages": {"outbox_high_water_marks": [],
                        "inbox_high_water_marks": [], "pending": [], "deduplication": []},
            "task_states": [], "run_states": [], "checkpoints": [], "artifacts": [], "seals": [],
            "consumption_guard": {"head_event_id": None, "sequence": 0, "sha256": None},
            "halt_state": {"admission": "DISARMED", "reason": "fixture only"},
            "reserve_accounting": {"total_bytes": 1073741824, "unused_bytes": 1073741824,
                                   "allocated_verified": False}}


def proposal():
    return {"schema_version": "1", "record_type": "AIProposal", "proposal_id": TASK_ID,
            "task_id": TASK_ID, "role": "research_proposer", "created_at": "2026-10-08T20:00:00Z",
            "prompt_sha256": HASH, "input_hashes": [HASH],
            "provider": {"name": "manual_subscription", "model_label": "operator supplied", "usage_status": "UNKNOWN"},
            "state": "PROPOSAL_ONLY", "summary": "Use a fixed synthetic fixture",
            "assumptions": ["Synthetic inputs"], "falsifier": "Fixture hash differs", "citations": [],
            "proposed_patch": None, "fictional_tool_proposal": None}


@pytest.mark.parametrize("schema,factory,nested", [("artifact_manifest.v1", artifact, "lineage"),
                                                   ("recovery_manifest.v1", recovery, "messages"),
                                                   ("ai_proposal.v1", proposal, "provider")])
def test_manifest_and_proposal_shape_is_strict(domain, workspace, schema, factory, nested):
    payload = factory()
    assert domain.validate_record(schema, payload, project_root=workspace)["record_type"] == payload["record_type"]
    payload[nested]["grant_authority"] = True
    assert_denied(domain, payload, workspace, "UNKNOWN_FIELD", schema)


def test_reversed_artifact_times_and_empty_complete_recovery_are_denied(domain, workspace):
    payload = artifact()
    payload["command"]["ended_at"] = "2026-10-08T19:59:00Z"
    assert_denied(domain, payload, workspace, "INVALID_UTC_TIMESTAMP", "artifact_manifest.v1")
    payload = recovery()
    payload["complete"] = True
    assert_denied(domain, payload, workspace, "INCOMPLETE_RECOVERY_SET", "recovery_manifest.v1")


def test_utc_offset_is_accepted_but_non_json_objects_are_denied(domain, workspace):
    payload = task()
    payload["created_at"] = "2026-10-08T20:00:00+00:00"
    assert domain.validate_record("task.v1", payload, project_root=workspace)["task_id"] == TASK_ID
    payload["input_hashes"] = {HASH}
    assert_denied(domain, payload, workspace, "INVALID_RECORD")


def test_nested_schema_errors_preserve_explicit_denial_reason(domain, workspace):
    payload = task()
    payload["deadline_at"] = "2026-10-08T20:30:00-04:00"
    assert_denied(domain, payload, workspace, "INVALID_UTC_TIMESTAMP")
    payload = task()
    payload["model_identity"] = {"provider": "strata", "model_label": "fixture", "sha256": None, "orders": True}
    assert_denied(domain, payload, workspace, "UNKNOWN_FIELD")


def test_financial_control_cannot_claim_confirmed_effect(domain, workspace):
    payload = {"schema_version": "1", "record_type": "ControlReceipt", "request_id": TASK_ID,
               "action": "paper.arm", "target": "paper", "state": "CONFIRMED",
               "evidence_label": "VERIFIED_PASS", "confirmed": True, "generation": 1,
               "requested_at": "2026-10-08T20:00:00Z", "observed_at": "2026-10-08T20:00:01Z",
               "exit_code": 0, "reason": "untrusted claim", "artifacts": []}
    assert_denied(domain, payload, workspace, "CAPABILITY_UNAVAILABLE", "control_receipt.v1")
    payload.update(state="CAPABILITY_UNAVAILABLE", evidence_label="CAPABILITY_UNAVAILABLE", confirmed=False, exit_code=3)
    assert domain.validate_record("control_receipt.v1", payload, project_root=workspace)["exit_code"] == 3


@pytest.mark.parametrize("state", ["SUBMITTED", "PENDING", "FAILED"])
def test_unconfirmed_control_cannot_carry_success(domain, workspace, state):
    payload = {"schema_version": "1", "record_type": "ControlReceipt", "request_id": TASK_ID,
               "action": "pause_research", "target": "research", "state": state,
               "evidence_label": "VERIFIED_PASS", "confirmed": False, "generation": 1,
               "requested_at": "2026-10-08T20:00:00Z", "observed_at": None,
               "exit_code": 0, "reason": "awaiting effect", "artifacts": []}
    assert_denied(domain, payload, workspace, "UNCONFIRMED_EFFECT", "control_receipt.v1")
    payload.update(state="CAPABILITY_UNAVAILABLE", evidence_label="UNVERIFIED", exit_code=3)
    assert_denied(domain, payload, workspace, "UNCONFIRMED_EFFECT", "control_receipt.v1")
    payload.update(evidence_label="CAPABILITY_UNAVAILABLE")
    assert domain.validate_record("control_receipt.v1", payload)["exit_code"] == 3
    payload.update(state="FAILED", evidence_label="VERIFIED_FAIL", exit_code=1)
    assert_denied(domain, payload, workspace, "INVALID_RECORD", "control_receipt.v1")


def complete_recovery():
    payload = recovery()
    run_id = "0199c3b4-1200-7000-8000-000000000002"
    checkpoint_id = "0199c3b4-1200-7000-8000-000000000003"
    artifact_id = "0199c3b4-1200-7000-8000-000000000004"
    payload["complete"] = True
    payload["barrier"]["completed_at"] = "2026-10-08T20:00:01Z"
    payload["reserve_accounting"]["allocated_verified"] = True
    payload["writers"] = [{"role": role, "process_instance_id": TASK_ID,
                           "generation": 1, "barrier_id": TASK_ID}
                          for role in ("coordinator", "evaluation", "execution", "watchdog")]
    payload["snapshots"] = [{"owner_role": role, "path": f"backups/{role}.sqlite",
                             "size_bytes": 1024, "sha256": HASH, "schema_version": "1",
                             "checkpoint_id": TASK_ID}
                            for role in ("coordinator", "evaluation", "execution")]
    payload["task_states"] = [{"task_id": TASK_ID, "state": "PAUSED", "checkpoint_id": checkpoint_id}]
    payload["run_states"] = [{"run_id": run_id, "task_id": TASK_ID, "state": "PAUSED", "checkpoint_id": checkpoint_id}]
    payload["checkpoints"] = [{"checkpoint_id": checkpoint_id, "run_id": run_id, "task_id": TASK_ID,
                               "code_sha256": HASH, "config_sha256": HASH, "input_hashes": [HASH],
                               "last_completed_unit": "fixture-1", "rng_state_artifact_id": artifact_id,
                               "artifact_ids": [artifact_id]}]
    payload["artifacts"] = [{"artifact_id": artifact_id, "path": "artifacts/fixtures/rng.json",
                             "size_bytes": 10, "sha256": HASH, "parent_artifact_ids": []}]
    return payload


@pytest.mark.parametrize("mutation", ["checkpoint", "run", "task", "artifact", "rng", "duplicate", "cross_task"])
def test_complete_recovery_requires_declared_reference_closure(domain, workspace, mutation):
    payload = complete_recovery()
    assert domain.validate_record("recovery_manifest.v1", payload, project_root=workspace)["complete"] is True
    if mutation == "checkpoint":
        payload["checkpoints"] = []
    elif mutation == "run":
        payload["run_states"] = []
    elif mutation == "task":
        payload["task_states"] = []
    elif mutation == "artifact":
        payload["checkpoints"][0]["artifact_ids"] = [TASK_ID]
    elif mutation == "rng":
        payload["checkpoints"][0]["rng_state_artifact_id"] = TASK_ID
    elif mutation == "cross_task":
        payload["checkpoints"][0]["task_id"] = "0199c3b4-1200-7000-8000-000000000005"
    else:
        payload["checkpoints"].append(copy.deepcopy(payload["checkpoints"][0]))
    assert_denied(domain, payload, workspace, "INCOMPLETE_RECOVERY_SET", "recovery_manifest.v1")


@pytest.mark.parametrize("value", [[], {}, None])
def test_malformed_kind_identity_and_lease_raise_domain_errors(domain, workspace, value):
    payload = task()
    payload["kind"] = value
    assert_denied(domain, payload, workspace, "INVALID_RECORD")
    with pytest.raises(domain.ContractError) as caught:
        domain.ProcessIdentity(TASK_ID, 10, 133000000000000000, "S-1-5-21-1-2-3-1001", value)
    assert caught.value.reason == "INVALID_PROCESS_IDENTITY"
    identity = domain.ProcessIdentity(TASK_ID, 10, 133000000000000000, "S-1-5-21-1-2-3-1001", "coordinator")
    with pytest.raises(domain.ContractError) as caught:
        domain.OwnerLease(value, 1, identity, object())
    assert caught.value.reason == "INVALID_OWNER_LEASE"


@pytest.mark.parametrize("field", ["project_id", "generation", "identity", "_live_handle"])
def test_owner_lease_cannot_lose_its_retained_fields(domain, field):
    identity = domain.ProcessIdentity(TASK_ID, 10, 133000000000000000, "S-1-5-21-1-2-3-1001", "coordinator")
    lease = domain.OwnerLease(HASH, 1, identity, object())
    with pytest.raises(AttributeError):
        delattr(lease, field)
