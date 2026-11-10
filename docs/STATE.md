# STATE — QRL-Lab strategic handoff
<!-- Read first. ≤ 8 KB / 150 lines. Facts with pointers. Full previous text (verbatim, same
     line numbers as cited below as «A:n»): docs/archive/STATE_2026-11-06_before_B6.md. Older: docs/archive/STATE_2026-10-30_before_J170.md -->
Last update: 2026-11-10 · J457 (c4 Φάση 0). Previous (verbatim): `docs/archive/STATE_2026-11-10_before_J457.md`.
## 1. Goal now
- PhD paper: hybrid quantum–classical extension of the DInos autoscaler; simulation first, then real cluster. **CCGrid abstract 24/11/2026**; remaining: Poisson experiments → quantum additions → new experiments → writing. Quantum work PAUSED (`docs/rules/paused.md`); order and start decided by the researcher in the dashboard (plan §1).
- Cycle 2 (R-20261028-001): all models + DRe-SCale baseline, noisy Poisson workload, Claude/Codex branches (`docs/cycle2_plan.md`).
## 2. In progress
- **C455 / cycle 4 (M-20261110-030):** οδηγίες `Mds με νέες οδηγίες Κώστα/QRL-Lab_cycle4_instructions.md`, ένας κλάδος c4 (`code-poisson-c4/`), Poisson ως 13/11· Φάσεις 0-2 sim προεγκεκριμένες, G2/τελικός έλεγχος θέλουν ΟΚ. Jobs J456 (φάκελος «Αποτελέσματα 2ου Κύκλου Πειραμάτων Poisson»), J457 (Φάση 0), J458 (υλοποίηση v2, Codex). Briefs `.lab/c455/`.
- **J458 / c4 ΣΤΑΣΗ πριν από υλοποίηση:** διαψεύστηκε η [Υ] §1.1: ο παλιός `hpa_demand` ήδη περιορίζεται σε ±1 μέσω `pms_reference.py:30–33,49`, με EWMA αφίξεων. Το §0 απαιτεί απόφαση ερευνητή· ενημερώθηκε C455. Δεν δημιουργήθηκαν c4 copy/branch, specs ή runs· `docs/c4_implementation_blocker.md`, `.lab/c4/implementation/GATES.md` (M-20261110-030). Commit blocked: read-only `.git/index.lock`.
- **J457 / c4 Φάση 0:** 0.1 έγινε (ο κανόνας είναι ήδη ±1, clip μόνο στο Dinos clip_frac 0,988, ε V.2 δεν φτάνει floor), 0.5 draft· 0.2 script+draft spec χωρίς approved request id, 0.3/0.4 όχι· G0 προσωρινό κλάδος 2. `.lab/c4/phase0/REPORT.md`.
- **J446 / J444:** ENV-cycle3 n0–177 175 done + 3 σκόπιμα failed selftests· J444 n170–177 eval-only seed19100· λείπει RPPO adaptation. `.lab/j446/{summary.json,REPORT.md}` (λεπτομέρειες στο archive before_J457).
- **T ΟΛΟΚΛΗΡΩΘΗΚΕ (R-20261110-001, J450):** 40/40 exit0, Dinos / Dinos+Transfer V.2 × spiky/shift ×10 seeds 19200–19209, val. V.2−Dinos 95%CI: spiky[-10208,+12060], shift[-27571,-4136]· exploratory. `.lab/j450/T-summary.json`.
- **J436/J442 (batch S ΤΕΛΕΙΩΣΕ 10/11):** 7 arms×10 seeds, spiky val, 70/70 exit0. Val: dinos 191,6k±7,1k, v2 188,1k±12,0k, lstm_transfer 179,9k, lstm 164,6k, derp 153,6k, derp_hist10/rppo ασταθή· όλα < tuned HPA 201,9k, oracle 222,7k. Paired v2−dinos −3,5k±16,9k. `.lab/j442/summary.json`· test13 μόνο με frozen spec/review.
- **J427:** F1–F3 draft (`tools/envelope.py`, `docs/envelopes/cycle3.json`, M-20261109-043), εκκρεμεί review/restart από ερευνητή. Διάγνωση: `.lab/c426/`· παλιά κατάσταση στο αρχείο πριν J446. Υποδομή μόνο fixes.
- **J383:** supervisor ΕΝΕΡΓΟ (`docs/rules/supervisor.md`). **J352/J343:** offline drafts `real/infra-draft/`, `docs/quantum_design_v1.md`· PAUSED.
- **v0.5.1:** B0–B7 merged 6/11, governor ON; freeze μόνο υποδομής. Issues `CHANGELOG_v05.md`. Baseline 24 failures (`.lab/backup-v051-20261105/`).
- **Cycle2 poisson_ms:** W (7/11, `.lab/j380/`), F 10 seeds (`.lab/c401/RESULTS.md`), test12 103/103 (M-20261109-040, SPENT). Council `.lab/c341/`· παλιότερα A:20-43.
- **J444/J450 PDFs:** `reports/2026-11-10-models-report/report.pdf`, `reports/2026-11-10-goals-experiments/report.pdf` (review.md, verification.json, 327f0d1). Αρχεία μόνο μέσω 📁 Αρχεία (M-20261110-014).
## 3. Waiting for the researcher
- R-20261110-001 εγκρίθηκε και T40/40 ολοκληρώθηκε (M-20261110-016/017), ανάλυση J450. Για νέο τελικό test χρειάζεται ξεχωριστό frozen spec/review. Εκκρεμεί επανεκκίνηση dispatcher για F3 (M-20261109-043).
- J421/J423: test12 ολοκληρώθηκε (103/103). Πύλη: μη διαβάζεις test12 ξανά (ledger `.lab/test12_ledger/`).
- Ανοιχτά (παλιά): R-20261101-005/stage-A (A:53), recovery κυμάτων 6-7 (A:55-56), results-retention (A:59), cleanup branches c19/c20/c22/c23 (A:60).
## 4. Next steps (in order)
1. **B7 freeze until the abstract (24/11) — «αφορά μόνο υποδομή (dispatcher, dashboard, tools, κανόνες)· η έρευνα, τα πειράματα και το paper συνεχίζουν κανονικά».** Infrastructure: only fixes. Issues: `CHANGELOG_v05.md`.
2. Researcher decides stage 2 / remaining stage-A arms (A:24-25); every run only via `launch_run.py` with an approved frozen spec.
3. Keep `docs/EXPERIMENTS.md` per batch; flaky `tests/test_lab.py::test_sandbox`.
## 5. Key facts (pointer each)
- **ENV-cycle3 / J438+J431 (9/11):** shift val 10×5000: HPA original 166699,14, tuned 224953,91, oracle 238595,64, DERP 188479,47, Dinos 211705,68 (−5,89% vs tuned)· 90 eval-only checkpoints, 3 σκόπιμα failed selftests· περιγραφικά, val-selected, όχι claim, όχι test. Spiky smoke DERP s19100 mean 179021,94 (J436 κάνει το πλήρες S). Αναλυτικά `.lab/j438/{summarize.py,summary.json,REPORT.md}`, `.lab/j431/REPORT.md`· Claude APPROVE P-20261109-225832-b5d0.
- Cycle1 finals test11 R-20261023-001/c24c, test10 R-20261022-005/c18c: `.lab/tuning/cycles/c24_test11_result.md`, `c21_test10_result.md`; test10/11 are spent single-use. Recipe `.lab/tuning/cycles/c24_freeze.md`. Not cycle2 targets (M-20261029-017).
- The 17x is a protocol artefact (DERP eps=1); original HPA reacts to independent random CPU/mem; oracle_Dstep is look-ahead, not an optimal bound (`docs/paper_notes.md` §6).
- Names: LSTM / LSTM+transfer / Dinos / Dinos+Transfer V.2 (always the full «Dinos+Transfer V.2»); `derp` original / `derp_hist10` enhanced (M-20261022-007).
- Stage results (val only, large variance, NO claim): `.lab/j299/stageA_summary.json`, `.lab/j312/summary.json`, `.lab/j289/summary.json`, `docs/EXPERIMENTS.md`.
- Real cluster/calibration PAUSED (`docs/rules/paused.md`). Governor/usage rules: plan §5, `tools/governor.py`.
## 6. Do not repeat
- Dropped in the loop: sim_v2 as primary, coupled env, D=15/20 delays, noise for B1, dueling, PER, a12, c23 (`docs/tuning_experiments.md`).
- Never DERP eps=1 or reuse spent test splits. Never ask approval for `sqlite3` (C2: `docs/researcher_requirements.md`; J360 not retried). J362: approved worktree retry blocked by read-only `.git`; no tests ran (`.lab/j362/retry.md`). R-003 without spec/hash cannot apply (A:80).
- No hourly in-session crons (A:82-84). `~/.local/bin` must be on PATH for services (A:85). Do not pin the coordinator to CPUs (A:87).
## 7. Standing rules (full text: `docs/claude-memory/`, A:89-104)
- Address «Κώστα», sign «— Πάρις». Cores: 0-3 dashboard, 4-7 agents/tests, 8-39 experiments. Check contradictions before editing rules. Research the practice online before important tasks. Cheapest adequate agent; scripts over LLM loops. Handoff `docs/rules/handoff.md`. Paper start: raise `docs/paper_notes.md` §6 first.
## 8. Pointers
- Requirements `docs/researcher_requirements.md` · Plan `docs/PLAN.md`, `docs/QRL-Lab_v0.5.1_final_plan.md` · Decisions `docs/DECISIONS.md` · Rules `docs/rules/` · Experiments `docs/EXPERIMENTS.md` · Index `docs/INDEX.md` · Journal `docs/journal/` · Retrieval `python3 tools/kb.py query "<question>"`.
- Worktrees: code-tuning (dinos-tuning), code-tuning-astra, code-tuning-c19/-c20/-c22/-c23. Original code read-only: ~/simulations, ~/redis, ~/k8s, ~/prometheus-grafana.
