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
| 10b | Confirmation on orig_d5 + orig_d10: LSTM, DInos+T, matched MLP, DERP, DERP-hist10, fresh traces 8000-8019, pre-registered (cycles/c10b_prereg.md) | running | open |

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
