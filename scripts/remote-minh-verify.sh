#!/usr/bin/env bash
# Fast verify: no interactive CLI --version (can hang npm.cmd on MSYS)
set -u
export PATH="/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts:/c/Users/bachq/AppData/Local/hermes/bin:/c/Users/bachq/AppData/Roaming/npm:/c/Users/bachq/AppData/Local/hermes/node:/c/Users/bachq/AppData/Local/hermes/git/cmd:$PATH"
HERMES_PY="/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
cd /c/Dev/CrewLab
LOG=runs/minh-verify.log
mkdir -p runs
{
echo "=== verify $(date -Iseconds) ==="
echo "=== files ==="
ls -la /c/Users/bachq/AppData/Roaming/npm/ | head -40
echo "=== command -v ==="
for c in hermes grok codex claude openclaw opencode cursor node npm git; do
  if command -v "$c" >/dev/null 2>&1; then echo "OK $c $(command -v $c)"; else echo "MISS $c"; fi
done
"$HERMES_PY" -m pip install -e ".[dev]" -q
echo "=== pytest ==="
"$HERMES_PY" -m pytest -q --tb=line
echo "=== smoke ==="
"$HERMES_PY" -m crewlab smoke
echo "=== backends resolve ==="
"$HERMES_PY" - <<'PY'
from crewlab.backends import resolve_agent_backend, BUILTIN_BACKENDS
for bid in sorted(BUILTIN_BACKENDS):
    r = resolve_agent_backend({"id": "t", "backend": bid, "cli": "echo ok" if bid in ("shell","custom") else None})
    print(f"{bid:10} available={r.available} detect={r.detect_hit} reason={r.reason[:80]}")
PY
echo "=== dry room turns ==="
rm -f examples/multi-cli-room/STATE.yaml examples/multi-cli-room/chat.jsonl examples/multi-cli-room/CHAT_LOG.md examples/multi-cli-room/ROOM.json 2>/dev/null || true
rm -rf examples/multi-cli-room/runs 2>/dev/null || true
for i in 1 2 3 4 5; do
  echo turn_$i
  "$HERMES_PY" -m crewlab speak examples/multi-cli-room --dry-run --auto-complete || true
done
"$HERMES_PY" -m crewlab status examples/multi-cli-room
echo "=== UI ==="
# kill port 8765 via powershell one-liner
"$HERMES_PY" - <<'PY'
import subprocess, time, json, urllib.request, os
from pathlib import Path
# kill listeners
try:
    out = subprocess.check_output("netstat -ano", shell=True, text=True, errors="replace")
    for line in out.splitlines():
        if ":8765" in line and "LISTENING" in line:
            pid = line.split()[-1]
            if pid.isdigit() and pid != "0":
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
except Exception as e:
    print("kill", e)
py = r"C:\Users\bachq\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
wd = r"C:\Dev\CrewLab"
log = Path(wd) / "runs"
log.mkdir(exist_ok=True)
# start UI
creationflags = 0x00000008  # DETACHED_PROCESS
si = subprocess.STARTUPINFO()
si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
p = subprocess.Popen(
    [py, "-m", "crewlab", "ui", "examples/multi-cli-room", "--host", "0.0.0.0", "--port", "8765", "--no-browser"],
    cwd=wd,
    stdout=open(log/"ui-8765.out.log","w"),
    stderr=open(log/"ui-8765.err.log","w"),
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008 if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0,
)
print("ui_pid", p.pid)
for _ in range(20):
    time.sleep(0.5)
    try:
        print(urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=2).read().decode())
        break
    except Exception:
        pass
else:
    print("UI health fail")
# dry speak API twice
for _ in range(2):
    req = urllib.request.Request(
        "http://127.0.0.1:8765/api/speak",
        data=json.dumps({"dry_run": True}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        print(urllib.request.urlopen(req, timeout=30).read().decode()[:220])
    except Exception as e:
        print("api speak", e)
print("DONE")
PY
echo "DONE_ALL $(date -Iseconds)"
} | tee "$LOG"
