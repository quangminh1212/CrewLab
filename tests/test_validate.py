from crewlab.templates import DEFAULT_SPEC
from crewlab.validate import validate_spec


def test_default_spec_passes():
    r = validate_spec(DEFAULT_SPEC)
    assert r.ok, r.summary()


def test_rejects_two_tasks_same_agent():
    spec = {
        "schema_version": "1.0",
        "name": "bad",
        "goal": "x",
        "agents": [
            {"id": "a", "role": "R", "task_id": "t1"},
            {"id": "b", "role": "R2", "task_id": "t1"},
        ],
        "tasks": [
            {"id": "t1", "title": "one", "owner": "a"},
        ],
        "meetings": {"default_kind": "standup"},
        "definition_of_done": ["done"],
        "stop_conditions": {"max_meetings": 3},
    }
    r = validate_spec(spec)
    assert not r.ok
    assert any("both" in e or "one agent" in e.lower() for e in r.errors)


def test_rejects_task_ids_list_on_agent():
    spec = dict(DEFAULT_SPEC)
    agents = [dict(a) for a in spec["agents"]]
    agents[0] = dict(agents[0], task_ids=["a", "b"])
    spec = {**spec, "agents": agents}
    r = validate_spec(spec)
    assert not r.ok
    assert any("task_ids" in e for e in r.errors)


def test_rejects_single_agent():
    spec = {
        "schema_version": "1.0",
        "name": "solo",
        "goal": "x",
        "agents": [{"id": "only", "role": "R", "task_id": "t1"}],
        "tasks": [{"id": "t1", "title": "t"}],
        "meetings": {"default_kind": "standup"},
        "definition_of_done": ["done"],
        "stop_conditions": {},
    }
    r = validate_spec(spec)
    assert not r.ok
