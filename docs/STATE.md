# STATE — QRL-Lab strategic handoff
<!-- Read first by every coordinator (Claude or Codex). At most 150 lines. Facts only, each with a pointer
     (M-/R-/run id, path, URL). Update it at the end of every task that changed something. Older detail goes to
     docs/DECISIONS.md, docs/journal/ or a topic file listed in docs/INDEX.md. -->
Last update: 2026-10-30 · by: Claude (J172) · task: R-20261030-002 reconcile s59, screen resumed
## 1. Goal now
- PhD paper: hybrid quantum–classical extension of the DInos autoscaler; simulation first, then real cluster;
  conference submission end of Nov 2026 (`docs/PLAN.md` §1, §11). Quantum work is PAUSED (`docs/rules/paused.md`).
- Cycle 1 (19-24/10): classical DInos tuning loop on spike300_d5; its numbers are NOT targets any more, only lessons
  (M-20261029-017; results §5, `docs/tuning_experiments.md`).
- **Cycle 2 TRIGGERED 29/10** (R-20261028-001, M-20261029-017/021): all our models + adapted DRe-SCale LSTM-PPO
  baseline (Gwydion cited, not ported: `docs/cycle2_plan.md:41`), new noisy Poisson microservice workload + env with
  latency/CPU/mem, Claude and Codex on separate branches, full autonomy, deadline 2/11, daily report. Wanted ordering: V.2 > LSTM+transfer > Dinos > LSTM > paper model > DERP > HPA. Budget 160 CPU-h sandbox, 7 days (R-20261029-001);
  file the sandbox request when runs start. Plan: `docs/cycle2_plan.md`, expert pack `docs/expert/` (J12, d6cfa11).

## 2. In progress (what · id · owner · next check)
- M-20261030-001 → J169: συνέχιση εγκεκριμένου R-010 screen, έλεγχος s59 και DB-lock fix· δεν τεκμαίρεται ακόμη επανεκκίνηση από την ανάθεση (`.lab/c168/`, §3). J170: απογραφή Markdown και token leaks (`.lab/j170/report.md`).
- R-010 screen: μόνο 56 tasks, hard136 CPU-h/cap2.5h, κοινή χρέωση R-006· actual/reservation/remaining-ledger gates, STOP και στα δύο lanes σε failure/overrun, χωρίς retry/αύξηση caps. test12/shift-test και επόμενα stages κλειστά. Frozen hash42ac17ed…6682a94, approvals/reviews J119/J120 (`.lab/j119/amendment-spec.json`, `.lab/j120/final-review.md`; R-20261029-010).
- J126/J132: τελευταία ενδιάμεση ανάλυση, όχι τελικό αποτέλεσμα· μόνο 2 val seeds, κανένας νικητής. Driver/ανά κύμα στοιχεία `.lab/j126/{driver.log,results.jsonl}`, κόστος/πίνακες `.lab/j132/{result.md,summary.json}`. Calibration J92 ολοκληρωμένο (`.lab/j92/calib_result.md`).
- J100/J143 committed4286965, J165 debounce committedf1a1e8c· dispatcher activation/restart εκκρεμεί (§3). Review/tests `.lab/j157/`, `.lab/j143/handoff.md`, `.lab/j165/tests.log`· όχι επανάληψη υλοποίησης.
- Dashboard restart R-011 DONE 29/10 19:42UTC: cycle2-first/DRe-SCale και λογότυπο πάνω από tokens επαληθεύθηκαν live (`.lab/j162/live.json`, M-20261029-293). Sidebar commit5e7daa2, Claude limits fix4a2828e (M-20261029-292/296). Bytes/4 είναι εκτίμηση ανά ανάγνωση, συνολική πραγματική εξοικονόμηση άγνωστη (`tools/token_metrics.py`).
- J97 tutorials draft, review/commit pending· J103 Race review pending: παραδόσεις `.lab/j97/handoff.md`, `.lab/j103/handoff.md`, `docs/tutorials/REVIEW.md`. Μην επαναλάβεις τους ήδη τεκμηριωμένους ελέγχους χωρίς νέο λόγο.
- Stale cycle1 end-notices R-20261021-005/007 έχουν ελεγχθεί επανειλημμένα· J130/J134/J141 και J133/J140: `.lab/j130/report.md`, `.lab/j134/report.md`, `.lab/j141/audit.json`, `.lab/j133/report.md`, `.lab/j140/audit.json`. Δεν είναι νέα πειράματα· dispatcher F1 fix στο4286965, activation pending (§3).
- Cycle2 frozen env238003f / harnessb609b93, launcher commit ecca33d, root guard7d55754 / astra182af33· CLI/περιορισμοί `docs/cycle2_launcher.md`, `.lab/cycle2-claude/status.md`. val13000–13019 / test12 14000–14019 locked (J64/R-006). Daily report `tools/cycle2_daily.py`, `.lab/cycle2_daily/cron.log` (J72).
- GitHub: main901fe54 + tags cycle1-claude-v1.0/cycle1-codex-v1.0 επαληθεύθηκαν J95· publishing `docs/github_publishing.md` (R-008). Η παλιά οδηγία J17 για push side branches είναι ιστορική, βλ. πλήρες αρχείο παρακάτω και `docs/rules/experiments.md` (M-20261029-050).
- Πλήρες ιστορικό πριν τη συμπύκνωση, με όλα τα run/test/commit στοιχεία και παλιές εκκρεμότητες: `docs/archive/STATE_2026-10-30_before_J170.md` (J170/M-20261030-001). Δεν φορτώνεται ολόκληρο στην έναρξη· αναζήτηση μόνο σχετικού θέματος.
## 3. Waiting for the researcher
- R-010 screen ΣΥΝΕΧΙΖΕΙ: R-20261030-002 APPROVED 30/10 05:40UTC (Πρόταση 1)· J172 έτρεξε `.lab/c168/reconcile_s59.py` → s59 done/exit0 inferred, ended 15:45:24 (`.lab/c168/reconcile.json`). Driver J126: wave4 done used6.64 CPU-h, wave5 s60-s67 ξεκίνησε 05:45UTC (`.lab/j126/driver.log`). Fix 95033ff ενεργό για νέα runs.
- R-012 APPROVED, (1)+(3) υλοποιημένα f1a1e8c, 33 tests PASS· (5) restart `qrl-dispatcher` δεν έγινε, system unit/headless gate και ενεργά jobs. Να γίνει όταν idle με νόμιμη έγκριση· ενεργοποιεί και J143. Χωρίς live επαλήθευση δεν δηλώνεται εξοικονόμηση (M-20261029-294, `.lab/j165/tests.log`).
- Results-retention policy εκκρεμεί (M-20261029-009)· παλιά open/waiting μηνύματα χρειάζονται triage, όχι αυτόματη επανεκτέλεση (`docs/archive/STATE_2026-10-30_before_J170.md` §3).
- Merge/delete branches dinos-tuning-c19/-c20/-c22/-c23: κοινό Claude+Codex review και ΟΚ ερευνητή (`docs/rules/handoff.md` rule4).
## 4. Next steps (in order)
1. J169 αποκατάσταση/συνέχεια μόνο εγκεκριμένου screen· μετά DONE/STOP ledger και stage review (§2–3, R-010, M-20261030-001). Cycle2 στρατηγική/κριτήρια `docs/cycle2_plan.md`, fairness/claims `docs/paper_notes.md`.
2. Dispatcher activation του ήδη εγκεκριμένου R-012 όταν idle και με το απαιτούμενο service permission (§3)· J170 προτάσεις χωρίς εφαρμογή `.lab/j170/proposals/`.
3. Διατήρηση `docs/EXPERIMENTS.md` για κάθε batch· branch cleanup (§3), flaky `tests/test_lab.py::test_sandbox` (handoff23/10).
4. Cheap Q&A/one-thread-per-topic παραμένουν προτάσεις, όχι απόφαση (`docs/token_practices.md`).

## 5. Key facts and numbers (each with a pointer)
- Cycle1 τελικά test11 R-20261023-001 / c24c, test10 R-20261022-005 / c18c: αποτελέσματα/CI `.lab/tuning/cycles/c24_test11_result.md`, `.lab/tuning/cycles/c21_test10_result.md`. Test10/11 είναι spent single-use· δεν ξαναχρησιμοποιούνται. Δεν αποτελούν στόχους cycle2 (M-20261029-017).
- Frozen cycle1 recipe a1h/n-step3/spike300_d5: `.lab/tuning/cycles/c24_freeze.md`; απορριφθέν c23: `.lab/tuning/cycles/c23_screen.md`. Πλήρης αριθμητική σύνοψη στο archive §5 (`docs/archive/STATE_2026-10-30_before_J170.md`).
- Το 17x είναι protocol artefact (DERP eps=1), όχι fair comparison· HPA αρχικού κώδικα αντιδρά σε ανεξάρτητο random CPU/mem· oracle_Dstep είναι look-ahead heuristic, όχι optimal bound (`docs/paper_notes.md` §6, `docs/tuning_experiments.md`).
- Ονόματα: LSTM / LSTM+transfer / Dinos / Dinos+Transfer V.2· πάντα πλήρες «Dinos+Transfer V.2». `derp` αρχικό / `derp_hist10` enhanced, best-val checkpoints (M-20261022-007, M-20261029-121).
- Real cluster/calibration PAUSED· stage-B δεν επαναλαμβάνεται (`docs/rules/paused.md`, `.lab/outbox/calib-status.md`, `.lab/outbox/stageB-rerun-ask.md`). Batch registry `docs/EXPERIMENTS.md`· μετρήσεις J170 `.lab/j170/{inventory.json,daily.json,report.md}`.

## 6. Do not repeat (dead ends, rejected options, known pitfalls)
- Dropped in the loop: sim_v2 as primary (c1), coupled env (c4), D=15/20 delays (c11a), noise15_multispike_d5 (c12a),
  spike300_d7 / multispike_d5 as acceptance envs (c14), noise for B1 (c17), dueling (−2.2k), PER (−15.6k), arch a12
  (c20), c23 package → `docs/tuning_experiments.md`.
- Never evaluate DERP at eps=1; never reuse a single-use test split (test10, test11 are spent).
- Sandbox-status over-reports use while runs are active (5 CPU-h reservation each) (handoff 23/10).
- Cost: long-lived sessions with hourly in-session crons burned the weekly limit and ≈$20 of extra credits on 23/10
  (`.lab/usage/extra_credits_state.json`; `docs/COORDINATION.md` §1). Do not recreate hourly crons; v0.3 wakes the
  coordinator on events.
- The old deputy (`tools/deputy.py`) failed with «codex not found» on 21/10 (`.lab/deputy_queue.jsonl`): the CLI is in
  `~/.local/bin`, which must be on PATH for any service.
- Don't pin the coordinator's process to CPUs: `launch_run.py` intersects its pin set with its own affinity.

## 7. Standing rules that lived only in Claude's memory (also mirrored in docs/claude-memory/)
- Address the researcher as «Κώστα» in every reply; he calls the coordinator «Πάρις» (Παρασκευάς); sign every reply «— Πάρις» (M-20261028-011). If he says "don't reply", set the message
  to done with `labq.py status` and post nothing (M-20261016-037).
- Cores (researcher 21/10): 0-3 dashboard only (`taskset -c 0-3`), 4-7 agents/tests (`taskset -c 4-7`), 8-39
  experiments (`launch_run.py` DEFAULT_SIM_CPUS). Engineer tests have no CPU-minute cap but never run experiments.
- Before adding to DECISIONS.md / PLAN.md / CLAUDE.md / AGENTS.md / rules: check for contradictions; on conflict ask
  with both texts (file:line) and wait (M-20261020-021; `docs/rules/README.md`).
- Before any important task: check established practice online with sources, write the strategy, then execute
  (M-20261021-040).
- Parallel Opus-vs-Codex branches were allowed only for the tuning loop; ask before using the idea again (21/10).
- Engineer on Opus only for experiment implementation; tools/docs/dashboard to the cheapest adequate agent;
  scripts over LLM loops; token-saving tools allowed but each install reported (21/10).
- Awake/asleep handoff between Claude and Codex: `docs/rules/handoff.md`.
- Tutorials (when he asks): conceptual, not code; style guide `docs/tutorial_style.md`, writer agent, beginner read
  test + Codex check; append every conceptual question to `docs/tutorial.md` (M-20261022-057/059, M-20261023-023).
- At the first paper-writing task: raise every item in `docs/paper_notes.md` §6 (esp. the oracle) before drafting.

## 8. Pointers
- Plan: docs/PLAN.md · Decisions: docs/DECISIONS.md · Rules: docs/rules/ · Experiments: docs/EXPERIMENTS.md ·
  Index: docs/INDEX.md · Journal: docs/journal/ · Loop log: docs/tuning_experiments.md · Cycles: .lab/tuning/cycles/
- Latest handoffs: docs/handoffs/coordinator_2026-10-23.md, .lab/codex-handoff/claude_limit_2026-10-23.md
- Worktrees: code-tuning (dinos-tuning, Opus), code-tuning-astra (dinos-tuning-astra, Codex), code-tuning-c19/-c20/-c22/-c23.
- Researcher's original code (read-only): ~/simulations, ~/redis, ~/k8s, ~/prometheus-grafana.
