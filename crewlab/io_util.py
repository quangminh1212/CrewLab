"""Load / dump crew specs and project state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

# Accepted filenames when user passes a project directory instead of a file path.
_SPEC_BASENAMES = ("crew-spec.yaml", "crew-spec.yml", "crew-spec.json")


def resolve_spec_path(path: str | Path) -> Path:
    """Resolve a crew-spec file path or a project directory containing one.

    User flow after ``crewlab init <dir>`` often uses the directory for
    ``status`` / ``meeting`` / ``task``; accept that without forcing the file path.
    """
    p = Path(path)
    if p.is_file():
        return p
    if p.is_dir():
        for name in _SPEC_BASENAMES:
            candidate = p / name
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(
            f"no crew-spec.yaml (or .yml/.json) in directory: {p}"
        )
    raise FileNotFoundError(f"spec not found: {p}")


def load_spec(path: str | Path) -> dict[str, Any]:
    p = resolve_spec_path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{p}: root must be a mapping")
    return data


def dump_yaml(path: str | Path, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )


def dump_json(path: str | Path, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def project_dir_for(spec_path: str | Path) -> Path:
    """Working directory for state/meeting logs = directory of the crew-spec."""
    return resolve_spec_path(spec_path).resolve().parent
