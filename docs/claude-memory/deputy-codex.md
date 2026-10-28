---
name: deputy-codex
description: When Claude is out of usage, Codex is full acting coordinator (not read-only); hand-off rules both ways
metadata:
  type: feedback
---
Κώστας, 2026-10-21 (M-20261021-075/078/081): when Claude's limits run out, Codex acts as full coordinator (not read-only): follows all our instructions, logs everything it does for joint review; continues the experiment loop with equally strong Codex agents, but only in NEW branches derived from each existing branch (e.g. dinos-tuning-codex, dinos-tuning-astra-codex), keeping its own experience/notes files; when Claude returns, Claude and Codex decide together what to keep/merge. Conversely, if Codex's resources run out, Claude reassigns both experiment branches to its own equivalent agents. The agents tab must show who actually acts (no hard-coded "Claude").
**Why:** the deputy failed (codex binary not found) and stayed read-only during the limit, so nothing advanced.
**How to apply:** before stopping at a limit, hand off explicitly (queue + notes); after returning, read .lab/codex-handoff/, merge decisions with Codex. Related: [[token-saving]], [[parallel-branches]].
Symmetric rule (M-20261021-084): when Claude works alone (Codex limited), Claude also works in new branches (dinos-tuning-claude, dinos-tuning-astra-claude) and keeps notes (.lab/codex-handoff/claude_solo_*.md); on Codex's return, a deep joint review decides merges or which parts to keep.
Consolidated 2026-10-23 (researcher, terminal): rules in ~/qrl-lab/docs/rules/handoff.md — awake = has usage and works; asleep = rate-limited. Awake one: full coordination with write rights; detailed notes for joint review; agent strength per existing criteria; solo code/experiments only in new single-purpose branches from BOTH existing versions; on return: joint analysis → agree merges (all/some/none) → delete those branches.
