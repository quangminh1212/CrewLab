"""Probe CrewLab backend availability on Minh (run with PYTHONPATH=/c/Dev/CrewLab)."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from crewlab.backends import BUILTIN_BACKENDS, resolve_agent_backend

print("=== backend resolve ===")
rows = []
for bid in sorted(BUILTIN_BACKENDS):
    r = resolve_agent_backend(
        {
            "id": "a",
            "backend": bid,
            "cli": "echo ok" if bid in {"shell", "custom"} else None,
        }
    )
    rows.append(
        {
            "id": bid,
            "available": r.available,
            "detect": r.detect_hit,
            "reason": r.reason,
        }
    )
    print(f"{bid:10} available={r.available} detect={r.detect_hit or '-'} {r.reason[:70]}")

# dry multi speak
print("=== dry speak x3 ===")
from crewlab.cli import main

os.chdir(r"C:\Dev\CrewLab")
# reset room artifacts lightly
ex = Path("examples/multi-cli-room")
for name in ("STATE.yaml", "chat.jsonl", "CHAT_LOG.md", "ROOM.json", "PLAN.md", "RUN_LOG.md"):
    p = ex / name
    if p.exists():
        p.unlink()
for i in range(3):
    rc = main(["speak", str(ex), "--dry-run", "--auto-complete"])
    print(f"turn{i+1} rc={rc}")

# UI health / restart
print("=== ui ===")
try:
    out = subprocess.check_output("netstat -ano", shell=True, text=True, errors="replace")
    for line in out.splitlines():
        if ":8765" in line and "LISTENING" in line:
            pid = line.split()[-1]
            if pid.isdigit() and int(pid) > 0:
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
except Exception as e:
    print("kill", e)

py = r"C:\Users\bachq\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
log = Path(r"C:\Dev\CrewLab\runs")
log.mkdir(parents=True, exist_ok=True)
flags = 0
if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
    flags |= subprocess.CREATE_NEW_PROCESS_GROUP
if hasattr(subprocess, "DETACHED_PROCESS"):
    flags |= subprocess.DETACHED_PROCESS
else:
    flags |= 0x00000008
p = subprocess.Popen(
    [
        py,
        "-m",
        "crewlab",
        "ui",
        "examples/multi-cli-room",
        "--host",
        "0.0.0.0",
        "--port",
        "8765",
        "--no-browser",
    ],
    cwd=r"C:\Dev\CrewLab",
    stdout=open(log / "ui-8765.out.log", "w", encoding="utf-8"),
    stderr=open(log / "ui-8765.err.log", "w", encoding="utf-8"),
    creationflags=flags,
)
print("ui_pid", p.pid)
ok = False
for _ in range(25):
    time.sleep(0.4)
    try:
        body = urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=2).read().decode()
        print("health", body)
        ok = True
        break
    except Exception:
        pass
if not ok:
    print("UI_FAIL")
else:
    req = urllib.request.Request(
        "http://127.0.0.1:8765/api/speak",
        data=json.dumps({"dry_run": True}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print("api_speak", urllib.request.urlopen(req, timeout=30).read().decode()[:200])

print("SUMMARY_AVAILABLE", [x["id"] for x in rows if x["available"] or x["id"] in ("manual", "dry-run")])
print("SUMMARY_MISSING", [x["id"] for x in rows if not x["available"] and x["id"] not in ("manual", "dry-run")])
print("DONE")
