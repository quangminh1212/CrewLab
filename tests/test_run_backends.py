from pathlib import Path

from crewlab.backends import invoke_backend, resolve_agent_backend
from crewlab.chat import append_message, load_messages
from crewlab.cli import main
from crewlab.features import FEATURE_MATRIX, format_features
from crewlab.io_util import dump_yaml, load_spec
from crewlab.process import dependency_order
from crewlab.run import build_plan, kickoff, ready_tasks
from crewlab.project import load_or_init_state
from crewlab.validate import validate_spec


def test_feature_matrix_nonempty():
    assert len(FEATURE_MATRIX) >= 20
    text = format_features(source="crewai")
    assert "kickoff" in text.lower() or "Kickoff" in text or "sequential" in text


def test_backend_resolve_manual():
    r = resolve_agent_backend({"id": "a", "backend": "manual"})
    assert r.backend_id == "manual"
    assert r.available


def test_invoke_dry_run(tmp_path: Path):
    res = invoke_backend(
        {"id": "x", "backend": "dry-run"},
        prompt="hello",
        work_dir=tmp_path / "w",
        task_id="t1",
        goal="g",
        dry_run=True,
    )
    assert res.ok
    assert res.mode == "dry-run"
    assert Path(res.prompt_file).is_file()


def test_chat_pool(tmp_path: Path):
    append_message(tmp_path, agent="lead", role="Lead", text="hi", kind="message")
    msgs = load_messages(tmp_path)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "hi"


def test_kickoff_dry_run_sequential(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    src = root / "examples" / "crewai-sequential" / "crew-spec.yaml"
    proj = tmp_path / "seq"
    proj.mkdir()
    spec = load_spec(src)
    for a in spec["agents"]:
        a["backend"] = "dry-run"
    dump_yaml(proj / "crew-spec.yaml", spec)
    assert validate_spec(spec).ok
    out = kickoff(spec, proj / "crew-spec.yaml", dry_run=True, max_steps=10, with_meeting=False)
    assert out["step_count"] >= 3
    assert out["complete"] is True


def test_ready_tasks_respects_deps(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    spec = load_spec(root / "examples" / "crewai-sequential" / "crew-spec.yaml")
    state = load_or_init_state(tmp_path, spec)
    ready = ready_tasks(spec, state)
    assert ready == ["gather-facts"]
    order = dependency_order(spec)
    assert order[0] == "gather-facts"
    assert order[-1] == "polish"


def test_cli_features_backends_plan(tmp_path: Path):
    assert main(["features"]) == 0
    assert main(["backends", "--no-probe"]) == 0
    root = Path(__file__).resolve().parents[1]
    ex = root / "examples" / "multi-cli-room" / "crew-spec.yaml"
    # plan needs writable project dir — copy
    proj = tmp_path / "room"
    proj.mkdir()
    dump_yaml(proj / "crew-spec.yaml", load_spec(ex))
    assert main(["plan", str(proj)]) == 0
    assert main(["run", str(proj), "--dry-run", "--no-meeting"]) == 0
    assert main(["chat", str(proj), "hello room", "--agent", "lead"]) == 0
    assert main(["chat", str(proj), "--list"]) == 0


def test_multi_cli_example_validates():
    root = Path(__file__).resolve().parents[1]
    spec = load_spec(root / "examples" / "multi-cli-room" / "crew-spec.yaml")
    r = validate_spec(spec)
    assert r.ok, r.summary()


def test_plan_writes_file(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    spec = load_spec(root / "examples" / "ship-feature" / "crew-spec.yaml")
    state = load_or_init_state(tmp_path, spec)
    text = build_plan(spec, state, tmp_path)
    assert "Plan" in text
    assert (tmp_path / "PLAN.md").is_file()


def test_sequential_gate_on_task_status(tmp_path: Path):
    from crewlab.project import set_task_status

    root = Path(__file__).resolve().parents[1]
    spec = load_spec(root / "examples" / "crewai-sequential" / "crew-spec.yaml")
    state = load_or_init_state(tmp_path, spec)
    try:
        set_task_status(
            state, "draft", "in_progress", spec=spec, enforce_deps=True
        )
        raised = False
    except RuntimeError as e:
        raised = True
        assert "sequential gate" in str(e)
    assert raised
    set_task_status(state, "gather-facts", "done", result="ok", spec=spec, enforce_deps=True)
    set_task_status(state, "draft", "in_progress", spec=spec, enforce_deps=True)


def test_argv_builders_exist():
    from crewlab.backends import ARGV_BUILDERS

    for name in ("hermes", "grok", "codex", "claude", "openclaw"):
        assert name in ARGV_BUILDERS
