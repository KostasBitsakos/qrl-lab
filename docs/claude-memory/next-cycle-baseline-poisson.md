---
name: next-cycle-baseline-poisson
description: "Plan for the experiment round after the tuning loop — DRe-SCale LSTM-PPO baseline, open Gwydion question, correct Poisson arrivals"
metadata:
  node_type: memory
  type: project
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-22T13:52:54.251Z
---

Κώστας, 2026-10-22 (M-20261022-033): in the next experiment round (after the tuning loop, when Poisson arrivals are added) we compare against **DRe-SCale LSTM-PPO** (Agarwal/Rodriguez/Buyya, IEEE TSC 2024, DOI 10.1109/TSC.2024.3387661, Apache-2.0), re-implemented in our simulator and presented as an adapted published baseline, not "SOTA". Open question to ask him then: **only DRe-SCale, or also Gwydion** (JNCA 2025, gym-hpa extension with Redis)? He asked me to keep both in memory.
Poisson plan: build our own correct Poisson PROCESS (exponential inter-arrivals / Poisson counts per tick) — DRe-SCale's generator samples "Poisson gaps" and is not a correct process (Codex r2). Fairness: equal tuning/interaction budgets, transfer pretraining cost charged, ≥10 seeds, paired traces, tuned HPA + no-transfer DDQN, SLO/pod-time/churn metrics.
**Why:** CCGrid reviewers expect a published, code-backed baseline.
**How to apply:** when the post-loop round starts, ask the Gwydion question first, then plan the port. Everything paper-relevant goes to ~/qrl-lab/docs/paper_notes.md. Related: [[experiment-loop]], [[initiative-strategy]].
