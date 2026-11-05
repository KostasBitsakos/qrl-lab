# Changelog v0.5.1 (worktree `v05`)

## B2 — usage governor (this change)
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
