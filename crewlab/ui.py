"""Messenger/Telegram-style chat UI for multi-CLI agent rooms.

stdlib only — no Flask/FastAPI dependency.
  crewlab ui <spec> --port 8765
"""

from __future__ import annotations

import json
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from crewlab.room import ChatRoom

# ---------------------------------------------------------------------------
# Embedded Messenger-like UI
# ---------------------------------------------------------------------------

ROOM_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>CrewLab Room</title>
<style>
  :root {
    --bg: #0e1621;
    --panel: #17212b;
    --panel2: #232e3c;
    --text: #e4e6eb;
    --muted: #8b98a5;
    --accent: #2AABEE;
    --border: #0f141a;
    --bubble-sys: #1e2c3a;
    --input: #242f3d;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); }
  .app { display: grid; grid-template-columns: 300px 1fr; height: 100vh; }
  .sidebar { background: var(--panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  .side-head { padding: 14px 16px; border-bottom: 1px solid var(--border); }
  .side-head h1 { margin: 0; font-size: 16px; font-weight: 700; }
  .side-head .goal { margin-top: 6px; font-size: 12px; color: var(--muted); line-height: 1.4; max-height: 3.6em; overflow: hidden; }
  .badge { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--panel2); color: var(--muted); margin-top: 8px; }
  .badge.ok { background: #1b4332; color: #95d5b2; }
  .badge.busy { background: #3d2c1e; color: #ffd166; }
  .roster { flex: 1; overflow-y: auto; padding: 8px; }
  .agent-card {
    display: flex; gap: 10px; padding: 10px; border-radius: 12px; cursor: default;
    margin-bottom: 6px; background: transparent; border: 1px solid transparent;
  }
  .agent-card.next { border-color: var(--accent); background: rgba(42,171,238,.08); }
  .agent-card.speaking { border-color: #F7B731; background: rgba(247,183,49,.1); }
  .avatar {
    width: 42px; height: 42px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 14px; color: #fff; flex-shrink: 0;
  }
  .agent-meta { min-width: 0; flex: 1; }
  .agent-meta .name { font-weight: 600; font-size: 13px; }
  .agent-meta .role { font-size: 11px; color: var(--muted); }
  .agent-meta .task { font-size: 11px; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .st { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: var(--panel2); color: var(--muted); }
  .st.done { background: #1b4332; color: #95d5b2; }
  .st.in_progress { background: #1a3a5c; color: #90caf9; }
  .st.blocked { background: #4a1c1c; color: #ef9a9a; }
  .side-foot { padding: 10px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); }

  .main { display: flex; flex-direction: column; min-width: 0; }
  .topbar {
    padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  .topbar .title { font-weight: 600; flex: 1; min-width: 120px; }
  .topbar .turn { font-size: 12px; color: var(--muted); }
  button {
    border: 0; border-radius: 18px; padding: 8px 14px; font-size: 13px; font-weight: 600;
    cursor: pointer; background: var(--accent); color: #fff;
  }
  button:disabled { opacity: .45; cursor: not-allowed; }
  button.secondary { background: var(--panel2); color: var(--text); }
  button.danger { background: #c0392b; }

  .messages {
    flex: 1; overflow-y: auto; padding: 16px 18px 24px;
    background: linear-gradient(180deg, #0e1621 0%, #0b1219 100%);
  }
  .day-sep { text-align: center; color: var(--muted); font-size: 11px; margin: 12px 0; }
  .row { display: flex; margin: 8px 0; gap: 8px; align-items: flex-end; }
  .row.me { flex-direction: row-reverse; }
  .row .av {
    width: 32px; height: 32px; border-radius: 50%; font-size: 11px; font-weight: 700;
    display: flex; align-items: center; justify-content: center; color: #fff; flex-shrink: 0;
  }
  .bubble {
    max-width: min(680px, 78%); padding: 8px 12px 6px; border-radius: 14px;
    background: var(--panel2); position: relative; word-wrap: break-word;
  }
  .row.me .bubble { background: #2b5278; border-bottom-right-radius: 4px; }
  .row.sys .bubble { background: var(--bubble-sys); max-width: 90%; margin: 0 auto; border-radius: 10px; }
  .row.sys { justify-content: center; }
  .b-name { font-size: 12px; font-weight: 700; margin-bottom: 3px; }
  .b-text { font-size: 14px; line-height: 1.45; white-space: pre-wrap; }
  .b-meta { font-size: 10px; color: var(--muted); margin-top: 4px; text-align: right; }
  .b-task { font-size: 10px; color: var(--accent); margin-top: 2px; }

  .composer {
    padding: 10px 14px; background: var(--panel); border-top: 1px solid var(--border);
    display: flex; gap: 10px; align-items: flex-end;
  }
  .composer textarea {
    flex: 1; resize: none; min-height: 44px; max-height: 140px;
    background: var(--input); color: var(--text); border: 0; border-radius: 20px;
    padding: 12px 16px; font-size: 14px; font-family: inherit; outline: none;
  }
  .err { color: #ef9a9a; font-size: 12px; padding: 0 16px 8px; min-height: 18px; }
  @media (max-width: 800px) {
    .app { grid-template-columns: 1fr; }
    .sidebar { display: none; }
  }
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="side-head">
      <h1 id="crewName">CrewLab</h1>
      <div class="goal" id="crewGoal">…</div>
      <div><span class="badge" id="processBadge">process</span>
           <span class="badge" id="statusBadge">…</span></div>
    </div>
    <div class="roster" id="roster"></div>
    <div class="side-foot" id="foot">Phân công: 1 agent = 1 task · nói lần lượt · đọc full chat</div>
  </aside>
  <main class="main">
    <div class="topbar">
      <div class="title" id="roomTitle">Chat room</div>
      <div class="turn" id="turnInfo">—</div>
      <button class="secondary" id="btnRefresh" title="Refresh">↻</button>
      <button id="btnNext" title="Agent kế tiếp phát biểu">▶ Next turn</button>
      <button class="secondary" id="btnDry" title="Mô phỏng lượt (không gọi CLI)">Dry turn</button>
    </div>
    <div class="messages" id="messages"></div>
    <div class="err" id="err"></div>
    <div class="composer">
      <textarea id="input" rows="1" placeholder="Nhắn như operator… (Enter gửi, Shift+Enter xuống dòng)"></textarea>
      <button id="btnSend">Gửi</button>
    </div>
  </main>
</div>
<script>
const $ = (id) => document.getElementById(id);
let state = null;
let autoScroll = true;

function initials(id) {
  if (!id) return "?";
  return String(id).slice(0, 2).toUpperCase();
}

function renderRoster(s) {
  const el = $("roster");
  el.innerHTML = "";
  const next = s.next_speaker;
  const speaking = s.turn_agent;
  (s.assignments || []).forEach(a => {
    const div = document.createElement("div");
    div.className = "agent-card" + (a.id === next ? " next" : "") + (a.id === speaking ? " speaking" : "");
    div.innerHTML = `
      <div class="avatar" style="background:${a.color}">${initials(a.id)}</div>
      <div class="agent-meta">
        <div class="name">${esc(a.id)} <span class="st ${esc(a.status)}">${esc(a.status)}</span></div>
        <div class="role">${esc(a.role)} · ${esc(a.backend)}${a.backend_available ? "" : " ⚠"}</div>
        <div class="task">📋 ${esc(a.task_id)} — ${esc(a.task_title || "")}</div>
      </div>`;
    el.appendChild(div);
  });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

function renderMessages(s) {
  const box = $("messages");
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  box.innerHTML = "";
  const msgs = s.messages || [];
  if (!msgs.length) {
    box.innerHTML = '<div class="day-sep">Chưa có tin nhắn — gửi tin hoặc Next turn</div>';
    return;
  }
  msgs.forEach(m => {
    const agent = m.agent || "?";
    const isOp = agent === "operator";
    const isSys = agent === "system" || m.kind === "system" || m.kind === "turn" || m.kind === "status";
    const row = document.createElement("div");
    row.className = "row" + (isOp ? " me" : "") + (isSys ? " sys" : "");
    const color = m.color || "#636E72";
    const av = isSys ? "" : `<div class="av" style="background:${color}">${initials(agent)}</div>`;
    const name = isSys ? "" : `<div class="b-name" style="color:${color}">${esc(agent)}${m.role ? " · " + esc(m.role) : ""}</div>`;
    const task = m.task_id ? `<div class="b-task">task: ${esc(m.task_id)}</div>` : "";
    row.innerHTML = `${av}<div class="bubble">${name}<div class="b-text">${esc(m.text)}</div>${task}<div class="b-meta">${esc(m.at || "")} · ${esc(m.kind || "message")}</div></div>`;
    box.appendChild(row);
  });
  if (autoScroll || nearBottom) box.scrollTop = box.scrollHeight;
}

function render(s) {
  state = s;
  $("crewName").textContent = s.crew || "CrewLab";
  $("crewGoal").textContent = s.goal || "";
  $("processBadge").textContent = "process: " + (s.process || "?");
  const sb = $("statusBadge");
  if (s.speaking) { sb.textContent = "🎙️ speaking"; sb.className = "badge busy"; }
  else if (s.complete) { sb.textContent = "✅ complete"; sb.className = "badge ok"; }
  else { sb.textContent = (s.message_count || 0) + " tin"; sb.className = "badge"; }
  $("roomTitle").textContent = (s.crew || "Room") + " · multi-CLI chat";
  $("turnInfo").textContent = s.next_speaker
    ? ("Lượt kế: " + s.next_speaker + (s.turn_order && s.turn_order.length ? " · hàng đợi: " + s.turn_order.join(" → ") : ""))
    : (s.complete ? "Hoàn thành dự án" : "Không còn agent sẵn sàng");
  $("btnNext").disabled = !!s.speaking || !!s.complete || !s.next_speaker;
  $("btnDry").disabled = !!s.speaking || !!s.complete || !s.next_speaker;
  $("err").textContent = s.last_error || "";
  $("foot").textContent = (s.project_dir || "") + " · full transcript cho mọi agent";
  renderRoster(s);
  renderMessages(s);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText || "request failed");
  return data;
}

async function refresh() {
  try {
    const s = await api("/api/state");
    render(s);
  } catch (e) {
    $("err").textContent = String(e.message || e);
  }
}

async function send() {
  const ta = $("input");
  const text = ta.value.trim();
  if (!text) return;
  ta.value = "";
  try {
    await api("/api/message", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ text })
    });
    await refresh();
  } catch (e) {
    $("err").textContent = String(e.message || e);
  }
}

async function nextTurn(dry) {
  $("btnNext").disabled = true;
  $("btnDry").disabled = true;
  $("err").textContent = dry ? "Dry turn…" : "Đang gọi agent CLI…";
  try {
    await api("/api/speak", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ dry_run: !!dry })
    });
    await refresh();
  } catch (e) {
    $("err").textContent = String(e.message || e);
    await refresh();
  }
}

$("btnSend").onclick = send;
$("btnRefresh").onclick = refresh;
$("btnNext").onclick = () => nextTurn(false);
$("btnDry").onclick = () => nextTurn(true);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
$("messages").addEventListener("scroll", () => {
  const box = $("messages");
  autoScroll = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
});

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


class _RoomHolder:
    room: ChatRoom | None = None
    speak_lock = threading.Lock()


def _json_response(handler: BaseHTTPRequestHandler, code: int, data: Any) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            # quiet default access log noise; keep errors
            if args and str(args[1]).startswith("5"):
                super().log_message(fmt, *args)

        def do_GET(self) -> None:
            room = _RoomHolder.room
            if room is None:
                _json_response(self, 503, {"error": "room not ready"})
                return
            path = urlparse(self.path).path
            if path in {"/", "/index.html", "/ui"}:
                body = ROOM_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/state":
                try:
                    _json_response(self, 200, room.snapshot())
                except Exception as e:
                    _json_response(self, 500, {"error": str(e)})
                return
            if path == "/api/health":
                _json_response(self, 200, {"ok": True, "crew": room.spec.get("name")})
                return
            _json_response(self, 404, {"error": "not found"})

        def do_POST(self) -> None:
            room = _RoomHolder.room
            if room is None:
                _json_response(self, 503, {"error": "room not ready"})
                return
            path = urlparse(self.path).path
            data = _read_json(self)
            try:
                if path == "/api/message":
                    msg = room.post_operator(str(data.get("text") or ""))
                    _json_response(self, 200, {"ok": True, "message": msg})
                    return
                if path == "/api/speak":
                    if not _RoomHolder.speak_lock.acquire(blocking=False):
                        _json_response(self, 409, {"error": "speak already in progress"})
                        return
                    try:
                        dry = bool(data.get("dry_run"))
                        # dry-run in UI auto-marks task done so queue advances demo-friendly;
                        # live CLI turns only auto_complete when client asks.
                        auto = bool(data.get("auto_complete")) or dry
                        out = room.speak(
                            agent_id=data.get("agent") or None,
                            dry_run=dry,
                            timeout=int(data.get("timeout") or 600),
                            auto_complete=auto,
                        )
                        _json_response(self, 200, out)
                    finally:
                        _RoomHolder.speak_lock.release()
                    return
                if path == "/api/task":
                    room.mark_task(
                        str(data.get("agent") or ""),
                        str(data.get("status") or "done"),
                        result=data.get("result"),
                    )
                    _json_response(self, 200, {"ok": True})
                    return
                _json_response(self, 404, {"error": "not found"})
            except Exception as e:
                _json_response(
                    self,
                    400,
                    {"error": str(e), "trace": traceback.format_exc()[-800:]},
                )

    return Handler


def serve_room(
    spec_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    room = ChatRoom(spec_path)
    _RoomHolder.room = room
    handler = make_handler()
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"CrewLab chat UI: {url}")
    print(f"  crew: {room.spec.get('name')}")
    print(f"  dir:  {room.project_dir}")
    print("  Open in browser. Ctrl+C to stop.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
