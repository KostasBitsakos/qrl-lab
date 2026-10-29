---
name: rl-eval-protocol
description: Evaluation and reporting protocol for QRL-Lab RL experiments (seeds, val vs single-use test, paired traces, IQM + bootstrap CIs, fixed-sequence hypotheses, SLO/pod-time/churn). Use before writing a freeze file, analysing a batch, or reporting any comparison between agents.
---
# RL evaluation protocol (cycle 2)
Background and sources: `docs/expert/rl_evaluation.md`. Plan: `docs/cycle2_plan.md`.
Checklist — every item must hold before a number is reported:
1. ≥10 fresh training seeds per arm, listed in the freeze file; no seed replaced or dropped.
2. Hyperparameters and checkpoints chosen on val only, by the rule written before tuning.
3. Test split used once after a committed freeze; per-split guard (`make_c18 --confirm-split`) on; no reruns.
4. All arms on identical paired test traces; analyse paired per-trace differences.
5. Report mean, IQM (rliable-style), stratified bootstrap 95% CI (≥2000 resamples), P(improvement).
6. Pre-registered ordered hypotheses; fixed sequence α=0.05; stop at first failure; the rest descriptive.
7. Report return AND SLO violation rate, p95 latency, pod-time, churn, drops; tuning CPU-h per arm; transfer pretraining cost.
8. Every number gets a pointer (file/run id); otherwise write "unknown". No real-cluster or quantum claims from simulation.
