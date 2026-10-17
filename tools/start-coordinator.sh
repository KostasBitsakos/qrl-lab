#!/usr/bin/env bash
# Start (or re-attach to) the QRL-Lab tmux session "lab" on the VM:
#   window "coordinator": Claude Code with Remote Control and the lab-bridge plugin (dashboard -> coordinator)
#   window "dashboard":   Streamlit on 127.0.0.1:8501 (reach it from the laptop through an SSH tunnel)
#   window "health":      tools/health_watch.py, writes .lab/health.json for the dashboard banner (no LLM)
# Usage:
#   tools/start-coordinator.sh          start, or attach if already running (adds a missing dashboard window)
#   tools/start-coordinator.sh resume   start the coordinator continuing the most recent conversation
#   tools/start-coordinator.sh [resume] --detached   same, but never attach (used by tools/boot_recover.sh)
# Detach without stopping anything: Ctrl+b then d.
set -euo pipefail

LAB="${QRL_LAB_DIR:-$HOME/qrl-lab}"
TMUX_SESSION="lab"
RC_NAME="qrl-lab"

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "Node >= 18.18 is needed by the Codex plugin; found: $(node --version 2>/dev/null || echo none)." >&2
  echo "Run: nvm install --lts" >&2
  exit 1
fi

mkdir -p "$LAB/.lab"

RESUME=0; DETACHED=0
for arg in "$@"; do
  case "$arg" in
    resume) RESUME=1 ;;
    --detached) DETACHED=1 ;;
  esac
done
finish() { if [ "$DETACHED" = 1 ]; then exit 0; else exec tmux attach -t "$TMUX_SESSION"; fi; }

start_dashboard_window() {
  if [ -x "$LAB/.venv/bin/streamlit" ] && ! tmux list-windows -t "$TMUX_SESSION" -F '#W' | grep -qx dashboard; then
    tmux new-window -d -t "$TMUX_SESSION" -n dashboard -c "$LAB" \
      "./.venv/bin/streamlit run dashboard/app.py; exec bash"
  fi
}

start_health_window() {
  if ! tmux list-windows -t "$TMUX_SESSION" -F '#W' | grep -qx health; then
    tmux new-window -d -t "$TMUX_SESSION" -n health -c "$LAB" \
      "python3 tools/health_watch.py; exec bash"
  fi
}

if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  start_dashboard_window
  start_health_window
  finish
fi

CONT=""
[ "$RESUME" = 1 ] && CONT="--continue"

tmux new-session -d -s "$TMUX_SESSION" -n coordinator -c "$LAB" \
  "claude $CONT --remote-control $RC_NAME --plugin-dir ./tools/lab-bridge; exec bash"
start_dashboard_window
start_health_window
finish
