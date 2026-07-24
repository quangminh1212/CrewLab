"""Blocker / decision / reassign feature tests."""

from pathlib import Path

from crewlab.cli import main


def test_blocker_blocks_and_resolves_complete(tmp_path: Path):
    proj = tmp_path / "crew"
    assert main(["init", str(proj), "--name", "bcrew"]) == 0
    assert main(["blocker", "add", str(proj), "waiting on API key", "--agent", "builder"]) == 0
    assert main(["blocker", "list", str(proj), "--open"]) == 0
    # mark all tasks done but open blocker → not complete
    for agent in ("lead", "builder", "reviewer", "integrator"):
        assert (
            main(
                [
                    "task",
                    str(proj),
                    "--agent",
                    agent,
                    "--status",
                    "done",
                    "--result",
                    "ok",
                ]
            )
            == 0
        )
    # status should mention open blocker / complete=False via smoke of meeting
    assert main(["status", str(proj)]) == 0
    from crewlab.io_util import load_spec
    from crewlab.project import is_project_complete, load_or_init_state

    spec = load_spec(proj)
    state = load_or_init_state(proj, spec)
    done, notes = is_project_complete(spec, state)
    assert done is False
    assert any("blocker" in n for n in notes)
    assert main(["blocker", "resolve", str(proj), "b1"]) == 0
    state = load_or_init_state(proj, spec)
    done, _ = is_project_complete(spec, state)
    assert done is True


def test_reassign_swaps_and_decision(tmp_path: Path):
    proj = tmp_path / "crew2"
    assert main(["init", str(proj), "--name", "rcrew"]) == 0
    assert (
        main(
            [
                "reassign",
                str(proj),
                "--agent",
                "builder",
                "--task",
                "review-and-test",
                "--decision",
                "swap builder/reviewer after meeting",
            ]
        )
        == 0
    )
    assert main(["assign", str(proj)]) == 0
    assert main(["decision", "list", str(proj)]) == 0
    from crewlab.io_util import load_spec

    spec = load_spec(proj)
    by_id = {a["id"]: a["task_id"] for a in spec["agents"]}
    assert by_id["builder"] == "review-and-test"
    assert by_id["reviewer"] == "implement-core"
    assert main(["validate", str(proj)]) == 0


def test_meeting_kind_override(tmp_path: Path):
    proj = tmp_path / "crew3"
    assert main(["init", str(proj), "--name", "kcrew"]) == 0
    assert main(["meeting", str(proj), "--kind", "kickoff", "--dry-run"]) == 0
