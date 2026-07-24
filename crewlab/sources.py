"""GitHub equivalent-source catalog for CrewLab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def catalog_path() -> Path:
    return repo_root() / "sources" / "catalog.yaml"


@dataclass
class SourceEntry:
    id: str
    url: str
    license: str
    status: str
    role: str
    evidence: list[str]


def load_catalog() -> list[SourceEntry]:
    path = catalog_path()
    if not path.is_file():
        raise FileNotFoundError(f"catalog missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[SourceEntry] = []
    for e in data.get("entries") or []:
        if not isinstance(e, dict):
            continue
        out.append(
            SourceEntry(
                id=str(e.get("id") or ""),
                url=str(e.get("url") or ""),
                license=str(e.get("license") or ""),
                status=str(e.get("status") or "referenced"),
                role=str(e.get("role") or ""),
                evidence=[str(x) for x in (e.get("evidence") or [])],
            )
        )
    return out


def check_catalog(root: Path | None = None) -> list[str]:
    """Return list of problems (empty = OK). Integrated entries need evidence paths."""
    root = root or repo_root()
    problems: list[str] = []
    entries = load_catalog()
    if not entries:
        problems.append("catalog empty")
        return problems
    for e in entries:
        if not e.id or not e.url:
            problems.append(f"incomplete entry: {e}")
            continue
        if e.status == "integrated":
            if not e.evidence:
                problems.append(f"{e.id}: integrated but no evidence paths")
            for rel in e.evidence:
                p = root / rel
                if not p.exists():
                    problems.append(f"{e.id}: missing evidence {rel}")
    return problems


def format_catalog() -> str:
    lines = ["CrewLab GitHub equivalent sources:", ""]
    for e in load_catalog():
        lines.append(f"  [{e.status:10}] {e.id:14} {e.url}")
        lines.append(f"               {e.role} ({e.license})")
    problems = check_catalog()
    lines.append("")
    if problems:
        lines.append(f"check: FAIL ({len(problems)})")
        for p in problems:
            lines.append(f"  - {p}")
    else:
        lines.append("check: PASS (all integrated evidence present)")
    return "\n".join(lines)
