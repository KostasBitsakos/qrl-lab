#!/usr/bin/env bash
# Restart the tmux windows `health` and `dashboard` of session "lab" when they are missing (or, for `health`,
# when its heartbeat .lab/health_watch.heartbeat is older than STALE seconds). Idempotent, no LLM, never starts
# the coordinator itself. Run from cron:  * * * * * /home/ubuntu/qrl-lab/tools/watchdog.sh
set -u
LAB="${QRL_LAB_DIR:-$HOME/qrl-lab}"
S="${QRL_TMUX_SESSION:-lab}"
STALE="${QRL_WATCHDOG_STALE:-180}"
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
LOG="$LAB/.lab/watchdog.log"
mkdir -p "$LAB/.lab"
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# Heartbeat for tools/boot_recover.sh (last moment the VM was up). If the VM rebooted since the last beat, keep that
# value in heartbeat_pre_boot first, so a beat written before boot_recover.sh runs cannot hide the outage.
HB="$LAB/.lab/heartbeat"
btime=$(awk '/^btime/{print $2}' /proc/stat 2>/dev/null)
old=$(cat "$HB" 2>/dev/null | head -c 20)
if [ -n "$btime" ] && [ -n "$old" ] && [ "$old" -lt "$btime" ] 2>/dev/null; then
  echo "$old" > "$LAB/.lab/heartbeat_pre_boot"
fi
date +%s > "$HB.tmp" && mv "$HB.tmp" "$HB"

tmux has-session -t "$S" 2>/dev/null || exit 0   # no session: the researcher has not started the lab; do nothing
have() { tmux list-windows -t "$S" -F '#W' | grep -qx "$1"; }

if have health; then
  hb="$LAB/.lab/health_watch.heartbeat"
  if [ -f "$hb" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$hb") ))
    if [ "$age" -gt "$STALE" ]; then
      say "health heartbeat stale (${age}s): recreating window"
      tmux kill-window -t "$S:health" 2>/dev/null
    fi
  fi
fi
if ! have health; then
  tmux new-window -d -t "$S" -n health -c "$LAB" "python3 tools/health_watch.py; exec bash" && say "started window health"
fi
if [ -x "$LAB/.venv/bin/streamlit" ] && ! have dashboard; then
  tmux new-window -d -t "$S" -n dashboard -c "$LAB" "./.venv/bin/streamlit run dashboard/app.py; exec bash" \
    && say "started window dashboard"
fi
exit 0
