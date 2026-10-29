# STATE — QRL-Lab strategic handoff
<!-- Read first by every coordinator (Claude or Codex). At most 150 lines. Facts only, each with a pointer
     (M-/R-/run id, path, URL). Update it at the end of every task that changed something. Older detail goes to
     docs/DECISIONS.md, docs/journal/ or a topic file listed in docs/INDEX.md. -->
Last update: 2026-10-29 · by: Claude (C160) · task: commit J139 a2c9e0c
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
- J136/M-20261029-225: `tools/token_metrics.py` σε sidebar+Επεκτάσεις, τεκμηριωμένες bytes/4 εκτιμήσεις ανά ανάγνωση και % baseline bytes· συνολικό πραγματικό saved/% άγνωστο. 7 focused tests PASS, live desktop1440/mobile390 PASS, J137 APPROVE για UI/content comparisons· ανοικτά audit F1–F4 (`.lab/j136/{GATES.md,handoff.md,live.json}`, `.lab/j137/review.md`). Χωρίς restart/runs· commit blocked `.git/index.lock` read-only.
- J139/M-236: cycle2-first και paper baseline rppo στον νέο κώδικα·21 focused/full AppTest PASS, first-render2.60s (όχι live), fastpath APPROVE J147+Codex (`.lab/j139/handoff.md`, `FINAL_GATES.md`:2met/1handoff). Live παλιό placeholder, R-011 restart pending(C151:όχι J139). `commit.patch` μόνο J139 hunks, cached-check PASS, .git readonly/J109 preserved. lab-only4PASS2FAIL cleanup αναπαράγονται χωρίς fastpath (`baseline-cleanup.json`), dispatcher-only7PASS2FAIL/10deselected (`dispatcher-only.log`), fulltest_lab130 incomplete κατάC153. **Committed a2c9e0c** (C160, μόνο hunks J139· J109/J136 uncommitted).
- J143/M-20261029-225: F1–F4 dispatcher διορθώθηκαν (full request runs+legacy refs, usage/cost ανά retry, pre-work resume-only fallback, peer context/TTL). Πλήρες fake suite19/19 PASS + focused5/5 PASS σε cores4–7 με test-only fsync bypass, αρχικά FAIL διατηρούνται. Claude τελικό APPROVE P-20261029-191109-5e76/M-20261029-273· FINAL_GATES3/3 MET· χωρίς dispatcher restart/activation. Commit blocked read-only .git (`.lab/j143/{handoff.md,test-current.log,focused-order-final.log,FINAL_GATES.md,commit.log}`). J137 audit/UI review: `.lab/j137/{report.md,review.md}`.
- J130: επαναληπτική ειδοποίηση R-20261021-005 s33–s146 ελέγχθηκε: 113 exit0 + s34 stopped/-15, αντικατάσταση s41 exit0· ήδη αναλυμένο c18/c19, χωρίς νέα runs/απόφαση (`.lab/j130/audit.json`, `report.md`; `docs/EXPERIMENTS.md`). J134 επανέλεγξε το subset s35–s146:112/112 done/exit0, έγκυρα JSON και step=total, ίδια με J130 (`.lab/j134/audit.json`, `report.md`). J141: s38–s146 109/109 done/exit0, ίδια με J134 (`.lab/j141/audit.json`).
- J132 29/10:44 done/exit0 JSON (smoke14,calib14,screen16/56 s28–s43), κόστος4.761944/136 CPU-h, screen0.881944. DERP c0 ίδιο στα lanes· διαφορετικά c1: code-poisson μέσος38816.059, astra159118.951 έναντι c0 141929.233· μόνο2 seeds val, χωρίς νικητή. Script/report `.lab/j132/{summarize.py,result.md,summary.json,table.md}`. J126 wave2 DONE και αυτόματη wave3 s44–s51 στις15:30:37/38 UTC,8 reservations=6h (όχι κατανάλωση)· `.lab/j126/{driver.log,results.jsonl}`. Συνεχίζεται μόνο εγκεκριμένο screen με frozen gates/STOP/no retry· μετά DONE/STOP ledger+stage review, κανένα επόμενο στάδιο αποδεσμευμένο.
- C118/M-20261029-196: μόνιμη αναπλήρωση όταν πάροχος κοιμάται· δύο ανταγωνιστικοί πράκτορες του διαθέσιμου παρόχου, ανεξάρτητο review από άλλο πράκτορα, συμβούλιο Claude+Codex στην επιστροφή. Καμία παύση λόγω Claude· frozen-spec εγκρίσεις/launcher/push gates ισχύουν (`AGENTS.md`, `docs/rules/handoff.md` §6, `docs/DECISIONS.md`).
- J119 running: Codex αναπληρωτής Claude lane + ανεξάρτητο review J109/J104 και κοινό frozen spec. J120 running: Codex astra lane + ανεξάρτητο ledger/manifest/cross-review. Briefs `.lab/c118/{standin-brief,astra-brief}.md`· ανταγωνισμός μόνο πειραμάτων, solo notes/προσωρινοί κλάδοι· κανένα νέο run πριν frozen approval (M-20261029-196).
- C124/J120: **APPROVE FOR FILING — SCREEN ONLY**, canonical amendment `42ac17ed9b0c4e2e8a29b39de365beb29137b7d6168274caf8292386d6682a94` (`.lab/j119/amendment-spec.json`, `.lab/j120/final-review.md`, `handoff.md`). Cheap-first διόρθωση PASS:56 CLI,14 waves exact coverage,7 paired nominal schedules,5 toy tests (`.lab/j120/audit-verified.log`, `check_schedule-verified.log`, `amendment-tests.log`). Μοναδικό filing J119 κατόπιν οδηγίας C124· request id εκκρεμεί. Nominal εφικτότητα, όχι measured guarantee: πραγματικό κόστος/reservations μπορεί να επιβάλει STOP και στα δύο lanes· καμία αύξηση caps/retry. Μόνο screen, κοινή χρέωση R-006, test12/shift-test κλειστά· κανένα νέο run/activation πριν έγκριση ερευνητή. Προσωρινό ref `j120-astra-screen`=182af33, frozen checkout αμετάβλητο (M-20261029-196).
- J119/J120 (Codex substitutes, M-20261029-196): ανεξάρτητο J109 launcher/RPPO και J104 ledger review APPROVE·60 engineering tests PASS (`.lab/j119/check-0.log`, `.lab/j120/final-review.md`· J120 gates4/4 `.lab/j120/gates-reverified.log`). **R-20261029-010 FILED/OPEN**, hash42ac17ed…6682a94: ίδιο R-006, hard136/cap2.5h, SCREEN ONLY56 tasks με14 exact waves4/cheap-first· καμία activation/new run (`.lab/j119/handoff.md`).
- Συνέχεια R-010 μόνο μετά frozen έγκριση ερευνητή: actual/reservation+remaining-ledger gates, STOP και στα2 lanes σε overrun/failure· test12/shift-test κλειστά, επόμενα stages απαιτούν concrete review/release. Απουσία Claude δεν μπλοκάρει· προσωρινά solo refs διατηρούνται, Claude+Codex council επιστροφής (`docs/rules/handoff.md` §6). J109 υλοποίηση uncommitted λόγω root read-only `.git` (`.lab/j109/commit.log`).
- J103 (Codex): Race συνδέθηκε με πραγματικά dispatcher jobs/ταυτότητα από tasks.refs· σύνδεση app.py από J97, χωρίς restart (M-20261029-167). 18 focused tests PASS + ανάγνωση/render πραγματικού board· J97 αναφέρει live browser επιβεβαίωση jobs/ταυτότητας (C110 escalation, `.lab/j97/`). Claude review ΕΚΚΡΕΜΕΙ: P-20261029-142936-7bcd FAILED λόγω ορίου έως 15:16 UTC. Παράδοση `.lab/j103/handoff.md`.
- J100+J143 COMMITTED 4286965 (J157): Claude APPROVE J100 `.lab/j157/review-j100.md`, J143 M-20261029-273; test_dispatcher+researcher_text+usage_limits 32 passed (`.lab/j157/tests.log`). Χωρίς restart dispatcher/dashboard (απαιτεί έγκριση ερευνητή).
- J97 (Codex), M-20261029-159: Greek tutorial draft **20 pages** + download tab `📚 Tutorials`; `docs/tutorials/` (PDF, PLAYBOOK, REVIEW, sources), `docs/tutorial_style.md`. Beginner-reader revisions done; 17 focused checks PASS; live desktop/390px phone downloads byte-identical; Race J103 integration verified (`.lab/j97/`). Full suite 288 PASS/19 FAIL; each failure rerun alone:17 PASS/2 FAIL (exp_view deadline, coordinator label); `docs/tutorials/REVIEW.md`, `.lab/j97/isolation-results.json`. Claude review/commit pending: `.lab/j97/handoff.md` (3/5 gates); dispatcher επανελέγχθηκε C115: exhausted, reset18:10UTC, 15:16=provider recheck (`.lab/j109/claude-availability.json`, M-20261029-189). Συνέχεια Codex μετά επιβεβαιωμένη διαθεσιμότητα, χωρίς polling· draft μέχρι τεχνική έγκριση (`.lab/j97/claude_review_brief.md`). Future tutorials→Codex/playbook; shared memory/index and iPhone access: C98, M-20261029-159.
- J104 29/10: **R-20261029-009 APPROVED**, 1.25x, same sandbox; no runs before new spec approval. Static DRe-SCale audit: no obvious action/scaling/reset defect, collapse cause unknown (`.lab/j104/static-rppo.md`). Ledger: 126.903/136 CPU-h incl. 3.88 consumed, 154 training + 210 inference tasks, 8h unmeasured pools; cap LSTM+transfer 2.5h (`.lab/j104/ledger.md`, `verify.py` PASS). Draft `.lab/j104/amendment-spec.json` BLOCKED, not filed: existing immutable R-006 cap2h, J109 πρόσθεσε same-parent υποστήριξη, ανεξάρτητο review ανατέθηκε J119 αντί αναμονής Claude (M-20261029-196); original-HPA/evaluator manifests and reference timing unresolved. Next: J119/J120 independent reviews, then frozen executable spec request; no new sandbox/no runs (`.lab/j104/handoff.md`).
- J92 calibration DONE: 14/14 exit0 (s14-s27); sandbox3.88/160 CPU-h, rppo collapse diagnostic (`.lab/j92/calib_result.md`); old2x re-gate FAIL superseded only as planning policy by R-009, not launch authorization.
- J64 DONE 29/10: Claude review M-20261029-110 (guard + work.py --worktree APPROVE; schedule AGREE, cond. A: val
  selection → claims only from test12 after freeze; B: smoke-first is policy, not launcher-enforced); Codex final
  M-20261029-111 APPROVE. Commits 7d55754 (root), 182af33 (astra wrapper). **Filed R-20261029-006** (sandbox 160 CPU-h,
  expires 05/11 05:10 UTC, spec `.lab/j64/final.json`, hash 1764ff9b…4052). Next on approval: ONLY 14 smoke via
  `launch_run.py sandbox-start` with branch smoke.json children; then cost gate. Root .git writable in Claude runs.
  APPROVE r3 key cycle2-harness. pms:<v> via c5 (`--env-family orig --orig-variant pms:poisson_ms`), native RecurrentPPO
  DRe-SCale `python -m tuning.rppo` (sb3_contrib not installable headless), references `python -m tuning.pms_reference`;
  splits val 13000-13019 / test12 14000-14019 (locked). CLI, costs, limitations: `.lab/cycle2-claude/status.md` (J40).
  Next: J41 files ONE sandbox request; re-spawn Codex branch job. No runs.
- J48 DONE 29/10: cycle2 launcher COMMITTED ecca33d (J41 guard + J48 harness pin): Claude APPROVE (M-20261029-087),
  Codex key cycle2-launcher-j48 r1 CHANGE → r2 APPROVE. Parent spec needs `worktrees`, `frozen_env_commit` 238003f,
  `frozen_harness_commit` b609b93 (7 harness files pinned; `docs/cycle2_launcher.md`). 19 focused + legacy test_sandbox
  pass; real worktrees verified. Handoff `.lab/cycle2-launcher/handoff.md`. Next: J51 files ONE aggregate request.
- J72: daily cycle-2 report `tools/cycle2_daily.py` (cron 0 15-17 UTC, self-removes after 02/11, `.lab/cycle2_daily/cron.log`). C44: `max_workers=16` (M-20261029-066); resource-aware scheduling (M-20261029-055/058); briefs `.lab/c38/`.
- 29/10 J24 (claude): cycle-2 shared env FROZEN, tag `cycle2-env-v1` = 238003f (dinos-poisson, worktree code-poisson;
  `tuning/poisson_ms.py`, 10 tests; Codex APPROVE r3, key cycle2-env). Worktree code-poisson-astra created for Codex.
  Historical preparation: `.lab/cycle2-claude/status.md`, M-20261029-057; harness/launcher progress in J40/J48/J64 above.
- J25 (Codex) prep done, J25 ended (`.lab/cycle2-codex/preparation.md`, GATES.md; M-20261029-030); re-spawn a Codex
  branch job from that brief. R-20261029-001 = answered question, no spec/hash, not launcher authorization.
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
- J88 29/10 R-20261029-008: GitHub versions = tags via `tools/publish_release.py` (`docs/github_publishing.md`);
  tags cycle1-claude-v1.0/cycle1-codex-v1.0 pushed and verified. J95 29/10: remote branches cycle1-claude/-codex gone;
  `git ls-remote github` = main 901fe54 + the two tags only.
- R-20261029-003 approved: `.claude/settings.json` now allows `git push github …` headless; force/-f/origin denied (da5d4e5, J33). Joint Claude+Codex review before push still required (AGENTS.md).
- J71/J79 29/10: Γνώση = zoomable tree (`tools/knowledge_tree.py`, `.lab/j71/`); phone CSS ≤480px + ☰ tab menu + home-screen tags
  (`tools/mobile_view.py`, `dashboard/static/`); `enableStaticServing` needs a dashboard restart (not done, J79).
## 3. Waiting for the researcher
- R-20261029-010 APPROVED 15:20UTC (screen only)· ενεργοποιήθηκε· σε εξέλιξη (§2 J126).
- R-20261029-011 (C151): restart qrl-dashboard.service (τρέχει από 29/10 01:20 με παλιό κώδικα) μετά J147 APPROVE + full AppTest· ενεργοποιεί και J136/J100/J103/J97.
- R-20261029-005 ANSWERED 29/10 (J66): «paper model» = adapted DRe-SCale LSTM-PPO (arm `tuning.rppo`); criterion
  reviewer weight, then ease of replication; told him DRe-SCale is IEEE TSC 2024 (Gwydion is the 2025 one) — he may correct.
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
  DERP, `derp_hist10` = enhanced DERP; each model tested at its best val checkpoint. Always write «Dinos+Transfer V.2», never bare «V.2» (M-20261029-121).
- Real cluster: 1 Redis pod ≈116-118k ops/s at c=1, no saturation; stage-B sweep failed at 1→2 pods (fix 84367e1,
  never re-run); calibration paused → `.lab/outbox/calib-status.md`, `stageB-rerun-ask.md`, `docs/rules/paused.md`.
- Every batch with status and pointers: `docs/EXPERIMENTS.md` (1532 launcher runs, 23 requests). R-20261021-007
  end-notices are stale cycle-1 duplicates (J83/J90; J133: exact s24–26+s33–80, 51/51 exit0, valid JSON: `.lab/j133/audit.json`, `report.md`; J140: s35–s80 again, 46/46 valid JSON) — no rerun.
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
