from pathlib import Path

from crewlab.meeting import run_meeting
from crewlab.project import load_or_init_state, save_state, set_task_status
from crewlab.templates import DEFAULT_SPEC


def test_meeting_marks_complete(tmp_path: Path):
    spec = dict(DEFAULT_SPEC)
    spec["name"] = "meet-test"
    spec_path = tmp_path / "crew-spec.yaml"
    # state lives beside spec
    import yaml

    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    state = load_or_init_state(tmp_path, spec)
    for t in state["tasks"]:
        set_task_status(state, t["id"], "done", result="ok")
    save_state(tmp_path, state)
    out = run_meeting(spec, spec_path)
    assert out["complete"] is True
    assert out["round"] == 1
    assert (tmp_path / "MEETING_LOG.md").exists()
    assert (tmp_path / "STATE.yaml").exists()


def test_dry_run_no_files(tmp_path: Path):
    spec = dict(DEFAULT_SPEC)
    spec_path = tmp_path / "crew-spec.yaml"
    import yaml

    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    out = run_meeting(spec, spec_path, dry_run=True)
    assert out.get("dry_run") is True
    assert not (tmp_path / "MEETING_LOG.md").exists()
