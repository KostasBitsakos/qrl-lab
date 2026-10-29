---
description: Dated log of every accepted researcher decision (newest first) with links to the active rules in docs/rules
---
# Accepted decisions — dated log

Newest first, one or two lines per decision. The rules themselves live in [`docs/rules/`](rules/README.md)
(index, precedence, contradiction-check procedure, resolved conflicts). Codex role table: [`docs/rules/models.md`](rules/models.md).
Before adding a decision, follow the procedure in `docs/rules/README.md` (M-20261020-021).

- 2026-10-22 — R-20261021-009/010 (researcher): loop extended to 2026-10-23 23:59 UTC (v7 +120 branch 1, v8 +60 branch 2); goal: Dinos+Transfer V.2 the best, closest to the paper picture (fair protocol). → .lab/codex-handoff/joint_review_decisions.md
- 2026-10-21 — R-20261021-007 (researcher): two parallel branches for this loop only (Opus dinos-tuning cores 8-19; Codex astra dinos-tuning-astra cores 20-31, sandbox v6 80 CPU-h); shared versioned protocol. → .lab/council/C-20261021-03/card.md
- 2026-10-21 — R-20261021-005 (researcher): loop to 22/10, sandbox v5; Dinos V.2 architecture search + Transfer V.2; checkpoints 1k-20k chosen on val. → .lab/council/C-20261021-02/
- 2026-10-21 — R-20261021-003 (researcher): council C-20261021-01 plan (B1, claims list, noise study, then QC). → .lab/council/C-20261021-01/card.md
- 2026-10-21 — researcher (terminal): model routing, core split, env freedom. → rules/models.md
- 2026-10-20 — M-20261020-027 (researcher): engineer on Opus only until the loop ends 2026-10-21; then routing by resources/task as before. → rules/models.md
- 2026-10-20 — M-20261020-025 (researcher): conflicts C1–C6 resolved as proposed in M-20261020-024 (later entries win; calibration paused; W1 deferred; closeness = progress indicator; engineer Opus for research code). → rules/README.md
- 2026-10-20 — R-20261020-001 (researcher): DECISIONS.md split into `docs/rules/`; conflicts C1–C6 listed there, awaiting researcher.
- 2026-10-20 — M-20261020-021 (researcher): contradiction check before adding rules; several cooperating md files allowed. → rules/README.md
- 2026-10-20 — M-20261020-015 (researcher): wider design latitude (inputs, reward, layers; sim need not match the real cluster), core of the work kept. → rules/experiments.md (C1, C2, C3)
- 2026-10-20 — M-20261020-013 (researcher): env variants allowed; tuning-loop implementation by engineer with opus, cross-checked. → rules/experiments.md, rules/models.md (C1, C4, C6)
- 2026-10-19 — M-20261019-048 (researcher): focus on reproducing the DInos picture; no quantum for now. → rules/research.md, rules/paused.md
- 2026-10-19 — M-20261019-044 (researcher): Sofia paper as a source; DInos wins on disagreement. → rules/research.md
- 2026-10-19 — M-20261019-037 (researcher): stronger models for the tuning loop, until 2026-10-21. → rules/models.md
- 2026-10-19 — M-20261019-029 (researcher): per-cycle closeness report. → rules/experiments.md (C5)
- 2026-10-17 — M-20261017-137 (researcher): tuning sandbox on `dinos-tuning` with guardrails. → rules/experiments.md (C1, C5)
- 2026-10-17 — R-20261017-018: SLO = 2 × single-pod p95 at 50 % load from calibration stage B. → rules/paused.md (C3)
- 2026-10-17 — R-20261017-017, council C-20261017-02: training reward = researcher's DInos reward via frozen adapter; classical scope; D5 paused. → rules/experiments.md, rules/paused.md (C2, C3)
- 2026-10-17 — M-20261017-114/117: venues always carry CORE tier and last-3 acceptance rates. → rules/research.md
- 2026-10-17 — M-20261017-005/006/007: mutual Claude/Codex fallback; limit messages and sudo tab in dashboard; simulation first, W0 then W1. → rules/models.md, rules/dashboard.md, rules/experiments.md (C4)
- 2026-10-17 — R-20261017-014: bounded exploratory W0 study; HPA reverse-engineered (M-20261017-068). → rules/archive.md, rules/experiments.md
- 2026-10-17 — R-20261017-011: IBM Quantum in this paper, inference only. → rules/paused.md
- 2026-10-17 — R-20261017-008 (D3): workloads W0+W1 train, W2 test, W3 adaptation. → rules/experiments.md (C4)
- 2026-10-17 — R-20261017-007 (D8): F1 not mentioned in the paper; no DInos sim numbers as comparison points. → rules/research.md
- 2026-10-17 — R-20261017-006 (D5): screen QC4 + QC1 (paused). → rules/paused.md
- 2026-10-16 — R-20261016-018: calibration with a stateless Deployment in namespace `qrl-calib` (paused). → rules/paused.md
- 2026-10-16 — R-20261016-016 + M-20261016-078: model routing, Codex roles, more OpenAI agents. → rules/models.md (C6)
- 2026-10-16 — R-20261016-013 (D2): Sim v2 design, option 1 of C-20261016-01. → rules/experiments.md, rules/archive.md
- 2026-10-16 — R-20261016-001 (D9): IBM account exists; no jobs for now. → rules/paused.md
- 2026-10-16 — handoff standing rules 1–5 and environment facts (D13). → rules/dashboard.md, rules/models.md, rules/security.md, rules/archive.md
- 2026-10-16 — D12: ChatGPT handoff adopted. → rules/security.md, rules/archive.md
- 2026-10-22 (M-20261022-007): model names LSTM / LSTM+transfer (was DInos+T) / Dinos / Dinos+Transfer V.2; test each model at its best checkpoint chosen on val; save convergence metrics (.lab/tuning/convergence.py).
- 2026-10-23 (researcher): handoff rules when one coordinator sleeps (full write coordination for the awake one, detailed notes, agent strength per existing criteria, solo work only in new single-purpose branches, joint review → merge decision → delete those branches): docs/rules/handoff.md.

- 2026-10-26 · R-20261023-004 (after test11: close loop / val-only exploratory run / both) REJECTED by the researcher («Όχι / απόρριψη»). No run, no council, no final summary started from it. Follow-up question R-20261028-001.

## 2026-10-28 — Trim always-loaded rules; disable unused connectors (M-20261028-004, researcher «κάντε το ναι»)
- CLAUDE.md and AGENTS.md shortened; removed duplicates; interactive-only sections moved verbatim to
  `docs/rules/interactive.md`. No rule was dropped (backups `.lab/*.md.bak-20261028`).
- `~/.claude/settings.json`: `enabledPlugins["data@synced"]=false`, `disableClaudeAiConnectors=true`.
- Superseded same day (M-20261028-006, «για αυτό το project»): toggles moved to `.claude/settings.local.json`;
  `~/.claude/settings.json` restored. `tools/build_md_index.py` also indexes `.lab/tuning`, `.lab/council`, `.lab/codex-handoff`.

## 2026-10-28 — R-20261028-001 (researcher)
New experiment cycle, to start only on the phrase «ξεκινα μπανάνες!» (reply «ξεκινανω capteain cagarou»): all current
models + a replicated related-paper model (DRe-SCale LSTM-PPO, see STATE §4.3); new Poisson microservice workload with
noise and spikes; env with latency/CPU/memory; Claude and Codex on separate branches; full decision autonomy for the
cycle (Claude↔Codex agree among themselves); deadline 2/11/2026; daily progress report. Stated target ordering:
Dinos+Transfer V.2 > LSTM+transfer > Dinos > LSTM > paper model > DERP > HPA. Text: `labq.py request R-20261028-001`.

## 2026-10-29 — R-20261028-002 approved: dashboard items 2d,3,5,6,7,8 implemented (dd26185..1bfe9cc); see docs/dashboard_requests_20261028.md

## 2026-10-29 — R-20261029-001 (researcher): CPU-h budget for the R-20261028-001 cycle
Option 1 chosen: one sandbox approval of **160 CPU-h, valid 7 days**; Claude+Codex approve the cycle's child specs
themselves within it (`launch_run.py sandbox-start`), per M-20261028-011 «κρινετε σεις τα specs του κυκλου».
The sandbox request is filed only after «ξεκινα μπανάνες!»; until then nothing runs. Text: `labq.py request R-20261029-001`.

## 2026-10-29 — R-20261029-002 (researcher): push to his GitHub repo
Approved «Ναι / έγκριση». `git push` allowed only to KostasBitsakos/dinos_sofia_k8s_redis_scaling (remote `github`,
deploy key `~/.config/qrl-deploy/id_ed25519`, private key never read/printed), only after a joint Claude+Codex
review, never `--force`, never secrets/logs/`.lab/usage`/kube/IBM files. First upload is curated: code of
dinos-tuning + dinos-tuning-astra, frozen specs, test10/11 result md + per-seed JSON, best checkpoints only (size told
to him first; large → Releases/LFS), LESSONS.md. AGENTS.md:10 and `docs/rules/security.md:3` updated. Text: `labq.py request R-20261029-002`.
- (2026-10-29, M-20261029-028) Standing: (1) Codex coordinates with the same rules/information when Claude is limited, keeps solo notes, joint
  review after (docs/rules/handoff.md 5); (2) every experiment cycle runs on competing Claude/Codex branches with periodic
  exchange of helpful changes (docs/rules/experiments.md); (3) coordinator picks the best model per task across vendors by
  quality/speed/cost and usage left (docs/rules/models.md).
- (2026-10-29, M-20261029-050) Agreed post-competition code goes straight to `github` main (no side branches, no PRs); rule in
  docs/rules/experiments.md. Push permission in .claude/settings.json applied (R-20261029-003).
- (2026-10-29, M-20261029-055) Researcher reiterates: use as many workers as assigned tasks require, with intelligent
  scheduling under his existing instructions. Coordinator schedules independent work in parallel and dependent work
  in order, respecting resources, budgets and model routing; do not ask him to choose a worker count again for each task.
  C37 verified current dispatcher `max_workers=4`; dispatcher settings were not changed.
- (2026-10-29, M-20261029-058, C43) Researcher explicitly authorizes raising max_workers as needed, retaining
  optimal, economical scheduling. Use capacity only for useful independent tasks. C43 attempted the supported
  ceiling 16 (`tools/dispatcher.py:189`); automatic approval review rejected the setting as researcher-only.
  Setting remains last verified at 4; no workaround used. Authorization is recorded; execution remains blocked.
- (2026-10-29, R-20261029-005, J66) «Paper model» in the desired ordering = the adapted DRe-SCale LSTM-PPO arm
  (`tuning.rppo`, IEEE TSC 2024, DOI 10.1109/TSC.2024.3387661). Researcher criterion: the published baseline that matters
  most to reviewers, then ease of replication; of the two candidates (DRe-SCale, Gwydion JNCA 2025) DRe-SCale wins on both
  (`docs/expert/autoscaling_baselines.md`; his choice M-20261022-033). Year mismatch («25 or 26») reported to him; Gwydion
  stays cited, not ported. No new arm, no spec change.
- (2026-10-29, M-20261029-142, C87) Competing Claude-vs-Codex branches ONLY for experiment cycles (to get the best
  results); every other task is done by ONE agent chosen for the objective (`docs/agent_routing.json`, CLAUDE.md routing).
  GitHub publishing of cycle results: versioned, automated after the joint review, without "Compare & pull" banners —
  mechanism (tags vs branches) pending his approval (Αποφάσεις, filed by C87).
