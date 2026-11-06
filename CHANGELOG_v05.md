# Changelog v0.5.1 (worktree `v05`)

## B2 — usage governor (this change)
- Ships CLOSED (`governor_enabled` default 0; the sweeper is part of it). Opening it is a setting change from the System tab/CLI.
- `tools/governor.py`: pace (share of the 7-day window passed), limits 90 / 85 / 97, conservative mode when usage is
  unknown/stale or a percentage has no known reset (one optional run per provider, 40 runs / 24 h).
- Admission = the task row: `DispatchDB.reserve` counts and inserts (`starting`) in one `BEGIN IMMEDIATE`; used by
  workers, peers, retries and failover. Counting is per provider and per lane (everything except `chat`).
- A governor-held job stays queued; the tick goes on to the next. A held peer is re-queued and skipped in the poll.
- Sweeper (every 30 s in `tick`): `starting` > 5 min, `running` > timeout + 5 min, peer claimed but never served, and
  peer requests held > `peer_hold_max_min` (30) are freed; their jobs return to the queue.
- Codex usage is read from its rollout logs at decision time (15 s memo).
- Out of B2 (goes to B6 with the STATE condensation): the 8 KB STATE limit.

## Known issues (found by Codex review, not blocking: they cannot freeze the system, lose or duplicate work, or bypass
## an approval or a safety refusal)
- Jobs held by the governor wait without a time limit (they stay visible in the queue); only peer requests expire.
- A `running` task whose process died is freed only after timeout + 5 min (no liveness probe).
- A failover after a real limit error is admitted by the same rule as any attempt, so it may be re-queued; the
  «Αναλαμβάνει ο …» notice has already been posted in that case.
- Usage from Claude's statusline file is only as fresh as the last Claude session that wrote it.
- `perm_answer` items re-queued by a denied attempt may be delayed by their own wake debounce.
- Review 3 (Codex) blocking finding, fixed: the sweeper judged runs by the *current* timeout settings. It now never
  declares a run dead before 6 h (`SWEEP_MIN_RUNNING_S`) and tolerates malformed settings. A per-attempt persisted
  deadline + owner identity (Codex's fuller fix) is a known follow-up; this fix itself was not re-reviewed by Codex.

## B3 — events by script (no model call)
- Clean batch end (all runs `done`, exit 0) → summary written by `tools/run_events.py` into the request's thread; a failed
  batch still wakes the coordinator once. Exactly once: marker `[run-summary <ref>]` in the thread + `notified`.
- Approved frozen `sim` spec (not sandbox) → `launch_run.start_entry` by the dispatcher, up to `max_parallel`; free slots are
  filled on later ticks. `real`/`qpu` approvals keep going through the coordinator. `launch_run` re-checks approval, hash, attempts.
- Worker escalations: `urgent` → a `question` card for the researcher; routine/final notes → a status line in the job's
  thread (batched by `escalation_debounce_s`). One marker per note. The old coordinator wake-up for escalations is removed.

## B4 — settings from the System tab, config cards
- Editors in the System tab: value rules (`SETTING_RULES`), audit (`old -> new`), compare-and-set (second click = no-op;
  a page whose value changed underneath shows «άλλαξε» and must be refreshed). The `set` CLI stays lenient on purpose.
- Agents propose with `dispatcher.py propose KEY VALUE --reason …` → a card; on approval the dispatcher applies it from the
  `config_proposals` table (not from the card text), with `expected_old`, so a stale card never overwrites a newer choice.

## B5 — failover completion
- Roles for workers: `work.py spawn --role research|work|light|quick` → settings `role_<role>_claude/_codex/_codex_effort`.
  Codex model names are left empty (config default): the plan's names were not verified to exist, set them in the System tab.
- After a finished Codex job the dispatcher commits only the job's claimed files (`work.commit_claimed`: blob-hash check;
  nested repos/gitlinks refused; `codex_commit`=1). A job that ran on the non-first provider is flagged solo; when the other
  provider is available again one read-only joint review is requested (deduplicated by key `solo-<job>`).
- Pinned providers (competing branches) already work through `work.py spawn --to`: a pinned job waits instead of failing over.

## B6 — knowledge
- «Σχετικά» block from `kb.py query` for chat messages longer than `kb_related_min_chars` (80); kb refresh after a finished job
  at most every `kb_refresh_min` (10) minutes on cores 4–7, only when an index exists.
- STATE.md 30.7 KB → 5.6 KB. The full previous text is `docs/archive/STATE_2026-11-06_before_B6.md` (verbatim, line numbers
  cited as «A:n» in the new STATE); limit `state_max_bytes` 8192 adds a note to the prompt when exceeded.
- AGENTS.md: the kb-vs-INDEX contradiction is resolved with one sentence (kb.py query first, INDEX.md only for titles).

## B7 — freeze
- From the merge of B3–B6: no further infrastructure changes until the CCGrid abstract (24/11/2026), only fixes — «αφορά μόνο υποδομή (dispatcher, dashboard, tools, κανόνες)· η έρευνα, τα πειράματα και το paper συνεχίζουν κανονικά». Settings are
  changed from the System tab.

## Known issues added by review 4 (Codex, not fixed; none bypasses an approval or a safety refusal)
- `launch_run.start_entry` commits a `starting` row before spawning the supervisor; a crash in between leaves an orphan
  `starting` run that holds a parallel slot (pre-existing behaviour, now also reachable from the script launch).
- Status messages ("launched", "config applied") are written after the state mark; a crash between the two can lose the
  message (the action itself is idempotent). No durable outbox yet.
- `peer_submit` has no key uniqueness; `_solo_reviews` deduplicates by key lookup, which is not atomic across processes.
- Fixed from that review: per-note escalation markers, `expected_old` on approved cards, UI baseline for stale pages,
  solo flag when the first provider was already unavailable. These fixes were not re-reviewed by Codex.

## Final infra round (liveness) — before the freeze
- Task rows carry `owner` (pid:boot) and `beat`. A row of this process is alive exactly while a live thread of this process
  owns it (`LIVE_TASKS`); the dispatcher's heartbeat thread refreshes the beat for others to read. A row of another process
  (inline `ask_peer`) is alive while its pid is. So the sweeper frees a dead row on its next pass (≤ 30 s), with no timeout
  setting involved. The 6 h floor of review 3 now applies only to rows without an owner (written by older code).
- `recover()` at start-up: every starting/running row of a dead owner is freed, unstarted peers are queued again, running
  peers fail with a clear message; rows and peers of a LIVE foreign owner are kept. Test: crash after `reserve` → free after restart.
- Sweeper transitions are conditional (status + owner) and side effects happen only if the row really moved; `task_end`
  deregisters after the terminal update. Held peer requests keep `peer_hold_max_min` (30 min).
- Codex review 5 (two P1s: recovery vs live inline peer, late heartbeat) and re-review (one P1: completion race) fixed.
  Not fixed (non-blocking): pid reuse ignores the owner timestamp; config apply/mark-applied are two transactions.

## Fix: CLIs find their lab from the script's location (6/11)
- `labdb.lab_root()` and `dispatcher.lab_root()` (used by dispatcher.py, labq.py, launch_run.py, work.py, ask_peer.py) fell back to the
  caller's current directory: `dispatcher.py exhaust claude 10` run from `~` wrote `~/.lab/dispatch.db`, which the live dispatcher
  never reads. Now `$QRL_LAB_DIR` wins, otherwise the lab the script lives in (`REPO_ROOT`). `tests/test_cli_root.py` (3 tests).
- No restart needed: the service has `WorkingDirectory=/home/ubuntu/qrl-lab`, so its root did not change.
