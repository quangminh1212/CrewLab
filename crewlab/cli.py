"""CrewLab CLI — multi-agent crews: validate, meet, track, attach Hermes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crewlab import __version__
from crewlab.install import attach_to_hermes, default_hermes_home, uninstall_from_hermes
from crewlab.io_util import load_spec, project_dir_for
from crewlab.meeting import run_meeting
from crewlab.project import (
    is_project_complete,
    load_or_init_state,
    save_state,
    set_task_status,
    status_report,
)
from crewlab.templates import write_init_spec, write_project_scaffold
from crewlab.validate import validate_spec


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
        out = run_meeting(spec, args.spec, dry_run=args.dry_run)
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
