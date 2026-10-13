"""Boundary checks: configuration cannot raise fixed M0 ceilings."""
import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return importlib.import_module("compertum.config")


def candidate(text):
    namespace = ROOT / ".cache/test-runs" / f"config-{uuid4().hex}"
    namespace.mkdir(parents=True)
    path = namespace / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def default_text():
    path = ROOT / "config/default.toml"
    assert path.is_file(), "M0 defaults are not implemented"
    return path.read_text(encoding="utf-8")


def test_resolved_defaults_preserve_reserve_inside_project_cap(config):
    value = config.load_config(ROOT / "config/default.toml", ROOT)
    assert value.storage_total_bytes == 53687091200
    assert sum(value.storage_categories.values()) == 53687091200
    assert value.execution_reserve_bytes == 1073741824
    assert value.storage_categories["records"] == 5368709120
    assert value.paths["state"] == ROOT / "state"
    with pytest.raises(FrozenInstanceError):
        value.storage_total_bytes = 999
    with pytest.raises(TypeError):
        value.storage_categories["records"] = 0


@pytest.mark.parametrize("old,new", [("research_cpu_threads = 4", "research_cpu_threads = 8"),
                                    ("local_request_seconds = 120", "local_request_seconds = 121"),
                                    ('new_spending_usd = "0.00"', 'new_spending_usd = "1.00"'),
                                    ("local_inference_slots = 1", "local_inference_slots = 2")])
def test_budget_cannot_increase_itself(config, old, new):
    text = default_text()
    assert old in text
    with pytest.raises(config.ConfigError) as caught:
        config.load_config(candidate(text.replace(old, new)), ROOT)
    assert caught.value.reason == "FIXED_M0_SETTING"


def test_unknown_config_field_and_path_escape_are_denied(config):
    text = default_text()
    with pytest.raises(config.ConfigError) as caught:
        config.load_config(candidate(text + '\n[unapproved]\norders = true\n'), ROOT)
    assert caught.value.reason == "UNKNOWN_CONFIG_FIELD"
    with pytest.raises(config.ConfigError) as caught:
        config.load_config(candidate(text.replace('state = "state"', 'state = "../state"')), ROOT)
    assert caught.value.reason == "ARTIFACT_ESCAPE"


def test_config_input_must_stay_inside_root_and_be_bounded(config):
    path = candidate(default_text())
    with pytest.raises(config.ConfigError) as caught:
        config.load_config(path, path.parent / "other")
    assert caught.value.reason == "CONFIG_OUTSIDE_PROJECT"
    oversized = candidate("#" * 65537)
    with pytest.raises(config.ConfigError) as caught:
        config.load_config(oversized, ROOT)
    assert caught.value.reason == "CONFIG_TOO_LARGE"


def test_daily_research_cap_is_absent_and_legacy_value_is_ignored(config):
    text = default_text()
    assert "cpu_job_wall_seconds_per_day" not in text
    current = config.load_config(ROOT / "config/default.toml", ROOT)
    assert "cpu_job_wall_seconds_per_day" not in current.resources
    legacy = text.replace("[resources]", "[resources]\ncpu_job_wall_seconds_per_day = 7200")
    loaded = config.load_config(candidate(legacy), ROOT)
    assert dict(loaded.resources) == dict(current.resources)


def test_retired_daily_setting_cannot_change_other_limits(config):
    text = default_text().replace("[resources]", "[resources]\ncpu_job_wall_seconds_per_day = 7200")
    with pytest.raises(config.ConfigError, match="FIXED_M0_SETTING"):
        config.load_config(candidate(text.replace("research_cpu_threads = 4", "research_cpu_threads = 8")), ROOT)
