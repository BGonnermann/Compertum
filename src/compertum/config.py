"""Read immutable, fixed M0 settings; never create state or contact a provider."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from compertum.domain import ContractError, resolve_project_path


class ConfigError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


# Kept in trusted source, independently of a user-supplied TOML file. Editing
# config alone cannot raise a ceiling. A new trusted release is a new review.
_DEFAULTS = {
    "project": {"schema_version": "1", "mode": "m0", "new_spending_usd": "0.00"},
    "storage": {
        "total_bytes": 214748364800, "data_bytes": 16106127360, "models_bytes": 5368709120,
        "scratch_bytes": 53687091200, "records_bytes": 5368709120, "backups_bytes": 22548578304,
        "execution_reserve_bytes": 1073741824, "reserve_release_bytes": 67108864,
        "minimum_unused_reserve_bytes": 268435456, "minimum_free_bytes": 53687091200,
        "ingestion_free_bytes": 107374182400, "maximum_write_chunk_bytes": 8388608,
        "attempt_log_bytes": 10485760,
    },
    "resources": {
        "research_cpu_threads": 4, "research_ram_bytes": 4294967296,
        "heavy_job_slots": 1, "local_inference_slots": 1,
        "ai_tasks_per_day": 8, "ai_requests_per_day": 40,
        "ai_wrapper_cpu_threads": 1, "ai_wrapper_ram_bytes": 268435456,
        "coordinator_ram_bytes": 268435456, "execution_ram_bytes": 536870912,
        "watchdog_ram_bytes": 134217728, "data_ram_bytes": 1073741824,
        "report_ram_bytes": 536870912, "report_output_bytes": 524288000,
        "dispatch_available_ram_bytes": 8589934592, "pause_available_ram_bytes": 6442450944,
        "local_input_tokens": 16384, "local_output_tokens": 2048, "local_request_seconds": 120,
        "manual_receipt_seconds": 86400, "heartbeat_seconds": 5, "missing_heartbeat_seconds": 15,
        "task_lease_seconds": 30, "volume_monitor_seconds": 1, "project_monitor_seconds": 35,
        "storage_scan_seconds": 30, "control_request_seconds": 300,
        "recovery_barrier_seconds": 240,
    },
    "paths": {"state": "state", "data": "data", "artifacts": "artifacts", "scratch": ".cache",
              "backups": "backups", "reports": "reports", "logs": "logs"},
    "seeds": {"campaign": 1729, "model": 1730, "bootstrap": 1731, "counterexample": 1732},
    "capabilities": {"paper": False, "authenticated_data": False, "final_evaluation": False,
                     "promotion": False, "gpu_training": False, "automatic_codex": False,
                     "local_ai_dispatch": False},
}


@dataclass(frozen=True)
class M0Config:
    project_root: Path
    new_spending_usd: Decimal
    storage_total_bytes: int
    storage_categories: Mapping[str, int]
    execution_reserve_bytes: int
    storage_policy: Mapping[str, int]
    resources: Mapping[str, int]
    paths: Mapping[str, Path]
    seeds: Mapping[str, int]
    capabilities: Mapping[str, bool]

    def to_payload(self) -> dict:
        """Nonsecret configuration receipt; no runtime verification claim."""
        return {
            "schema_version": "1", "mode": "m0", "new_spending_usd": str(self.new_spending_usd),
            "project_root": str(self.project_root), "storage_total_bytes": self.storage_total_bytes,
            "storage_categories": dict(self.storage_categories),
            "execution_reserve_bytes": self.execution_reserve_bytes,
            "storage_policy": dict(self.storage_policy), "resources": dict(self.resources),
            "paths": {key: str(path) for key, path in self.paths.items()},
            "seeds": dict(self.seeds), "capabilities": dict(self.capabilities),
            "broker_state": "NOT_CONFIGURED", "native_enforcement": "UNVERIFIED",
        }


def load_config(path: Path, project_root: Path) -> M0Config:
    root = Path(project_root).absolute()
    config_path = Path(path).absolute()
    try:
        relative = config_path.relative_to(root).as_posix()
    except ValueError:
        raise ConfigError("CONFIG_OUTSIDE_PROJECT") from None
    try:
        config_path = resolve_project_path(relative, root)
        with config_path.open("rb") as stream:
            raw = stream.read(65537)
    except ContractError as exc:
        raise ConfigError(exc.reason) from None
    except OSError:
        raise ConfigError("CONFIG_UNAVAILABLE") from None
    if len(raw) > 65536:
        raise ConfigError("CONFIG_TOO_LARGE")
    try:
        supplied = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError):
        raise ConfigError("INVALID_CONFIG") from None
    # Read historical project configs without restoring the retired daily cap.
    resources = supplied.get("resources")
    # The owner revised workload limits on 16 October. Read frozen older
    # configurations without rewriting their bytes or changing runtime identity.
    storage = supplied.get("storage")
    # Frozen configurations hold the retired scratch limits (5 GiB until 16 October 2026, 12 GiB until 24 October 2026).
    if isinstance(storage, dict) and storage.get("scratch_bytes") in (5368709120, 12884901888):
        storage["scratch_bytes"] = _DEFAULTS["storage"]["scratch_bytes"]
    # The project total was 50 GiB until 24 October 2026 (owner decision: 200 GiB). Frozen configurations read as the current total.
    if isinstance(storage, dict) and storage.get("total_bytes") == 53687091200:
        storage["total_bytes"] = _DEFAULTS["storage"]["total_bytes"]
    if isinstance(resources, dict):
        if resources.get("project_monitor_seconds") == 5:
            resources["project_monitor_seconds"] = 35
        if resources.get("recovery_barrier_seconds") == 30:
            resources["recovery_barrier_seconds"] = 240
        for key in ("storage_scan_seconds", "control_request_seconds"):
            resources.setdefault(key, _DEFAULTS["resources"][key])
    if isinstance(resources, dict) and "cpu_job_wall_seconds_per_day" in resources:
        legacy_daily_cap = resources.pop("cpu_job_wall_seconds_per_day")
        if type(legacy_daily_cap) is not int or legacy_daily_cap != 7200:
            raise ConfigError("FIXED_M0_SETTING")
    if supplied.keys() != _DEFAULTS.keys():
        raise ConfigError("UNKNOWN_CONFIG_FIELD")
    resolved_paths = {}
    for section, expected in _DEFAULTS.items():
        actual = supplied[section]
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ConfigError("UNKNOWN_CONFIG_FIELD")
        if section == "paths":
            for name, relative_path in actual.items():
                try:
                    resolved_paths[name] = resolve_project_path(relative_path, root)
                except ContractError as exc:
                    raise ConfigError(exc.reason) from None
        if any(type(actual[key]) is not type(value) or actual[key] != value for key, value in expected.items()):
            raise ConfigError("FIXED_M0_SETTING")
    storage = supplied["storage"]
    categories = {name: storage[f"{name}_bytes"] for name in ("data", "models", "scratch", "records", "backups")}
    return M0Config(
        project_root=root.resolve(), new_spending_usd=Decimal(supplied["project"]["new_spending_usd"]),
        storage_total_bytes=storage["total_bytes"], storage_categories=MappingProxyType(categories),
        execution_reserve_bytes=storage["execution_reserve_bytes"],
        storage_policy=MappingProxyType(dict(storage)), resources=MappingProxyType(dict(supplied["resources"])),
        paths=MappingProxyType(resolved_paths), seeds=MappingProxyType(dict(supplied["seeds"])),
        capabilities=MappingProxyType(dict(supplied["capabilities"])),
    )
