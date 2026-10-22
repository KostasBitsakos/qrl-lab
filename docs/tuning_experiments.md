# DInos tuning loop — what we tried (M-20261019-009)

Separate log of every change tried in the sim tuning loop (branch `dinos-tuning`, sandboxes R-20261019-001 and
R-20261020-005). Researcher, M-20261020-038: keep it here; what works moves into our own md files at the end.
Each line: cycle, what changed, result (with pointer), verdict. Details: `.lab/tuning/cycles/cN_*.md`.

Legend: **kept** = carried forward; **dropped** = did not help; **open** = still being tested.

| Cycle | What we tried | Result (pointer) | Verdict |
|---|---|---|---|
| 1 | sim_v2 (our new simulator), 400k steps | DInos+T 1.15M vs DERP 0.56M on d_sec; 0% on V2 (c1_synthesis.md) | dropped (not his env) |
| 3 | Verbatim port of his legacy env + agents, paper protocol vs fair protocol, 10 seeds | Paper protocol reproduces ~11x (88% closeness); fair protocol (greedy, reset) collapses to always-down (c3_synthesis.md) | the 17x is a protocol artefact (DERP evaluated at eps=1) |
| 4 | Coupled env (latency/cpu/mem depend on pods) | fixed N=5 478k > HPA > DERP 443k > DInos+T 330k; 21% (c4_synthesis.md) | dropped as primary |
| 5 | Common target, transfer sources, checkpoints | all LSTM arms at constant pods; 25% (c5_synthesis.md) | — |
| 6 | Fixed LSTM agent (hidden reset per window, Double DQN, target sync) | transfer 406k, scratch 414k, DERP 400k; still collapse (c6_synthesis.md) | **kept** (fixed agent) |
| 7 | Oracles / headroom on the coupled env | env allows only +3-7% over fixed pods; agents were the bottleneck (c7_synthesis.md) | diagnostic |
| 8 | Conditioning: reward/210, observation scaling, linear-10k epsilon | collapse fixed; DInos+T 490k ~ LSTM 489k > fixed 478k > DERP 461k ~ HPA 459k; 28% (c8_brief.md) | **kept** (conditioning) |
| 9a | His original `environment.py` (2024-07-16, reward min(capacity,load) - 3 VMs) + variants noise15, multispike, spike300, noise15+multispike | first clear LSTM > DERP >> HPA (orig 87k / 75k / 6.5k) (c9_brief.md) | **kept** (his env) |
| 9b | Confirmation orig -> spike300 transfer, fresh seeds + traces, pre-registered | DInos+T 100.3k > LSTM 97.5k > DERP-hist 90.4k > DERP 81.5k > HPA-demand 61.4k > his HPA 9.8k; 5/5 criteria; 31% (ratio 1.23x vs 17x) (c9_codex_verdict.md) | **kept** |
| 9b2 | Robustness: transfer noise15+multispike -> orig, 3 seeds, test6 | DInos+T 96.2k > LSTM 94.9k > DERP-hist 91.5k > DERP 85.7k > HPA-demand 56.9k; transfer-DERP +10.5k, DERP-HPA +28.8k support; transfer-scratch inconclusive (c9b2_summary.json) | **kept** |
| 10a | Pod startup delay D=5/10 (anticipation matters), 7th feature pending pods, DERP-hist10; screen 3 seeds, test5 | DERP collapses with delay (orig_d10 22.6k, spike300_d10 18.6k) while LSTM holds (62.9k / 59.8k): LSTM/DERP 2.8-3.2x at D=10; orig_d5 LSTM 85.4k > causal_be 68.0k, DERP 68.9k; his HPA negative (c10a_summary.json) | **kept** (orig_d5, orig_d10 to 10b) |
| 10b | Confirmation on orig_d5 + orig_d10: LSTM, DInos+T, matched MLP, DERP, DERP-hist10, fresh traces 8000-8019, pre-registered (cycles/c10b_prereg.md) | d5: DInos+T 82.8k > LSTM 76.2k ~ MLP 75.0k > DERP-hist 67.8k > DERP 54.8k; d10: 73.0k > 62.2k > 57.6k > 37.2k > 19.3k (DERP 1 pod). Supported: T-DERP (both), L-DERPhist and T-L (d10); LSTM-MLP inconclusive (both); DERP-HPA contradicted at d10. Ratio 1.5x / 3.8x; 36% / 37% (c10b_brief.md, c10b_codex.md) | **kept** d5 (fair DERP); d10 picture shaped but DERP degenerate; recurrence claim not supported |
| 11a | Larger delay D=15/20 screen, 3 seeds, test5 | all scratch learners collapse to 1-2 pods (~20k) below fixed 59.8k (c11a_partial.json) | **dropped** (no similar numbers) |
| 12a | His sinusoid+noise+spike workloads with D=5: spike300_d5, noise15_multispike_d5, all 5 arms, seeds 20-24, fresh test8, frozen absolute-return acceptance (cycles/c12a_prereg.md) | spike300_d5: DInos+T 85.9k > MLP 79.2k ~ LSTM 78.7k > DERP-hist 74.2k > DERP 56.5k > HPA-demand 47.6k; passes all acceptance; noise15_multispike_d5: LSTM 64.8k < fixed 72.0k, DERP 44.9k overprovisions (c12_brief.md, c12_codex.md) | **kept** spike300_d5 (accepted, operational criterion); noise15_multispike_d5 **dropped** |
| 12b | Training length 40k on orig_d10, 3 seeds, test5 (exploratory) | original DERP stays ~1.5 pods (23.3k); enhanced DERP 50.8k ~ LSTM 54.7k (CIs contain 0) (c12b_partial.json) | original DERP collapse under delay not a training-length artefact; LSTM vs enhanced DERP gap not robust |
| 13a | Replication of spike300_d5, 2 fresh seeds (28,29), fresh test9 (cycles/c13a_prereg.md) | DInos+T 88.2k > MLP 86.8k ~ LSTM 86.4k > DERP-hist 74.9k > DERP 58.8k > HPA-demand 47.5k; passes all acceptance; ratio 1.50x (c13_brief.md, c13_codex.md) | **kept** (replicates at n=2) |
| 14 | Robustness: spike300_d7 (3 seeds), multispike_d5 (2 seeds), test9 reused (cycles/c14_prereg.md) | d7: DInos+T 79.1k > LSTM 77.7k ~ MLP 76.4k > DERP-hist 53.0k > HPA 42.5k > DERP 31.6k; multispike: MLP 99.4k > DInos+T 94.5k > LSTM 90.7k > DERP-hist 68.6k > HPA 62.9k ~ DERP 59.0k; both fail acceptance (iii) (c14_brief.md) | **dropped**; accepted picture is narrow |
| 15 | 5 seeds per condition, pooled (cycles/c15_prereg.md), test9 | spike300_d5: DInos+T 86.7k > LSTM 82.9k > MLP 79.5k > DERP-hist 69.3k > DERP 64.1k > HPA 47.5k, passes all acceptance (ratio 1.35x, 33%); spike300_d7, multispike_d5 fail (iii) (c15_brief.md) | **kept** spike300_d5 = B1 candidate |
| 16 | Noise gap: noise15_d5, noise5_d5 (original spike), 3 seeds (cycles/c16_prereg.md) | DERP drops to HPA level, ratio ~2x; both fail (iii) (c16_brief.md) | superseded by 17 |
| 17 | Noise at n=5 (cycles/c17_prereg.md) | noise5: DInos+T 82.7k, DERP 43.1k ~ HPA 43.3k (inconclusive); noise15: 79.5k vs 38.3k, LSTM ~ fixed; both REJECTED; ratio 1.9-2.1x (c17_brief.md) | **dropped** for B1; noise = stated limit |
| 18 | Dinos V.2 search (a1..a10) + Transfer V.2, two branches, successive halving; n=5-7 on spike300_d5, noise5 robustness | V.2 a1h 86.4k val ≈ LSTM+transfer 86.9k (n=7, no detectable diff); V.2 − a1h scratch +4.7k [+1.1k,+8.9k]; LSTM-first > matched MLP; a2,a5,a6,a8,a9,a10 no gain; transfer = jumpstart (c18_n7_opus.md, c18_transfer_curve.md) | **kept** a1h |
| 19 | DDQN techniques (n-step 3, dueling, PER) + transfer techniques (source, pretrain 40k, ft-eps) on V.2 a1h; gate at n=5 | n-step 3 +6.9k val, test9 +6.7k [+3.8k,+9.4k], 5/5 seeds — ADOPTED; dueling −2.2k, PER −15.6k, others ≤ +1.1k (c19_screen.md) | **kept** n-step 3 |
| 20 | Archs a11/a12 (2×/3× LSTM128 + a1h head) with n-step 3, n=5 | running (c20_a12.md) | open |

## Notes
- His HPA (`P/HPA/simpleagent.py:9-14`, verified 2026-10-20): scale up if CPU > 50 **or** memory > 50, else scale down.
  In his envs CPU and memory are random and do not depend on the number of VMs (`P/environment.py` cpu 30-50, memory
  40-60; `P/HPA/environment.py` cpu 30-75, memory 40-65), so his HPA is close to a random walk. That is why it scores
  far below everything. We report it as-is and also a load-based HPA tuned on validation (fair baseline).
- Closeness % is a progress indicator (rules C5), not a paper result.
- Naming (researcher, M-20261020-048): `derp` = **his original DERP** — verified one 6-feature observation, no history
  (`P/dense/doubledeep.py:11,14`, `P/dense/doubledeepfinal.py:29,159`), his network and mechanics (ported verbatim,
  `tuning/legacy/ddqnagent.py`). `derp_hist10` = **enhanced DERP** (same agent, 10-step flattened history). Both are in
  every cycle since 9. `mlp_hist10` = dense control with the LSTM's training mechanics (cycle 10b).
- Researcher, M-20261020-048: keep tuning everything after Claude+Codex discussion; reject what does not produce
  numbers similar to his.
