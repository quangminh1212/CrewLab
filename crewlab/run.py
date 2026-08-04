"""Kickoff / plan / sequential|hierarchical|collaborative execution.

Maps CrewAI Crew.kickoff + planning + process models onto CrewLab state machine
and multi-CLI backends.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crewlab.backends import invoke_backend, resolve_agent_backend
from crewlab.chat import append_message, context_blob
from crewlab.meeting import run_meeting
from crewlab.process import normalize_process
from crewlab.project import (
    is_project_complete,
    load_or_init_state,
    save_state,
    set_task_status,
    utc_now,
)
from crewlab.validate import validate_spec


def memory_path(project_dir: Path) -> Path:
    return project_dir / "MEMORY.md"


def run_log_path(project_dir: Path) -> Path:
    return project_dir / "RUN_LOG.md"


def _agent_for_task(spec: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for a in spec.get("agents") or []:
        if isinstance(a, dict) and a.get("task_id") == task_id:
            return a
    return None


def _task_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for t in spec.get("tasks") or []:
        if isinstance(t, dict) and t.get("id"):
            out[str(t["id"])] = t
    return out


def _state_status(state: dict[str, Any], task_id: str) -> str:
    for t in state.get("tasks") or []:
        if t.get("id") == task_id:
            return str(t.get("status") or "todo")
    return "todo"


def _deps_satisfied(spec: dict[str, Any], state: dict[str, Any], task_id: str) -> bool:
    tmap = _task_map(spec)
    t = tmap.get(task_id) or {}
    deps = t.get("depends_on") or []
    if not isinstance(deps, list):
        return True
    for d in deps:
        st = _state_status(state, str(d))
        if st not in {"done", "skipped"}:
            return False
    return True


def ready_tasks(spec: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Tasks that can run now given process model + depends_on + status."""
    proc = normalize_process(spec)
    pending = []
    for t in state.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        if not tid:
            continue
        if t.get("status") in {"done", "skipped"}:
            continue
        if t.get("status") == "blocked":
            continue
        if proc in {"sequential", "hierarchical", "collaborative"}:
            if not _deps_satisfied(spec, state, str(tid)):
                continue
        pending.append(str(tid))

    if proc == "sequential":
        # stable order by tasks[] declaration
        order = [str(t.get("id")) for t in (spec.get("tasks") or []) if isinstance(t, dict)]
        pending.sort(key=lambda x: order.index(x) if x in order else 999)
        return pending[:1] if pending else []

    if proc == "hierarchical":
        # manager (first agent or manager:true) plans first if its task open
        manager = _manager_agent(spec)
        if manager and manager.get("task_id") in pending:
            return [str(manager["task_id"])]
        return pending

    return pending


def _manager_agent(spec: dict[str, Any]) -> dict[str, Any] | None:
    agents = [a for a in (spec.get("agents") or []) if isinstance(a, dict)]
    for a in agents:
        if a.get("manager") is True or str(a.get("role") or "").lower() in {
            "crew lead",
            "manager",
            "lead",
            "pm",
            "ceo",
        }:
            return a
        if a.get("id") in {"lead", "manager", "pm", "ceo"}:
            return a
    return agents[0] if agents else None


def load_memory(project_dir: Path) -> str:
    p = memory_path(project_dir)
    if p.is_file():
        return p.read_text(encoding="utf-8")[:4000]
    return ""


def append_run_log(project_dir: Path, text: str) -> None:
    path = run_log_path(project_dir)
    if not path.exists():
        path.write_text("# CrewLab Run Log\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n\n")


def build_task_prompt(
    spec: dict[str, Any],
    state: dict[str, Any],
    *,
    agent: dict[str, Any],
    task: dict[str, Any],
    project_dir: Path,
    plan_text: str | None = None,
) -> str:
    goal = str(spec.get("goal") or "")
    tid = str(task.get("id"))
    prior_results = []
    for st in state.get("tasks") or []:
        if st.get("status") in {"done", "skipped"} and st.get("result"):
            prior_results.append(f"- {st.get('id')}: {st.get('result')}")
    knowledge = []
    for kp in spec.get("knowledge_paths") or agent.get("knowledge_paths") or []:
        knowledge.append(str(kp))
    expected = task.get("expected_output") or "Concise deliverable + acceptance notes."
    lines = [
        f"# CrewLab task assignment",
        f"",
        f"**Crew:** {spec.get('name')}",
        f"**Goal:** {goal}",
        f"**Process:** {normalize_process(spec)}",
        f"**Agent:** {agent.get('id')} — {agent.get('role')}",
        f"**Mission:** {agent.get('mission') or ''}",
        f"**Your ONLY task:** `{tid}` — {task.get('title') or task.get('description')}",
        f"",
        f"## Task description",
        str(task.get("description") or task.get("title") or ""),
        f"",
        f"## Expected output",
        str(expected),
        f"",
        f"## Rules",
        f"- One agent = one task. Do not work other agents' tasks.",
        f"- Report blockers clearly; do not silently reassign.",
        f"- Write final result to CREWLAB_RESULT_FILE when set.",
        f"",
        f"## Prior task results",
        "\n".join(prior_results) if prior_results else "(none)",
        f"",
        f"## Shared chat context (FULL transcript — read every message)",
        context_blob(project_dir, limit=None),
        f"",
        f"## Memory / lessons",
        load_memory(project_dir) or "(empty)",
    ]
    if plan_text:
        lines.extend(["", "## Plan", plan_text[:3000]])
    if knowledge:
        lines.extend(["", "## Knowledge paths", "\n".join(f"- {k}" for k in knowledge)])
    tools = agent.get("tools") or task.get("tools") or []
    if tools:
        lines.extend(["", "## Tools (advisory)", ", ".join(str(t) for t in tools)])
    return "\n".join(lines)


def build_plan(
    spec: dict[str, Any],
    state: dict[str, Any],
    project_dir: Path,
) -> str:
    """Planning phase (CrewAI planning analogue) — structured, no LLM required."""
    proc = normalize_process(spec)
    ready = ready_tasks(spec, state)
    lines = [
        f"# Plan — {spec.get('name')} ({utc_now()})",
        f"Goal: {spec.get('goal')}",
        f"Process: {proc}",
        "",
        "## Agent roster",
    ]
    for a in spec.get("agents") or []:
        if not isinstance(a, dict):
            continue
        br = resolve_agent_backend(a)
        lines.append(
            f"- {a.get('id')} [{a.get('role')}] task={a.get('task_id')} "
            f"backend={br.backend_id} available={br.available}"
        )
    lines.append("")
    lines.append("## Task graph")
    for t in spec.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        st = _state_status(state, str(tid))
        deps = t.get("depends_on") or []
        flag = "READY" if tid in ready else st.upper()
        lines.append(f"- [{flag}] {tid} deps={deps} status={st}")
    lines.append("")
    lines.append("## Next execution order")
    if not ready:
        lines.append("- (none — blocked or complete)")
    else:
        for tid in ready:
            agent = _agent_for_task(spec, tid)
            lines.append(f"1. {tid} → agent={agent.get('id') if agent else '?'}")
    lines.append("")
    lines.append("## Definition of done")
    for d in spec.get("definition_of_done") or []:
        lines.append(f"- {d}")
    text = "\n".join(lines)
    plan_file = project_dir / "PLAN.md"
    plan_file.write_text(text, encoding="utf-8")
    append_message(
        project_dir,
        agent="system",
        role="Planner",
        text=f"Plan written ({proc}); ready={ready}",
        kind="plan",
    )
    return text


def run_one_task(
    spec: dict[str, Any],
    state: dict[str, Any],
    *,
    project_dir: Path,
    task_id: str,
    dry_run: bool = False,
    timeout: int = 600,
    auto_complete: bool = True,
    plan_text: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    agent = _agent_for_task(spec, task_id)
    if not agent:
        raise KeyError(f"no agent owns task: {task_id}")
    tmap = _task_map(spec)
    task = tmap.get(task_id)
    if not task:
        raise KeyError(f"unknown task: {task_id}")
    if not _deps_satisfied(spec, state, task_id):
        raise RuntimeError(f"dependencies not satisfied for {task_id}")

    work = project_dir / "runs" / task_id
    prompt = build_task_prompt(
        spec, state, agent=agent, task=task, project_dir=project_dir, plan_text=plan_text
    )
    set_task_status(state, task_id, "in_progress", result=None)
    save_state(project_dir, state)

    result = invoke_backend(
        agent,
        prompt=prompt,
        work_dir=work,
        task_id=task_id,
        goal=str(spec.get("goal") or ""),
        timeout=timeout,
        dry_run=dry_run,
    )

    summary = result.stdout[:500] if result.stdout else (result.error or result.mode)
    if result.result_file and Path(result.result_file).is_file():
        body = Path(result.result_file).read_text(encoding="utf-8", errors="replace")
        if body and not body.startswith("# Awaiting"):
            summary = body[:1500]

    append_message(
        project_dir,
        agent=str(agent.get("id")),
        role=str(agent.get("role") or ""),
        text=summary[:2000],
        task_id=task_id,
        kind="task_result" if result.ok else "task_error",
    )
    append_run_log(
        project_dir,
        f"## {utc_now()} task={task_id} agent={agent.get('id')} "
        f"backend={result.backend} mode={result.mode} ok={result.ok}\n"
        f"prompt: {result.prompt_file}\nresult: {result.result_file}\n"
        f"{summary[:800]}",
    )

    if auto_complete and result.ok and result.mode in {"executed", "dry-run"}:
        set_task_status(state, task_id, "done", result=summary[:1000])
    elif auto_complete and result.ok and result.mode == "prompt_only":
        # leave in_progress for human/CLI completion
        set_task_status(state, task_id, "in_progress", result=f"prompt_only: {result.prompt_file}")
    elif not result.ok:
        set_task_status(state, task_id, "blocked", result=result.error or "run failed")

    complete, notes = is_project_complete(spec, state)
    if complete:
        state["status"] = "complete"
    save_state(project_dir, state)

    out = {
        "task_id": task_id,
        "agent": agent.get("id"),
        "ok": result.ok,
        "mode": result.mode,
        "backend": result.backend,
        "exit_code": result.exit_code,
        "prompt_file": result.prompt_file,
        "result_file": result.result_file,
        "command": result.command,
        "error": result.error,
        "summary": summary[:500],
        "project_complete": complete,
        "notes": notes,
    }
    if verbose:
        out["stdout"] = result.stdout
        out["stderr"] = result.stderr
    return out


def kickoff(
    spec: dict[str, Any],
    spec_path: str | Path,
    *,
    dry_run: bool = False,
    max_steps: int | None = None,
    timeout: int = 600,
    auto_complete: bool = True,
    with_meeting: bool = True,
    with_plan: bool = True,
    step: bool = False,
    agent_filter: str | None = None,
    task_filter: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run crew until complete, max_steps, or step mode (one ready task)."""
    v = validate_spec(spec)
    if not v.ok:
        raise ValueError("invalid crew-spec:\n" + v.summary())

    from crewlab.io_util import project_dir_for

    project_dir = project_dir_for(spec_path)
    state = load_or_init_state(project_dir, spec)
    plan_text = None
    if with_plan or normalize_process(spec) == "hierarchical":
        plan_text = build_plan(spec, state, project_dir)

    stop = spec.get("stop_conditions") or {}
    if max_steps is None:
        max_steps = int(stop.get("max_kickoff_steps") or stop.get("max_meetings") or 20)

    steps: list[dict[str, Any]] = []
    for i in range(max_steps):
        complete, _ = is_project_complete(spec, state)
        if complete:
            break
        ready = ready_tasks(spec, state)
        if task_filter:
            ready = [t for t in ready if t == task_filter]
        if agent_filter:
            ready = [
                t
                for t in ready
                if (_agent_for_task(spec, t) or {}).get("id") == agent_filter
            ]
        if not ready:
            break
        tid = ready[0]
        step_out = run_one_task(
            spec,
            state,
            project_dir=project_dir,
            task_id=tid,
            dry_run=dry_run,
            timeout=timeout,
            auto_complete=auto_complete,
            plan_text=plan_text,
            verbose=verbose,
        )
        # fix auto_complete: for prompt_only keep in_progress (already handled in run_one_task)
        steps.append(step_out)
        if step:
            break
        # refresh state from disk in case external edits
        state = load_or_init_state(project_dir, spec)
        if with_meeting and (i % 2 == 1 or step_out.get("mode") == "prompt_only"):
            try:
                run_meeting(spec, spec_path, dry_run=False)
                state = load_or_init_state(project_dir, spec)
            except Exception:
                pass

    complete, notes = is_project_complete(spec, state)
    if complete:
        state["status"] = "complete"
        save_state(project_dir, state)
        if with_meeting:
            try:
                run_meeting(spec, spec_path, kind="closeout")
            except Exception:
                pass

    return {
        "crew": spec.get("name"),
        "process": normalize_process(spec),
        "steps": steps,
        "step_count": len(steps),
        "complete": complete,
        "notes": notes,
        "plan": plan_text,
        "project_dir": str(project_dir),
    }
