"""Validate crew-spec: one agent ↔ one task, meeting + DoD rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REQUIRED_TOP = (
    "schema_version",
    "name",
    "goal",
    "agents",
    "tasks",
    "meetings",
    "definition_of_done",
    "stop_conditions",
)

ALLOWED_STATUS = frozenset({"todo", "in_progress", "blocked", "done", "skipped"})
ALLOWED_MEETING_KINDS = frozenset(
    {"kickoff", "standup", "sync", "review", "retro", "decision", "closeout"}
)
ALLOWED_PROCESS = frozenset({"collaborative", "sequential", "hierarchical"})


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"validate: {status}"]
        for e in self.errors:
            lines.append(f"  error: {e}")
        for w in self.warnings:
            lines.append(f"  warn:  {w}")
        return "\n".join(lines)


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_spec(spec: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(spec, dict):
        return ValidationResult(False, ["root must be an object"])

    for key in REQUIRED_TOP:
        if key not in spec:
            errors.append(f"missing required field: {key}")

    if "schema_version" in spec and str(spec["schema_version"]) not in {"1.0", "1"}:
        warnings.append(f"unknown schema_version: {spec.get('schema_version')}")

    name = spec.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        errors.append("name must be a non-empty string")

    goal = spec.get("goal")
    if goal is not None and (not isinstance(goal, str) or not goal.strip()):
        errors.append("goal must be a non-empty string")

    if "process" in spec:
        proc = str(spec.get("process") or "").strip().lower()
        if proc and proc not in ALLOWED_PROCESS:
            errors.append(
                f"process invalid: {spec.get('process')} "
                f"(allowed: {sorted(ALLOWED_PROCESS)})"
            )

    agents = spec.get("agents")
    tasks = spec.get("tasks")
    if not isinstance(agents, list) or len(agents) < 2:
        errors.append("agents must be a list with at least 2 agents (crew needs collaboration)")
    if not isinstance(tasks, list) or len(tasks) < 1:
        errors.append("tasks must be a non-empty list")

    agent_ids: set[str] = set()
    agent_task_map: dict[str, str] = {}
    if isinstance(agents, list):
        for i, raw in enumerate(agents):
            a = _obj(raw)
            path = f"agents[{i}]"
            aid = a.get("id")
            if not isinstance(aid, str) or not aid.strip():
                errors.append(f"{path}.id is required")
                continue
            if aid in agent_ids:
                errors.append(f"duplicate agent id: {aid}")
            agent_ids.add(aid)
            if not a.get("role"):
                errors.append(f"{path}.role is required ({aid})")
            tid = a.get("task_id")
            if not isinstance(tid, str) or not tid.strip():
                errors.append(f"{path}.task_id is required — one agent, one task ({aid})")
            else:
                if tid in agent_task_map.values():
                    owner = next(k for k, v in agent_task_map.items() if v == tid)
                    errors.append(
                        f"task_id '{tid}' assigned to both '{owner}' and '{aid}' "
                        "(one agent per task)"
                    )
                agent_task_map[aid] = tid
            # Forbid multi-task lists on agent
            if "task_ids" in a or "tasks" in a:
                errors.append(
                    f"{path}: use single task_id only (found task_ids/tasks) — one agent one task"
                )

    task_ids: set[str] = set()
    if isinstance(tasks, list):
        for i, raw in enumerate(tasks):
            t = _obj(raw)
            path = f"tasks[{i}]"
            tid = t.get("id")
            if not isinstance(tid, str) or not tid.strip():
                errors.append(f"{path}.id is required")
                continue
            if tid in task_ids:
                errors.append(f"duplicate task id: {tid}")
            task_ids.add(tid)
            if not t.get("title") and not t.get("description"):
                errors.append(f"{path}: title or description required ({tid})")
            owner = t.get("owner")
            if owner is not None:
                if owner not in agent_ids:
                    errors.append(f"{path}.owner '{owner}' is not a known agent")
                elif agent_task_map.get(str(owner)) not in (None, tid):
                    errors.append(
                        f"{path}.owner '{owner}' is bound to task "
                        f"'{agent_task_map.get(str(owner))}', not '{tid}'"
                    )
            status = t.get("status", "todo")
            if status not in ALLOWED_STATUS:
                errors.append(f"{path}.status invalid: {status}")
            deps = t.get("depends_on") or []
            if deps and not isinstance(deps, list):
                errors.append(f"{path}.depends_on must be a list")

    # Every agent task_id must exist; every task should have an owner agent
    for aid, tid in agent_task_map.items():
        if tid not in task_ids:
            errors.append(f"agent '{aid}' task_id '{tid}' not found in tasks[]")

    owned = set(agent_task_map.values())
    if isinstance(tasks, list):
        for raw in tasks:
            t = _obj(raw)
            tid = t.get("id")
            if isinstance(tid, str) and tid not in owned:
                warnings.append(f"task '{tid}' has no agent owner (orphan)")

    # Cross-check owner field consistency
    if isinstance(tasks, list) and isinstance(agents, list):
        for raw in agents:
            a = _obj(raw)
            aid, tid = a.get("id"), a.get("task_id")
            if not isinstance(aid, str) or not isinstance(tid, str):
                continue
            for traw in tasks:
                t = _obj(traw)
                if t.get("id") == tid:
                    if t.get("owner") and t.get("owner") != aid:
                        errors.append(
                            f"task '{tid}' owner='{t.get('owner')}' but agent '{aid}' claims it"
                        )
                    break

    meetings = spec.get("meetings")
    if isinstance(meetings, dict):
        kind = meetings.get("default_kind", "standup")
        if kind not in ALLOWED_MEETING_KINDS:
            errors.append(f"meetings.default_kind invalid: {kind}")
        cadence = meetings.get("cadence")
        if cadence is not None and not isinstance(cadence, str):
            errors.append("meetings.cadence must be a string")
        if not meetings.get("agenda_template") and not meetings.get("phases"):
            warnings.append("meetings: set phases or agenda_template for predictable sync")
    elif meetings is not None:
        errors.append("meetings must be an object")

    dod = spec.get("definition_of_done")
    if isinstance(dod, list):
        if len(dod) < 1:
            errors.append("definition_of_done must have at least one item")
    elif dod is not None:
        errors.append("definition_of_done must be a list")

    stop = _obj(spec.get("stop_conditions"))
    if "stop_conditions" in spec:
        if "max_meetings" not in stop and "success_signal" not in stop:
            warnings.append("stop_conditions: prefer max_meetings and/or success_signal")

    # Collaboration rule: no single-agent "crew"
    if len(agent_ids) == 1:
        errors.append("crew needs ≥2 agents to meet and collaborate")

    ok = len(errors) == 0
    return ValidationResult(ok=ok, errors=errors, warnings=warnings)
