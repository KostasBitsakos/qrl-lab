---
name: engineer-test-cpu
description: No CPU-minute cap on engineer tests; only cores 0-7 and no experiments
metadata:
  node_type: memory
  type: feedback
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-21T12:04:45.495Z
---

Engineer subagents have no CPU-minute cap on tests/smoke/proof runs (researcher dropped it 2026-10-21: «αν δεν επηρεαζει τα πειραματα δεν καταλαβαινω γιατι καν να υπαρχει το οριο»).
**Why:** the old ≤2-3 CPU-min cap was only in my delegation prompts (in no rule file); with tests pinned to CPUs 0-7 they never touch the loop's cores 8-39 or sandbox budgets.
**How to apply:** in engineer briefs say: tests pinned with `taskset -c 4-7` (see [[core-split]]), no experiments (results-producing runs only via tools/launch_run.py), no touching runs/drivers/results. Do not report test CPU time as a violation. Related: [[tuning-engineer-opus]], [[experiment-loop]].
