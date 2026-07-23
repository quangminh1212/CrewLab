"""Project state: load/save STATE, mark tasks, completion check."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crewlab.io_util import dump_yaml, load_spec
from crewlab.validate import ALLOWED_STATUS, validate_spec


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_path(project_dir: Path) -> Path:
    return project_dir / "STATE.yaml"


def meeting_log_path(project_dir: Path) -> Path:
    return project_dir / "MEETING_LOG.md"


def default_state(spec: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for t in spec.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tasks.append(
            {
                "id": t.get("id"),
                "status": t.get("status") or "todo",
                "owner": t.get("owner"),
                "result": None,
                "updated_at": None,
            }
        )
    # fill owner from agents if missing
    for a in spec.get("agents") or []:
        if not isinstance(a, dict):
            continue
        for st in tasks:
            if st["id"] == a.get("task_id") and not st.get("owner"):
                st["owner"] = a.get("id")
    return {
        "crew": spec.get("name"),
        "goal": spec.get("goal"),
        "meeting_round": 0,
        "status": "active",
        "tasks": tasks,
        "decisions": [],
        "blockers": [],
        "updated_at": utc_now(),
    }


def load_or_init_state(project_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    path = state_path(project_dir)
    if path.exists():
        data = load_spec(path)
        return data
    state = default_state(spec)
    dump_yaml(path, state)
    return state


def save_state(project_dir: Path, state: dict[str, Any]) -> Path:
    state["updated_at"] = utc_now()
    path = state_path(project_dir)
    dump_yaml(path, state)
    return path


def set_task_status(
    state: dict[str, Any],
    task_id: str,
    status: str,
    result: str | None = None,
) -> None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"invalid status: {status}")
    found = False
    for t in state.get("tasks") or []:
        if t.get("id") == task_id:
            t["status"] = status
            t["updated_at"] = utc_now()
            if result is not None:
                t["result"] = result
            found = True
            break
    if not found:
        raise KeyError(f"task not found: {task_id}")


def task_progress(state: dict[str, Any]) -> dict[str, int]:
    counts = {s: 0 for s in ALLOWED_STATUS}
    for t in state.get("tasks") or []:
        st = t.get("status") or "todo"
        counts[st] = counts.get(st, 0) + 1
    counts["total"] = sum(counts.get(s, 0) for s in ALLOWED_STATUS)
    return counts


def is_project_complete(spec: dict[str, Any], state: dict[str, Any]) -> tuple[bool, list[str]]:
    """Complete when all owned tasks done/skipped and no open blockers (simple DoD)."""
    notes: list[str] = []
    tasks = state.get("tasks") or []
    if not tasks:
        return False, ["no tasks in state"]
    pending = [t for t in tasks if t.get("status") not in {"done", "skipped"}]
    if pending:
        notes.append(f"{len(pending)} task(s) not done: " + ", ".join(t.get("id", "?") for t in pending))
    blockers = state.get("blockers") or []
    open_b = [b for b in blockers if not (isinstance(b, dict) and b.get("resolved"))]
    if open_b:
        notes.append(f"{len(open_b)} open blocker(s)")
    # Optional explicit success_signal
    stop = spec.get("stop_conditions") or {}
    signal = stop.get("success_signal")
    if signal == "all_tasks_done" and not pending and not open_b:
        return True, ["all_tasks_done"]
    if not pending and not open_b:
        notes.append("all tasks done, no open blockers")
        return True, notes
    return False, notes


def status_report(spec: dict[str, Any], state: dict[str, Any]) -> str:
    v = validate_spec(spec)
    prog = task_progress(state)
    done, notes = is_project_complete(spec, state)
    lines = [
        f"crew:   {spec.get('name')}",
        f"goal:   {spec.get('goal')}",
        f"round:  {state.get('meeting_round', 0)}",
        f"status: {state.get('status')} | complete={done}",
        f"tasks:  {prog.get('done', 0)}/{prog.get('total', 0)} done "
        f"(todo={prog.get('todo', 0)} in_progress={prog.get('in_progress', 0)} "
        f"blocked={prog.get('blocked', 0)} skipped={prog.get('skipped', 0)})",
        f"spec:   {'PASS' if v.ok else 'FAIL'}",
    ]
    lines.append("agents:")
    for a in spec.get("agents") or []:
        if not isinstance(a, dict):
            continue
        tid = a.get("task_id")
        st = next((t.get("status") for t in (state.get("tasks") or []) if t.get("id") == tid), "?")
        lines.append(f"  - {a.get('id')} [{a.get('role')}] → {tid} ({st})")
    if notes:
        lines.append("notes:")
        for n in notes:
            lines.append(f"  - {n}")
    if state.get("decisions"):
        lines.append(f"decisions: {len(state['decisions'])}")
    return "\n".join(lines)
