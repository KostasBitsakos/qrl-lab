---
description: Codex round-2 recommendation - DRe-SCale LSTM-PPO as the adapted baseline; its Poisson generator is not a correct process
---
# Related work round 2 — Codex (gpt-6-astra, high), 2026-10-22; verbatim summary of its answer
Recommendation: DRe-SCale LSTM-PPO (Agarwal, Rodriguez, Buyya, IEEE TSC 17(5) 1899-1910, 2024, DOI 10.1109/TSC.2024.3387661;
arXiv 2308.05937; github.com/SidAg26/DRe-SCale, Apache-2.0) as an ADAPTED published recurrent-RL baseline; "SOTA" not established.
Ranked: 1 DRe-SCale; 2 Gwydion (JNCA 234, 2025, 104067; github.com/jpedro1992/gwydion; gym-hpa extension, Redis, cluster-free
dataset simulation; noncommercial-research licence); 3 ASTRA (TSE 2025, DOI 10.1109/TSE.2025.3603995; github.com/igeng/ASTRA;
adversarial SAC + learned simulator; missing checkpoint, action-mapping bug, licence unresolved).
Corrections to round 1: DRe-SCale hold penalty −100; features normalised by resource requests; generator samples Poisson GAPS
(not a Poisson arrival process); 2026 commits are licence-only. AWARE: 60 days is total runtime, not a porting budget; GitLab
inaccessible. gym-hpa licence = noncommercial research (explicit). Lipari: IPDPSW 2025 verified, UCC attribution wrong, has a
cluster-free train_dqn.py path; simulator forecast inputs commented out. RLScale-Bench: June-2026 v3 preprint, not peer-reviewed,
code "upon publication"; use cost-SLO trade-offs. Also code exists for Erlang, Autothrottle (round 1 gap), ProSmart HPA (JSS 2025),
VASIM (vertical). Port plan: keep LSTM-256, actor/critic [64,64], recurrent resets; common obs/actions/reward/delays/horizon;
disclose deviations. Fairness: correct Poisson arrivals, equal tuning/interaction budgets, transfer pretraining charged, >=10 seeds,
paired test traces, CIs, tail latency, SLO violations, pod-time, churn; include tuned HPA and no-transfer DDQN.
Note (coordinator): Codex repeats round 1's PLAN F1 caveat; the current tuning env (his env_orig) serves min(capacity, load), so
served load depends on pods — F1 applies to the old sim_v2 only.
