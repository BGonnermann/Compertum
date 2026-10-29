"""Harness settings loaded from Compertum's existing model files."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from compertum.ai.engine.practice import MODEL_NAME, chosen_roles
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


def _choice_path(root: Path) -> Path:
    return root / "state" / "harness" / "model.json"


def remembered(root: Path) -> tuple[str, str | None] | None:
    """Return the last model choice, or None when there is none or it is not valid."""
    try:
        value = json.loads(_choice_path(root).read_text(encoding="utf-8"))
        models, model = value["models"], value.get("model")
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if not isinstance(models, str) or not MODEL_NAME.fullmatch(models) or not (model is None or isinstance(model, str)):
        return None
    return models, model


def remember(root: Path, models: str, model: str) -> None:
    """Keep the model choice for the next start and resume. A failed save leaves the current choice working."""
    try:
        path = _choice_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"models": models, "model": model}), encoding="utf-8")
    except OSError:
        pass


def model_files(root: Path) -> tuple[str, ...]:
    names = {"local"}
    for path in sorted((root / "config").glob("models-*.toml")):
        name = path.stem.removeprefix("models-")
        if MODEL_NAME.fullmatch(name):
            names.add(name)
        if len(names) > 32:
            raise ValueError("too many model files")
    return tuple(sorted(names))
