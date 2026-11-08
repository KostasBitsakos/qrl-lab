# STATE — QRL-Lab strategic handoff
<!-- Read first. ≤ 8 KB / 150 lines. Facts with pointers. Full previous text (verbatim, same
     line numbers as cited below as «A:n»): docs/archive/STATE_2026-11-06_before_B6.md. Older: docs/archive/STATE_2026-10-30_before_J170.md -->
Last update: 2026-11-07 · Codex · J395. Previous: `docs/archive/STATE_2026-11-07_before_J395.md` (verbatim).
## 1. Goal now
- PhD paper: hybrid quantum–classical extension of the DInos autoscaler; simulation first, then real cluster. **CCGrid abstract 24/11/2026**; remaining: Poisson experiments → quantum additions → new experiments → writing. Quantum work PAUSED (`docs/rules/paused.md`); order and start decided by the researcher in the dashboard (plan §1).
- Cycle 2 (triggered 29/10, R-20261028-001): all models + DRe-SCale LSTM-PPO baseline, noisy Poisson microservice workload, Claude/Codex branches (`docs/cycle2_plan.md`, `docs/expert/`).
## 2. In progress
- **J383 / M-20261107-005:** supervisor `tools/supervisor.py` (script-only, νέα αρχεία + `driver.py resume`): ειδοποίηση άμεσα + ασφαλής αυτόματη συνέχιση (max 2, ίδιο εγκεκριμένο spec), 87 tests pass, Codex APPROVE (3 γύροι, `.lab/j383/`). Κανόνες `docs/rules/supervisor.md`. ΕΝΕΡΓΟΠΟΙΗΘΗΚΕ 7/11 13:16 UTC (R-20261107-004, J387): transient timer `qrl-supervisor`, ανά 2 λεπτά, cores 4-7· δεν επιβιώνει reboot. Χωρίς phone push.
- **J377:** monitors, 22 tests + Claude review: `.lab/j377/REPORT.md`. J394: 6ωρο timer ενεργό, waiter F-B θέλει host stop· `.lab/j395/REPORT.md`.
- **J352 / R-20261106-002(δ):** offline drafts `real/infra-draft/` (Redis YAML, namespace `qrl-calib`, seeded RESP schedule, runbook); Codex: αποδοχή μόνο ως draft (`.lab/j352/GATES.md`, `codex_review_round2.md`). Χωρίς cluster· calibration PAUSED.
- **J351 / R-20261106-002(γ):** `docs/quantum_design_v1.md`: 4 Quantum Dinos V.2 (+transfer) παραλλαγές, parameter-matched controls· design-only, quantum PAUSED (`.lab/j351/`).
- R-20261106-001 / J343: εγκρίθηκε η Πρόταση 2· Redis αντίγραφο στο `code/real/` (173 υπάρχοντα αρχεία ίδια), K8s στο `code/real/k8s/` (6 νέα). SHA-256 επαλήθευση 179 αρχείων: `code/real/COPY_MANIFEST.json`, προέλευση/όρια `code/real/PROVENANCE.md`. Originals read-only, χωρίς cluster/run· calibration παραμένει PAUSED.
- **v0.5.1:** B0–B7 merged 6/11 (75c56e2), governor ON, dispatcher/dashboard restarted. Infrastructure-only freeze; research continues. Issues/rollback: `CHANGELOG_v05.md`; deviations: `docs/V051_changes_from_original_plan.md`. Baseline: 24 failures (`.lab/backup-v051-20261105/`); merge requires same set.
- **J341 council C341 (M-20261106-011)**: Opus+Astra converged plan to 9/11 on poisson_ms (W screening → freeze → F 10 seeds × 39,936 ticks + HPA → test12 once, integrity gate), new control `derp_ddqn`; card **R-20261106-002** (~350 CPU-h envelope, code work, quantum design-only, Opus workers). LSTM: Double DQN· DERP: max target (`.lab/c341/ddqn_findings.md`, `.lab/c341/council_record.md`). Council record only.
- **J380 / C345 W DONE (7/11):** 55/55, 0 errors, 41,4 of 80,56 CPU-h; M-091 = watchdog race, fixed + test. Selection + F draft: `.lab/j380/`, card R-20261107-001 (approved, Πρόταση 1).
- **J381 / R-20261107-001:** F extension DONE, δεν ξεκίνησε τίποτα: `tools/c345/build_f.py` → `.lab/j381/F-spec-A/B.json` (2 parents × 50 tasks, 135,2 CPU-h each, seeds 18600-09, val only), driver `f_from_w` mode, 37 tests pass· επιλογή W 10/10. Review + whole-spec check: `.lab/j381/codex_review.md`. Ξεχωριστό `QRL_C345_OUT` ανά γονέα.
- Older experiments: A:20-43, `docs/EXPERIMENTS.md`; W history: `.lab/j370/REPORT.md`.
## 3. Waiting for the researcher
- **J408: F-B ΤΕΛΕΙΩΣΕ (8/11 ~18:30 UTC)**, 50/50 done, 10 seeds×10 arms. Πίνακας 10 seeds (val, χωρίς claim): `.lab/c401/RESULTS.md`, `f_analysis.json`. 8 μοντέλα +53..+69χιλ. από HPA, κανένα δεν νικά tuned HPA (211,8χιλ.· καλύτερο Dinos 200χιλ.)· DERP αρχικό ≈HPA, rppo χειρότερο. Επόμενο: integrity gate → test12 (μόνο με έγκριση/κανόνα κύκλου 9/11). Παλιά attempts: `tools/c345/fb_restart.py`, `.lab/c345f-b/superseded.json`.
- v0.5.1: dashboard live message + approved small `sim` pending (B3).
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
- Never DERP eps=1 or reuse spent test splits. Never ask approval for `sqlite3` (C2: `docs/researcher_requirements.md`; J360 not retried). J362: approved worktree retry blocked by read-only `.git`; no tests ran (`.lab/j362/retry.md`). R-003 without spec/hash cannot apply (A:80).
- No hourly in-session crons (A:82-84). `~/.local/bin` must be on PATH for services (A:85). Do not pin the coordinator to CPUs (A:87).
## 7. Standing rules (full text: `docs/claude-memory/`, A:89-104)
- Address «Κώστα», sign «— Πάρις». Cores: 0-3 dashboard, 4-7 agents/tests, 8-39 experiments. Check contradictions before editing rules. Research the practice online before important tasks. Cheapest adequate agent; scripts over LLM loops. Handoff `docs/rules/handoff.md`. Paper start: raise `docs/paper_notes.md` §6 first.
## 8. Pointers
- Requirements `docs/researcher_requirements.md` · Plan `docs/PLAN.md`, `docs/QRL-Lab_v0.5.1_final_plan.md` · Decisions `docs/DECISIONS.md` · Rules `docs/rules/` · Experiments `docs/EXPERIMENTS.md` · Index `docs/INDEX.md` · Journal `docs/journal/` · Retrieval `python3 tools/kb.py query "<question>"`.
- Worktrees: code-tuning (dinos-tuning), code-tuning-astra, code-tuning-c19/-c20/-c22/-c23. Original code read-only: ~/simulations, ~/redis, ~/k8s, ~/prometheus-grafana.
