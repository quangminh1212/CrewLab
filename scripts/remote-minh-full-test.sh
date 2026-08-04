#!/usr/bin/env bash
# ALL tests run ON Minh only. View UI from browser: http://192.168.1.2:8765/
set -u
export PATH="${HOME}/AppData/Local/hermes/hermes-agent/venv/Scripts:${HOME}/AppData/Local/hermes/bin:${HOME}/AppData/Roaming/npm:${HOME}/AppData/Local/hermes/node:${HOME}/AppData/Local/Programs/cursor/resources/app/bin:/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts:/c/Users/bachq/AppData/Local/hermes/bin:$PATH"
export PYTHONPATH=/c/Dev/CrewLab
resolve_crewlab_py() {
  local cands=(
    "/c/Dev/CrewLab/.venv/Scripts/python.exe"
    "${HOME}/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
    "/c/Users/Minh/AppData/Roaming/uv/python/cpython-3.11.15-windows-x86_64-none/python.exe"
    "/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
  )
  local c
  for c in "${cands[@]}"; do
    if [ -f "$c" ] && "$c" -c "import sys" >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  command -v python 2>/dev/null || echo "python"
}
PY="$(resolve_crewlab_py)"
export CREWLAB_PY="$PY"
cd /c/Dev/CrewLab
mkdir -p runs
LOG=runs/minh-full-remote-test.log
exec > >(tee "$LOG") 2>&1

echo "=== HOST $(hostname) $(whoami) $(date -Iseconds) ==="
echo "=== PY $PY ==="
echo "=== CLI which ==="
for c in hermes grok codex claude opencode cursor node npm git; do
  if command -v "$c" >/dev/null 2>&1; then
    echo "OK $c -> $(command -v "$c")"
  else
    echo "MISS $c"
  fi
done

echo "=== pytest ==="
"$PY" -m pytest -q --tb=line

echo "=== smoke ==="
"$PY" -m crewlab smoke

echo "=== backends resolve ==="
"$PY" - <<'PY'
from crewlab.backends import resolve_agent_backend, BUILTIN_BACKENDS
for b in sorted(BUILTIN_BACKENDS):
    x = resolve_agent_backend(
        {"id": "a", "backend": b, "cli": "echo 1" if b in ("shell", "custom") else None}
    )
    print(f"{b:10} avail={x.available} hit={x.detect_hit or '-'}")
PY

echo "=== ensure UI (clean room — no pre-complete tasks) ==="
# Wipe room artifacts so browser demo has speakers left
rm -f examples/multi-cli-room/STATE.yaml examples/multi-cli-room/chat.jsonl \
  examples/multi-cli-room/CHAT_LOG.md examples/multi-cli-room/ROOM.json \
  examples/multi-cli-room/PLAN.md examples/multi-cli-room/RUN_LOG.md \
  examples/multi-cli-room/MEETING_LOG.md examples/multi-cli-room/last-meeting.json 2>/dev/null || true
rm -rf examples/multi-cli-room/runs 2>/dev/null || true
"$PY" - <<'PY'
import subprocess, time, urllib.request
from pathlib import Path

# kill :8765
try:
    out = subprocess.check_output("netstat -ano", shell=True, text=True, errors="replace")
    for line in out.splitlines():
        if ":8765" in line and "LISTENING" in line:
            pid = line.split()[-1]
            if pid.isdigit() and int(pid) > 0:
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
except Exception as e:
    print("kill", e)

import os
py = os.environ.get("CREWLAB_PY") or r"C:\Dev\CrewLab\.venv\Scripts\python.exe"
if not os.path.isfile(py):
    for cand in (
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"),
        r"C:\Users\Minh\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe",
        r"C:\Users\bachq\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe",
    ):
        if os.path.isfile(cand):
            py = cand
            break
wd = r"C:\Dev\CrewLab"
log = Path(wd) / "runs"
log.mkdir(parents=True, exist_ok=True)
flags = 0
if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
    flags |= subprocess.CREATE_NEW_PROCESS_GROUP
if hasattr(subprocess, "DETACHED_PROCESS"):
    flags |= subprocess.DETACHED_PROCESS
else:
    flags |= 0x00000008
p = subprocess.Popen(
    [py, "-m", "crewlab", "ui", "examples/multi-cli-room",
     "--host", "0.0.0.0", "--port", "8765", "--no-browser"],
    cwd=wd,
    stdout=open(log / "ui-8765.out.log", "w", encoding="utf-8"),
    stderr=open(log / "ui-8765.err.log", "w", encoding="utf-8"),
    creationflags=flags,
)
print("ui_pid", p.pid)
for _ in range(30):
    time.sleep(0.4)
    try:
        print(urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=2).read().decode())
        break
    except Exception:
        pass
else:
    raise SystemExit("UI failed to start on Minh")
PY

echo "=== UI health localhost ==="
curl -sS -m 5 http://127.0.0.1:8765/api/health
echo

echo "=== visible chat actions for browser watchers ==="
"$PY" - <<'PY'
import json, time, urllib.request

base = "http://127.0.0.1:8765"

def post(path, obj):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

print("msg1", post("/api/message", {
    "text": "REMOTE TEST only on Minh (DESKTOP-G63F7QO). NOT GHC. Dry turns lan luot — xem bubble tren browser."
})["ok"])
time.sleep(1.2)
for i in range(3):
    r = post("/api/speak", {"dry_run": True})
    print(f"turn{i+1}", r.get("agent"), r.get("mode"), "next=", r.get("next_speaker"))
    time.sleep(1.5)
print("msg2", post("/api/message", {
    "text": "REMOTE TEST xong tren Minh. Theme Telegram/Messenger/Zalo. Bam Next turn de tiep."
})["ok"])
with urllib.request.urlopen(base + "/api/state", timeout=10) as resp:
    st = json.loads(resp.read().decode())
print("state msgs=", st.get("message_count"), "next=", st.get("next_speaker"),
      "agents=", len(st.get("assignments") or []))
for a in st.get("assignments") or []:
    print(" ", a.get("id"), "->", a.get("task_id"), a.get("status"), a.get("backend"))
PY

echo "=== DONE_REMOTE_ONLY on Minh ==="
