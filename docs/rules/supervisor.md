# Supervisor — alert + safe auto-resume (J383, M-20261107-005)

`tools/supervisor.py` (script only, no LLM). One check per call; a systemd `--user` timer calls it every 2 min.
Not active until the researcher approves (see Activation). Tests: `tests/test_supervisor.py` (cores 4-7).

## Detects → action
| Situation | Notify (labq status in thread M-20261102-040) | Action |
|---|---|---|
| driver/watch dead, state RUNNING/READY, no STOP | at first sight ("confirming") | after a 2nd poll ≥90 s later: `driver.py resume` (re-spawns only dead roles, same approved spec/session/hash; Engine re-checks approval + CPU-h caps). Max 2 resumes (receipt + supervisor counters, persisted before the effect). Failure/exception → `resume_failed`, `labq ask`, no retry. |
| driver gone but state DONE (clean exit, J380 false alarm) | one "finished" message only if the supervisor saw it RUNNING | none |
| STOP file, state STOPPED/INCOMPLETE, active run without process, stall (no new output of any active run 60 min, or driver heartbeat >180 s with live pid) | yes | `labq ask` (no action) |
| dead qrl-dispatcher/dashboard user service | yes | `systemctl --user restart`, max 2 per 6 h, then ask |
| dispatcher active but `.lab/bridge_heartbeat` >5 min | yes | none |
| new `] failed` line in today's dispatcher journal | yes | none |
| history: parent terminal or silent >6 h when first seen | silent baseline | never auto-resumed |

Never: start a new run, change a spec/cap, touch test splits, resume STOP/STOPPED/abandoned parents. `driver.py resume` itself refuses
phase≠GO, hash mismatch, missing state, state older than 6 h, STOP file, terminal state, both roles alive, `resumes>=2`. The receipt stays
at GO during resume (a surviving role keeps passing its approval check); on failure the old pids are restored.
Targets: every `.lab/*/receipt.json` with `parent-spec.json` (C345 W and each F parent with its own `QRL_C345_OUT`).

## Limits
- No phone push: `PushNotification` is an agent-session tool, scripts cannot call it. Channel = dashboard thread + `labq ask` cards.
- Auto-resume covers the C345 driver family only; other experiment types (launch_run payloads outside a C345 parent) are alert-only.
- Failed dispatcher jobs are detected from the journal; the supervisor cannot see jobs that never wrote a line.
- Delay ≈ timer period (2 min) + 90 s confirmation.

## Activation (researcher OK needed)
`python3 tools/supervisor.py install` prints the `systemd-run --user` command (transient timer `qrl-supervisor`, cores 4-7, KillMode=process);
run it on the host, then `systemctl --user list-timers qrl-supervisor`. Stop: `systemctl --user stop qrl-supervisor.timer qrl-supervisor.service`.
Dry run: `python3 tools/supervisor.py --dry-run`. Transient timers do not survive reboot (same as J377).
