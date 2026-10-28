"""Harness settings loaded from Compertum's existing model files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from compertum.ai.engine.practice import chosen_roles
from compertum.ai.models import RoleModel, auth_headers, checked_spec


@dataclass(frozen=True)
class Settings:
    root: Path
    workspace: Path
    model: RoleModel
    models: str
    max_steps: int = 30
    max_seconds: float = 900.0

    def headers(self) -> dict:
        return auth_headers(self.model)


def load(root: Path, workspace: Path, models: str, model: str | None, max_steps: int, max_minutes: float) -> Settings:
    root = root.resolve(strict=True)
    workspace = workspace.resolve(strict=True)
    if not root.is_dir() or not workspace.is_dir() or not workspace.is_relative_to(root):
        raise ValueError("the workspace must be a folder inside the project")
    if type(max_steps) is not int or not 1 <= max_steps <= 100 or not 1 <= max_minutes <= 60:
        raise ValueError("task limits must be 1 to 100 steps and 1 to 60 minutes")
    spec = chosen_roles(root, models, model)["director"]
    if not checked_spec(spec):
        raise ValueError("the model configuration is not valid")
    return Settings(root, workspace, spec, models, max_steps, max_minutes * 60)
