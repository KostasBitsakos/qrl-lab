# STATE — QRL-Lab strategic handoff
<!-- Read first. ≤ 8 KB / 150 lines. Facts with pointers. Full previous text (verbatim, same
     line numbers as cited below as «A:n»): docs/archive/STATE_2026-11-06_before_B6.md. Older: docs/archive/STATE_2026-10-30_before_J170.md -->
Last update: 2026-11-07 · Claude · J380 (C345 W done). Previous: `docs/archive/STATE_2026-11-06_before_J360.md`.
## 1. Goal now
- PhD paper: hybrid quantum–classical extension of the DInos autoscaler; simulation first, then real cluster. **CCGrid abstract 24/11/2026**; remaining: Poisson experiments → quantum additions → new experiments → writing. Quantum work PAUSED (`docs/rules/paused.md`); order and start decided by the researcher in the dashboard (plan §1).
- Cycle 2 (triggered 29/10, R-20261028-001): all models + DRe-SCale LSTM-PPO baseline, noisy Poisson microservice workload, Claude/Codex branches (`docs/cycle2_plan.md`, `docs/expert/`).
## 2. In progress
- **J377 / M-20261106-082:** scripts 2min alerts/6h reports, 22 tests, Claude APPROVE· `.lab/j377/REPORT.md`. Host ενεργοποίηση/κινητό ανεπιβεβαίωτα. Πρώτο slot 7/11 02:18:28 UTC μετά install.
- **J352 / R-20261106-002(δ):** offline drafts στο `real/infra-draft/` (αυτούσια Redis YAML + namespace overlay `qrl-calib`, τοπολογία, seeded Poisson/NHPP RESP schedule, runbook/rollback). SHA-256 και unit tests σε cores 4–7 πέρασαν (`.lab/j352/GATES.md`, `checks.log`). Ανεξάρτητο Codex review: αποδοχή μόνο ως offline draft (`.lab/j352/codex_review_round2.md`, `P-20261106-141607-96d6`), όλα τα gates πέρασαν. Χωρίς cluster/φορτίο· calibration PAUSED.
- **J351 / R-20261106-002(γ):** `docs/quantum_design_v1.md` σχεδιάζει τέσσερις Quantum Dinos V.2 (+transfer) παραλλαγές με ακριβώς parameter-matched controls, τύπους πόρων και όρια ισχυρισμών. Μόνο design· screens/training/QPU παραμένουν paused. Codex review: αποδεκτό για design-only (`.lab/j351/codex_review_round2.md`), ακριβές parameter matching και δισέλιδο PDF: `.lab/j351/`.
- R-20261106-001 / J343: εγκρίθηκε η Πρόταση 2· Redis αντίγραφο στο `code/real/` (173 υπάρχοντα αρχεία ίδια), K8s στο `code/real/k8s/` (6 νέα). SHA-256 επαλήθευση 179 αρχείων: `code/real/COPY_MANIFEST.json`, προέλευση/όρια `code/real/PROVENANCE.md`. Originals read-only, χωρίς cluster/run· calibration παραμένει PAUSED.
- **v0.5.1:** B0–B7 merged 6/11 (75c56e2), governor ON, dispatcher/dashboard restarted. Infrastructure-only freeze; research continues. Issues/rollback: `CHANGELOG_v05.md`; deviations: `docs/V051_changes_from_original_plan.md`. Baseline: 24 failures (`.lab/backup-v051-20261105/`); merge requires same set.
- **J341 council C341 (M-20261106-011)**: Opus+Astra converged plan to 9/11 on poisson_ms (W screening → freeze → F 10 seeds × 39,936 ticks + HPA → test12 once, integrity gate), new control `derp_ddqn`; card **R-20261106-002** (~350 CPU-h envelope, code work, quantum design-only, Opus workers). DDQN check: all LSTM arms are Double DQN; DERP uses plain max target (`.lab/c341/ddqn_findings.md`, `.lab/c341/council_record.md`). Nothing started.
- **J380 / C345 W DONE (7/11):** 55/55, 0 errors, 41,4 of 80,56 CPU-h; M-091 alert = watchdog race, fixed + test. Selection per arm + F draft (270 CPU-h reserved, 2 parents, NOT launch-ready): `.lab/j380/`, `tools/c345/build_f.py`; card R-20261107-001 waits for researcher; next: joint review, driver stage F, frozen F card.
- **J369/J373 / R-20261106-006 (W ran to completion 6/11 23:22):** W (55 tasks, poisson_ms, cap 80,56 CPU-h, spec hash 27c7de9e…26d10db236d3, `.lab/c345run/parent-spec.json`) restarted 20:18:27 UTC via systemd-run (first start died, `.lab/j370/REPORT.md`). 20:21: driver+watcher alive, P0 gate run `c345-W-reference-hpa` running (state.json); W tasks follow after P0 (max_parallel 16).
- J350/J364: DDQN d9357d4, `tools/c345/`, `tests/test_c345.py`, `.lab/j364/`; R-006 supersedes launch draft.
- Older experiments (J332, J311/J312, J299/J304, J291, J289, J282/J269/C275, J253): A:20-43, `docs/EXPERIMENTS.md`.
## 3. Waiting for the researcher
- **R-20261106-007 / J374:** ο ερευνητής εξουσιοδότησε ό,τι χρειάζεται για την τεχνική αποκατάσταση της εγκεκριμένης εκκίνησης W. Διαβιβάστηκε στον ήδη ενεργό **J373 / R-20261106-008**, που αναλαμβάνει αποκλειστικά την επανεκκίνηση· δεν εκκρεμεί νέα έγκριση για την ίδια αποκατάσταση. Πραγματική εκκίνηση παραμένει ανεπιβεβαίωτη από J374 (`.lab/j374/REPORT.md`, προηγούμενη αποτυχία `.lab/j370/REPORT.md`).
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
- Never DERP eps=1 or reuse spent test splits. Never ask approval for `sqlite3` (C2: `docs/researcher_requirements.md`; J360 not retried). J362: approved worktree retry blocked by read-only `.git`; no tests ran (`.lab/j362/retry.md`). R-003 without spec/hash cannot apply (A:80).
- No hourly in-session crons (A:82-84). `~/.local/bin` must be on PATH for services (A:85). Do not pin the coordinator to CPUs (A:87).
## 7. Standing rules (full text: `docs/claude-memory/`, A:89-104)
- Address «Κώστα», sign «— Πάρις». Cores: 0-3 dashboard, 4-7 agents/tests, 8-39 experiments. Check contradictions before editing rules. Research the practice online before important tasks. Cheapest adequate agent; scripts over LLM loops. Handoff `docs/rules/handoff.md`. Paper start: raise `docs/paper_notes.md` §6 first.
## 8. Pointers
- Requirements `docs/researcher_requirements.md` · Plan `docs/PLAN.md`, `docs/QRL-Lab_v0.5.1_final_plan.md` · Decisions `docs/DECISIONS.md` · Rules `docs/rules/` · Experiments `docs/EXPERIMENTS.md` · Index `docs/INDEX.md` · Journal `docs/journal/` · Retrieval `python3 tools/kb.py query "<question>"`.
- Worktrees: code-tuning (dinos-tuning), code-tuning-astra, code-tuning-c19/-c20/-c22/-c23. Original code read-only: ~/simulations, ~/redis, ~/k8s, ~/prometheus-grafana.
