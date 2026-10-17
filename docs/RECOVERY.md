# VM outage recovery

What happens when the VM reboots or loses power (approved as R-20261017-016, option 1).

## Pieces
- `tools/watchdog.sh` (cron, every minute) writes the epoch to `.lab/heartbeat` before anything else. If the VM
  booted since the previous beat, the old value is first copied to `.lab/heartbeat_pre_boot`, so a beat written
  before recovery runs cannot hide the outage.
- `tools/boot_recover.sh` (cron `@reboot`, after `sleep 30`), idempotent per boot (flock + one record per boot time):
  1. `tools/outage.py record` appends `{down_at, boot_at, recovered_at, downtime_s, kind}` to `.lab/outages.jsonl`
     and writes `.lab/recovery_flag.json`. `down_at` is the last heartbeat (+-1 min). `kind` is `reboot` when
     `last -x` shows a shutdown entry between the last heartbeat and the boot, `crash/power` when the log is readable
     but has none, `unknown` otherwise (no heartbeat or no log).
  2. `tools/start-coordinator.sh resume --detached` creates tmux session `lab` (coordinator continues the last
     conversation; dashboard and health windows) without attaching.
  3. The on-demand web terminal is started (`web_terminal.start()`); it still exits after 30 min idle.
  4. `tools/outage.py announce` posts a Greek status message in the dashboard thread «Διακοπές VM».
- The dashboard shows a banner for 24 h after a recovery and the tab «🔌 Διακοπές» (counter, table, uptime, heartbeat age).
- The lab-bridge watcher is a plugin monitor (`tools/lab-bridge/monitors/monitors.json`), so it starts with the coordinator.
- Log: `.lab/boot_recover.log`. Dry run (no tmux, no post, temp files): `QRL_BOOT_DRYRUN=1 tools/boot_recover.sh`.

## Crontab lines
```
* * * * * /home/ubuntu/qrl-lab/tools/watchdog.sh >/dev/null 2>&1  # qrl-lab watchdog
@reboot sleep 30 && /home/ubuntu/qrl-lab/tools/boot_recover.sh  # qrl-lab boot
```

## Not covered
- Claude Code asking for a new login or a permission prompt after the restart: needs the researcher in the terminal.
- Runs that were in progress are not resumed; check `.lab/runs/` after an outage.
- The Codex broker/companion is started by its plugin when first used, not by this script.

## Disable
`crontab -e` and delete the line ending `# qrl-lab boot` (the heartbeat in the watchdog is harmless).
