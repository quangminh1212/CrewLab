#!/usr/bin/env bash
# Install + smoke-test CLIs needed by CrewLab multi-agent room on Minh worker.
set -u
LOG="${LOG:-/c/Dev/CrewLab/runs/minh-cli-setup.log}"
mkdir -p "$(dirname "$LOG")" /c/Dev/CrewLab/runs
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date -Iseconds) Minh CLI setup ==="
export PATH="/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts:/c/Users/bachq/AppData/Local/hermes/bin:/c/Users/bachq/AppData/Local/hermes/node:/c/Users/bachq/AppData/Local/hermes/git/cmd:/c/Users/bachq/AppData/Local/hermes/git/bin:/c/Program Files/nodejs:/c/Users/bachq/AppData/Roaming/npm:$PATH"

HERMES_PY="/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
NPM_BIN="/c/Users/bachq/AppData/Local/hermes/node/npm.cmd"
NODE_BIN="/c/Users/bachq/AppData/Local/hermes/node/node.exe"
# Prefer Windows npm if hermes npm broken
if [ ! -f "$NPM_BIN" ] || ! "$NPM_BIN" -v >/dev/null 2>&1; then
  if command -v npm >/dev/null 2>&1; then NPM_BIN="$(command -v npm)"; fi
fi
if [ ! -f "$NODE_BIN" ]; then
  if command -v node >/dev/null 2>&1; then NODE_BIN="$(command -v node)"; fi
fi

echo "node=$NODE_BIN"
echo "npm=$NPM_BIN"
"$NODE_BIN" -v 2>&1 || true
"$NPM_BIN" -v 2>&1 || true
"$HERMES_PY" --version 2>&1 || true
hermes --version 2>&1 | head -5 || true

echo "=== before: which tools ==="
for c in hermes grok codex claude openclaw opencode cursor cursor-agent node npm git; do
  if command -v "$c" >/dev/null 2>&1; then
    echo "OK  $c -> $(command -v "$c")"
  else
    echo "MISS $c"
  fi
done

# Global npm prefix user-writable
export npm_config_prefix="/c/Users/bachq/AppData/Roaming/npm"
mkdir -p "$npm_config_prefix" "/c/Users/bachq/AppData/Roaming/npm"
export PATH="$npm_config_prefix:$npm_config_prefix/bin:$PATH"

install_npm_pkg() {
  local pkg="$1"
  echo "--- npm i -g $pkg ---"
  if "$NPM_BIN" install -g "$pkg" ; then
    echo "INSTALLED $pkg"
  else
    echo "FAIL install $pkg (continue)"
  fi
}

# Claude Code CLI
install_npm_pkg "@anthropic-ai/claude-code"

# OpenAI Codex CLI (official package name variants)
install_npm_pkg "@openai/codex" || true
install_npm_pkg "codex" || true

# OpenCode CLI if published
install_npm_pkg "opencode-ai" || true
install_npm_pkg "@opencode-ai/cli" || true

# Refresh PATH after npm globals
export PATH="/c/Users/bachq/AppData/Roaming/npm:/c/Users/bachq/AppData/Roaming/npm/bin:$PATH"

# Symlink / shim helpers into hermes bin for consistent PATH
HERMES_BIN="/c/Users/bachq/AppData/Local/hermes/bin"
mkdir -p "$HERMES_BIN"

# Ensure hermes shim
if [ -x "/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe" ]; then
  cp -f "/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe" "$HERMES_BIN/hermes.exe" 2>/dev/null || true
fi

# Copy npm global .cmd into hermes bin when present
for name in claude codex opencode; do
  for cand in \
    "/c/Users/bachq/AppData/Roaming/npm/${name}.cmd" \
    "/c/Users/bachq/AppData/Roaming/npm/${name}" \
    "/c/Users/bachq/AppData/Local/hermes/node/${name}.cmd"
  do
    if [ -f "$cand" ]; then
      cp -f "$cand" "$HERMES_BIN/" 2>/dev/null || true
      echo "shim $name from $cand"
      break
    fi
  done
done

# Cursor agent: link if installed
for cand in \
  "/c/Users/bachq/AppData/Local/Programs/cursor/resources/app/bin/cursor.cmd" \
  "/c/Users/bachq/AppData/Local/Programs/cursor/Cursor.exe" \
  "/c/Program Files/cursor/resources/app/bin/cursor.cmd"
do
  if [ -f "$cand" ]; then
    echo "FOUND cursor at $cand"
    # create thin bat shim
    cat > "$HERMES_BIN/cursor.cmd" <<EOF
@echo off
"$cand" %*
EOF
    break
  fi
done

# Grok CLI: try npm / winget / known path
if ! command -v grok >/dev/null 2>&1; then
  install_npm_pkg "@xai/grok" || true
  install_npm_pkg "grok-cli" || true
  # winget (may need UI interaction - try silent)
  winget install --id xAI.Grok -e --accept-package-agreements --accept-source-agreements 2>&1 | tail -20 || true
fi

# OpenClaw: npm if exists
install_npm_pkg "openclaw" || true
install_npm_pkg "@openclaw/cli" || true

echo "=== after: which tools ==="
export PATH="/c/Users/bachq/AppData/Local/hermes/hermes-agent/venv/Scripts:/c/Users/bachq/AppData/Local/hermes/bin:/c/Users/bachq/AppData/Roaming/npm:/c/Users/bachq/AppData/Roaming/npm/bin:/c/Users/bachq/AppData/Local/hermes/node:$PATH"
for c in hermes grok codex claude openclaw opencode cursor cursor-agent node npm git; do
  if command -v "$c" >/dev/null 2>&1; then
    echo "OK  $c -> $(command -v "$c")"
    "$c" --version 2>&1 | head -2 || "$c" -v 2>&1 | head -2 || true
  else
    echo "MISS $c"
  fi
done

# List npm global
echo "=== npm root -g ==="
"$NPM_BIN" root -g 2>&1 || true
"$NPM_BIN" list -g --depth=0 2>&1 | head -40 || true

echo "=== CrewLab reinstall + full tests ==="
cd /c/Dev/CrewLab
git fetch origin
git checkout master
git pull --ff-only origin master
"$HERMES_PY" -m pip install -e ".[dev]" -q
"$HERMES_PY" -m pytest -q --tb=line
"$HERMES_PY" -m crewlab smoke
"$HERMES_PY" -m crewlab backends

# Probe each backend resolve
"$HERMES_PY" - <<'PY'
from crewlab.backends import resolve_agent_backend, BUILTIN_BACKENDS
print("backend probe:")
for bid in sorted(BUILTIN_BACKENDS):
    r = resolve_agent_backend({"id": "t", "backend": bid, "cli": "echo hi" if bid in ("shell","custom") else None})
    print(f"  {bid:10} available={r.available} reason={r.reason[:60] if r.reason else ''}")
PY

# End-to-end room: dry turns for all sequential agents
echo "=== room multi-turn dry ==="
"$HERMES_PY" -m crewlab speak examples/multi-cli-room --dry-run --auto-complete || true
"$HERMES_PY" -m crewlab speak examples/multi-cli-room --dry-run --auto-complete || true
"$HERMES_PY" -m crewlab speak examples/multi-cli-room --dry-run --auto-complete || true

# Live hermes speak if available (short timeout)
echo "=== live hermes one-shot smoke (optional) ==="
if command -v hermes >/dev/null 2>&1; then
  timeout 45 hermes chat -q "Reply with exactly: HERMES_OK" 2>&1 | head -30 || echo "hermes live timeout/fail (keys/network?)"
else
  echo "hermes missing"
fi

# Restart UI bound to 0.0.0.0:8765
echo "=== restart UI ==="
# kill listen 8765
netstat -ano | grep ':8765' | grep LISTENING | while read -r line; do
  pid=$(echo "$line" | awk '{print $NF}')
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    taskkill //F //PID "$pid" 2>/dev/null || true
  fi
done
export PYTHONUNBUFFERED=1
nohup "$HERMES_PY" -m crewlab ui examples/multi-cli-room --host 0.0.0.0 --port 8765 --no-browser \
  >runs/ui-8765.out.log 2>runs/ui-8765.err.log &
sleep 3
curl -sS -m 5 http://127.0.0.1:8765/api/health || true
echo
curl -sS -m 5 http://127.0.0.1:8765/api/state | head -c 300 || true
echo
netsh advfirewall firewall add rule name="CrewLab-UI-8765" dir=in action=allow protocol=TCP localport=8765 >/dev/null 2>&1 || true

echo "=== SUMMARY ==="
"$HERMES_PY" - <<'PY'
from crewlab.backends import resolve_agent_backend, BUILTIN_BACKENDS
ok, miss = [], []
for bid in ("hermes","grok","codex","claude","openclaw","opencode","cursor","manual","dry-run"):
    r = resolve_agent_backend({"id":"x","backend":bid})
    (ok if r.available or bid in ("manual","dry-run") else miss).append(bid)
print("available:", ", ".join(ok))
print("missing_cli:", ", ".join(miss))
PY
echo "DONE $(date -Iseconds)"
