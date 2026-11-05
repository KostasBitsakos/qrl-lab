---
name: parallel-branches
description: Every experiment cycle runs on competing Claude/Codex branches with periodic exchange of helpful changes (standing since 29/10)
metadata:
  type: feedback
---
Κώστας, 2026-10-29 (M-20261029-028): in ALL experiments for his work, Claude and Codex work in parallel on two branches/repos that compete for better results and periodically share the changes that helped. Replaces the 21/10 «only for this loop, ask before reusing».
**Why:** faster exploration and better performance through competition plus exchange.
**How to apply:** every new cycle: branches `<topic>` (Claude) and `<topic>-astra` (Codex); exchange at least at each daily report; rule text in docs/rules/experiments.md. Related: [[deputy-codex]], [[tuning-engineer-opus]].
