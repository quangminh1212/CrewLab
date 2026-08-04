"""Shared multi-agent message pool (MetaGPT / AutoGen inspired)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crewlab.project import utc_now


def chat_log_path(project_dir: Path) -> Path:
    return project_dir / "CHAT_LOG.md"


def chat_jsonl_path(project_dir: Path) -> Path:
    return project_dir / "chat.jsonl"


def append_message(
    project_dir: Path,
    *,
    agent: str,
    role: str,
    text: str,
    task_id: str | None = None,
    kind: str = "message",
) -> dict[str, Any]:
    """Append one message to markdown log + jsonl pool."""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    msg = {
        "at": utc_now(),
        "agent": agent,
        "role": role,
        "task_id": task_id,
        "kind": kind,
        "text": (text or "").strip(),
    }
    # jsonl
    with chat_jsonl_path(project_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    # markdown
    md = chat_log_path(project_dir)
    if not md.exists():
        md.write_text("# CrewLab Shared Chat (message pool)\n\n", encoding="utf-8")
    with md.open("a", encoding="utf-8") as f:
        who = f"{agent}" + (f" / {task_id}" if task_id else "")
        f.write(f"### {msg['at']} — **{who}** ({role}) [{kind}]\n\n")
        f.write(msg["text"] + "\n\n")
    return msg


def load_messages(project_dir: Path, *, limit: int | None = 50) -> list[dict[str, Any]]:
    """Load chat messages. limit=None → full history (agents must read everything)."""
    path = chat_jsonl_path(project_dir)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if limit is None:
        return rows
    return rows[-limit:]


def format_recent(project_dir: Path, *, limit: int = 20) -> str:
    msgs = load_messages(project_dir, limit=limit)
    if not msgs:
        return "chat: (empty message pool)"
    lines = [f"chat: last {len(msgs)} message(s)", ""]
    for m in msgs:
        lines.append(
            f"[{m.get('at')}] {m.get('agent')} ({m.get('kind')}): "
            f"{(m.get('text') or '')[:200]}"
        )
    return "\n".join(lines)


def full_transcript(project_dir: Path) -> str:
    """Full chat transcript — every agent must read this before speaking."""
    msgs = load_messages(project_dir, limit=None)
    if not msgs:
        return "(no messages yet — you speak first after operator kickoff)"
    parts = ["# FULL CHAT TRANSCRIPT (read every message before you reply)", ""]
    for i, m in enumerate(msgs, 1):
        who = m.get("agent") or "?"
        role = m.get("role") or ""
        task = m.get("task_id") or "-"
        kind = m.get("kind") or "message"
        at = m.get("at") or ""
        text = m.get("text") or ""
        parts.append(f"## [{i}] {at} | {who} ({role}) | task={task} | {kind}")
        parts.append(text)
        parts.append("")
    return "\n".join(parts)


def context_blob(project_dir: Path, *, limit: int | None = None) -> str:
    """Chat context for prompts. Default = FULL history (no truncation)."""
    if limit is None:
        return full_transcript(project_dir)
    msgs = load_messages(project_dir, limit=limit)
    if not msgs:
        return "(no prior chat)"
    parts = []
    for m in msgs:
        parts.append(f"- {m.get('agent')}: {(m.get('text') or '')}")
    return "\n".join(parts)
