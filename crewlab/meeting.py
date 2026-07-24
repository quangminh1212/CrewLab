"""Run a crew meeting round: agenda → reports → decisions → next actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crewlab.io_util import dump_json, project_dir_for
from crewlab.project import (
    is_project_complete,
    load_or_init_state,
    meeting_log_path,
    save_state,
    task_progress,
    utc_now,
)
from crewlab.validate import validate_spec

DEFAULT_PHASES = [
    "open",
    "status_reports",
    "blockers",
    "sync_decisions",
    "next_actions",
    "close",
]


def _agent_by_task(spec: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for a in spec.get("agents") or []:
        if isinstance(a, dict) and a.get("task_id") == task_id:
            return a
    return None


def build_agenda(spec: dict[str, Any], state: dict[str, Any], round_no: int) -> dict[str, Any]:
    meetings = spec.get("meetings") or {}
    phases = meetings.get("phases") or DEFAULT_PHASES
    kind = meetings.get("default_kind") or "standup"
    reports = []
    for t in state.get("tasks") or []:
        agent = _agent_by_task(spec, t.get("id"))
        reports.append(
            {
                "agent": (agent or {}).get("id"),
                "role": (agent or {}).get("role"),
                "task_id": t.get("id"),
                "status": t.get("status"),
                "result": t.get("result"),
                "speak": (
                    f"[{(agent or {}).get('id')}] task={t.get('id')} status={t.get('status')}: "
                    f"report progress on single owned task only."
                ),
            }
        )
    next_actions = []
    for t in state.get("tasks") or []:
        if t.get("status") in {"done", "skipped"}:
            continue
        agent = _agent_by_task(spec, t.get("id"))
        next_actions.append(
            {
                "agent": (agent or {}).get("id"),
                "task_id": t.get("id"),
                "action": f"Continue/complete only task '{t.get('id')}' (no scope creep)",
            }
        )
    return {
        "crew": spec.get("name"),
        "goal": spec.get("goal"),
        "kind": kind,
        "round": round_no,
        "at": utc_now(),
        "phases": phases,
        "status_reports": reports,
        "blockers": state.get("blockers") or [],
        "next_actions": next_actions,
        "definition_of_done": spec.get("definition_of_done") or [],
        "rule": "ONE AGENT = ONE TASK. No agent may pick up another's task without a formal reassignment in a meeting decision.",
    }


def render_meeting_md(agenda: dict[str, Any], complete: bool, notes: list[str]) -> str:
    lines = [
        f"## Meeting round {agenda.get('round')} — {agenda.get('kind')} ({agenda.get('at')})",
        "",
        f"**Crew:** {agenda.get('crew')}",
        f"**Goal:** {agenda.get('goal')}",
        f"**Rule:** {agenda.get('rule')}",
        "",
        "### Phases",
    ]
    for p in agenda.get("phases") or []:
        lines.append(f"- {p}")
    lines.append("")
    lines.append("### Status reports (one task each)")
    for r in agenda.get("status_reports") or []:
        lines.append(
            f"- **{r.get('agent')}** ({r.get('role')}): `{r.get('task_id')}` → `{r.get('status')}`"
        )
        if r.get("result"):
            lines.append(f"  - result: {r.get('result')}")
    lines.append("")
    lines.append("### Blockers")
    blockers = agenda.get("blockers") or []
    if not blockers:
        lines.append("- (none)")
    else:
        for b in blockers:
            if isinstance(b, dict):
                lines.append(f"- {b.get('text', b)}")
            else:
                lines.append(f"- {b}")
    lines.append("")
    lines.append("### Next actions")
    for a in agenda.get("next_actions") or []:
        lines.append(f"- **{a.get('agent')}**: {a.get('action')}")
    if not agenda.get("next_actions"):
        lines.append("- (none — all tasks done/skipped)")
    lines.append("")
    lines.append("### Definition of done")
    for d in agenda.get("definition_of_done") or []:
        lines.append(f"- {d}")
    lines.append("")
    lines.append(f"### Project complete: **{complete}**")
    for n in notes:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def append_meeting_log(project_dir: Path, md: str) -> Path:
    path = meeting_log_path(project_dir)
    header = "# CrewLab Meeting Log\n\n" if not path.exists() else ""
    with path.open("a", encoding="utf-8") as f:
        f.write(header)
        f.write(md)
        f.write("\n")
    return path


def run_meeting(
    spec: dict[str, Any],
    spec_path: str | Path,
    *,
    dry_run: bool = False,
    kind: str | None = None,
) -> dict[str, Any]:
    """Execute one meeting round. Returns agenda + paths written."""
    result = validate_spec(spec)
    if not result.ok:
        raise ValueError("invalid crew-spec:\n" + result.summary())

    project_dir = project_dir_for(spec_path)
    state = load_or_init_state(project_dir, spec)
    round_no = int(state.get("meeting_round") or 0) + 1
    stop = spec.get("stop_conditions") or {}
    max_m = stop.get("max_meetings")
    if max_m is not None and round_no > int(max_m):
        raise RuntimeError(f"max_meetings={max_m} exceeded (next would be {round_no})")

    agenda = build_agenda(spec, state, round_no)
    if kind:
        from crewlab.validate import ALLOWED_MEETING_KINDS

        k = kind.strip().lower()
        if k not in ALLOWED_MEETING_KINDS:
            raise ValueError(f"invalid meeting kind: {kind} (allowed: {sorted(ALLOWED_MEETING_KINDS)})")
        agenda["kind"] = k
    complete, notes = is_project_complete(spec, state)
    md = render_meeting_md(agenda, complete, notes)

    out: dict[str, Any] = {
        "round": round_no,
        "complete": complete,
        "notes": notes,
        "progress": task_progress(state),
        "agenda": agenda,
        "markdown": md,
    }

    if dry_run:
        out["dry_run"] = True
        return out

    state["meeting_round"] = round_no
    if complete:
        state["status"] = "complete"
    # record lightweight decision when complete
    if complete:
        state.setdefault("decisions", []).append(
            {"at": utc_now(), "text": "Project complete after meeting", "round": round_no}
        )
    state_path = save_state(project_dir, state)
    log_path = append_meeting_log(project_dir, md)
    run_dir = Path(spec_path).resolve().parents[0]
    # also write last agenda json under project or runs/
    last_json = project_dir / "last-meeting.json"
    dump_json(last_json, {k: v for k, v in out.items() if k != "markdown"})
    out["paths"] = {
        "state": str(state_path),
        "meeting_log": str(log_path),
        "last_meeting": str(last_json),
        "project_dir": str(project_dir),
    }
    # silence unused
    _ = run_dir
    return out
