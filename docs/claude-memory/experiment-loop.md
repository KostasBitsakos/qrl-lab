---
name: experiment-loop
description: Autonomous sim tuning loop (dates/rules: ~/qrl-lab/.lab/tuning/protocols.md latest P line) — recreate the hourly check-in cron after any restart
metadata:
  node_type: memory
  type: project
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-20T18:15:55.757Z
---

Κώστας (M-20261019-009, 2026-10-19) ordered a non-stop loop: sim cycles → numbers → Claude+Codex council → implement → next cycle, on branch dinos-tuning (worktree ~/qrl-lab/code-tuning), sandbox R-20261019-001 (≤500 CPU-h, cores 8–39, until 2026-10-21T23:59Z), no questions to him, stop only when results converge to the DInos paper picture.

**Why:** on 2026-10-19 he complained the loop looked stopped; crons are session-only and die with the session.
**How to apply:** at session start before 2026-10-22, if CronList lacks it, recreate the hourly "Experiment loop check-in" cron (minute 13) and the 20:47 daily report to thread M-20261017-137. Second sandbox R-20261020-005 (+200 CPU-h, same rules/expiry) approved 2026-10-20; drive_chunks.py counts both. Cycle state lives in ~/qrl-lab/.lab/tuning/cycles/ and .lab/tuning/c*_b*.json specs. Keep cores busy; never leave them idle between cycles.


Update 2026-10-21 (researcher): loop window extended to 2026-10-22 23:59 UTC (one extra working day) to add Dinos (DDQN with LSTM only in the first layer) and Dinos+Transfer V.2, alongside the existing LSTM and DInos+T arms; Opus engineer for loop experiment code until then; needs sandbox v5 (R-20261021-004).

Update 2026-10-22 00:00 (researcher, terminal): extension by one more day offered ("αν χρειάζεσαι πάρε παράταση άλλη μια μέρα") — filed sandboxes v7 (R-20261021-009, branch 1, +120) and v8 (R-20261021-010, branch 2, +60) to 2026-10-23 23:59 UTC. Goal stated: Dinos+Transfer V.2 should end up the best, as close as possible to his paper picture (17x and the other paper claims) — pursued with fair protocol only (17x came from DERP evaluated at eps=1).

Update 2026-10-22 13:40: protocols.md P2 is the single source of dates, names (LSTM / LSTM+transfer / Dinos / Dinos+Transfer V.2) and the freeze rule; +14 h extension requested (R-20261022-002/003).
