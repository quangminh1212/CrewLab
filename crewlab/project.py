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


def _next_blocker_id(state: dict[str, Any]) -> str:
    existing = []
    for b in state.get("blockers") or []:
        if isinstance(b, dict) and isinstance(b.get("id"), str):
            existing.append(b["id"])
    n = 1
    while f"b{n}" in existing:
        n += 1
    return f"b{n}"


def add_blocker(
    state: dict[str, Any],
    text: str,
    *,
    agent: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Record an open blocker (blocks project complete until resolved)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("blocker text required")
    item = {
        "id": _next_blocker_id(state),
        "text": text,
        "agent": agent,
        "task_id": task_id,
        "at": utc_now(),
        "resolved": False,
    }
    state.setdefault("blockers", []).append(item)
    return item


def resolve_blocker(state: dict[str, Any], blocker_id: str) -> dict[str, Any]:
    """Mark blocker resolved by id."""
    bid = (blocker_id or "").strip()
    for b in state.get("blockers") or []:
        if isinstance(b, dict) and b.get("id") == bid:
            b["resolved"] = True
            b["resolved_at"] = utc_now()
            return b
    raise KeyError(f"blocker not found: {bid}")


def list_blockers(state: dict[str, Any], *, open_only: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in state.get("blockers") or []:
        if not isinstance(b, dict):
            continue
        if open_only and b.get("resolved"):
            continue
        out.append(b)
    return out


def add_decision(
    state: dict[str, Any],
    text: str,
    *,
    round_no: int | None = None,
) -> dict[str, Any]:
    """Record a formal meeting decision (e.g. reassignment approval)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("decision text required")
    item = {
        "at": utc_now(),
        "text": text,
        "round": round_no if round_no is not None else state.get("meeting_round") or 0,
    }
    state.setdefault("decisions", []).append(item)
    return item


def reassign_agent_task(
    spec: dict[str, Any],
    state: dict[str, Any],
    *,
    agent_id: str,
    task_id: str,
    decision: str | None = None,
) -> dict[str, Any]:
    """Reassign one agent to one task (swap if another agent already owns it).

    Enforces one-agent-one-task. Records a decision when ``decision`` is set
    (or a default note). Updates both crew-spec agents[] and STATE owners.
    """
    agent_id = (agent_id or "").strip()
    task_id = (task_id or "").strip()
    agents = [a for a in (spec.get("agents") or []) if isinstance(a, dict)]
    tasks = [t for t in (spec.get("tasks") or []) if isinstance(t, dict)]
    agent = next((a for a in agents if a.get("id") == agent_id), None)
    if not agent:
        raise KeyError(f"unknown agent: {agent_id}")
    if not any(t.get("id") == task_id for t in tasks):
        raise KeyError(f"unknown task: {task_id}")

    old_task = agent.get("task_id")
    other = next(
        (a for a in agents if a.get("id") != agent_id and a.get("task_id") == task_id),
        None,
    )
    if old_task == task_id:
        return {
            "agent": agent_id,
            "task_id": task_id,
            "swapped_with": None,
            "unchanged": True,
        }

    agent["task_id"] = task_id
    swapped_with = None
    if other is not None:
        other["task_id"] = old_task
        swapped_with = other.get("id")

    # Sync STATE task owners
    for st in state.get("tasks") or []:
        if not isinstance(st, dict):
            continue
        if st.get("id") == task_id:
            st["owner"] = agent_id
            st["updated_at"] = utc_now()
        elif swapped_with and st.get("id") == old_task:
            st["owner"] = swapped_with
            st["updated_at"] = utc_now()

    # Sync task.owner in spec when present
    for t in tasks:
        if t.get("id") == task_id:
            t["owner"] = agent_id
        elif swapped_with and t.get("id") == old_task:
            t["owner"] = swapped_with

    note = decision or (
        f"Reassign {agent_id}: {old_task} → {task_id}"
        + (f" (swap with {swapped_with})" if swapped_with else "")
    )
    add_decision(state, note)
    return {
        "agent": agent_id,
        "from_task": old_task,
        "task_id": task_id,
        "swapped_with": swapped_with,
        "decision": note,
        "unchanged": False,
    }


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
    from crewlab.process import normalize_process, process_notes

    v = validate_spec(spec)
    prog = task_progress(state)
    done, notes = is_project_complete(spec, state)
    lines = [
        f"crew:   {spec.get('name')}",
        f"goal:   {spec.get('goal')}",
        f"process:{normalize_process(spec)}",
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
        backend = a.get("backend") or a.get("runtime") or "manual"
        lines.append(f"  - {a.get('id')} [{a.get('role')}] backend={backend} → {tid} ({st})")
    for pn in process_notes(spec):
        lines.append(f"  · {pn}" if not pn.startswith("process=") else f"hint:  {pn}")
    open_b = list_blockers(state, open_only=True)
    if open_b:
        lines.append("blockers (open):")
        for b in open_b:
            who = b.get("agent") or b.get("task_id") or "-"
            lines.append(f"  - [{b.get('id')}] {b.get('text')} ({who})")
    if notes:
        lines.append("notes:")
        for n in notes:
            lines.append(f"  - {n}")
    decisions = state.get("decisions") or []
    if decisions:
        lines.append(f"decisions: {len(decisions)}")
        for d in decisions[-3:]:
            if isinstance(d, dict):
                lines.append(f"  - r{d.get('round', '?')}: {d.get('text')}")
    return "\n".join(lines)
