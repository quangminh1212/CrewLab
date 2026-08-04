#!/usr/bin/env bash
# Finish CLI PATH shims + full CrewLab tests on Minh (no long winget).
set -u
export PATH="/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts:/c/Users/bachq/AppData/Local/hermes/bin:/c/Users/bachq/AppData/Roaming/npm:/c/Users/bachq/AppData/Roaming/npm/bin:/c/Users/bachq/AppData/Local/hermes/node:/c/Users/bachq/AppData/Local/hermes/git/cmd:$PATH"
HERMES_PY="/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
LOG=/c/Dev/CrewLab/runs/minh-finish-test.log
mkdir -p /c/Dev/CrewLab/runs /c/Users/bachq/AppData/Local/hermes/bin
exec > >(tee -a "$LOG") 2>&1
echo "=== finish $(date -Iseconds) ==="

# Ensure shims
HERMES_BIN=/c/Users/bachq/AppData/Local/hermes/bin
for name in claude codex opencode grok; do
  for cand in \
    "/c/Users/bachq/AppData/Roaming/npm/${name}.cmd" \
    "/c/Users/bachq/AppData/Roaming/npm/${name}"
  do
    if [ -f "$cand" ]; then
      cp -f "$cand" "$HERMES_BIN/" 2>/dev/null || true
      echo "shim $name <- $cand"
      break
    fi
  done
done
# cursor
if [ -f "/c/Users/bachq/AppData/Local/Programs/cursor/resources/app/bin/cursor.cmd" ]; then
  cp -f "/c/Users/bachq/AppData/Local/Programs/cursor/resources/app/bin/cursor.cmd" "$HERMES_BIN/cursor.cmd" 2>/dev/null || true
  echo "shim cursor"
fi

echo "=== which ==="
for c in hermes grok codex claude openclaw opencode cursor node npm git; do
  if command -v "$c" >/dev/null 2>&1; then
    echo "OK  $c -> $(command -v $c)"
    timeout 8 "$c" --version 2>&1 | head -2 || timeout 8 "$c" -v 2>&1 | head -2 || true
  else
    echo "MISS $c"
  fi
done

cd /c/Dev/CrewLab
git fetch origin 2>&1 | tail -3
git pull --ff-only origin master 2>&1 | tail -5
"$HERMES_PY" -m pip install -e ".[dev]" -q
echo "=== pytest ==="
"$HERMES_PY" -m pytest -q --tb=line
echo "=== smoke ==="
"$HERMES_PY" -m crewlab smoke
echo "=== backends ==="
"$HERMES_PY" -m crewlab backends
echo "=== resolve backends ==="
"$HERMES_PY" - <<'PY'
from crewlab.backends import resolve_agent_backend, BUILTIN_BACKENDS
for bid in sorted(BUILTIN_BACKENDS):
    r = resolve_agent_backend({"id": "t", "backend": bid, "cli": "echo ok" if bid in ("shell","custom") else None})
    print(f"{bid:10} available={str(r.available):5} {r.reason[:70]}")
PY

# Multi-turn dry complete room
echo "=== multi dry speak ==="
rm -f examples/multi-cli-room/STATE.yaml examples/multi-cli-room/chat.jsonl examples/multi-cli-room/CHAT_LOG.md examples/multi-cli-room/ROOM.json 2>/dev/null || true
rm -rf examples/multi-cli-room/runs 2>/dev/null || true
for i in 1 2 3 4 5 6; do
  echo "-- turn $i --"
  "$HERMES_PY" -m crewlab speak examples/multi-cli-room --dry-run --auto-complete || break
done
"$HERMES_PY" -m crewlab status examples/multi-cli-room || true

# Live hermes short
echo "=== hermes live ==="
if command -v hermes >/dev/null 2>&1; then
  # hermes wrapper may be broken (OK: command not found) - try .exe
  if [ -x /c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe ]; then
    timeout 60 /c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe chat -q "Reply exactly: HERMES_OK" 2>&1 | head -40 || echo hermes_timeout
  else
    timeout 60 hermes chat -q "Reply exactly: HERMES_OK" 2>&1 | head -40 || echo hermes_timeout
  fi
fi

# Live claude/codex help only (no API burn)
echo "=== claude/codex help ==="
timeout 15 claude --help 2>&1 | head -8 || true
timeout 15 codex --help 2>&1 | head -8 || true
timeout 15 opencode --help 2>&1 | head -8 || true
timeout 15 grok --help 2>&1 | head -8 || true

# Restart UI
echo "=== UI restart ==="
cmd.exe /c "for /f \"tokens=5\" %a in ('netstat -ano ^| findstr :8765 ^| findstr LISTENING') do taskkill /F /PID %a" 2>/dev/null || true
export PYTHONUNBUFFERED=1
nohup "$HERMES_PY" -m crewlab ui examples/multi-cli-room --host 0.0.0.0 --port 8765 --no-browser >runs/ui-8765.out.log 2>runs/ui-8765.err.log &
sleep 3
curl -sS -m 5 http://127.0.0.1:8765/api/health || true
echo
# dry speak API
"$HERMES_PY" - <<'PY'
import json, urllib.request
for dry in (True, True):
    req = urllib.request.Request(
        "http://127.0.0.1:8765/api/speak",
        data=json.dumps({"dry_run": dry}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        print(urllib.request.urlopen(req, timeout=60).read().decode()[:250])
    except Exception as e:
        print("speak err", e)
req = urllib.request.Request(
    "http://127.0.0.1:8765/api/message",
    data=json.dumps({"text": "Minh CLI finish test"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
print(urllib.request.urlopen(req, timeout=15).read().decode()[:200])
PY

echo "=== SUMMARY ==="
"$HERMES_PY" - <<'PY'
from crewlab.backends import resolve_agent_backend
avail, miss = [], []
for bid in ("hermes","grok","codex","claude","openclaw","opencode","cursor","manual","dry-run"):
    r = resolve_agent_backend({"id":"x","backend":bid})
    if r.available or bid in ("manual","dry-run"):
        avail.append(bid)
    else:
        miss.append(bid)
print("available:", ",".join(avail))
print("missing:", ",".join(miss))
PY
echo "DONE $(date -Iseconds)"
