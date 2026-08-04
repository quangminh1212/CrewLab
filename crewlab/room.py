"""Chat room: turn-taking multi-CLI agents + clear task assignment.

Rules:
1. Agents speak one at a time (turn lock).
2. Turn order follows sequential ready-tasks / roster.
3. Every agent prompt includes FULL chat transcript.
4. Assignments (agent → task → backend → status) always visible.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from crewlab.backends import invoke_backend, resolve_agent_backend
from crewlab.chat import append_message, full_transcript, load_messages
from crewlab.io_util import dump_yaml, load_spec, project_dir_for
from crewlab.process import normalize_process
from crewlab.project import (
    is_project_complete,
    load_or_init_state,
    save_state,
    set_task_status,
    utc_now,
)
from crewlab.run import ready_tasks
from crewlab.validate import validate_spec

# Distinct bubble colors (Messenger-like)
AGENT_COLORS = [
    "#2AABEE",  # telegram blue
    "#34B7F1",
    "#0088CC",
    "#25D366",  # green
    "#FF6B6B",
    "#F7B731",
    "#A55EEA",
    "#FD9644",
    "#26DE81",
    "#45AAF2",
]


def room_state_path(project_dir: Path) -> Path:
    return project_dir / "ROOM.json"


def load_room_meta(project_dir: Path) -> dict[str, Any]:
    p = room_state_path(project_dir)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {
        "turn_agent": None,
        "speaking": False,
        "turn_index": 0,
        "updated_at": None,
    }


def save_room_meta(project_dir: Path, meta: dict[str, Any]) -> None:
    meta["updated_at"] = utc_now()
    p = room_state_path(project_dir)
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class ChatRoom:
    """In-memory + disk-backed multi-agent chat room for one crew-spec."""

    def __init__(self, spec_path: str | Path):
        self.spec_path = Path(spec_path)
        self.spec = load_spec(self.spec_path)
        v = validate_spec(self.spec)
        if not v.ok:
            raise ValueError("invalid crew-spec:\n" + v.summary())
        self.project_dir = project_dir_for(self.spec_path)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._speaking = False
        self._last_error: str | None = None
        # ensure state exists
        load_or_init_state(self.project_dir, self.spec)
        meta = load_room_meta(self.project_dir)
        if not meta.get("bootstrapped"):
            self._bootstrap()
            meta["bootstrapped"] = True
            save_room_meta(self.project_dir, meta)

    def reload(self) -> None:
        self.spec = load_spec(self.spec_path)

    def _bootstrap(self) -> None:
        """System message: goal + clear assignments so everyone reads them."""
        lines = [
            f"🚀 Room opened — crew **{self.spec.get('name')}**",
            f"**Goal:** {self.spec.get('goal')}",
            f"**Process:** {normalize_process(self.spec)}",
            "",
            "## Phân công (mỗi agent 1 task)",
        ]
        for a in self.spec.get("agents") or []:
            if not isinstance(a, dict):
                continue
            br = resolve_agent_backend(a)
            lines.append(
                f"- **{a.get('id')}** [{a.get('role')}] → task `{a.get('task_id')}` "
                f"| backend=`{br.backend_id}` | {a.get('mission') or ''}"
            )
        lines.extend(
            [
                "",
                "## Quy tắc phòng chat",
                "1. Chỉ **1 agent** phát biểu mỗi lượt.",
                "2. Trước khi nói phải **đọc toàn bộ** tin nhắn trong phòng.",
                "3. Chỉ làm **task được giao** — không lấy task của agent khác.",
                "4. Operator gửi tin bất kỳ lúc nào; bấm **Next turn** để agent kế tiếp nói.",
            ]
        )
        append_message(
            self.project_dir,
            agent="system",
            role="Room",
            text="\n".join(lines),
            kind="system",
        )

    def assignments(self) -> list[dict[str, Any]]:
        state = load_or_init_state(self.project_dir, self.spec)
        st_map = {
            str(t.get("id")): t
            for t in (state.get("tasks") or [])
            if isinstance(t, dict)
        }
        colors = {}
        out = []
        for i, a in enumerate(self.spec.get("agents") or []):
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id"))
            colors[aid] = AGENT_COLORS[i % len(AGENT_COLORS)]
            tid = str(a.get("task_id") or "")
            st = st_map.get(tid) or {}
            br = resolve_agent_backend(a)
            out.append(
                {
                    "id": aid,
                    "role": a.get("role"),
                    "mission": a.get("mission") or "",
                    "task_id": tid,
                    "task_title": next(
                        (
                            t.get("title")
                            for t in (self.spec.get("tasks") or [])
                            if isinstance(t, dict) and t.get("id") == tid
                        ),
                        tid,
                    ),
                    "expected_output": next(
                        (
                            t.get("expected_output")
                            for t in (self.spec.get("tasks") or [])
                            if isinstance(t, dict) and t.get("id") == tid
                        ),
                        None,
                    ),
                    "status": st.get("status") or "todo",
                    "result": st.get("result"),
                    "backend": br.backend_id,
                    "backend_available": br.available,
                    "color": colors[aid],
                    "manager": bool(a.get("manager")),
                }
            )
        return out

    def turn_order(self) -> list[str]:
        """Agent ids in speak order — rotate so each agent gets a turn in chat.

        Sequential process still prefers dependency-ready tasks first, then
        rotates past last_speaker so the room is not stuck on one agent.
        """
        state = load_or_init_state(self.project_dir, self.spec)
        ready = ready_tasks(self.spec, state)
        order: list[str] = []
        for tid in ready:
            for a in self.spec.get("agents") or []:
                if isinstance(a, dict) and a.get("task_id") == tid:
                    aid = str(a.get("id"))
                    if aid not in order:
                        order.append(aid)
        if not order:
            # all agents with open tasks (chat round-robin across open work)
            for a in self.spec.get("agents") or []:
                if not isinstance(a, dict):
                    continue
                tid = a.get("task_id")
                st = next(
                    (
                        t.get("status")
                        for t in (state.get("tasks") or [])
                        if t.get("id") == tid
                    ),
                    "todo",
                )
                if st not in {"done", "skipped"}:
                    order.append(str(a.get("id")))
        # rotate past last speaker so agents speak lần lượt
        meta = load_room_meta(self.project_dir)
        last = meta.get("last_speaker")
        if last and last in order and len(order) > 1:
            i = order.index(last)
            order = order[i + 1 :] + order[: i + 1]
        return order

    def next_speaker(self) -> str | None:
        order = self.turn_order()
        return order[0] if order else None

    def snapshot(self) -> dict[str, Any]:
        state = load_or_init_state(self.project_dir, self.spec)
        complete, notes = is_project_complete(self.spec, state)
        meta = load_room_meta(self.project_dir)
        msgs = load_messages(self.project_dir, limit=None)
        # stamp colors on messages
        color_map = {a["id"]: a["color"] for a in self.assignments()}
        color_map["system"] = "#8E8E93"
        color_map["operator"] = "#5856D6"
        for m in msgs:
            m["color"] = color_map.get(str(m.get("agent")), "#636E72")
        return {
            "crew": self.spec.get("name"),
            "goal": self.spec.get("goal"),
            "process": normalize_process(self.spec),
            "project_dir": str(self.project_dir),
            "complete": complete,
            "notes": notes,
            "assignments": self.assignments(),
            "turn_order": self.turn_order(),
            "next_speaker": self.next_speaker(),
            "speaking": self._speaking or bool(meta.get("speaking")),
            "turn_agent": meta.get("turn_agent"),
            "messages": msgs,
            "message_count": len(msgs),
            "last_error": self._last_error,
            "version": "room-1",
        }

    def post_operator(self, text: str, *, agent: str = "operator") -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty message")
        msg = append_message(
            self.project_dir,
            agent=agent,
            role="Operator",
            text=text,
            kind="operator",
        )
        return msg

    def _agent_by_id(self, agent_id: str) -> dict[str, Any] | None:
        for a in self.spec.get("agents") or []:
            if isinstance(a, dict) and a.get("id") == agent_id:
                return a
        return None

    def _build_speak_prompt(self, agent: dict[str, Any]) -> str:
        state = load_or_init_state(self.project_dir, self.spec)
        tid = str(agent.get("task_id") or "")
        task = next(
            (
                t
                for t in (self.spec.get("tasks") or [])
                if isinstance(t, dict) and t.get("id") == tid
            ),
            {"id": tid, "title": tid},
        )
        assigns = self.assignments()
        assign_lines = []
        for a in assigns:
            mark = "← BẠN" if a["id"] == agent.get("id") else ""
            assign_lines.append(
                f"- {a['id']} [{a['role']}] task=`{a['task_id']}` "
                f"status={a['status']} backend={a['backend']} {mark}"
            )
        expected = task.get("expected_output") or "Báo cáo ngắn + kết quả task của bạn."
        return "\n".join(
            [
                "# CrewLab Chat Room — lượt nói của bạn",
                "",
                f"**Crew:** {self.spec.get('name')}",
                f"**Goal:** {self.spec.get('goal')}",
                f"**Bạn:** {agent.get('id')} — {agent.get('role')}",
                f"**Mission:** {agent.get('mission') or ''}",
                f"**TASK DUY NHẤT CỦA BẠN:** `{tid}` — {task.get('title') or task.get('description')}",
                f"**Expected output:** {expected}",
                "",
                "## Phân công toàn crew (chỉ làm task có ← BẠN)",
                *assign_lines,
                "",
                "## QUY TẮC BẮT BUỘC",
                "1. Đọc TOÀN BỘ transcript bên dưới — không bỏ sót tin nhắn.",
                "2. Chỉ phát biểu / làm việc liên quan task của bạn.",
                "3. Trả lời bằng nội dung hữu ích (tiến độ, kết quả, câu hỏi, blocker).",
                "4. Không giả vờ làm task của agent khác.",
                "",
                full_transcript(self.project_dir),
                "",
                "## Nhiệm vụ lượt này",
                "Sau khi đọc hết transcript, hãy gửi **một tin nhắn** vào phòng:",
                "- tóm tắt những gì bạn đã hiểu từ chat",
                "- làm / đề xuất phần thuộc task của bạn",
                "- nêu blocker nếu có",
                "",
                f"Prior task results in STATE: "
                + "; ".join(
                    f"{t.get('id')}={t.get('status')}"
                    for t in (state.get("tasks") or [])
                    if isinstance(t, dict)
                ),
            ]
        )

    def speak(
        self,
        *,
        agent_id: str | None = None,
        dry_run: bool = False,
        timeout: int = 600,
        auto_complete: bool = False,
    ) -> dict[str, Any]:
        """Give the floor to one agent (next in line or explicit id)."""
        with self._lock:
            if self._speaking:
                raise RuntimeError("another agent is speaking — wait for turn")
            self._speaking = True
            self._last_error = None

        try:
            self.reload()
            aid = agent_id or self.next_speaker()
            if not aid:
                raise RuntimeError("no agent ready to speak (all tasks done or blocked)")
            agent = self._agent_by_id(aid)
            if not agent:
                raise KeyError(f"unknown agent: {aid}")

            # enforce turn order when not dry and agent not next
            nxt = self.next_speaker()
            if agent_id and nxt and agent_id != nxt and not dry_run:
                # allow only if operator force — still warn in message
                pass

            meta = load_room_meta(self.project_dir)
            meta["speaking"] = True
            meta["turn_agent"] = aid
            save_room_meta(self.project_dir, meta)

            # announce turn
            append_message(
                self.project_dir,
                agent="system",
                role="Room",
                text=f"🎙️ Lượt của **{aid}** ({agent.get('role')}) — task `{agent.get('task_id')}`",
                task_id=str(agent.get("task_id") or ""),
                kind="turn",
            )

            prompt = self._build_speak_prompt(agent)
            work = self.project_dir / "runs" / f"chat-{aid}"
            result = invoke_backend(
                agent,
                prompt=prompt,
                work_dir=work,
                task_id=str(agent.get("task_id") or ""),
                goal=str(self.spec.get("goal") or ""),
                timeout=timeout,
                dry_run=dry_run,
            )

            # extract reply text
            reply = ""
            if result.mode == "dry-run":
                reply = (
                    f"[dry-run] {aid} đã đọc full transcript "
                    f"({len(load_messages(self.project_dir, limit=None))} tin) "
                    f"và sẵn sàng làm task `{agent.get('task_id')}`."
                )
            elif result.result_file and Path(result.result_file).is_file():
                body = Path(result.result_file).read_text(encoding="utf-8", errors="replace")
                if body.startswith("# Awaiting"):
                    reply = (
                        f"[prompt-only] Backend `{result.backend}` chưa chạy CLI. "
                        f"Prompt đầy đủ (gồm full chat) tại: {result.prompt_file}\n"
                        f"Điền kết quả vào {result.result_file} rồi bấm Complete task."
                    )
                else:
                    reply = body.strip()
            elif result.stdout:
                reply = result.stdout.strip()
            else:
                reply = result.error or f"({result.mode}) no output"

            msg = append_message(
                self.project_dir,
                agent=aid,
                role=str(agent.get("role") or ""),
                text=reply[:50000],  # full content, large cap
                task_id=str(agent.get("task_id") or ""),
                kind="agent" if result.ok else "agent_error",
            )

            state = load_or_init_state(self.project_dir, self.spec)
            tid = str(agent.get("task_id") or "")
            if result.ok and result.mode in {"executed", "dry-run"} and auto_complete:
                try:
                    set_task_status(
                        state,
                        tid,
                        "done",
                        result=reply[:1000],
                        spec=self.spec,
                        enforce_deps=True,
                    )
                except Exception:
                    set_task_status(state, tid, "in_progress", result=reply[:1000])
            elif result.ok and result.mode == "prompt_only":
                set_task_status(state, tid, "in_progress", result=f"awaiting CLI: {result.prompt_file}")
            elif not result.ok:
                set_task_status(state, tid, "blocked", result=result.error or "speak failed")
            else:
                set_task_status(state, tid, "in_progress", result=reply[:1000])
            save_state(self.project_dir, state)

            meta = load_room_meta(self.project_dir)
            meta["speaking"] = False
            meta["turn_agent"] = None
            meta["turn_index"] = int(meta.get("turn_index") or 0) + 1
            meta["last_speaker"] = aid
            save_room_meta(self.project_dir, meta)

            return {
                "ok": result.ok,
                "agent": aid,
                "mode": result.mode,
                "backend": result.backend,
                "message": msg,
                "prompt_file": result.prompt_file,
                "result_file": result.result_file,
                "error": result.error,
                "next_speaker": self.next_speaker(),
            }
        except Exception as e:
            self._last_error = str(e)
            meta = load_room_meta(self.project_dir)
            meta["speaking"] = False
            save_room_meta(self.project_dir, meta)
            raise
        finally:
            self._speaking = False

    def mark_task(
        self,
        agent_id: str,
        status: str,
        result: str | None = None,
    ) -> None:
        agent = self._agent_by_id(agent_id)
        if not agent:
            raise KeyError(f"unknown agent: {agent_id}")
        state = load_or_init_state(self.project_dir, self.spec)
        set_task_status(
            state,
            str(agent.get("task_id")),
            status,
            result=result,
            spec=self.spec,
            enforce_deps=True,
        )
        save_state(self.project_dir, state)
        append_message(
            self.project_dir,
            agent="system",
            role="Room",
            text=f"📌 Task `{agent.get('task_id')}` → **{status}** (agent {agent_id})"
            + (f"\n{result}" if result else ""),
            task_id=str(agent.get("task_id")),
            kind="status",
        )
