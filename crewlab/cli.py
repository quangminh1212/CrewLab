"""CrewLab CLI — multi-agent crews: validate, meet, track, attach Hermes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crewlab import __version__
from crewlab.install import attach_to_hermes, default_hermes_home, uninstall_from_hermes
from crewlab.io_util import dump_yaml, load_spec, project_dir_for, resolve_spec_path
from crewlab.meeting import run_meeting
from crewlab.project import (
    add_blocker,
    add_decision,
    is_project_complete,
    list_blockers,
    load_or_init_state,
    reassign_agent_task,
    resolve_blocker,
    save_state,
    set_task_status,
    status_report,
)
from crewlab.templates import write_init_spec, write_project_scaffold
from crewlab.validate import ALLOWED_MEETING_KINDS, validate_spec


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.suffix.lower() in {".yaml", ".yml", ".json"}:
        write_init_spec(path, name=args.name)
        print(f"wrote {path}")
        return 0
    written = write_project_scaffold(path, name=args.name)
    print(f"scaffolded crew project at {path}")
    for p in written:
        print(f"  + {p}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    rc = 0
    for path in args.specs:
        spec = load_spec(path)
        result = validate_spec(spec)
        print(f"== {path} ==")
        print(result.summary())
        if not result.ok:
            rc = 1
    return rc


def _cmd_meeting(args: argparse.Namespace) -> int:
    try:
        spec = load_spec(args.spec)
        out = run_meeting(spec, args.spec, dry_run=args.dry_run, kind=args.kind)
    except Exception as e:
        print(f"FAIL meeting: {e}", file=sys.stderr)
        return 1
    print(out["markdown"])
    print(f"round={out['round']} complete={out['complete']}")
    if out.get("paths"):
        for k, v in out["paths"].items():
            print(f"  {k}: {v}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    project_dir = project_dir_for(args.spec)
    state = load_or_init_state(project_dir, spec)
    print(status_report(spec, state))
    return 0 if validate_spec(spec).ok else 1


def _cmd_task(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    v = validate_spec(spec)
    if not v.ok:
        print(v.summary(), file=sys.stderr)
        return 1
    project_dir = project_dir_for(args.spec)
    state = load_or_init_state(project_dir, spec)

    task_id = args.task
    if args.agent:
        # resolve task from agent id
        for a in spec.get("agents") or []:
            if isinstance(a, dict) and a.get("id") == args.agent:
                task_id = a.get("task_id")
                break
        if not task_id:
            print(f"unknown agent: {args.agent}", file=sys.stderr)
            return 1
    if not task_id:
        print("need --task or --agent", file=sys.stderr)
        return 1
    try:
        set_task_status(state, task_id, args.status, result=args.result)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    complete, notes = is_project_complete(spec, state)
    if complete:
        state["status"] = "complete"
    save_state(project_dir, state)
    print(f"updated task {task_id} → {args.status}")
    if args.result:
        print(f"  result: {args.result}")
    print(f"project complete={complete}")
    for n in notes:
        print(f"  - {n}")
    return 0


def _cmd_assign(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    v = validate_spec(spec)
    print(v.summary())
    print("assignments (one agent → one task):")
    for a in spec.get("agents") or []:
        if not isinstance(a, dict):
            continue
        print(f"  {a.get('id'):12} [{a.get('role')}] → {a.get('task_id')}")
        if a.get("mission"):
            print(f"               mission: {a.get('mission')}")
    return 0 if v.ok else 1


def _cmd_blocker(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    project_dir = project_dir_for(args.spec)
    state = load_or_init_state(project_dir, spec)
    action = args.blocker_cmd
    if action == "list":
        items = list_blockers(state, open_only=args.open)
        if not items:
            print("blockers: (none)")
            return 0
        for b in items:
            flag = "open" if not b.get("resolved") else "resolved"
            print(f"  [{b.get('id')}] ({flag}) {b.get('text')}")
            if b.get("agent") or b.get("task_id"):
                print(f"           agent={b.get('agent')} task={b.get('task_id')}")
        return 0
    if action == "add":
        try:
            item = add_blocker(
                state,
                args.text,
                agent=args.agent,
                task_id=args.task,
            )
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if args.agent and not args.task:
            # auto-mark agent task blocked when raising a blocker
            for a in spec.get("agents") or []:
                if isinstance(a, dict) and a.get("id") == args.agent and a.get("task_id"):
                    try:
                        set_task_status(state, a["task_id"], "blocked", result=args.text)
                    except Exception:
                        pass
                    break
        save_state(project_dir, state)
        print(f"blocker added: {item['id']} — {item['text']}")
        return 0
    if action == "resolve":
        try:
            item = resolve_blocker(state, args.id)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        save_state(project_dir, state)
        print(f"blocker resolved: {item.get('id')}")
        return 0
    print("unknown blocker action", file=sys.stderr)
    return 1


def _cmd_decision(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    project_dir = project_dir_for(args.spec)
    state = load_or_init_state(project_dir, spec)
    action = args.decision_cmd
    if action == "list":
        items = state.get("decisions") or []
        if not items:
            print("decisions: (none)")
            return 0
        for d in items:
            if isinstance(d, dict):
                print(f"  [r{d.get('round', '?')}] {d.get('at')}: {d.get('text')}")
            else:
                print(f"  - {d}")
        return 0
    if action == "add":
        try:
            item = add_decision(state, args.text, round_no=args.round)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        save_state(project_dir, state)
        print(f"decision recorded: {item['text']}")
        return 0
    print("unknown decision action", file=sys.stderr)
    return 1


def _cmd_reassign(args: argparse.Namespace) -> int:
    """Formal reassignment (one agent → one task); updates crew-spec + STATE."""
    spec_path = resolve_spec_path(args.spec)
    spec = load_spec(spec_path)
    v = validate_spec(spec)
    if not v.ok:
        print(v.summary(), file=sys.stderr)
        return 1
    project_dir = project_dir_for(spec_path)
    state = load_or_init_state(project_dir, spec)
    try:
        result = reassign_agent_task(
            spec,
            state,
            agent_id=args.agent,
            task_id=args.task,
            decision=args.decision,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    # Persist updated crew-spec (agent.task_id may have swapped)
    dump_yaml(spec_path, spec)
    v2 = validate_spec(spec)
    if not v2.ok:
        print(v2.summary(), file=sys.stderr)
        return 1
    save_state(project_dir, state)
    if result.get("unchanged"):
        print(f"unchanged: {result['agent']} already owns {result['task_id']}")
        return 0
    print(
        f"reassigned {result['agent']}: {result.get('from_task')} → {result['task_id']}"
        + (f" (swapped with {result['swapped_with']})" if result.get("swapped_with") else "")
    )
    print(f"  decision: {result.get('decision')}")
    print(f"  wrote: {spec_path}")
    return 0


def _cmd_attach(args: argparse.Namespace) -> int:
    home = Path(args.hermes_home) if args.hermes_home else default_hermes_home()
    try:
        linked = attach_to_hermes(home)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"attached to {home}")
    for p in linked:
        print(f"  + {p}")
    print("In Hermes chat: /crewlab")
    return 0


def _cmd_detach(args: argparse.Namespace) -> int:
    home = Path(args.hermes_home) if args.hermes_home else default_hermes_home()
    try:
        removed = uninstall_from_hermes(home)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"detached from {home}")
    for p in removed:
        print(f"  - {p}")
    return 0


def _cmd_smoke(args: argparse.Namespace) -> int:
    """End-to-end: init temp crew, validate, task updates, meeting, complete."""
    import shutil
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="crewlab-smoke-"))
    try:
        write_project_scaffold(root, name="smoke-crew")
        spec_path = root / "crew-spec.yaml"
        spec = load_spec(spec_path)
        v = validate_spec(spec)
        print(v.summary())
        if not v.ok:
            return 1
        # mark all done
        state = load_or_init_state(root, spec)
        for t in state["tasks"]:
            set_task_status(state, t["id"], "done", result="smoke ok")
        save_state(root, state)
        out = run_meeting(spec, spec_path)
        print(f"meeting round={out['round']} complete={out['complete']}")
        if not out["complete"]:
            print("FAIL: expected complete after all tasks done", file=sys.stderr)
            return 1
        print("smoke: PASS")
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)
        else:
            print(f"kept: {root}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crewlab",
        description="CrewLab — multi-agent crews (one agent, one task; meet and ship)",
    )
    p.add_argument("--version", action="version", version=f"crewlab {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Scaffold crew-spec or project folder")
    s.add_argument("path", help="file.yaml or project directory")
    s.add_argument("--name", default=None)
    s.set_defaults(func=_cmd_init)

    s = sub.add_parser("validate", help="Validate crew-spec (one agent one task)")
    s.add_argument("specs", nargs="+")
    s.set_defaults(func=_cmd_validate)

    s = sub.add_parser("assign", help="Show agent→task assignments")
    s.add_argument("spec")
    s.set_defaults(func=_cmd_assign)

    s = sub.add_parser("meeting", help="Run one crew meeting round")
    s.add_argument("spec")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument(
        "--kind",
        default=None,
        choices=sorted(ALLOWED_MEETING_KINDS),
        help="Override meetings.default_kind for this round",
    )
    s.set_defaults(func=_cmd_meeting)

    s = sub.add_parser("status", help="Project + task status")
    s.add_argument("spec")
    s.set_defaults(func=_cmd_status)

    s = sub.add_parser("task", help="Update a task status (by --task or --agent)")
    s.add_argument("spec")
    s.add_argument("--task", default=None)
    s.add_argument("--agent", default=None)
    s.add_argument(
        "--status",
        required=True,
        choices=["todo", "in_progress", "blocked", "done", "skipped"],
    )
    s.add_argument("--result", default=None)
    s.set_defaults(func=_cmd_task)

    s = sub.add_parser("blocker", help="Add / resolve / list open blockers")
    bs = s.add_subparsers(dest="blocker_cmd", required=True)
    ba = bs.add_parser("add", help="Add open blocker")
    ba.add_argument("spec")
    ba.add_argument("text", help="Blocker description")
    ba.add_argument("--agent", default=None)
    ba.add_argument("--task", default=None)
    ba.set_defaults(func=_cmd_blocker)
    br = bs.add_parser("resolve", help="Resolve blocker by id")
    br.add_argument("spec")
    br.add_argument("id", help="Blocker id (e.g. b1)")
    br.set_defaults(func=_cmd_blocker)
    bl = bs.add_parser("list", help="List blockers")
    bl.add_argument("spec")
    bl.add_argument("--open", action="store_true", help="Only open blockers")
    bl.set_defaults(func=_cmd_blocker)

    s = sub.add_parser("decision", help="Record / list formal meeting decisions")
    ds = s.add_subparsers(dest="decision_cmd", required=True)
    da = ds.add_parser("add", help="Record decision text")
    da.add_argument("spec")
    da.add_argument("text")
    da.add_argument("--round", type=int, default=None)
    da.set_defaults(func=_cmd_decision)
    dl = ds.add_parser("list", help="List decisions")
    dl.add_argument("spec")
    dl.set_defaults(func=_cmd_decision)

    s = sub.add_parser(
        "reassign",
        help="Reassign agent→task (swap if needed); records decision + writes crew-spec",
    )
    s.add_argument("spec")
    s.add_argument("--agent", required=True, help="Agent id receiving the task")
    s.add_argument("--task", required=True, help="Task id to own")
    s.add_argument("--decision", default=None, help="Optional decision note")
    s.set_defaults(func=_cmd_reassign)

    s = sub.add_parser("attach", help="Junction skill into Hermes")
    s.add_argument("--hermes-home", default=None)
    s.set_defaults(func=_cmd_attach)

    s = sub.add_parser("detach", help="Remove Hermes skill junction")
    s.add_argument("--hermes-home", default=None)
    s.set_defaults(func=_cmd_detach)

    s = sub.add_parser("smoke", help="Self-test scaffold + meeting + complete")
    s.add_argument("--keep", action="store_true", help="Keep temp project dir")
    s.set_defaults(func=_cmd_smoke)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
