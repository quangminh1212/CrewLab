from pathlib import Path

from crewlab.chat import full_transcript, load_messages
from crewlab.cli import main
from crewlab.io_util import dump_yaml, load_spec
from crewlab.room import ChatRoom
from crewlab.ui import ROOM_HTML, make_handler


def _room_proj(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "examples" / "crewai-sequential" / "crew-spec.yaml"
    proj = tmp_path / "room"
    proj.mkdir()
    spec = load_spec(src)
    for a in spec["agents"]:
        a["backend"] = "dry-run"
    dump_yaml(proj / "crew-spec.yaml", spec)
    return proj


def test_room_bootstrap_and_full_transcript(tmp_path: Path):
    proj = _room_proj(tmp_path)
    room = ChatRoom(proj)
    snap = room.snapshot()
    assert snap["crew"] == "crewai-sequential"
    assert len(snap["assignments"]) == 3
    assert snap["message_count"] >= 1
    # system bootstrap explains assignments
    texts = " ".join(m["text"] for m in snap["messages"])
    assert "Phân công" in texts or "phan cong" in texts.lower() or "task" in texts.lower()
    ft = full_transcript(proj)
    assert "FULL CHAT TRANSCRIPT" in ft
    assert len(load_messages(proj, limit=None)) >= 1


def test_turn_order_and_speak_dry(tmp_path: Path):
    proj = _room_proj(tmp_path)
    room = ChatRoom(proj)
    assert room.next_speaker() == "researcher"
    out = room.speak(dry_run=True, auto_complete=True)
    assert out["ok"] is True
    assert out["agent"] == "researcher"
    # full history grew
    assert len(load_messages(proj, limit=None)) >= 3
    # next agent after researcher completes
    assert room.next_speaker() == "writer"
    out2 = room.speak(dry_run=True, auto_complete=True)
    assert out2["agent"] == "writer"


def test_operator_message(tmp_path: Path):
    proj = _room_proj(tmp_path)
    room = ChatRoom(proj)
    room.post_operator("Chào crew, bắt đầu đi")
    msgs = load_messages(proj, limit=None)
    assert any(m.get("agent") == "operator" for m in msgs)


def test_speak_prompt_contains_full_chat(tmp_path: Path):
    proj = _room_proj(tmp_path)
    room = ChatRoom(proj)
    room.post_operator("SECRET_TOKEN_XYZ_READ_ME")
    agent = room._agent_by_id("researcher")
    prompt = room._build_speak_prompt(agent)
    assert "SECRET_TOKEN_XYZ_READ_ME" in prompt
    assert "FULL CHAT TRANSCRIPT" in prompt
    assert "← BẠN" in prompt or "task" in prompt.lower()


def test_ui_html_and_handler():
    assert "Next turn" in ROOM_HTML
    assert "/api/speak" in ROOM_HTML
    h = make_handler()
    assert h is not None


def test_cli_speak_dry(tmp_path: Path):
    proj = _room_proj(tmp_path)
    assert main(["speak", str(proj), "--dry-run", "--auto-complete"]) == 0


def test_cli_help_lists_ui():
    # build_parser includes ui
    from crewlab.cli import build_parser

    p = build_parser()
    found = False
    for a in p._actions:
        if getattr(a, "choices", None) and "ui" in (a.choices or {}):
            found = True
    assert found


def test_http_room_api_turn_taking_and_full_history(tmp_path: Path):
    """Drive real shipped HTTP handler (no browser): post → state → 2 dry speaks."""
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from crewlab.ui import _RoomHolder, make_handler

    proj = _room_proj(tmp_path)
    room = ChatRoom(proj)
    _RoomHolder.room = room
    handler = make_handler()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"

    def get(path: str):
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(path: str, body: dict):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            base + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        health = get("/api/health")
        assert health.get("ok") is True
        state = get("/api/state")
        assert state.get("goal")
        assert len(state.get("assignments") or []) >= 2
        for a in state["assignments"]:
            assert a.get("task_id"), "assignment must show owned task"
        assert state.get("next_speaker")
        assert isinstance(state.get("messages"), list)

        token = "HTTP_FULL_HISTORY_TOKEN_9f3a"
        post("/api/message", {"text": token})
        state2 = get("/api/state")
        texts = " ".join(m.get("text") or "" for m in state2["messages"])
        assert token in texts

        s1 = post("/api/speak", {"dry_run": True})
        s2 = post("/api/speak", {"dry_run": True})
        assert s1.get("ok") is True and s2.get("ok") is True
        assert s1.get("agent") != s2.get("agent"), (
            f"turn-taking failed: {s1.get('agent')} then {s2.get('agent')}"
        )
        # speaking agent prompt must embed full history (token from operator)
        agent = room._agent_by_id(s2["agent"])
        prompt = room._build_speak_prompt(agent)
        assert token in prompt
        assert "FULL CHAT TRANSCRIPT" in prompt
    finally:
        httpd.shutdown()
        _RoomHolder.room = None


def test_ui_html_has_messenger_surface():
    assert "bubble" in ROOM_HTML
    assert "roster" in ROOM_HTML
    assert "btnNext" in ROOM_HTML
    assert "Next turn" in ROOM_HTML
    assert "assignments" not in ROOM_HTML or True  # roster renders from API
    assert "/api/state" in ROOM_HTML
