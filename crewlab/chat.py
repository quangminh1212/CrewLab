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


def load_messages(project_dir: Path, *, limit: int = 50) -> list[dict[str, Any]]:
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


def context_blob(project_dir: Path, *, limit: int = 12) -> str:
    """Compact context for kickoff prompts."""
    msgs = load_messages(project_dir, limit=limit)
    if not msgs:
        return "(no prior chat)"
    parts = []
    for m in msgs:
        parts.append(f"- {m.get('agent')}: {(m.get('text') or '')[:400]}")
    return "\n".join(parts)
