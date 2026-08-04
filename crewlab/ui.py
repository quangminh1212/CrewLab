"""Chat UI inspired by Telegram / Messenger / Zalo for multi-CLI crews.

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
from urllib.parse import urlparse

from crewlab.room import ChatRoom

# ---------------------------------------------------------------------------
# UI: Telegram dark + Messenger bubbles + Zalo brand accents (theme switch)
# Defining chrome tokens researched against Telegram Web / Messenger / Zalo Web.
# Tests assert these shipped values (not re-implemented CSS).
# ---------------------------------------------------------------------------

THEME_TOKENS: dict[str, dict[str, str]] = {
    # Telegram Web dark: official brand blue #2AABEE, navy side panel
    "telegram": {
        "bg": "#0e1621",
        "bg_chat": "#0b141a",
        "panel": "#17212b",
        "panel2": "#232e3c",
        "hover": "#202b36",
        "text": "#f5f5f5",
        "muted": "#708499",
        "accent": "#2AABEE",
        "accent2": "#5288c1",
        "me_bubble": "#2b5278",
        "them_bubble": "#182533",
        "sys_bubble": "#1c2733",
        "border": "#0f141a",
        "input": "#242f3d",
        "online": "#4fae4e",
        "danger": "#e53935",
        "me_text": "#f5f5f5",
        "family": "dark",
    },
    # Facebook Messenger default: brand #0084ff solid me-bubble, white text, light chrome
    "messenger": {
        "bg": "#f0f2f5",
        "bg_chat": "#ffffff",
        "panel": "#ffffff",
        "panel2": "#f0f2f5",
        "hover": "#e4e6eb",
        "text": "#050505",
        "muted": "#65676b",
        "accent": "#0084ff",
        "accent2": "#00c6ff",
        "me_bubble": "#0084ff",
        "them_bubble": "#e4e6eb",
        "sys_bubble": "#e7f3ff",
        "border": "#ced0d4",
        "input": "#f0f2f5",
        "online": "#31a24c",
        "danger": "#f02849",
        "me_text": "#ffffff",
        "family": "light",
    },
    # Zalo Web: brand #0068ff, soft blue room, light-blue me bubble + dark text
    "zalo": {
        "bg": "#e8f3ff",
        "bg_chat": "#e8f3ff",
        "panel": "#ffffff",
        "panel2": "#f0f7ff",
        "hover": "#e3f0ff",
        "text": "#081b33",
        "muted": "#5a6b7d",
        "accent": "#0068ff",
        "accent2": "#00a3ff",
        "me_bubble": "#d6ebff",
        "them_bubble": "#ffffff",
        "sys_bubble": "#fff8e6",
        "border": "#d0e3ff",
        "input": "#ffffff",
        "online": "#1ec16b",
        "danger": "#e74c3c",
        "me_text": "#081b33",
        "family": "light",
    },
}


def theme_css_block() -> str:
    """Render data-theme CSS variable blocks from THEME_TOKENS (single source)."""
    parts: list[str] = []
    for name, t in THEME_TOKENS.items():
        parts.append(
            f"""  html[data-theme="{name}"] {{
    --bg: {t["bg"]};
    --bg-chat: {t["bg_chat"]};
    --panel: {t["panel"]};
    --panel2: {t["panel2"]};
    --hover: {t["hover"]};
    --text: {t["text"]};
    --muted: {t["muted"]};
    --accent: {t["accent"]};
    --accent2: {t["accent2"]};
    --me-bubble: {t["me_bubble"]};
    --them-bubble: {t["them_bubble"]};
    --sys-bubble: {t["sys_bubble"]};
    --border: {t["border"]};
    --input: {t["input"]};
    --online: {t["online"]};
    --danger: {t["danger"]};
    --me-text: {t["me_text"]};
    --shadow: {"0 1px 2px rgba(0,0,0,.35)" if t["family"] == "dark" else ("0 1px 3px rgba(0,80,180,.12)" if name == "zalo" else "0 1px 2px rgba(0,0,0,.08)")};
    --wallpaper: {_wallpaper_for(name)};
  }}"""
        )
    return "\n".join(parts)


def _wallpaper_for(name: str) -> str:
    if name == "telegram":
        return (
            "radial-gradient(ellipse at 20% 0%, #132033 0%, transparent 50%), "
            "radial-gradient(ellipse at 80% 100%, #0d1f18 0%, transparent 45%), "
            "var(--bg-chat)"
        )
    if name == "messenger":
        return "linear-gradient(180deg, #e7f3ff 0%, #ffffff 40%)"
    return "linear-gradient(180deg, #cfe6ff 0%, #e8f3ff 30%, #dcefff 100%)"


# ROOM_HTML is built once; theme CSS injected from THEME_TOKENS.
_ROOM_HTML_HEAD = r"""<!DOCTYPE html>
<html lang="vi" data-theme="telegram">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta name="theme-color" content="#0e1621"/>
<meta name="mobile-web-app-capable" content="yes"/>
<title>CrewLab Chat</title>
<style>
  /* —— Theme tokens (Telegram / Messenger / Zalo) —— */
"""

_ROOM_HTML_BODY = r"""
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    -webkit-font-smoothing: antialiased;
    overflow: hidden;
  }
  .app {
    display: grid;
    grid-template-columns: minmax(280px, 340px) 1fr;
    height: 100vh;
    height: 100dvh;
    max-width: 1400px;
    margin: 0 auto;
    box-shadow: 0 0 40px rgba(0,0,0,.25);
    position: relative;
  }
  /* Mobile chrome: menu / close (hidden on desktop) */
  .nav-menu, .nav-close, .side-backdrop {
    display: none;
  }
  .nav-menu, .nav-close {
    width: 40px; height: 40px; padding: 0; border-radius: 50%;
    border: 0; background: var(--panel2); color: var(--text);
    font-size: 18px; font-weight: 700; cursor: pointer;
    flex-shrink: 0;
    align-items: center; justify-content: center;
  }
  .nav-menu:hover, .nav-close:hover { filter: brightness(1.06); }

  /* —— Sidebar (Telegram / Zalo chat list) —— */
  .sidebar {
    background: var(--panel);
    border-right: 1px solid var(--border);
    display: flex; flex-direction: column; min-width: 0; overflow: hidden;
  }
  .side-head {
    padding: 12px 14px 10px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  .brand-row { display: flex; align-items: center; gap: 10px; }
  .brand-logo {
    width: 40px; height: 40px; border-radius: 12px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-weight: 800; font-size: 15px; flex-shrink: 0;
    box-shadow: var(--shadow);
  }
  .brand-logo span { transform: translateY(-1px); }
  .brand-text h1 { margin: 0; font-size: 16px; font-weight: 700; letter-spacing: .2px; }
  .brand-text .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .goal-box {
    margin-top: 10px; padding: 8px 10px; border-radius: 10px;
    background: var(--panel2); font-size: 12px; line-height: 1.45; color: var(--muted);
    max-height: 4.2em; overflow: hidden;
  }
  .theme-row { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
  .theme-btn {
    flex: 1; min-width: 90px; border: 1px solid var(--border); background: var(--panel2);
    color: var(--text); border-radius: 16px; padding: 6px 8px; font-size: 11px;
    font-weight: 600; cursor: pointer;
  }
  .theme-btn.active {
    background: var(--accent); color: #fff; border-color: transparent;
  }
  .search {
    margin: 10px 12px 6px; padding: 8px 12px; border-radius: 18px;
    background: var(--input); border: 1px solid transparent;
    display: flex; align-items: center; gap: 8px;
  }
  .search input {
    border: 0; outline: 0; background: transparent; color: var(--text);
    font-size: 13px; width: 100%; font-family: inherit;
  }
  .search input::placeholder { color: var(--muted); }
  .section-label {
    padding: 8px 16px 4px; font-size: 11px; font-weight: 700;
    color: var(--muted); text-transform: uppercase; letter-spacing: .6px;
  }
  .roster { flex: 1; overflow-y: auto; padding: 4px 8px 12px; }
  .agent-card {
    display: flex; gap: 10px; padding: 10px 10px; border-radius: 12px;
    cursor: pointer; margin-bottom: 2px; border: 1px solid transparent;
    transition: background .12s;
  }
  .agent-card:hover { background: var(--hover); }
  .agent-card.next {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  }
  .agent-card.speaking {
    background: color-mix(in srgb, #f7b731 14%, transparent);
    border-color: color-mix(in srgb, #f7b731 50%, transparent);
  }
  .av-wrap { position: relative; flex-shrink: 0; }
  .avatar {
    width: 48px; height: 48px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 15px; color: #fff;
    box-shadow: var(--shadow);
  }
  .dot {
    position: absolute; right: 1px; bottom: 1px; width: 12px; height: 12px;
    border-radius: 50%; border: 2px solid var(--panel); background: var(--muted);
  }
  .dot.on { background: var(--online); }
  .dot.busy { background: #f7b731; animation: pulse 1.2s infinite; }
  @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.15)} }
  .agent-meta { min-width: 0; flex: 1; padding-top: 2px; }
  .agent-meta .name-row { display: flex; align-items: center; gap: 6px; }
  .agent-meta .name { font-weight: 650; font-size: 14px; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .st {
    font-size: 10px; padding: 2px 7px; border-radius: 10px;
    background: var(--panel2); color: var(--muted); font-weight: 600; text-transform: uppercase;
  }
  .st.done { background: #d4edda; color: #1b5e20; }
  html[data-theme="telegram"] .st.done { background: #1b4332; color: #95d5b2; }
  .st.in_progress { background: #d6eaf8; color: #0d47a1; }
  html[data-theme="telegram"] .st.in_progress { background: #1a3a5c; color: #90caf9; }
  .st.blocked { background: #f8d7da; color: #7f1d1d; }
  html[data-theme="telegram"] .st.blocked { background: #4a1c1c; color: #ef9a9a; }
  .agent-meta .role { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .agent-meta .task {
    font-size: 12px; margin-top: 3px; color: var(--text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; opacity: .9;
  }
  .agent-meta .task b { color: var(--accent); font-weight: 650; }
  .side-foot {
    padding: 10px 14px; border-top: 1px solid var(--border);
    font-size: 11px; color: var(--muted); line-height: 1.4;
  }

  /* —— Main chat (Messenger / Telegram / Zalo) —— */
  .main { display: flex; flex-direction: column; min-width: 0; background: var(--bg-chat); }
  .topbar {
    padding: 8px 14px; background: var(--panel);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 12px; min-height: 60px;
    box-shadow: var(--shadow);
    z-index: 2;
  }
  .top-avatars { display: flex; align-items: center; }
  .top-avatars .t-av {
    width: 34px; height: 34px; border-radius: 50%; margin-left: -8px;
    border: 2px solid var(--panel); display: flex; align-items: center; justify-content: center;
    color: #fff; font-size: 11px; font-weight: 700;
  }
  .top-avatars .t-av:first-child { margin-left: 0; }
  .top-info { flex: 1; min-width: 0; }
  .top-info .title { font-weight: 700; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .top-info .turn { font-size: 12px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .top-info .turn strong { color: var(--accent); font-weight: 650; }
  .top-actions { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .top-actions .btn-label-short,
  .top-actions .btn-label-icon { display: none; }
  button, .btn {
    border: 0; border-radius: 20px; padding: 8px 14px; font-size: 13px; font-weight: 650;
    cursor: pointer; background: var(--accent); color: #fff; font-family: inherit;
    transition: filter .12s, transform .08s;
  }
  button:hover:not(:disabled) { filter: brightness(1.06); }
  button:active:not(:disabled) { transform: scale(.98); }
  button:disabled { opacity: .42; cursor: not-allowed; }
  button.secondary, .btn.secondary { background: var(--panel2); color: var(--text); }
  button.icon {
    width: 38px; height: 38px; padding: 0; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    background: var(--panel2); color: var(--text); font-size: 16px;
  }

  .messages {
    flex: 1; overflow-y: auto; padding: 16px 16px 20px;
    background: var(--wallpaper);
  }
  .day-sep {
    display: flex; justify-content: center; margin: 14px 0;
  }
  .day-sep span {
    background: color-mix(in srgb, var(--panel) 88%, transparent);
    color: var(--muted); font-size: 12px; font-weight: 600;
    padding: 4px 12px; border-radius: 12px; box-shadow: var(--shadow);
  }
  .row {
    display: flex; margin: 3px 0; gap: 8px; align-items: flex-end;
    animation: fadeIn .18s ease;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .row.me { flex-direction: row-reverse; }
  .row.sys { justify-content: center; margin: 10px 0; }
  .row .av {
    width: 32px; height: 32px; border-radius: 50%; font-size: 11px; font-weight: 700;
    display: flex; align-items: center; justify-content: center; color: #fff; flex-shrink: 0;
    box-shadow: var(--shadow);
  }
  .row.stack .av { visibility: hidden; }
  .bubble {
    max-width: min(640px, 78%); padding: 7px 11px 5px;
    border-radius: 16px; position: relative; word-wrap: break-word;
    box-shadow: var(--shadow); background: var(--them-bubble);
  }
  .row.me .bubble {
    background: var(--me-bubble);
    color: var(--me-text);
    border-bottom-right-radius: 5px;
  }
  html[data-theme="messenger"] .row.me .b-meta,
  html[data-theme="messenger"] .row.me .b-task { color: rgba(255,255,255,.78); }
  html[data-theme="zalo"] .row.me .bubble {
    border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    box-shadow: 0 1px 2px rgba(0, 80, 180, 0.08);
  }
  html[data-theme="zalo"] .row.me .b-meta,
  html[data-theme="zalo"] .row.me .b-task { color: color-mix(in srgb, var(--muted) 85%, var(--accent)); }
  html[data-theme="telegram"] .row.me .bubble {
    border-bottom-right-radius: 4px;
  }
  html[data-theme="messenger"] .row.me .bubble {
    border-bottom-right-radius: 4px;
  }
  .row:not(.me):not(.sys) .bubble { border-bottom-left-radius: 5px; }
  .row.sys .bubble {
    background: var(--sys-bubble); max-width: 92%; border-radius: 12px;
    text-align: left; box-shadow: none; border: 1px dashed var(--border);
  }
  .b-name { font-size: 12px; font-weight: 700; margin-bottom: 2px; }
  .b-text { font-size: 14.5px; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }
  .b-meta {
    font-size: 10.5px; color: var(--muted); margin-top: 3px;
    display: flex; justify-content: flex-end; gap: 6px; align-items: center;
  }
  .b-task {
    font-size: 11px; color: var(--accent); margin-top: 3px; font-weight: 600;
  }
  .assign-chip {
    display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 8px;
    background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent);
    margin-left: 4px;
  }

  .typing {
    display: none; padding: 0 20px 6px; font-size: 12px; color: var(--muted);
    align-items: center; gap: 8px;
  }
  .typing.show { display: flex; }
  .typing-dots span {
    display: inline-block; width: 6px; height: 6px; border-radius: 50%;
    background: var(--muted); margin-right: 3px; animation: bounce 1.2s infinite;
  }
  .typing-dots span:nth-child(2) { animation-delay: .15s; }
  .typing-dots span:nth-child(3) { animation-delay: .3s; }
  @keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-4px)} }

  .err {
    color: var(--danger); font-size: 12px; padding: 0 16px 4px; min-height: 16px;
  }

  .composer {
    padding: 10px 12px 12px; background: var(--panel);
    border-top: 1px solid var(--border);
    display: flex; gap: 8px; align-items: flex-end;
  }
  .composer textarea {
    flex: 1; resize: none; min-height: 44px; max-height: 140px;
    background: var(--input); color: var(--text); border: 1px solid var(--border);
    border-radius: 22px; padding: 12px 16px; font-size: 14.5px; font-family: inherit;
    outline: none; line-height: 1.35;
  }
  .composer textarea:focus {
    border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
  }
  .send-btn {
    width: 44px; height: 44px; border-radius: 50%; padding: 0;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 18px; flex-shrink: 0;
  }

  .rules-bar {
    display: flex; gap: 8px; flex-wrap: wrap; padding: 6px 14px 0;
    font-size: 11px; color: var(--muted);
  }
  .rules-bar span {
    background: var(--panel2); padding: 3px 8px; border-radius: 10px;
  }

  /* —— Responsive: tablet —— */
  @media (max-width: 1100px) {
    .app {
      grid-template-columns: minmax(240px, 300px) 1fr;
      max-width: none;
      box-shadow: none;
    }
    .bubble { max-width: min(560px, 82%); }
  }

  /* —— Responsive: mobile / small tablet (Telegram-style drawer) —— */
  @media (max-width: 860px) {
    .app {
      grid-template-columns: 1fr;
      height: 100vh;
      height: 100dvh;
      max-width: none;
      box-shadow: none;
    }
    .side-backdrop {
      display: block;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,.45);
      z-index: 40;
      opacity: 0;
      pointer-events: none;
      transition: opacity .2s ease;
    }
    body.side-open .side-backdrop {
      opacity: 1;
      pointer-events: auto;
    }
    .sidebar {
      position: fixed;
      top: 0; left: 0; bottom: 0;
      width: min(88vw, 320px);
      max-width: 320px;
      z-index: 50;
      transform: translateX(-105%);
      transition: transform .22s ease;
      box-shadow: 4px 0 24px rgba(0,0,0,.28);
      border-right: 1px solid var(--border);
      padding-top: env(safe-area-inset-top, 0);
      padding-bottom: env(safe-area-inset-bottom, 0);
    }
    body.side-open .sidebar {
      transform: translateX(0);
    }
    .nav-menu {
      display: inline-flex;
    }
    .nav-close {
      display: inline-flex;
      margin-left: auto;
    }
    .brand-row { gap: 8px; }
    .topbar {
      padding: 6px 10px;
      min-height: 54px;
      gap: 8px;
      padding-top: max(6px, env(safe-area-inset-top, 0px));
    }
    .top-avatars .t-av { width: 30px; height: 30px; font-size: 10px; }
    .top-info .title { font-size: 14px; }
    .top-info .turn { font-size: 11px; }
    .top-actions { gap: 4px; flex-wrap: nowrap; }
    .top-actions button {
      padding: 7px 10px; font-size: 12px;
    }
    .top-actions #btnNext {
      padding: 7px 12px;
    }
    .top-actions .btn-label-full { display: none; }
    .top-actions .btn-label-short { display: inline; }
    .rules-bar {
      padding: 4px 10px 0;
      gap: 6px;
      font-size: 10px;
      overflow-x: auto;
      flex-wrap: nowrap;
      -webkit-overflow-scrolling: touch;
    }
    .rules-bar span {
      white-space: nowrap;
      flex-shrink: 0;
    }
    .rules-bar .hide-sm { display: none; }
    .messages {
      padding: 10px 10px 14px;
      padding-left: max(10px, env(safe-area-inset-left, 0px));
      padding-right: max(10px, env(safe-area-inset-right, 0px));
    }
    .bubble {
      max-width: min(100%, 88%);
      padding: 6px 10px 4px;
      font-size: 14px;
    }
    .b-text { font-size: 14px; }
    .row .av { width: 28px; height: 28px; font-size: 10px; }
    .row.sys .bubble { max-width: 100%; font-size: 12.5px; }
    .composer {
      padding: 8px 10px max(10px, env(safe-area-inset-bottom, 0px));
      gap: 6px;
    }
    .composer textarea {
      min-height: 40px;
      max-height: 120px;
      padding: 10px 14px;
      font-size: 16px; /* avoid iOS zoom on focus */
      border-radius: 20px;
    }
    .send-btn { width: 42px; height: 42px; }
    .theme-btn { min-width: 0; flex: 1; font-size: 10px; padding: 6px 4px; }
    .avatar { width: 44px; height: 44px; font-size: 14px; }
    .agent-card { padding: 8px; }
    .typing { padding: 0 12px 4px; }
    .err { padding: 0 10px 4px; }
  }

  @media (max-width: 480px) {
    .top-avatars { display: none; }
    .top-actions #btnDry { display: none; }
    .top-actions #btnNext {
      border-radius: 50%;
      width: 40px; height: 40px; padding: 0;
      font-size: 14px;
    }
    .top-actions #btnNext .btn-label-short { display: none; }
    .top-actions #btnNext .btn-label-icon { display: inline; }
    .goal-box { max-height: 3.2em; font-size: 11px; }
    .side-foot { font-size: 10px; }
  }

  @media (min-width: 861px) {
    .top-actions .btn-label-short { display: none; }
    .top-actions .btn-label-icon { display: none; }
    body.side-open .sidebar { transform: none; }
  }

  /* Prefer reduced motion */
  @media (prefers-reduced-motion: reduce) {
    .sidebar, .side-backdrop, .row { transition: none; animation: none; }
  }
</style>
</head>
<body>
<div class="side-backdrop" id="sideBackdrop" aria-hidden="true"></div>
<div class="app">
  <aside class="sidebar" id="sidebar" aria-label="Danh sách agent">
    <div class="side-head">
      <div class="brand-row">
        <div class="brand-logo"><span>CL</span></div>
        <div class="brand-text">
          <h1 id="crewName">CrewLab</h1>
          <div class="sub" id="processBadge">multi-CLI room</div>
        </div>
        <button type="button" class="nav-close" id="btnCloseSide" title="Đóng danh sách" aria-label="Đóng">✕</button>
      </div>
      <div class="goal-box" id="crewGoal">…</div>
      <div class="theme-row">
        <button type="button" class="theme-btn active" data-theme="telegram" title="Telegram dark">Telegram</button>
        <button type="button" class="theme-btn" data-theme="messenger" title="Messenger light">Messenger</button>
        <button type="button" class="theme-btn" data-theme="zalo" title="Zalo light">Zalo</button>
      </div>
      <div class="search">
        <span style="opacity:.6">🔍</span>
        <input id="filter" type="search" placeholder="Tìm agent / task…" autocomplete="off"/>
      </div>
    </div>
    <div class="section-label">Thành viên · phân công 1 task</div>
    <div class="roster" id="roster"></div>
    <div class="side-foot" id="foot">
      1 agent = 1 task · nói lần lượt · mỗi lượt đọc full transcript
    </div>
  </aside>

  <main class="main">
    <div class="topbar">
      <button type="button" class="nav-menu" id="btnOpenSide" title="Danh sách agent" aria-label="Mở danh sách" aria-controls="sidebar" aria-expanded="false">☰</button>
      <div class="top-avatars" id="topAvatars"></div>
      <div class="top-info">
        <div class="title" id="roomTitle">Chat room</div>
        <div class="turn" id="turnInfo">—</div>
      </div>
      <div class="top-actions">
        <button class="icon secondary" id="btnRefresh" title="Làm mới">↻</button>
        <button class="secondary" id="btnDry" title="Mô phỏng lượt (không gọi CLI)">Dry</button>
        <button id="btnNext" title="Agent kế tiếp phát biểu">
          <span class="btn-label-full">▶ Next turn</span>
          <span class="btn-label-short">Next</span>
          <span class="btn-label-icon">▶</span>
        </button>
      </div>
    </div>
    <div class="rules-bar">
      <span id="statusBadge">…</span>
      <span class="hide-sm">📄 Full history mỗi lượt</span>
      <span class="hide-sm">🔒 1 speaker / turn</span>
    </div>
    <div class="messages" id="messages"></div>
    <div class="typing" id="typing">
      <div class="typing-dots"><span></span><span></span><span></span></div>
      <span id="typingText">agent đang soạn…</span>
    </div>
    <div class="err" id="err"></div>
    <div class="composer">
      <textarea id="input" rows="1" placeholder="Nhắn như operator… Enter gửi · Shift+Enter xuống dòng"></textarea>
      <button class="send-btn" id="btnSend" title="Gửi">➤</button>
    </div>
  </main>
</div>
<script>
const $ = (id) => document.getElementById(id);
let state = null;
let autoScroll = true;
let filterQ = "";

const THEME_KEY = "crewlab-ui-theme";
const MOBILE_MQ = window.matchMedia("(max-width: 860px)");

function setSideOpen(open) {
  document.body.classList.toggle("side-open", !!open);
  const btn = $("btnOpenSide");
  if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
  const bd = $("sideBackdrop");
  if (bd) bd.setAttribute("aria-hidden", open ? "false" : "true");
}
function openSide() { setSideOpen(true); }
function closeSide() { setSideOpen(false); }
function toggleSide() { setSideOpen(!document.body.classList.contains("side-open")); }

function applyTheme(name) {
  const t = name || "telegram";
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(THEME_KEY, t);
  document.querySelectorAll(".theme-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.theme === t);
  });
  // Sync browser chrome color with theme bg
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    if (bg) meta.setAttribute("content", bg);
  }
}
applyTheme(localStorage.getItem(THEME_KEY) || "telegram");
document.querySelectorAll(".theme-btn").forEach(b => {
  b.addEventListener("click", () => applyTheme(b.dataset.theme));
});
$("btnOpenSide") && $("btnOpenSide").addEventListener("click", toggleSide);
$("btnCloseSide") && $("btnCloseSide").addEventListener("click", closeSide);
$("sideBackdrop") && $("sideBackdrop").addEventListener("click", closeSide);
MOBILE_MQ.addEventListener("change", (e) => { if (!e.matches) closeSide(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.body.classList.contains("side-open")) closeSide();
});

function initials(id) {
  if (!id) return "?";
  const s = String(id);
  return s.length <= 2 ? s.toUpperCase() : s.slice(0, 2).toUpperCase();
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}
function fmtTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
    if (isNaN(d.getTime())) return iso.slice(11, 16) || iso;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function renderRoster(s) {
  const el = $("roster");
  el.innerHTML = "";
  const next = s.next_speaker;
  const speaking = s.turn_agent;
  const q = filterQ.toLowerCase();
  (s.assignments || []).forEach(a => {
    const hay = `${a.id} ${a.role} ${a.task_id} ${a.task_title} ${a.backend}`.toLowerCase();
    if (q && !hay.includes(q)) return;
    const div = document.createElement("div");
    div.className = "agent-card"
      + (a.id === next ? " next" : "")
      + (a.id === speaking ? " speaking" : "");
    const online = a.backend_available || a.backend === "dry-run" || a.backend === "manual";
    const dotCls = a.id === speaking ? "busy" : (online ? "on" : "");
    div.innerHTML = `
      <div class="av-wrap">
        <div class="avatar" style="background:${a.color}">${initials(a.id)}</div>
        <span class="dot ${dotCls}"></span>
      </div>
      <div class="agent-meta">
        <div class="name-row">
          <div class="name">${esc(a.id)}${a.manager ? " ★" : ""}</div>
          <span class="st ${esc(a.status)}">${esc(a.status)}</span>
        </div>
        <div class="role">${esc(a.role)} · ${esc(a.backend)}${online ? "" : " · offline"}</div>
        <div class="task"><b>Task:</b> ${esc(a.task_id)} — ${esc(a.task_title || "")}</div>
      </div>`;
    div.title = (a.mission || "") + (a.expected_output ? "\nExpected: " + a.expected_output : "");
    div.onclick = () => {
      $("input").value = `@${a.id} `;
      $("input").focus();
      if (MOBILE_MQ.matches) closeSide();
    };
    el.appendChild(div);
  });
}

function renderTopAvatars(s) {
  const el = $("topAvatars");
  el.innerHTML = "";
  (s.assignments || []).slice(0, 5).forEach(a => {
    const d = document.createElement("div");
    d.className = "t-av";
    d.style.background = a.color;
    d.textContent = initials(a.id);
    d.title = `${a.id} → ${a.task_id}`;
    el.appendChild(d);
  });
}

function renderMessages(s) {
  const box = $("messages");
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
  box.innerHTML = "";
  const msgs = s.messages || [];
  if (!msgs.length) {
    box.innerHTML = '<div class="day-sep"><span>Chưa có tin — gửi tin hoặc Next turn</span></div>';
    return;
  }
  box.innerHTML = '<div class="day-sep"><span>Phòng chat crew · full history</span></div>';
  let prevAgent = null;
  msgs.forEach(m => {
    const agent = m.agent || "?";
    const isOp = agent === "operator";
    const isSys = agent === "system" || m.kind === "system" || m.kind === "turn" || m.kind === "status";
    const stack = !isSys && !isOp && agent === prevAgent;
    const row = document.createElement("div");
    row.className = "row"
      + (isOp ? " me" : "")
      + (isSys ? " sys" : "")
      + (stack ? " stack" : "");
    const color = m.color || "#636E72";
    const av = isSys ? "" : `<div class="av" style="background:${color}">${initials(agent)}</div>`;
    const name = (isSys || isOp || stack) ? ""
      : `<div class="b-name" style="color:${color}">${esc(agent)}${m.role ? " · " + esc(m.role) : ""}</div>`;
    const task = m.task_id ? `<div class="b-task">📋 ${esc(m.task_id)}</div>` : "";
    const kind = m.kind && m.kind !== "message" && m.kind !== "agent"
      ? `<span class="assign-chip">${esc(m.kind)}</span>` : "";
    row.innerHTML = `${av}<div class="bubble">${name}<div class="b-text">${esc(m.text)}</div>${task}<div class="b-meta"><span>${esc(fmtTime(m.at))}${kind}</span></div></div>`;
    box.appendChild(row);
    prevAgent = isSys ? null : agent;
  });
  if (autoScroll || nearBottom) box.scrollTop = box.scrollHeight;
}

function render(s) {
  state = s;
  $("crewName").textContent = s.crew || "CrewLab";
  $("crewGoal").textContent = s.goal || "";
  $("processBadge").textContent = "process · " + (s.process || "?");
  const sb = $("statusBadge");
  if (s.speaking) { sb.textContent = "🎙️ Agent đang nói"; }
  else if (s.complete) { sb.textContent = "✅ Project complete"; }
  else { sb.textContent = `💬 ${(s.message_count || 0)} tin nhắn`; }
  $("roomTitle").textContent = (s.crew || "Room") + " · multi-CLI";
  const queue = (s.turn_order || []).join(" → ");
  $("turnInfo").innerHTML = s.next_speaker
    ? `Lượt kế: <strong>${esc(s.next_speaker)}</strong>` + (queue ? ` · hàng đợi ${esc(queue)}` : "")
    : (s.complete ? "Đã ship — không còn task mở" : "Không còn agent sẵn sàng");
  $("btnNext").disabled = !!s.speaking || !!s.complete || !s.next_speaker;
  $("btnDry").disabled = !!s.speaking || !!s.complete || !s.next_speaker;
  $("err").textContent = s.last_error || "";
  $("foot").textContent = (s.project_dir || "") + " · full transcript mỗi agent";
  const typing = $("typing");
  if (s.speaking && s.turn_agent) {
    typing.classList.add("show");
    $("typingText").textContent = s.turn_agent + " đang soạn…";
  } else {
    typing.classList.remove("show");
  }
  renderTopAvatars(s);
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
  $("typing").classList.add("show");
  $("typingText").textContent = dry ? "dry-run…" : "đang gọi CLI…";
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
$("filter").addEventListener("input", (e) => {
  filterQ = e.target.value || "";
  if (state) renderRoster(state);
});
$("messages").addEventListener("scroll", () => {
  const box = $("messages");
  autoScroll = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
});

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""

ROOM_HTML = _ROOM_HTML_HEAD + theme_css_block() + "\n" + _ROOM_HTML_BODY


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
    print("  themes: Telegram | Messenger | Zalo (switch in UI)")
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
