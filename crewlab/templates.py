"""Scaffold crew projects and default specs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_SPEC: dict[str, Any] = {
    "schema_version": "1.0",
    "name": "example-crew",
    "goal": "Ship one bounded project outcome with a multi-agent crew.",
    "agents": [
        {
            "id": "lead",
            "role": "Crew Lead",
            "task_id": "plan-and-coordinate",
            "mission": "Own the plan, meetings, and scope. Do not implement.",
        },
        {
            "id": "builder",
            "role": "Builder",
            "task_id": "implement-core",
            "mission": "Implement only the core deliverable task.",
        },
        {
            "id": "reviewer",
            "role": "Reviewer",
            "task_id": "review-and-test",
            "mission": "Review, test, and block merge until quality bar is met.",
        },
        {
            "id": "integrator",
            "role": "Integrator",
            "task_id": "integrate-and-ship",
            "mission": "Integrate pieces, finalize ship checklist, close project.",
        },
    ],
    "tasks": [
        {
            "id": "plan-and-coordinate",
            "title": "Plan scope and run crew meetings",
            "owner": "lead",
            "status": "todo",
            "depends_on": [],
        },
        {
            "id": "implement-core",
            "title": "Implement core deliverable",
            "owner": "builder",
            "status": "todo",
            "depends_on": ["plan-and-coordinate"],
        },
        {
            "id": "review-and-test",
            "title": "Review and test deliverable",
            "owner": "reviewer",
            "status": "todo",
            "depends_on": ["implement-core"],
        },
        {
            "id": "integrate-and-ship",
            "title": "Integrate, document ship, closeout",
            "owner": "integrator",
            "status": "todo",
            "depends_on": ["review-and-test"],
        },
    ],
    "meetings": {
        "default_kind": "standup",
        "cadence": "per-iteration",
        "phases": [
            "open",
            "status_reports",
            "blockers",
            "sync_decisions",
            "next_actions",
            "close",
        ],
    },
    "definition_of_done": [
        "All tasks status=done or skipped",
        "No open blockers",
        "Meeting log records final closeout",
        "Ship artifact path recorded in integrator task result",
    ],
    "stop_conditions": {
        "max_meetings": 12,
        "success_signal": "all_tasks_done",
        "failure_policy": "stop_and_report",
    },
    "hermes": {
        "skill": "crewlab",
        "delegate": True,
    },
}


def write_init_spec(path: Path, name: str | None = None) -> Path:
    data = dict(DEFAULT_SPEC)
    if name:
        data["name"] = name
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def write_project_scaffold(path: Path, name: str | None = None) -> list[Path]:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    crew_name = name or root.name
    written: list[Path] = []
    spec_path = root / "crew-spec.yaml"
    write_init_spec(spec_path, name=crew_name)
    written.append(spec_path)

    project_md = root / "PROJECT.md"
    project_md.write_text(
        f"# {crew_name}\n\n"
        f"Goal: {DEFAULT_SPEC['goal']}\n\n"
        "## Rules\n"
        "- One agent = one task\n"
        "- Scope changes only via meeting decision\n"
        "- Ship together; no silent solo merges of foreign tasks\n",
        encoding="utf-8",
    )
    written.append(project_md)

    readme = root / "README.md"
    readme.write_text(
        f"# {crew_name}\n\n"
        "```bash\n"
        "crewlab validate crew-spec.yaml\n"
        "crewlab meeting crew-spec.yaml\n"
        "crewlab status crew-spec.yaml\n"
        "crewlab task crew-spec.yaml --task implement-core --status done --result 'shipped'\n"
        "```\n",
        encoding="utf-8",
    )
    written.append(readme)
    return written
