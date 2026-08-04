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
    dests = [a.dest for a in p._subparsers._actions if hasattr(a, "choices") and a.choices]
    # argparse stores subcommands in choices of subparsers action
    found = False
    for a in p._actions:
        if getattr(a, "choices", None) and "ui" in (a.choices or {}):
            found = True
    assert found
