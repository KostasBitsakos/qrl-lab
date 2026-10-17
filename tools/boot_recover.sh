#!/usr/bin/env bash
# Run once after a VM boot (cron @reboot): record the outage, restart the lab detached (conversation resumed),
# make sure the web terminal is up, then post a Greek status message to the dashboard. Idempotent per boot.
# Crontab line:  @reboot sleep 30 && /home/ubuntu/qrl-lab/tools/boot_recover.sh  # qrl-lab boot
# QRL_BOOT_DRYRUN=1: no tmux start/kill, no dashboard post, outages and flag go to a temp dir (printed at the end).
set -u
LAB="${QRL_LAB_DIR:-$HOME/qrl-lab}"
export QRL_LAB_DIR="$LAB"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"   # cron's PATH is minimal; claude lives in ~/.local/bin
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"                      # node for claude and the Codex plugin
mkdir -p "$LAB/.lab"
LOG="$LAB/.lab/boot_recover.log"
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }
DRY="${QRL_BOOT_DRYRUN:-0}"

if [ "$DRY" = 1 ]; then
  T="${QRL_BOOT_DRYRUN_DIR:-$(mktemp -d)}"
  export QRL_OUTAGES_FILE="$T/outages.jsonl" QRL_RECOVERY_FLAG="$T/recovery_flag.json"
  say "DRY RUN: outputs in $T"
else
  exec 9> "$LAB/.lab/boot_recover.lock"
  flock -n 9 || { say "another boot_recover is running"; exit 0; }
fi

cd "$LAB" || exit 1
say "start (boot $(uptime -s 2>/dev/null))"
rec=$(python3 tools/outage.py record 2>>"$LOG") || { say "record failed"; rec=""; }
say "record: $rec"
case "$rec" in *'"created": false'*) say "already handled this boot"; [ "$DRY" = 1 ] || exit 0 ;; esac

if [ "$DRY" = 1 ]; then
  say "dry run: would run tools/start-coordinator.sh resume --detached and start web_terminal"
else
  ./tools/start-coordinator.sh resume --detached >> "$LOG" 2>&1 && say "lab session ensured" || say "start-coordinator failed"
  python3 - >> "$LOG" 2>&1 <<'PY'
import sys; sys.path.insert(0, "tools")
import web_terminal
print("web_terminal:", web_terminal.start())
PY
  sleep 10   # let the windows come up before listing them
fi

if [ "$DRY" = 1 ]; then
  python3 tools/outage.py announce --dry | tee -a "$LOG"
  echo "dry-run files: $T"
else
  python3 tools/outage.py announce >> "$LOG" 2>&1 && say "announced" || say "announce failed"
fi
exit 0
