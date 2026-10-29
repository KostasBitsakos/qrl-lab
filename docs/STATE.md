# STATE — QRL-Lab strategic handoff

<!-- Read first by every coordinator (Claude or Codex). At most 150 lines. Facts only, each with a pointer
     (M-/R-/run id, path, URL). Update it at the end of every task that changed something. Older detail goes to
     docs/DECISIONS.md, docs/journal/ or a topic file listed in docs/INDEX.md. -->

Last update: 2026-10-29 · by: claude (J13) · task: R-20261029-002 (push approval: rule, deploy key, remote)

## 1. Goal now
- PhD paper: hybrid quantum–classical extension of the DInos autoscaler; simulation first, then real cluster;
  conference submission end of Nov 2026 (`docs/PLAN.md` §1, §11). Quantum work is PAUSED (`docs/rules/paused.md`).
- Since 19/10 the work has been the classical **DInos tuning loop** in simulation: reproduce the DInos picture with a
  fair protocol; goal stated by the researcher: Dinos+Transfer V.2 best, closest to his paper (R-20261021-009/010,
  `docs/DECISIONS.md`). The loop window ended 24/10 21:59 UTC (`docs/handoffs/coordinator_2026-10-23.md`).
- Now: R-20261028-001 ANSWERED 28/10: new cycle (all our models + replicated DRe-SCale-type paper model, new noisy
  Poisson microservice workload + env with latency/CPU/mem, Claude and Codex on separate branches, full autonomy,
  deadline 2/11, daily report). START ONLY when the researcher writes «ξεκινα μπανάνες!» → reply exactly
  «ξεκινανω capteain cagarou». Target ordering he wants: V.2 > LSTM+transfer > Dinos > LSTM > paper model > DERP > HPA.
  Pre-start proposals sent in M-20261019-009 (Gwydion yes/no, fairness/reporting caveat).
  CPU-h budget decided (R-20261029-001): 160 CPU-h sandbox, valid 7 days; file the sandbox request on the trigger.

## 2. In progress (what · id · owner · next check)
- M-20261029-003 (29/10): J1 DONE: right-click tab fixed (88d4465, Streamlit 1.66 tabs are div[role=tab]) and headless
  approvals now honoured once on retry (6563e65, perm_store.take_approval); both verified live (headless chromium via
  playwright 1.40 in .venv, headless claude). Dashboard restart needed for the tab fix; J2 zoomable knowledge tree; J3 (codex)
  `tools/vscode_asks.py` for the researcher's VS Code requests. v0.4 dispatcher + tools/work.py are the researcher's own.
- Nothing is running (28/10: no launcher/driver/simulator processes; `python3 tools/launch_run.py list`). All
  sandboxes expired (latest R-20261023-001, 120.6/160 CPU-h, expired 24/10 21:59 UTC).
- v0.3 switch (dispatcher + systemd units) — researcher, after this install (`SETUP_v03.md` §2).
- Stale db row: run `20261019-092534-R-20261017-021-s93-a1` shows "starting" since 19/10 (no process). Harmless.

## 3. Waiting for the researcher
- Trigger phrase «ξεκινα μπανάνες!» for the R-20261028-001 cycle (§1); answer to pre-start proposals (M-20261019-009).
- `python3 tools/labq.py pending` on 28/10: 25 open messages, oldest M-20261016-043; newest **M-20261026-001**
  «ποιος είναι συντονιστής τώρα;» (status new, unanswered). Waiting_approval: M-20261020-019, M-20261021-086,
  M-20261023-002, M-20261023-004. Most "in_progress" items are old and were never closed — triage them, do not redo.
- Unanswered proposal: check-ins every 2 h instead of hourly (M-20261022-020 / M-20261023-027) — moot with v0.3.
- Merge/delete of single-purpose branches dinos-tuning-c19/-c20/-c22/-c23 (worktrees `code-tuning-c19` …) needs a
  joint Claude+Codex review and the researcher's OK (`docs/rules/handoff.md` rule 4; handoff 23/10 «Next steps» 3).

- M-20261029-009 (29/10): (a) results-retention policy proposed (keep only per-seed JSON + result md + best ckpt;
  audit that every test10/11 number traces to a file) — awaiting OK; (b) before the next cycle push final models+code
  to git: needs rule change (AGENTS.md:10 forbids push) + remote + credentials from him; no remote set now (`git remote -v`);
  (c) parallel models: v0.4 `max_workers` default 2, max 4 (`tools/dispatcher.py:78,189`) — his `dispatcher.py set`.

- M-20261029-017: cycle-1 numbers not wanted; keep lessons, upload to his repo
  github.com/KostasBitsakos/dinos_sofia_k8s_redis_scaling, then Poisson cycle. R-20261029-002 APPROVED 29/10 (J13):
  AGENTS.md:10 rule changed, deploy key ~/.config/qrl-deploy/id_ed25519 (.pub sent), remote `github` + core.sshCommand
  set; ls-remote denied until he adds the key (Deploy keys, write). Next: curated upload after joint Claude+Codex review.
- 29/10 C9: cycle 2 TRIGGERED («go bananes», M-20261029-017). DRe-SCale chosen (Gwydion pending J12 check).
  Workers: J10 md cleanup (codex), J11 Experiments-tab UX (codex), J12 cycle-2 expert pack + plan (claude,
  docs/cycle2_plan.md, docs/expert/). Order: push (after R-20261029-002) → cleanup → cycle 2 implementation.

## 4. Next steps (in order)
1. Done 28/10 (M-20261028-004): CLAUDE.md 5.7k→1.5k chars, AGENTS.md 3.2k→2.0k; moved text verbatim to
   `docs/rules/interactive.md` (backups `.lab/CLAUDE.md.bak-20261028`, `.lab/AGENTS.md.bak-20261028`); connectors
   off for this project only (`.claude/settings.local.json`, M-20261028-006; user scope reverted).
   INDEX now covers `.lab/tuning`, `.lab/council`, `.lab/codex-handoff` (276 files). Dashboard items (R-20261028-002, approved
   29/10) committed dd26185..1bfe9cc; researcher must restart dashboard + dispatcher; right-click JS and headless
   approval retry not verified in a browser/live run → `docs/dashboard_requests_20261028.md` «Implemented». Still proposed: cheap model for Q&A, one
   thread per topic → `docs/token_practices.md`.
2. On the trigger: run pending council items first, decide retrain-vs-test, then the cycle (R-20261028-001).
   Researcher pre-authorised all decisions in that cycle; runs still go through `tools/launch_run.py`.
3. When the next round starts (memory, M-20261022-033): ask first «μόνο DRe-SCale ή και Gwydion;», then plan the
   DRe-SCale LSTM-PPO port (IEEE TSC 2024, DOI 10.1109/TSC.2024.3387661, Apache-2.0) as an *adapted published
   baseline* (not "SOTA") and a correct Poisson arrival process (exponential inter-arrivals; DRe-SCale's generator is
   not a correct process, Codex r2). Fairness: equal tuning budgets, transfer pretraining cost charged, ≥10 seeds,
   paired traces, tuned HPA + no-transfer DDQN, SLO/pod-time/churn metrics. Paper notes → `docs/paper_notes.md`.
4. Branch cleanup (§3), flaky `tests/test_lab.py::test_sandbox` (handoff 23/10).
5. Keep `docs/EXPERIMENTS.md` current for every batch.

- Dashboard (29/10): sidebar coordinator state + name from the dispatcher (02ad310, `tools/coord_status.py`); Experiments
  tab «Μεγάλος κύκλος … ημιτονοειδή είσοδο 1» (a61e337, `tools/cycle1_report.py`, figures on button → `.lab/figs/cycle1/`).

## 5. Key facts and numbers (each with a pointer)
- **test11** (R-20261023-001, tag c24c, 46/46, seeds 80-84, single-use split): V.2 83,983 · Dinos 88,026 ·
  LSTM+transfer 89,331 · LSTM 87,347 · enhanced DERP 68,592 · DERP 62,228 · HPA-demand 47,572 · his HPA 249.
  H1 V.2>DERP +21.8k and H2 V.2>enhanced DERP +15.4k CONFIRMED; H3 Dinos>LSTM +0.7k [−2.5k,+3.7k] NOT confirmed
  (fixed sequence stops); V.2 − LSTM+transfer −5.3k (CI excludes 0) → `.lab/tuning/cycles/c24_test11_result.md`.
- **test10** (R-20261022-005, c18c): same picture, LSTM+transfer 90.6k > V.2 87.8k → `c21_test10_result.md`.
- Frozen recipe: a1h (LSTM only in the first layer), n-step 3, workload spike300_d5 (his env + pod delay D=5) →
  `.lab/tuning/cycles/c24_freeze.md`; n-step 3 adopted in c19 (+6.7k test9) → `c19_screen.md`.
- c23 package NOT adopted (rule C-20261023-01: +1.5k val on both Dinos and V.2) → `c23_screen.md`.
- The earlier paper's 17x (`docs/paper_notes.md:34`) is a protocol artefact: DERP evaluated at eps=1; our verbatim port
  gives ~11x under the paper protocol (`docs/tuning_experiments.md` row 3, `c3_synthesis.md`); fair-protocol ratio
  ≈1.2-1.5x on spike300_d5 (`docs/tuning_experiments.md` rows 9b-15).
- His HPA ≈ random walk (CPU/memory random, independent of VMs; `P/HPA/simpleagent.py:9-14`) → report as-is plus a
  load-based HPA tuned on val (`docs/tuning_experiments.md` Notes).
- oracle_Dstep is a D-step look-ahead heuristic, not an optimal bound (`docs/paper_notes.md` §6).
- Names (M-20261022-007): LSTM / LSTM+transfer (was DInos+T) / Dinos / Dinos+Transfer V.2; `derp` = his original
  DERP, `derp_hist10` = enhanced DERP; each model tested at its best val checkpoint.
- Real cluster: 1 Redis pod ≈116-118k ops/s at c=1, no saturation; stage-B sweep failed at 1→2 pods (fix 84367e1,
  never re-run); calibration paused → `.lab/outbox/calib-status.md`, `stageB-rerun-ask.md`, `docs/rules/paused.md`.
- Every batch with status and pointers: `docs/EXPERIMENTS.md` (1532 launcher runs, 23 requests).

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
