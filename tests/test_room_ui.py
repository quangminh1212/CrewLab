from pathlib import Path

from crewlab.chat import full_transcript, load_messages
from crewlab.cli import main
from crewlab.io_util import dump_yaml, load_spec
from crewlab.room import ChatRoom
from crewlab.ui import ROOM_HTML, THEME_TOKENS, make_handler, theme_css_block


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
    assert "/api/state" in ROOM_HTML
    # Telegram / Messenger / Zalo theme switch
    assert 'data-theme="telegram"' in ROOM_HTML
    assert 'data-theme="messenger"' in ROOM_HTML or 'data-theme="messenger"' in ROOM_HTML
    assert "zalo" in ROOM_HTML
    assert "typing" in ROOM_HTML
    assert "theme-btn" in ROOM_HTML


def test_theme_tokens_match_brand_chrome():
    """Shipped THEME_TOKENS define recognizable Telegram / Messenger / Zalo chrome."""
    assert set(THEME_TOKENS) == {"telegram", "messenger", "zalo"}

    tg = THEME_TOKENS["telegram"]
    assert tg["family"] == "dark"
    assert tg["accent"].upper() == "#2AABEE"
    assert tg["bg"].lower() == "#0e1621"
    assert tg["panel"].lower() == "#17212b"
    assert tg["me_bubble"].lower() == "#2b5278"

    ms = THEME_TOKENS["messenger"]
    assert ms["family"] == "light"
    assert ms["accent"].lower() == "#0084ff"
    assert ms["me_bubble"].lower() == "#0084ff"
    assert ms["me_text"].lower() == "#ffffff"
    assert ms["bg"].lower() == "#f0f2f5"
    assert ms["them_bubble"].lower() == "#e4e6eb"

    zl = THEME_TOKENS["zalo"]
    assert zl["family"] == "light"
    assert zl["accent"].lower() == "#0068ff"
    assert zl["me_bubble"].lower() != ms["me_bubble"].lower()
    assert zl["me_text"].lower() != "#ffffff"
    assert zl["bg"].lower().startswith("#e")  # soft blue family

    # CSS generated from tokens must appear in the single HTML document
    css = theme_css_block()
    assert "#2AABEE" in css or "#2aabee" in css.lower()
    assert "#0084ff" in css.lower()
    assert "#0068ff" in css.lower()
    for name in THEME_TOKENS:
        assert f'data-theme="{name}"' in ROOM_HTML
        assert f'data-theme="{name}"' in css or f"data-theme=\"{name}\"" in css
    # layout chrome: sidebar + main + composer + send + theme switch
    for sel in (".sidebar", ".main", ".composer", ".send-btn", ".theme-btn", ".bubble", ".row.me", ".row.sys"):
        assert sel in ROOM_HTML
    # switch control without page break (client-side applyTheme)
    assert "applyTheme" in ROOM_HTML
    assert "crewlab-ui-theme" in ROOM_HTML


def test_ui_responsive_drawer_and_breakpoints():
    """Mobile drawer + safe-area + breakpoints ship in ROOM_HTML (no separate CSS file)."""
    html = ROOM_HTML
    assert "viewport-fit=cover" in html
    assert "100dvh" in html
    assert "side-backdrop" in html or "sideBackdrop" in html
    assert "btnOpenSide" in html
    assert "btnCloseSide" in html
    assert "side-open" in html
    assert "setSideOpen" in html or "openSide" in html
    assert "max-width: 860px" in html
    assert "max-width: 480px" in html
    assert "safe-area-inset" in html
    assert "nav-menu" in html
    # drawer not permanently display:none on mobile (must remain usable)
    assert "body.side-open .sidebar" in html
    assert "translateX" in html
    # touch-friendly iOS font size on composer
    assert "font-size: 16px" in html


def test_cli_real_user_lifecycle_dry(tmp_path):
    """Drive shipped main() end-to-end like an operator (init → speak)."""
    proj = tmp_path / "life"
    assert main(["init", str(proj), "--name", "life"]) == 0
    assert main(["validate", str(proj)]) == 0
    assert main(["plan", str(proj)]) == 0
    assert main(["run", str(proj), "--dry-run", "--max-steps", "1"]) == 0
    assert main(["meeting", str(proj), "--dry-run"]) == 0
    assert main(["chat", str(proj), "hello operator"]) == 0
    assert main(["task", str(proj), "--agent", "lead", "--status", "in_progress"]) == 0
    assert main(["blocker", "add", str(proj), "wait design", "--task", "plan-and-coordinate"]) == 0
    assert main(["blocker", "list", str(proj)]) == 0
    assert main(["decision", "add", str(proj), "use dry-run"]) == 0
    assert (
        main(
            [
                "reassign",
                str(proj),
                "--agent",
                "builder",
                "--task",
                "plan-and-coordinate",
                "--decision",
                "swap demo",
            ]
        )
        == 0
    )
    assert main(["status", str(proj)]) == 0
    assert main(["speak", str(proj), "--dry-run"]) == 0
    assert main(["speak", str(proj), "--dry-run"]) == 0
    assert main(["backends", "--no-probe"]) == 0
