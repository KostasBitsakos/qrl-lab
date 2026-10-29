# STATE — QRL-Lab strategic handoff

<!-- Read first by every coordinator (Claude or Codex). At most 150 lines. Facts only, each with a pointer
     (M-/R-/run id, path, URL). Update it at the end of every task that changed something. Older detail goes to
     docs/DECISIONS.md, docs/journal/ or a topic file listed in docs/INDEX.md. -->

Last update: 2026-10-29 · by: claude (J48) · task: md cleanup (M-20261029-017); pre-cleanup copy:
`docs/archive/STATE_2026-10-29_before_cleanup.md`

## 1. Goal now
- PhD paper: hybrid quantum–classical extension of the DInos autoscaler; simulation first, then real cluster;
  conference submission end of Nov 2026 (`docs/PLAN.md` §1, §11). Quantum work is PAUSED (`docs/rules/paused.md`).
- Cycle 1 (19-24/10): classical DInos tuning loop on spike300_d5; its numbers are NOT targets any more, only lessons
  (M-20261029-017; results §5, `docs/tuning_experiments.md`).
- **Cycle 2 TRIGGERED 29/10** (R-20261028-001, M-20261029-017/021): all our models + adapted DRe-SCale LSTM-PPO
  baseline (Gwydion cited, not ported: `docs/cycle2_plan.md:41`), new noisy Poisson microservice workload + env with
  latency/CPU/mem, Claude and Codex on separate branches, full autonomy, deadline 2/11, daily report. Wanted ordering:
  V.2 > LSTM+transfer > Dinos > LSTM > paper model > DERP > HPA. Budget 160 CPU-h sandbox, 7 days (R-20261029-001);
  file the sandbox request when runs start. Plan: `docs/cycle2_plan.md`, expert pack `docs/expert/` (J12, d6cfa11).

## 2. In progress (what · id · owner · next check)
- C50: J40 reports reviewed `cycle2-harness-v1` = b609b93 on both Poisson branches (Codex APPROVE r3;
  `.lab/cycle2-claude/status.md`). J51 (Codex, queued) owns competing-branch configs and ONE concrete aggregate
  sandbox request after J48 launcher review/commit; brief `.lab/c50/codex-continuation.md`. J40/J48 notified;
  reviewed harness protection and measured-cost gate required. No runs authorized by this handoff.
- J40 DONE 30/10: shared harness tag `cycle2-harness-v1` = b609b93 (code-poisson; dinos-poisson-astra ff to it), Codex
  APPROVE r3 key cycle2-harness. pms:<v> via c5 (`--env-family orig --orig-variant pms:poisson_ms`), native RecurrentPPO
  DRe-SCale `python -m tuning.rppo` (sb3_contrib not installable headless), references `python -m tuning.pms_reference`;
  splits val 13000-13019 / test12 14000-14019 (locked). CLI, costs, limitations: `.lab/cycle2-claude/status.md` (J40).
  Next: J41 files ONE sandbox request; re-spawn Codex branch job. No runs.
- J48 DONE 29/10: cycle2 launcher COMMITTED ecca33d (J41 guard + J48 harness pin): Claude APPROVE (M-20261029-087),
  Codex key cycle2-launcher-j48 r1 CHANGE → r2 APPROVE. Parent spec needs `worktrees`, `frozen_env_commit` 238003f,
  `frozen_harness_commit` b609b93 (7 harness files pinned; `docs/cycle2_launcher.md`). 19 focused + legacy test_sandbox
  pass; real worktrees verified. Handoff `.lab/cycle2-launcher/handoff.md`. Next: J51 files ONE aggregate request.
- C44 (M-20261029-066): researcher applied the ceiling change; `dispatcher.py status` verified `max_workers=16`.
  C43 automatic-approval obstacle resolved by researcher action (R-20261029-004). J40/J41 remain queued
  (`work.py status`); schedule useful independent work by dependencies, resources and budget (M-20261029-055/058).
- C38: J24 finished shared env `cycle2-env-v1` = 238003f, Codex APPROVE r3; worktree
  `code-poisson-astra` exists (`.lab/cycle2-claude/status.md`). J40 (Claude) queued: shared harness + adapted
  DRe-SCale; J41 (Codex) queued: launcher protection + shared budget ledger + ONE frozen sandbox request.
  Briefs `.lab/c38/{harness,launcher}.md`; both notified to coordinate interfaces. No runs authorized by this handoff.
- 29/10 J24 (claude): cycle-2 shared env FROZEN, tag `cycle2-env-v1` = 238003f (dinos-poisson, worktree code-poisson;
  `tuning/poisson_ms.py`, 10 tests; Codex APPROVE r3, key cycle2-env). Worktree code-poisson-astra created for Codex.
  Still to do before any run: harness adapter, DRe-SCale arm (sb3_contrib missing), sandbox_guard for the new
  worktrees, ONE sandbox request → `.lab/cycle2-claude/status.md`. No runs (M-20261029-057).
- C29: J25 (Codex) prep done (.lab/cycle2-codex/preparation.md, GATES.md); J25 ends. RE-SPAWN a Codex branch job
  (brief /tmp/c9/b6.md or .lab/cycle2-codex/preparation.md) after J40 reviewed shared harness readiness.
- J25 Codex preparation (M-20261029-030): `.lab/cycle2-codex/preparation.md`, review checklist and gates;
  no runs. Env/tag and worktree now ready (J24); waiting for J40 shared harness + frozen sandbox approval. R-20261029-001 is an
  answered question with no spec/hash (`labq.py request`), not launcher authorization; coordinator/J24 notified.
- J23 completed Experiments UX: cycle-1 summary/table/CI at top INSIDE tab, figures on demand, raw runs collapsed
  (`dashboard/app.py`, `tools/cycle1_report.py`); Claude review M-20261029-036, 10 tests passed
  (`tests/test_cycle1_report.py`, `tests/test_tab_links.py`); HTTP health OK, no service restart (M-20261029-030).
- 29/10 C21 (M-20261029-030): Codex fixed (~/.codex/config.toml model gpt-6.1-sol). Cycle 2 started: J24 (Claude) shared
  env/workload/DRe-SCale + branch dinos-poisson; J25 (Codex) competing branch dinos-poisson-astra; J23 (Codex) Experiments
  tab; J17 GitHub push after Codex review; J18 md cleanup. Current worker scheduling: C37 entry above.
- J17 (claude): curated GitHub upload READY, Codex APPROVED round 2 (key github-export; briefs `.lab/export/`), push
  NOT done (headless permission denied `git push`). Exact approved refs: export-main 901fe54→main, cycle1-claude
  afc4ea7, cycle1-codex ad283e4 (log-free snapshots of dinos-tuning 5eae972 / -astra 16d9bf4; worktree `export/`).
  Push = `git push github 901fe54:refs/heads/main afc4ea7:refs/heads/cycle1-claude ad283e4:refs/heads/cycle1-codex`.
- J18 (claude): md cleanup (this update); J19 (claude): Experiments-tab UX + cycle-1 report. J10/J11 (codex) FAILED:
  «gpt-5.1-codex-max not supported with ChatGPT account» (M-20261029-019/020) — Codex peer calls fail until the model
  in `~/.codex/config.toml` or `peer_codex_model` is changed by the researcher (M-20261029-025).
- R-20261029-003 approved: `.claude/settings.json` now allows `git push github …` headless; force/-f/origin denied (da5d4e5, J33). Joint Claude+Codex review before push still required (AGENTS.md).
- Nothing is running (`python3 tools/launch_run.py list`); all sandboxes expired (latest R-20261023-001, 120.6/160 CPU-h).
- Stale db row: run `20261019-092534-R-20261017-021-s93-a1` shows "starting" since 19/10 (no process). Harmless.

## 3. Waiting for the researcher
- Codex model fix (above) — blocks every Codex review, incl. the push review and the cycle-2 plan review
  (`docs/expert/codex_brief_cycle2.md`, M-20261029-025).
- M-20261029-009: (a) results-retention policy (keep per-seed JSON + result md + best ckpt; audit that every
  test10/11 number traces to a file) — awaiting OK. Worker-count clarification resolved by M-20261029-055 (§2).
- `labq.py pending` on 28/10: 25 open messages, oldest M-20261016-043; waiting_approval: M-20261020-019,
  M-20261021-086, M-20261023-002, M-20261023-004. Most old "in_progress" items were never closed — triage, do not redo.
- Merge/delete of single-purpose branches dinos-tuning-c19/-c20/-c22/-c23 (worktrees `code-tuning-c19` …) needs a
  joint Claude+Codex review and his OK (`docs/rules/handoff.md` rule 4).

## 4. Next steps (in order)
1. Finish J17 push after the joint review; then implement cycle 2 per `docs/cycle2_plan.md` (skills
   `poisson-workload`, `drl-tuning`, `rl-eval-protocol`). Researcher pre-authorised all cycle decisions; runs still
   only via `tools/launch_run.py`. DRe-SCale (IEEE TSC 2024, DOI 10.1109/TSC.2024.3387661, Apache-2.0) = *adapted
   published baseline*, not "SOTA"; its generator is not a correct Poisson process (Codex r2) → exponential
   inter-arrivals. Fairness: equal tuning budgets, transfer pretraining cost charged, ≥10 seeds, paired traces,
   tuned HPA + no-transfer DDQN, SLO/pod-time/churn metrics. Paper notes → `docs/paper_notes.md`.
2. Branch cleanup (§3), flaky `tests/test_lab.py::test_sandbox` (handoff 23/10).
3. Keep `docs/EXPERIMENTS.md` current for every batch.
4. Still proposed, not decided: cheap model for Q&A, one thread per topic (`docs/token_practices.md`).

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
- Dashboard (28-29/10): R-20261028-002 items dd26185..1bfe9cc; right-click tab fix 88d4465 + headless approval
  retry 6563e65 verified live (M-20261029-003); sidebar coordinator state 02ad310; cycle-1 report a61e337
  (`tools/cycle1_report.py`). CLAUDE.md/AGENTS.md slimmed 28/10 (M-20261028-004; text in `docs/rules/interactive.md`); connectors off for this project (`.claude/settings.local.json`, M-20261028-006).

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
