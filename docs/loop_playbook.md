# Experiment-loop playbook (lessons on HOW to run an autonomous tuning loop) — QRL-Lab, 2026-10-19 → 2026-10-22
For future projects (researcher request M-20261021-043). What we learned about working, not the research results
(those are in docs/tuning_experiments.md). Each item: the practice, and where it came from.

## 1. Goal and authority
- State one objective and the fixed core up front (here: DRL autoscaler, LSTM/transfer vs DERP, sinusoid+noise+spike), and what
  the team may change freely (env, inputs, reward, layers, training, workloads) — M-20261019-009, M-20261020-015/048.
- Approve a sandbox (budget, cores, branch, seed ranges, expiry) once; inside it the team launches without asking. Extensions and
  new branches need a new approval — R-20261019-001, R-20261020-005, R-20261021-001/005/007.
- Never target a number that is a known artefact (the paper's 17x came from evaluating DERP at eps=1) — cycle 3.

## 2. The cycle
- run → summary script (no LLM) → brief → second opinion (Codex) → synthesis → implement → launch next; never leave cores idle
  between cycles for more than one check-in; hourly check-ins and a daily report.
- One fixed report format per cycle (first line «Κύκλος N: X%», sanity, other side's view, synthesis, next cycle).
- Pre-register each confirmation (targets, seeds, splits, contrasts, acceptance) BEFORE results exist; freeze absolute-return
  acceptance criteria, including a fairness check that the opponent is not degenerate (DERP must beat a tuned load HPA).
- Screens are exploratory; only pre-registered runs on fresh traces count; report every condition, including failures.

## 3. Honest comparisons
- Separate splits: tuning/selection on validation, report on a fresh test split, final confirmation once on another fresh split.
- Select checkpoints (1k/2k/5k/10k/20k) on validation only — researcher's own protocol, made leak-free.
- Crossed bootstrap over training seeds × paired traces; verdict = support / inconclusive / contradicted; no multiplicity hiding.
- Always include the researcher's own baselines (original DERP, his HPA) and fair ones (tuned load HPA, fixed pods, oracle).
- Parameter-matched controls for every architecture claim (e.g. MLP with the same parameter count as the LSTM).
- Name arms precisely (DERP original vs enhanced DERP; LSTM = myLSTM 3×128 scratch; LSTM+transfer (formerly DInos+T) = same + transfer).
- Closeness % is a progress indicator, never a result. Allowed / not-allowed claims written down (council C-20261021-01).
- Before trusting a reported number, check it against the summary file; correct overclaims immediately.

## 4. Search strategy
- Before executing an important task: check established practice online, write the strategy, then run (M-20261021-040).
- Budgeted search: successive halving (short rung → promote top 1/3 → full runs), several tuning seeds, confirmation reserved
  ~30-35% of CPU (Hyperband/ASHA; Eimer et al. 2023; Henderson 2018; Agarwal 2021) — .lab/tuning/strategy.md.
- Change one variable at a time; when stuck, change env/workload/checkpoints jointly as a new shared protocol version.
- Shared memory of what helped / did not (.lab/tuning/lessons.md), read before and updated after every cycle.
- Parallel branches with different engineers only with one shared, versioned protocol (asked for each project) — C-20261021-03.

## 5. Agents and models
- Best models (Opus engineer, Codex astra) for experiment code, architecture and numbers; fallback to Codex astra when Opus runs
  short; cheapest adequate agent for everything else; Codex can implement (coordinator commits for it).
- Every implementation is cross-checked by the other side before its results are used; bit-identity proof when touching shared code.
- Engineers never run experiments; tests pinned to non-experiment cores, no CPU-minute cap there.
- Consult the other model for real, one call at a time, and post its view verbatim as its own contribution.

## 6. Machine and tools
- Core split: experiments on dedicated cores, dashboard and agents on others (0-3 dashboard, 4-7 agents/tests, 8-39 runs).
- Worst-case budget reservations can block launches: drivers that shrink chunks on refusal and fill free slots automatically.
- Live recording (opt-in, proven not to change numbers) and saved selected weights, so results can be re-plotted later.
- Heavy work outside the UI process; profile before guessing (one pandas attrs copy made the dashboard 200x slower).
- Token economy: scripts for repetitive work, short briefs, no settings that could hide failures or reduce review quality.

## 7. Communication
- Answer in the researcher's language, short, with file pointers; every message gets a reply and a final status.
- Approvals cover exactly what they list; "changes requested" means refile with the changes, not proceed.
- Contradiction check before adding rules; latest instruction wins when the researcher says so; one line per decision.
- Do not overload one md with trial details: per-cycle files, one-line logs.
