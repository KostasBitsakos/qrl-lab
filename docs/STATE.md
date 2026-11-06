# STATE — QRL-Lab strategic handoff
<!-- Read first by every coordinator. ≤ 8 KB / 150 lines. Facts only, each with a pointer. Full previous text (verbatim, same
     line numbers as cited below as «A:n»): docs/archive/STATE_2026-11-06_before_B6.md. Older: docs/archive/STATE_2026-10-30_before_J170.md -->
Last update: 2026-11-06 · by: Claude · task: v0.5.1 B3–B6 in worktree `v05` (plan `docs/QRL-Lab_v0.5.1_final_plan.md`)
## 1. Goal now
- PhD paper: hybrid quantum–classical extension of the DInos autoscaler; simulation first, then real cluster. **CCGrid abstract 24/11/2026**; remaining: Poisson experiments → quantum additions → new experiments → writing. Quantum work PAUSED (`docs/rules/paused.md`); order and start decided by the researcher in the dashboard (plan §1).
- Cycle 2 (triggered 29/10, R-20261028-001): all models + DRe-SCale LSTM-PPO baseline, noisy Poisson microservice workload, Claude/Codex branches (`docs/cycle2_plan.md`, `docs/expert/`).
## 2. In progress
- **v0.5.1 system work** (CHANGELOG_v05.md, known issues there): B0–B7 merged in master 6/11 (75c56e2); governor ON since 6/11; dispatcher+dashboard restarted 6/11 (heartbeat ok). B3 events by script, B4 settings edit + config cards, B5 roles/Codex commit/solo review, B6 knowledge + this condensation. Deviations from the plan: `docs/V051_changes_from_original_plan.md`. Freeze (B7): «αφορά μόνο υποδομή (dispatcher, dashboard, tools, κανόνες)· η έρευνα, τα πειράματα και το paper συνεχίζουν κανονικά». Final infra round merged+restarted 6/11 (liveness owner+heartbeat, fast sweeper, recover for peers; `CHANGELOG_v05.md`). Rollback: `git reset --hard 5360422` (before liveness) or `dfe5bcb` (before B3) + restart both services. Baseline: 24 known test failures (`.lab/backup-v051-20261105/`); merge rule: same set.
- Experiments, latest first (details A:n): J332 Codex 24h draft proposal, nothing started (A:20) · J311/J312 stage 1b R-20261102-001 finished 24/24, no claim, stage 2 awaits decision (A:24) · J299/J304 stage A stopped 2/11 by reservation guard (A:25) · J291 audit + R-20261101-004/005 cards (A:26) · J289 cycle3 finished (A:28) · J282/J269/C275 cycle3 history (A:29-31) · J253 screen final (A:43).
- Earlier infrastructure notes (J322, J314 kb.py, C326 sidebar, J279 usage fix, J228 mobile latency, J221 deny-rule loop, J230 tokens, J225 graphify, J241/J236/J233/C235/C232 recovery of waves 5-7, R-010 screen, J126/J132/J92, J100/J143/J165, R-011, J97/J103, cycle1 notices, cycle2 frozen env/launcher, GitHub tags): A:21-23, A:27, A:32-42, A:44-50.
## 3. Waiting for the researcher
- v0.5.1: a live test message from the dashboard after the 6/11 restart; one small approved `sim` run would exercise B3.
- R-20261101-005 and the stage-A remainder: new card/approval needed; nothing starts without it (A:53). R-20261031-001 ran to 2/11 (A:54).
- R-20261030-004/005 recovery of waves 6-7 needs a host-visible check first (A:55-56, `.lab/j236/`); R-012 dispatcher restart done 6/11 (live token-saving still unverified, A:58); results-retention policy open (A:59); branch cleanup dinos-tuning-c19/-c20/-c22/-c23 needs joint review + OK (A:60).
## 4. Next steps (in order)
1. **B7 freeze until the abstract (24/11) — «αφορά μόνο υποδομή (dispatcher, dashboard, tools, κανόνες)· η έρευνα, τα πειράματα και το paper συνεχίζουν κανονικά».** Infrastructure: only fixes. Known issues: `CHANGELOG_v05.md`.
2. Researcher decides stage 2 / remaining stage-A arms (A:24-25); every run only via `launch_run.py` with an approved frozen spec.
3. Keep `docs/EXPERIMENTS.md` per batch; flaky `tests/test_lab.py::test_sandbox`.
## 5. Key facts (pointer each)
- Cycle1 finals test11 R-20261023-001/c24c, test10 R-20261022-005/c18c: `.lab/tuning/cycles/c24_test11_result.md`, `c21_test10_result.md`; test10/11 are spent single-use. Recipe `.lab/tuning/cycles/c24_freeze.md`. Not cycle2 targets (M-20261029-017).
- The 17x is a protocol artefact (DERP eps=1); original HPA reacts to independent random CPU/mem; oracle_Dstep is look-ahead, not an optimal bound (`docs/paper_notes.md` §6).
- Names: LSTM / LSTM+transfer / Dinos / Dinos+Transfer V.2 (always the full «Dinos+Transfer V.2»); `derp` original / `derp_hist10` enhanced (M-20261022-007).
- Stage results (val only, large variance, NO claim): `.lab/j299/stageA_summary.json`, `.lab/j312/summary.json`, `.lab/j289/summary.json`, `docs/EXPERIMENTS.md`.
- Real cluster/calibration PAUSED (`docs/rules/paused.md`). Governor/usage rules: plan §5, `tools/governor.py`.
## 6. Do not repeat
- Dropped in the loop: sim_v2 as primary, coupled env, D=15/20 delays, noise15_multispike_d5, spike300_d7/multispike_d5 envs, noise for B1, dueling, PER, arch a12, c23 (`docs/tuning_experiments.md`).
- Never evaluate DERP at eps=1; never reuse a spent test split. Never ask approval for `sqlite3` (deny rule; A:79). R-003 approved without spec/hash cannot be applied (A:80).
- No hourly in-session crons (A:82-84). `~/.local/bin` must be on PATH for services (A:85). Do not pin the coordinator to CPUs (A:87).
## 7. Standing rules (full text: `docs/claude-memory/`, A:89-104)
- Address «Κώστα», sign «— Πάρις». Cores: 0-3 dashboard, 4-7 agents/tests, 8-39 experiments. Check contradictions before editing rules. Research the practice online before important tasks. Cheapest adequate agent; scripts over LLM loops. Handoff `docs/rules/handoff.md`. Paper start: raise `docs/paper_notes.md` §6 first.
## 8. Pointers
- Requirements `docs/researcher_requirements.md` · Plan `docs/PLAN.md`, `docs/QRL-Lab_v0.5.1_final_plan.md` · Decisions `docs/DECISIONS.md` · Rules `docs/rules/` · Experiments `docs/EXPERIMENTS.md` · Index `docs/INDEX.md` · Journal `docs/journal/` · Retrieval `python3 tools/kb.py query "<question>"`.
- Worktrees: code-tuning (dinos-tuning), code-tuning-astra, code-tuning-c19/-c20/-c22/-c23. Original code read-only: ~/simulations, ~/redis, ~/k8s, ~/prometheus-grafana.
