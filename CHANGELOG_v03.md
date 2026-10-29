# Changelog v0.4 — 2026-10-29: parallel work (researcher's request, M-thread of 29/10)
- Two lanes in `tools/dispatcher.py`: the chat coordinator (job `C<n>`, one at a time) answers researcher messages
  even while workers run; up to `max_workers` (default 2, researcher setting 1–16) parallel workers (`J<n>`) take
  decisions, permission answers, run events and jobs the coordinator hands over (`tools/work.py spawn`).
- `tools/work.py`: job board in `.lab/dispatch.db` — atomic file claims (directories cover their files), conflicts
  show the holder's goal (exit 2), agent-to-agent messages (`say`/`inbox`), recorded agreements posted in the thread
  (`agree`), escalation to the chat coordinator (`say coordinator`), own-files-only commits under a lock, `cancel`.
- Heartbeat from its own thread: the dashboard no longer shows "offline" while a long task runs.
- Workers never resume the thread's session; chat runs use `chat_budget_usd` (3), workers `max_budget_usd` (5).
  A researcher request stays in_progress until its last spawned job reports. Restart: spawned jobs are queued
  again with a note; all claims are cleared.
- `prompts/coordinator.md`: "Parallel work" section (roles, claim → negotiate → agree, shared docs, commits).
- Coordinator panel lists active jobs. Tests: 3 new in `tests/test_dispatcher.py` (fake CLI: match/sleep/sh steps).

# Changelog v0.3.2 — 2026-10-28
- `tools/upgrade_v03.sh` + `prompts/upgrade_v03.md`: one new Claude Code session on the VM runs the tests and fixes
  VM-specific failures (without weakening assertions), lists what must be stopped before the switch, builds
  `docs/EXPERIMENTS.md` and `docs/STATE.md` from handoffs, memory and the launcher, and installs after the researcher's
  OK. Replaces `prompts/migrate_v03.md`.
- `docs/EXPERIMENTS.md` (template `prompts/EXPERIMENTS.template.md`): registry of every experiment batch; the
  coordinator prompt and run-finished events require keeping it current.
- `dispatcher.py exhaust PROVIDER MINUTES`: failover drill (researcher only; denied to both agents).
- Tests: Streamlit log noise silenced; the process always exits after the verdict (a dashboard thread could keep it
  alive on the VM). Claude-memory mirror is no longer git-ignored (the project stays portable with its memory).

# Changelog v0.3.1 — 2026-10-28
- On the VM, `tests/test_dispatcher.py` stalled in its 4th test on a write to the dispatch database; it passes here
  (Python 3.11–3.13, SQLite 3.45) and the cause is not confirmed. Removed the likely suspects: the tests deleted and
  re-created database files between tests while earlier connections could still be open. Each test now gets its own
  new database file, and connections are closed explicitly (dispatcher, peer worker, dashboard panel).
- The dispatch database path no longer depends on `labdb.py` helpers (`QRL_DISPATCH_DB` overrides it). Busy timeout:
  30 s.
- Tests: a 90 s watchdog per test prints all stacks and the processes holding the test files, then exits; the
  runner continues after a failure and prints the environment (python, sqlite, journal mode, labdb.py changed or not).
- `prompts/migrate_v03.md`: one fresh, short Claude session on the VM moves the coordinator's memory into
  docs/STATE.md and lists what must be stopped (cron, watchdog, old tmux coordinator) before the switch.

# Changelog v0.3 — 2026-10-26: event-driven coordinator, Claude or Codex, failover, shared memory files

Problem (researcher's report "QRL-Lab: κόστος tokens και λύσεις", 2026-10-26): weekly Claude limit reached on 23/10;
~$15.6 of extra credits in ~1.5 h by a coordinator session running since 16/10 (282 MB history), hourly in-session
checks on a cold cache, `--continue` reloads.

Design
- `tools/dispatcher.py` replaces the always-on coordinator session. A Python loop (no tokens while idle) starts one
  headless run per work item (`claude -p` or `codex exec`) with a bounded context pack: docs/STATE.md + recent thread
  messages + new input. Same-thread follow-ups resume the session only while the prompt cache is warm and the context
  is under 120k tokens; otherwise they start fresh from STATE.md.
- Work items: researcher messages, researcher decisions, finished experiment batches (replaces LLM polling).
- Coordinator choice in the dashboard (`dashboard/coord_panel.py`) or per message (`@claude` / `@codex`).
- Failover: a usage-limit failure re-runs the same task with the other model; the first is marked exhausted until its
  reset time (from Claude's `rate_limit_event` lines in stream-json, or parsed from the error text). If Claude reports
  `isUsingOverage` (paid extra usage) and paid credits are not allowed, later work goes to Codex.
- `tools/ask_peer.py`: symmetric, logged, read-only peer consultation (Claude↔Codex), served by the dispatcher outside
  the Codex sandbox; `--key` continues a topic thread.
- Shared memory: `docs/STATE.md` (handoff, ≤150 lines), `docs/journal/` (one line per task, by script),
  `docs/INDEX.md` + `docs/index.json` (all .md files, by `tools/build_md_index.py`, no LLM), Claude auto-memory mirrored
  to `docs/claude-memory/` for Codex.
- Safety: Codex runs in `workspace-write` with `approval_policy=never` and `~/.codex/rules/qrl-lab.rules`
  (forbidden: kubectl mutations, helm, push, sudo, crontab, labq decide/say, dispatcher set/clear/run; checked with
  `codex execpolicy check`). Claude keeps `.claude/settings.json`; new deny rules for the dispatcher's settings.
- Ops: systemd user units (`deploy/`), `Restart=on-failure` with a start limit; no cron, no agent-managed restarts.
- `tools/install_v03.py`: dry run by default; merge-only settings change; marked, idempotent appends; backups.

Verified
- Flags against the CLIs installed on the VM (Claude Code 2.1.300, codex-cli 0.162.1): `claude -p --output-format
  stream-json --verbose --permission-prompts none --max-budget-usd --append-system-prompt --resume --tools`;
  `codex exec [resume <id>] --json -o --skip-git-repo-check -c sandbox_mode=… -m`.
- `tests/test_dispatcher.py` (10 tests, fake CLIs, no tokens) and the unchanged `tests/test_lab.py` (6) pass,
  including the dashboard with the panel added by the installer.
