---
name: tuning-engineer-opus
description: "In the tuning loop, engineer runs with model opus and every implementation is cross-checked; env variants are allowed"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-20T14:10:18.875Z
---

Κώστας (M-20261020-013, 2026-10-20): use a stronger engineer (`model: opus`) for loop implementation work ONLY until the loop ends 2026-10-21 23:59 UTC (M-20261020-027; afterwards route by resources/task as before), and make sure it really implements what the council proposed (review by Codex or Claude before results are used). The DInos env is a guide; variants (more sinusoid noise, stronger/more spikes) may be tried if they give better results — council decides, keep the original env as reference.

Scope clarified 2026-10-21 by Κώστας: Opus engineer ONLY for experiment implementation; dashboard/tools/docs go to the cheapest adequate agent (Sonnet/Haiku or Codex in implementation mode after a Claude-Codex discussion); weekly Claude limit is tight.

**Why:** he saw the engineer ran on a low-power model and doubted implementations were correct.
**How to apply:** every engineer delegation in [[experiment-loop]] passes `model: "opus"`; add a review step before launching.


Update 2026-10-21 (researcher): loop window extended to 2026-10-22 23:59 UTC (one extra working day) to add Dinos (DDQN with LSTM only in the first layer) and Dinos+Transfer V.2, alongside the existing LSTM and DInos+T arms; Opus engineer for loop experiment code until then; needs sandbox v5 (R-20261021-004).

Update 2026-10-21 (researcher): if Opus runs short of usage, give experiment engineering to Codex gpt-6-astra (high) — whichever is better and has resources. The experiment scope (models, coordination, architecture discussion, numbers) gets the best models; be frugal on everything else. Do not overload one md with trial details: per-cycle files in .lab/tuning/cycles/, one line per cycle in docs/tuning_experiments.md, one line per decision in DECISIONS.md.
