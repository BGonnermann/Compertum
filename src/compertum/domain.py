"""Immutable M0 admission contracts. Validation grants no runtime authority.

Path checks are portable preflight observations, not race-safe native opens.
Task 3 supplies native identity and ownership; Task 5 owns admitted writes.
No providers, transports, source execution, or application writes live here.
"""
from __future__ import annotations

import json
import math
import re
import stat
import sysconfig
from collections.abc import Mapping
from dataclasses import InitVar, dataclass
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
from typing import ClassVar
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


class ContractError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)  # Never echo caller-controlled values.


_SCHEMAS = frozenset({"task.v1", "control_receipt.v1", "artifact_manifest.v1",
                      "recovery_manifest.v1", "ai_proposal.v1", "consumption_event.v1", "execution_observation.v1", "execution_intent.v1", "execution_plan.v1", "execution_authorization.v1", "execution_calendar.v1", "execution_inputs.v1", "execution_start.v1", "execution_decision.v1"})
_FORMATS = FormatChecker()
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$")
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@_FORMATS.checks("utc-time")
def _utc_time(value):
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        return False
    try:
        return _time(value).utcoffset() == timedelta(0)
    except ValueError:
        return False


@_FORMATS.checks("project-path")
def _project_path(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        return False
    if any(c in value for c in '\\:<>"|?*') or any(ord(c) < 32 for c in value):
        return False
    if value.startswith("/") or PureWindowsPath(value).drive:
        return False
    return all(part and part not in (".", "..") and not part.endswith((".", " "))
               and part.split(".")[0].upper() not in _RESERVED
               for part in value.split("/"))


def resolve_project_path(value: str, project_root: Path) -> Path:
    """Reject lexical escapes and existing symlink/reparse components.

    Does not create directories and does not establish an open-handle identity.
    Native consumers must recheck paths at the actual operation boundary.
    """
    if not _project_path(value):
        raise ContractError("ARTIFACT_ESCAPE")
    root = Path(project_root).absolute()
    target = root.joinpath(*value.split("/"))
    # Check the root's own ancestry, too; do not silently follow a root alias.
    current = Path(target.anchor)
    try:
        if not root.is_dir():
            raise ContractError("PROJECT_ROOT_UNVERIFIED")
        for part in target.parts[1:]:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ContractError("REPARSE_TARGET")
        resolved = target.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ContractError("ARTIFACT_ESCAPE")
        return resolved
    except OSError:
        raise ContractError("PATH_UNVERIFIED") from None


def _plain(value, *, depth=0, count=None):
    """Bound the copy before handing data to JSON Schema."""
    if count is None:
        count = [0, 0]
    count[0] += 1
    if depth > 32 or count[0] > 20000:
        raise ContractError("RECORD_TOO_LARGE")
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("NONFINITE_NUMBER")
    if isinstance(value, str):
        count[1] += len(value)
        if count[1] > 1048576:
            raise ContractError("RECORD_TOO_LARGE")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ContractError("INVALID_RECORD")
        result = {}
        for key, item in value.items():
            _plain(key, depth=depth + 1, count=count)
            result[key] = _plain(item, depth=depth + 1, count=count)
        return result
    if isinstance(value, (tuple, list)):
        return [_plain(item, depth=depth + 1, count=count) for item in value]
    if value is None or type(value) in (int, float, bool):
        return value
    raise ContractError("INVALID_RECORD")


def _schema(name):
    source = Path(__file__).resolve().parents[2] / "schemas" / f"{name}.json"
    installed = Path(sysconfig.get_path("data")) / "share/compertum/schemas" / f"{name}.json"
    path = source if source.is_file() else installed
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ContractError("SCHEMA_UNAVAILABLE")
        schema = json.loads(raw)
        Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, ValueError, SchemaError):
        raise ContractError("SCHEMA_UNAVAILABLE") from None


def _paths(schema, payload):
    if schema.get("format") == "project-path":
        yield payload
    if isinstance(payload, dict):
        for name, child in schema.get("properties", {}).items():
            if name in payload:
                yield from _paths(child, payload[name])
    elif isinstance(payload, list):
        for item in payload:
            yield from _paths(schema.get("items", {}), item)
    for child in schema.get("anyOf", []):
        if child.get("type") != "null" and payload is not None:
            yield from _paths(child, payload)


def _validation_reason(error):
    errors = [error]
    for child in error.context:
        errors.extend(_validation_errors(child))
    if any(e.validator == "additionalProperties" for e in errors):
        return "UNKNOWN_FIELD"
    for e in errors:
        if e.validator == "format" and e.validator_value == "utc-time":
            return "INVALID_UTC_TIMESTAMP"
        if e.validator == "format" and e.validator_value == "project-path":
            return "ARTIFACT_ESCAPE"
    return "INVALID_RECORD"


def _validation_errors(error):
    yield error
    for child in error.context:
        yield from _validation_errors(child)


# (wall seconds, CPU threads, committed bytes, output bytes, AI requests).
# AI proposal roles describe the adapter process; Strata is external/shared.
_GIB = 1073741824
_ROLE_LIMITS = MappingProxyType({
    "experiment_runner": (1800, 4, 4 * _GIB, 2 * _GIB, 0),
    "research_proposer": (1200, 1, 268435456, 2 * _GIB, 8),
    "ml_planner": (1200, 1, 268435456, 2 * _GIB, 8),
    "mathematician": (1800, 1, 268435456, 2 * _GIB, 10),
    "mathematical_checker": (1200, 4, 2 * _GIB, 2 * _GIB, 8),
    "experiment_auditor": (2700, 4, 4 * _GIB, 2 * _GIB, 0),
    "ai_adapter": (1200, 1, 268435456, 2 * _GIB, 8),
})


def _campaign_fit_path(path,task_id):
    match=re.fullmatch(r'artifacts/runs/'+re.escape(task_id)+r'/baseline/unit-([0-9]{2})-attempt-[12]\.campaign',path)
    return match is not None and int(match[1])<63 and int(match[1])%21 in range(3,21,2)


def _audit_source_path(path,p):
    source=p['parent_task_id']
    if p['kind']!='OFFLINE_FIXTURE' or p['role']!='experiment_auditor' or source is None or source!=p['campaign_id'] or source==p['task_id']:return False
    base=f'artifacts/runs/{source}/baseline/'
    if path==base+'inputs.json':return True
    match=re.fullmatch(re.escape(base)+r'unit-([0-9]{2})-attempt-[12]\.campaign',path)
    return match is not None and int(match[1])<63


def _scorecard_source_path(path,p):
    source=p['parent_task_id'];task=p['task_id']
    if (p['kind']!='OFFLINE_FIXTURE' or p['role']!='experiment_runner' or source is None or source!=p['campaign_id'] or source==task
            or p['permissions']['output_directory']!=f'artifacts/runs/{task}/review'):return False
    if path==f'artifacts/runs/{task}/review/input/request.review':return True
    base=f'artifacts/runs/{source}/baseline/'
    if path==base+'inputs.json':return True
    match=re.fullmatch(re.escape(base)+r'unit-([0-9]{2})-attempt-[12]\.campaign',path)
    return match is not None and int(match[1])<63


def _aggregate_source_path(path,p):
    source=p['parent_task_id'];task=p['task_id'];permissions=p['permissions']
    if (p['kind']!='OFFLINE_FIXTURE' or p['role']!='experiment_auditor' or source is None or source!=p['campaign_id'] or source==task
            or permissions['output_directory']!=f'artifacts/runs/{task}/review'
            or f'artifacts/runs/{task}/review/input/unit-audits-0.json' not in permissions['filesystem_bundle']):return False
    if path in [f'artifacts/runs/{task}/review/input/request.review',*[f'artifacts/runs/{task}/review/input/unit-audits-{i}.json' for i in (0,1)]]:return True
    # Exact foreign task IDs and manifests are authenticated by ReviewRuns at
    # launch and resume; this contract admits only these bounded artifact shapes.
    match=re.fullmatch(r'artifacts/runs/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/(?:audit/attempt-[12]\.json|review/scorecard-attempt-[12]\.review)',path)
    return match is not None and match[1] not in (task,source)


def _pair_compare_source_path(path,p):
    source=p['parent_task_id'];task=p['task_id'];permissions=p['permissions'];paths=permissions['filesystem_bundle']
    if (p['kind']!='OFFLINE_FIXTURE' or p['role']!='experiment_auditor' or source is None or source!=p['campaign_id'] or source==task
            or permissions['output_directory']!=f'artifacts/runs/{task}/review' or len(paths)!=4):return False
    if paths[:2]!=[f'artifacts/runs/{task}/review/input/request.review',f'artifacts/runs/{source}/baseline/inputs.json']:return False
    owners=set()
    for value in paths[2:]:
        match=re.fullmatch(r'artifacts/runs/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/review/aggregate-attempt-[12]\.review',value)
        if match is None or match[1] in {task,source}|owners:return False
        owners.add(match[1])
    # ReviewRuns independently authenticates the exact pair and every manifest.
    return path in paths


def _final_source_path(path,p):
    source=p['parent_task_id'];task=p['task_id'];permissions=p['permissions'];paths=permissions['filesystem_bundle']
    if (p['kind']!='OFFLINE_FIXTURE' or p['role']!='experiment_runner' or source is None or source!=p['campaign_id'] or source==task
            or permissions['output_directory']!=f'artifacts/runs/{task}/final' or len(paths)!=2):return False
    if paths[0] not in [f'artifacts/runs/{task}/input/final/attempt-{n:02}.json' for n in (1,2)]:return False
    # Final task and owner dispatch validators bind these exact artifacts.
    return path==paths[1]==f'artifacts/runs/{source}/baseline/inputs.json'


def _final_audit_source_path(path,p):
    source=p['parent_task_id'];task=p['task_id'];permissions=p['permissions'];paths=permissions['filesystem_bundle']
    if (p['kind']!='OFFLINE_FIXTURE' or p['role']!='experiment_auditor' or source is None or source!=p['campaign_id'] or source==task
            or permissions['output_directory']!=f'artifacts/runs/{task}/final_audit' or len(paths)!=3):return False
    if paths[0] not in [f'artifacts/runs/{task}/final_audit/input/attempt-{n:02}.json' for n in (1,2)]:return False
    if paths[1] not in [f'artifacts/runs/{source}/final/attempt-{n:02}.final' for n in (1,2)]:return False
    if paths[2]!=f'artifacts/runs/{task}/final_audit/input/environment.json':return False
    # The live audit owner authenticates original completion and all publications.
    return path in paths


def _task_rules(p):
    role, kind, b, permissions, clock = p["role"], p["kind"], p["budget"], p["permissions"], p["clock"]
    allowed_roles = {
        "OFFLINE_FIXTURE": {"experiment_runner", "mathematical_checker", "experiment_auditor"},
        "RECOVERY_FIXTURE": {"experiment_runner"},
        "AI_PROPOSAL": {"research_proposer", "ml_planner", "mathematician", "mathematical_checker"},
        "AI_QUALIFICATION": {"ai_adapter"},
    }
    if role not in allowed_roles[kind]:
        raise ContractError("CAPABILITY_UNAVAILABLE")
    wall, threads, ram, output, requests = _ROLE_LIMITS[role]
    if kind not in ("AI_PROPOSAL", "AI_QUALIFICATION"):
        requests = 0
    else:
        threads, ram = 1, 268435456
    caps = {"wall_seconds": wall, "cpu_threads": threads, "ram_bytes": ram,
            "output_bytes": output, "max_attempts": 2, "ai_requests": requests,
            "input_tokens": 16384 if requests else 0, "output_tokens": 2048 if requests else 0,
            "request_deadline_seconds": 120 if requests else 0}
    if b["gpu_training"] or any(b[key] > maximum for key, maximum in caps.items()):
        raise ContractError("BUDGET_EXCEEDED")
    if any(permissions[key] for key in ("broker", "shell", "protected_data")):
        raise ContractError("PERMISSION_DENIED")
    if any(not (path == "artifacts/fixture-input" or path.startswith("artifacts/fixtures/")
                or path.startswith(f"artifacts/ai/{p['task_id']}/input/")
                or path == f"artifacts/ai/{p['task_id']}/input"
                or path.startswith(f"artifacts/runs/{p['task_id']}/input/")
                or path == f"artifacts/runs/{p['task_id']}/input")
                and path != f"artifacts/runs/{p['task_id']}/baseline/inputs.json"
                and not _campaign_fit_path(path,p['task_id'])
                and not _audit_source_path(path,p)
                and not _scorecard_source_path(path,p)
                and not _aggregate_source_path(path,p)
                and not _pair_compare_source_path(path,p)
                and not _final_source_path(path,p)
                and not _final_audit_source_path(path,p)
           for path in permissions["filesystem_bundle"]):
        raise ContractError("PERMISSION_DENIED")
    prefix = f"artifacts/runs/{p['task_id']}/"
    if not permissions["output_directory"].startswith(prefix):
        raise ContractError("PERMISSION_DENIED")
    if kind in ("AI_PROPOSAL", "AI_QUALIFICATION"):
        if p["model_identity"] is None or "trusted_fixture" in permissions["tools"]:
            raise ContractError("PERMISSION_DENIED")
        if permissions["network_destinations"] and p["model_identity"]["provider"] != "strata":
            raise ContractError("PERMISSION_DENIED")
    elif permissions["network_destinations"] or p["model_identity"] is not None or "propose_fixture_tool" in permissions["tools"]:
        raise ContractError("PERMISSION_DENIED")
    if clock["active_elapsed_seconds"] > b["wall_seconds"]:
        raise ContractError("INVALID_TASK_CLOCK")
    if clock["state"] == "WAITING_FOR_OPERATOR":
        if (kind != "AI_PROPOSAL" or p["model_identity"]["provider"] != "manual_subscription"
                or p["deadline_at"] is not None or clock["process_lease_id"] is not None
                or clock["cpu_reserved"] or clock["active_started_at"] is not None
                or not clock["manual_wait_started_at"] or not clock["manual_deadline_at"]):
            raise ContractError("INVALID_TASK_CLOCK")
        if (_time(clock["manual_deadline_at"]) - _time(clock["manual_wait_started_at"]) != timedelta(hours=24)
                or _time(clock["manual_wait_started_at"]) < _time(p["created_at"])):
            raise ContractError("INVALID_TASK_CLOCK")
    else:
        if (clock["manual_wait_started_at"] is not None or clock["manual_deadline_at"] is not None
                or p["deadline_at"] is None):
            raise ContractError("INVALID_TASK_CLOCK")
        if clock["state"] == "REGISTERED":
            if (clock["cpu_reserved"] or clock["process_lease_id"] is not None
                    or clock["active_started_at"] is not None or clock["active_elapsed_seconds"] != 0):
                raise ContractError("INVALID_TASK_CLOCK")
            start = _time(p["created_at"])
        else:
            if not clock["cpu_reserved"] or clock["process_lease_id"] is None or clock["active_started_at"] is None:
                raise ContractError("INVALID_TASK_CLOCK")
            start = _time(clock["active_started_at"])
            if start < _time(p["created_at"]):
                raise ContractError("INVALID_TASK_CLOCK")
        duration = (_time(p["deadline_at"]) - start).total_seconds()
        if not 0 < duration <= b["wall_seconds"] - clock["active_elapsed_seconds"]:
            raise ContractError("INVALID_TASK_CLOCK")


def _recovery_rules(p):
    """Check declared closure. Later recovery verifies actual content/barriers."""
    if not p["complete"]:
        return
    barrier = p["barrier"]
    if barrier["completed_at"] is None:
        raise ContractError("INCOMPLETE_RECOVERY_SET")
    duration = (_time(barrier["completed_at"]) - _time(barrier["started_at"])).total_seconds()
    if not 0 <= duration <= 30 or _time(p["created_at"]) < _time(barrier["completed_at"]):
        raise ContractError("INCOMPLETE_RECOVERY_SET")
    writer_roles = [w["role"] for w in p["writers"]]
    snapshot_roles = [s["owner_role"] for s in p["snapshots"]]
    if (len(writer_roles) != 4 or set(writer_roles) != {"coordinator", "evaluation", "execution", "watchdog"}
            or len(snapshot_roles) != 3 or set(snapshot_roles) != {"coordinator", "evaluation", "execution"}
            or any(w["barrier_id"] != barrier["barrier_id"] for w in p["writers"])
            or not p["reserve_accounting"]["allocated_verified"]):
        raise ContractError("INCOMPLETE_RECOVERY_SET")
    artifacts = {a["artifact_id"]: a for a in p["artifacts"]}
    paths = {a["path"]: a for a in p["artifacts"]}
    if len(artifacts) != len(p["artifacts"]) or len(paths) != len(p["artifacts"]):
        raise ContractError("INCOMPLETE_RECOVERY_SET")
    if any(parent not in artifacts for a in artifacts.values() for parent in a["parent_artifact_ids"]):
        raise ContractError("INCOMPLETE_RECOVERY_SET")
    tasks = {t["task_id"]: t for t in p["task_states"]}
    runs = {r["run_id"]: r for r in p["run_states"]}
    checkpoints = {c["checkpoint_id"]: c for c in p["checkpoints"]}
    if (len(tasks) != len(p["task_states"]) or len(runs) != len(p["run_states"])
            or len(checkpoints) != len(p["checkpoints"])):
        raise ContractError("INCOMPLETE_RECOVERY_SET")
    for run in runs.values():
        if run["task_id"] not in tasks:
            raise ContractError("INCOMPLETE_RECOVERY_SET")
    for checkpoint in checkpoints.values():
        run = runs.get(checkpoint["run_id"])
        if (checkpoint["task_id"] not in tasks or run is None
                or run["task_id"] != checkpoint["task_id"]
                or any(a not in artifacts for a in checkpoint["artifact_ids"])
                or (checkpoint["rng_state_artifact_id"] is not None and checkpoint["rng_state_artifact_id"] not in artifacts)):
            raise ContractError("INCOMPLETE_RECOVERY_SET")
    for task in tasks.values():
        if task["checkpoint_id"] is not None:
            checkpoint = checkpoints.get(task["checkpoint_id"])
            if checkpoint is None or checkpoint["task_id"] != task["task_id"]:
                raise ContractError("INCOMPLETE_RECOVERY_SET")
    for run in runs.values():
        if run["checkpoint_id"] is not None:
            checkpoint = checkpoints.get(run["checkpoint_id"])
            if (checkpoint is None or checkpoint["run_id"] != run["run_id"]
                    or checkpoint["task_id"] != run["task_id"]):
                raise ContractError("INCOMPLETE_RECOVERY_SET")
    for message in p["messages"]["pending"]:
        artifact = paths.get(message["payload_path"])
        if artifact is None or artifact["sha256"] != message["payload_sha256"]:
            raise ContractError("INCOMPLETE_RECOVERY_SET")
    seal_ids = [s['seal_id'] for s in p['seals']]
    evaluations = [s['evaluation_id'] for s in p['seals'] if s['evaluation_id'] is not None]
    if len(seal_ids)!=len(set(seal_ids)) or len(evaluations)!=len(set(evaluations)):
        raise ContractError('INCOMPLETE_RECOVERY_SET')
    for seal in p['seals']:
        if seal['checkpoint_id'] is not None:
            checkpoint=checkpoints.get(seal['checkpoint_id']);eid=seal['evaluation_id']
            if checkpoint is None or eid is None or checkpoint['task_id']!=eid or checkpoint['run_id']!=eid:
                raise ContractError('INCOMPLETE_RECOVERY_SET')
            if tasks[eid]['checkpoint_id']!=seal['checkpoint_id'] or runs[eid]['checkpoint_id']!=seal['checkpoint_id']:
                raise ContractError('INCOMPLETE_RECOVERY_SET')
    guard = p["consumption_guard"]
    if any(s["consumption_state"] == "CONSUMED" for s in p["seals"]):
        if guard["sequence"] == 0 or guard["head_event_id"] is None or guard["sha256"] is None:
            raise ContractError("INCOMPLETE_RECOVERY_SET")


def validate_record(schema_name: str, payload: dict, *, project_root: Path | None = None) -> dict:
    """Validate and detach a record. Explicit root required when it has paths.

    Extra keyword resolves the plan's missing path-validation context; ambient
    cwd is never treated as artifact authority. Actual bytes/ownership/effects
    are verified by the later native consumers, not by a record's claims.
    """
    if not isinstance(schema_name, str) or schema_name not in _SCHEMAS:
        raise ContractError("UNKNOWN_SCHEMA")
    plain = _plain(payload)
    if not isinstance(plain, dict):
        raise ContractError("INVALID_RECORD")
    expected_version = 1 if schema_name == "consumption_event.v1" else "1"
    if type(plain.get("schema_version")) is not type(expected_version) or plain.get("schema_version") != expected_version:
        raise ContractError("UNKNOWN_SCHEMA_VERSION")
    if schema_name == "task.v1":
        if not isinstance(plain.get("kind"), str):
            raise ContractError("INVALID_RECORD")
        if plain["kind"] not in {"OFFLINE_FIXTURE", "AI_PROPOSAL", "AI_QUALIFICATION", "RECOVERY_FIXTURE"}:
            raise ContractError("CAPABILITY_UNAVAILABLE")
    schema = _schema(schema_name)
    for error in Draft202012Validator(schema, format_checker=_FORMATS).iter_errors(plain):
        raise ContractError(_validation_reason(error))
    paths = list(_paths(schema, plain))
    if paths and project_root is None:
        raise ContractError("PROJECT_ROOT_REQUIRED")
    for path in paths:
        resolve_project_path(path, project_root)
    if schema_name.startswith("execution_"):
        from .execution_contracts import validate_execution_record
        validate_execution_record(plain)
    if schema_name == "task.v1":
        _task_rules(plain)
    if schema_name == "artifact_manifest.v1":
        if (_time(plain["command"]["ended_at"]) < _time(plain["command"]["started_at"])
                or _time(plain["created_at"]) < _time(plain["command"]["ended_at"])):
            raise ContractError("INVALID_UTC_TIMESTAMP")
    if schema_name == "recovery_manifest.v1":
        _recovery_rules(plain)
    if schema_name == "control_receipt.v1":
        if plain["action"] not in _CONTROL_ACTIONS:
            if (plain["state"] != "CAPABILITY_UNAVAILABLE" or plain["exit_code"] != 3
                    or plain["confirmed"] or plain["evidence_label"] != "CAPABILITY_UNAVAILABLE"):
                raise ContractError("CAPABILITY_UNAVAILABLE")
        if plain["confirmed"] != (plain["state"] == "CONFIRMED"):
            raise ContractError("UNCONFIRMED_EFFECT")
        if plain["confirmed"] and (plain["evidence_label"] != "VERIFIED_PASS" or plain["observed_at"] is None or plain["exit_code"] != 0):
            raise ContractError("UNCONFIRMED_EFFECT")
        if not plain["confirmed"] and (plain["evidence_label"] == "VERIFIED_PASS" or plain["exit_code"] == 0):
            raise ContractError("UNCONFIRMED_EFFECT")
        if plain["state"] == "CAPABILITY_UNAVAILABLE" and (plain["evidence_label"] != "CAPABILITY_UNAVAILABLE" or plain["exit_code"] != 3):
            raise ContractError("UNCONFIRMED_EFFECT")
        if plain["state"] in {"SUBMITTED", "PENDING", "UNKNOWN"} and (plain["evidence_label"] not in {"UNVERIFIED", "PENDING_EXTERNAL_TIME"} or plain["exit_code"] not in (None, 5)):
            raise ContractError("UNCONFIRMED_EFFECT")
        if plain["observed_at"] and _time(plain["observed_at"]) < _time(plain["requested_at"]):
            raise ContractError("INVALID_UTC_TIMESTAMP")
    return plain


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class _Record:
    payload: Mapping
    project_root: InitVar[Path | None] = None
    schema_name: ClassVar[str]

    def __post_init__(self, project_root):
        plain = validate_record(self.schema_name, self.payload, project_root=project_root)
        object.__setattr__(self, "payload", _freeze(plain))

    def to_payload(self) -> dict:
        return _plain(self.payload)


@dataclass(frozen=True)
class TaskSpec(_Record):
    schema_name = "task.v1"

    @property
    def task_id(self) -> str:
        return self.payload["task_id"]


@dataclass(frozen=True)
class ControlReceipt(_Record):
    schema_name = "control_receipt.v1"


@dataclass(frozen=True)
class ArtifactManifest(_Record):
    schema_name = "artifact_manifest.v1"


@dataclass(frozen=True)
class RecoveryManifest(_Record):
    schema_name = "recovery_manifest.v1"


@dataclass(frozen=True)
class AIProposal(_Record):
    schema_name = "ai_proposal.v1"


@dataclass(frozen=True)
class ProcessIdentity:
    process_instance_id: str
    pid: int
    creation_filetime: int
    operator_sid: str
    role: str

    def __post_init__(self):
        try:
            valid_id = str(UUID(self.process_instance_id)) == self.process_instance_id
        except (ValueError, AttributeError, TypeError):
            valid_id = False
        if (not valid_id or type(self.pid) is not int or self.pid < 1
                or type(self.creation_filetime) is not int or self.creation_filetime < 1
                or not isinstance(self.operator_sid, str) or not re.fullmatch(r"S-1-\d+(?:-\d+)+", self.operator_sid)
                or not isinstance(self.role, str)
                or self.role not in {"supervisor", "coordinator", "evaluation", "execution", "watchdog", "recovery", *_ROLE_LIMITS}):
            raise ContractError("INVALID_PROCESS_IDENTITY")
        # Shape only: callers cannot turn supplied PID/SID strings into proof.


class OwnerLease:
    """Opaque nonserializable holder, not a native lease acquisition API."""
    __slots__ = ("project_id", "generation", "identity", "_live_handle")

    def __init__(self, project_id: str, generation: int, identity: ProcessIdentity, live_handle):
        if (not isinstance(project_id, str) or not re.fullmatch(r"[0-9a-f]{64}", project_id) or type(generation) is not int
                or generation < 1 or not isinstance(identity, ProcessIdentity) or live_handle is None):
            raise ContractError("INVALID_OWNER_LEASE")
        for key, value in (("project_id", project_id), ("generation", generation), ("identity", identity), ("_live_handle", live_handle)):
            object.__setattr__(self, key, value)

    def __setattr__(self, name, value):
        raise AttributeError("immutable owner lease")

    def __delattr__(self, name):
        raise AttributeError("immutable owner lease")

    def to_payload(self):
        raise ContractError("PRIVATE_CAPABILITY")

    def __getstate__(self):
        raise ContractError("PRIVATE_CAPABILITY")


@dataclass(frozen=True)
class CapabilityDecision:
    status: str
    exit_code: int
    broker_state: str = "NOT_CONFIGURED"


_CONTROL_ACTIONS = frozenset({"start", "attach", "status", "doctor.read_only", "foundation.check",
                              "pause_research", "resume_research", "checkpoint", "stop_research",
                              "shutdown", "ai.export", "ai.import", "baseline", "final", "final_audit", "synthetic_protocol", "owner_heartbeat", "fake_operator", "paper_read", "paper_read_transfer", "paper_market_read", "paper_market_transfer"})

M0_CAPABILITIES = MappingProxyType({
    **{action: "CONTRACT_DEFINED" for action in _CONTROL_ACTIONS},
    "paper.arm": "CAPABILITY_UNAVAILABLE", "paper.start": "CAPABILITY_UNAVAILABLE",
    "paper.cancel": "CAPABILITY_UNAVAILABLE", "paper.close": "CAPABILITY_UNAVAILABLE",
    "data.fetch": "CAPABILITY_UNAVAILABLE", "evaluate.final": "CAPABILITY_UNAVAILABLE",
    "promote": "CAPABILITY_UNAVAILABLE",
})


def capability_for(action: str) -> CapabilityDecision:
    status = M0_CAPABILITIES.get(action, "CAPABILITY_UNAVAILABLE") if isinstance(action, str) else "CAPABILITY_UNAVAILABLE"
    return CapabilityDecision(status, 3 if status == "CAPABILITY_UNAVAILABLE" else 0)


@dataclass(frozen=True)
class ExecutionObservation(_Record):
    schema_name = "execution_observation.v1"


@dataclass(frozen=True)
class ExecutionIntent(_Record):
    schema_name = "execution_intent.v1"


@dataclass(frozen=True)
class ExecutionPlan(_Record):
    schema_name = "execution_plan.v1"


@dataclass(frozen=True)
class ExecutionAuthorization(_Record):
    schema_name = "execution_authorization.v1"


@dataclass(frozen=True)
class ExecutionCalendar(_Record):
    schema_name = "execution_calendar.v1"


@dataclass(frozen=True)
class ExecutionInputs(_Record):
    schema_name = "execution_inputs.v1"


@dataclass(frozen=True)
class ExecutionStart(_Record):
    schema_name = "execution_start.v1"


@dataclass(frozen=True)
class ExecutionDecision(_Record):
    schema_name = "execution_decision.v1"

    def __getitem__(self,key):
        return self.payload[key]
