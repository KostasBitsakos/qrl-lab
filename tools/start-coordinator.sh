#!/usr/bin/env bash
# Start the QRL-Lab coordinator in tmux on the VM, or attach if it is already running.
#   tools/start-coordinator.sh          start a new coordinator session (or attach)
#   tools/start-coordinator.sh resume   continue the most recent conversation in this directory
# The session is reachable from claude.ai/code and the Claude app through Remote Control.
set -euo pipefail

LAB="${QRL_LAB_DIR:-$HOME/qrl-lab}"
TMUX_SESSION="lab"
RC_NAME="qrl-lab"

if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  exec tmux attach -t "$TMUX_SESSION"
fi

# Node from nvm (needed by the Codex CLI and the Codex plugin); does not touch system Node or Python envs.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

mkdir -p "$LAB/.lab"
touch "$LAB/.lab/inbox.jsonl" "$LAB/.lab/requests.jsonl" "$LAB/.lab/events.jsonl"

CONT=""
[ "${1:-}" = "resume" ] && CONT="--continue"

tmux new-session -d -s "$TMUX_SESSION" -n coordinator -c "$LAB" \
  "claude $CONT --remote-control $RC_NAME --plugin-dir ./tools/lab-bridge; exec bash"

# Dashboard window, once the engineer has built it.
if [ -f "$LAB/dashboard/app.py" ]; then
  tmux new-window -t "$TMUX_SESSION" -n dashboard -c "$LAB" \
    "./.venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501; exec bash"
fi

exec tmux attach -t "$TMUX_SESSION"
