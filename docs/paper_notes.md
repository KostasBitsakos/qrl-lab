# Paper notes — what the publication will need (researcher M-20261022-033)

Living file. Every change to the environment, models or protocol that may appear in the paper goes here with WHY and the
evidence pointer. Writers (agent `writer`, Codex, humans) read this before drafting. Numbers only with pointers; final paper
numbers come from the guarded test10 batch and `paper/generated/results.tex`, never from this file.

## 1. Environment (simulator) — changes and why
| Change | Why | Evidence / effect |
|---|---|---|
| Use the researcher's own env (`P/environment.py`, 2024-07-16; ported verbatim as `env_orig`), reward min(capacity, load) − 3·VMs | Our earlier sim_v2/coupled envs were not his env and gave numbers unlike his (cycles 1-8) | cycle 9a, docs/tuning_experiments.md |
| Served load depends on the number of pods (capacity), so "always scale down" is NOT optimal | Answers the PLAN F1 concern raised by the related-work agents: F1 (every learner converges to scale-down) applied to the OLD sim_v2 only, not to env_orig | cycle 9 onwards; DERP/LSTM learn non-trivial policies |
| Pod startup delay D (D=5 primary), 7th feature = pending pods | Real pods take time to start; anticipation is where memory (LSTM) matters; DERP collapses with delay | cycles 10a/10b, 12-15 |
| Workload: sinusoid (amp 50, period ~159 ticks) + load noise sd 0.2 + spike 300 at ticks 1500-1600 of 5000 (spike300_d5) | Closest to the researcher's DInos-paper picture with fair baselines (fairness: DERP > HPA-demand) | cycle 15 acceptance (c15_brief.md) |
| Rejected as primary: noise5/noise15 (DERP ≈ HPA-demand, fairness fails), D ≥ 7, multispike | Report as stated limits/robustness | cycles 14, 16, 17 |
| Next cycle: Poisson arrivals | Requested; must be a correct Poisson PROCESS (exponential inter-arrival times / Poisson counts per tick), not "Poisson-distributed gaps" as in DRe-SCale's generator | Codex related-work r2 |

## 2. Agents / models — changes and why
| Change | Why | Evidence |
|---|---|---|
| "Fixed" LSTM agent: hidden state reset per window, true Double DQN target, target sync 250 | Verbatim agent collapsed to constant pods | cycle 6 |
| Conditioning: reward/10 (learning targets only), observation scaling, linear epsilon over 10k ticks | Fixed the collapse; same for all learning arms | cycle 8 |
| Names: LSTM (his myLSTM 3×128, scratch) · LSTM+transfer (was DInos+T) · Dinos (DDQN, LSTM in first layer(s) + dense head; arch a1h) · Dinos+Transfer V.2 (Dinos + transfer, same arch) | Researcher M-20261022-007/013 | .lab/tuning/model_definitions.md, protocols.md P2 |
| Dinos arch search: a1..a10, matched-parameter MLP controls | LSTM-first beats matched MLP (a1h, a4); variants a2, a5, a6, a8, a9, a10 gave no gain | cycle 18 briefs |
| Arch chosen by its TRANSFER arm on val (researcher rule) — claims must say transfer is evaluated within an arch selected for transfer | Avoid over-claiming "transfer always helps" | Codex C-20261022-01 r2 |
| Transfer = big jumpstart / faster convergence (≈2× fewer ticks to 95% of best), plus +4.7k at the end for a1h (n=7, test9 dev) | Report learning curves + convergence metrics, not only the endpoint | c18_transfer_curve.md, c18_convergence_spike.json, c18_n7_opus.md |
| Cycle 19 (in progress): DDQN techniques n-step / dueling / PER; transfer techniques (source workload, pretrain length, fine-tune epsilon) | Researcher: try policy and transfer techniques; Rainbow ablation (Hessel et al., AAAI 2018) | c19_policy_strategy.md, protocols.md P2 |

## 3. Protocol (what makes the comparison fair)
Val-only selection (seeds 1100-1104) + test9 development gate (disclosed); single guarded test10 (11000-11019) with ≥5 fresh seeds;
across-seed locked checkpoint per arm; crossed bootstrap 95% CIs; baselines always reported: his HPA (rule-based), HPA-demand
(load-based, tuned on val), fixed pods, oracle_Dstep (heuristic reference, not an upper bound); the 17× of the earlier paper came
from evaluating DERP at eps=1 (paper protocol) — fair protocol gives ~1.3-1.4× vs DERP on spike300_d5 (dev numbers).

## 4. Related work (for the paper; verified by scholar r1 + Codex astra r2 — see docs/related_work_sota_autoscaler.md, docs/related_work_sota_codex_r2.md)
- Chosen comparison baseline: DRe-SCale LSTM-PPO — Agarwal, Rodriguez, Buyya, IEEE TSC 17(5) 1899-1910, 2024, DOI 10.1109/TSC.2024.3387661 (code Apache-2.0). Present as an ADAPTED published recurrent-RL baseline, not "the SOTA".
- Gwydion — JNCA 234 (2025) 104067 (gym-hpa extension, Redis, cluster-free sim): candidate second baseline (decision pending, researcher).
- ASTRA — IEEE TSE 2025, DOI 10.1109/TSE.2025.3603995 (adversarial SAC + learned simulator, sim-to-real).
- AWARE — USENIX ATC 2023 (meta-learning RL autoscaler; transfer-related).
- gym-hpa — NOMS 2023 (Gym env for K8s HPA; noncommercial-research licence).
- Lipari et al. — IPDPSW 2025 (DDQN + LSTM forecaster: closest prior art, must cite).
- RLScale-Bench — arXiv 2605.26418 (preprint; rule-based controller competitive on cost; report cost–SLO trade-offs).
- Others with code: Erlang, Autothrottle, ProSmart HPA (JSS 2025), VASIM (vertical). Rainbow ablation (Hessel et al., AAAI 2018) for c19.
Fairness requirements for the baseline comparison (Codex r2): correct Poisson arrivals, equal tuning/interaction budgets, transfer
pretraining cost charged, ≥10 seeds, paired test traces, CIs, SLO violations, pod-time, churn; include tuned HPA and no-transfer DDQN.

## 5. Target picture (researcher M-20261022-050)
Ideal ordering: Dinos+Transfer V.2 > Dinos > LSTM+transfer > LSTM > {DERP, MLP} > HPA-demand (load) > his HPA (old).
The published DInos numbers map to Dinos+Transfer V.2, Dinos, DERP and his old HPA (not HPA-demand). The researcher accepts that
the absolute numbers/17x cannot be reached under the fair protocol; the paper explains that DERP was also changed and improved
(enhanced DERP = 10-step history) and why. Check with .lab/tuning/order_check.py <summary.json> [--suffix _dqn3].

## 6. Reminders for the writing phase (researcher)
- M-20261022-077: REMIND the researcher, when writing starts, to discuss the oracle (oracle_Dstep): what it is (heuristic with
  D-step look-ahead, not an optimal upper bound), and that V.2 with n-step exceeds it (dev ~1.05×) — report it carefully.

## 7. Final confirmation result (test10, 2026-10-23; .lab/tuning/cycles/c21_test10_result.md)
Confirmed (pre-registered fixed sequence): Dinos+Transfer V.2 (a1h, n-step 3) > DERP (+24.8k [+17.9k,+31.8k]) and > enhanced DERP (+18.0k
[+9.8k,+29.5k]) on spike300_d5, 5 fresh seeds. NOT confirmed: Dinos > LSTM (H3), so V.2 vs Dinos / LSTM+transfer is descriptive only
(test10: LSTM+transfer 90.6k, MLP 90.2k, LSTM 90.0k, V.2 87.8k, Dinos 86.1k). Dev gains did not replicate (selection optimism and/or seed
variance; Dinos sd 11k). Exploratory: V.2 has the highest validation AUC/jumpstart and earliest 95%-of-own-best crossing (5k ticks).
Do NOT claim 'V.2 is the best model'. Disclose: test9 used as a development gate; arch chosen by its transfer arm; all screens listed.
