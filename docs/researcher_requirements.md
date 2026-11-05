---
description: Researcher's standing requirements digest (Κώστας) - deduplicated, with M-/R- pointers and status; read this instead of re-asking him. Keywords - requirements, preferences, standing instructions, rules he gave, contradictions
---
# Researcher requirements — standing instructions, deduplicated (J248, 2026-10-30)

Purpose: so the researcher never has to repeat himself. One line per standing item: statement · pointer · status.
Sources mined: his chat messages (thread M-20261029-006, 44 messages; dated 29–30/10), `docs/DECISIONS.md`, `docs/rules/*`,
`docs/claude-memory/*`, STATE §7. Not mined: pre-29/10 chat messages other than via those files (full text:
`python3 tools/labq.py show M-… --full`). One-off chat, stale approvals, status chatter are intentionally left out.
An item marked **superseded** is kept only so nobody revives it. Do not edit the rule files from here; this is a derived index.
Active rule texts live in `docs/rules/`; if this file and a rule file disagree, see §H (open contradictions) and ask him.

## A. Mission and priorities
- A1 Goal: DInos-based hybrid autoscaler paper; experiments are the first priority over everything else. M-20261030-076, PLAN §1. active
- A2 He will be away (Κόρινθος) ~4 days from 30/10 evening, only a phone (no VS Code, Terminal tab does not open on mobile); wants experiments to keep running unattended and all work doable from the phone. M-20261030-083/086/088, M-20261029-118. active
- A3 Cycle 2 (Poisson microservice workload, noisy, latency/CPU/mem), all our models + adapted DRe-SCale LSTM-PPO («paper model»); cycle-1 numbers are NOT targets, only lessons. R-20261028-001, M-20261029-017, R-20261029-005. active
- A4 Wanted ordering: Dinos+Transfer V.2 > LSTM+transfer > Dinos > LSTM > paper model > DERP > HPA (`docs/cycle2_plan.md:14`). active — see §H1 on how to treat it
- A5 Agents may change/tune whatever they judge necessary in Dinos and Dinos+Transfer V.2 (params, additions, removals, env/reward variants) until the numbers he asked for are reached. M-20261030-094, M-20261029-017, M-20261020-013/015. active — new experiments still go through frozen spec + `tools/launch_run.py`
- A6 Deadline for cycle 2: 2/11/2026; daily progress report; paper submission end of Nov may slip («δεν θα προλάβω να κάνω submit paper»). R-20261028-001, M-20261030-088. active
- A7 Focus on reproducing the DInos picture first; quantum paused (not dropped; revive conditions in `docs/rules/paused.md`). M-20261019-048. active
- A8 Council (Claude+Codex) **when the current R-010 screen ends**, to decide what continues. M-20261030-094. active (new)

## B. Experiments and agents
- B1 Every experiment cycle runs on two competing branches/repos (Claude `<topic>`, Codex `<topic>-astra`) with periodic exchange of what helped (at least each daily report). M-20261029-028, `rules/experiments.md`. active
- B2 Competition ONLY for experiment cycles; every other task = one well-chosen agent. M-20261029-142. active
- B3 If one provider sleeps, the other continues at once; for experiments two independent competing agents; Claude+Codex council on return decides what to keep. M-20261029-196, `rules/handoff.md` §6. active (supersedes the 21/10 «only for this loop»)
- B4 Codex as deputy/coordinator uses all the same rules/info as Claude, keeps notes of solo actions for joint review. M-20261029-028, M-20261021-075/078/081, `rules/handoff.md`. active
- B5 Coordinator picks per task the best model across vendors by quality/speed/cost/usage left; as many parallel workers as tasks need (intelligent scheduling); the chat coordinator answers fast, independent from workers. M-20261029-028/055/058, M-20261029-011, M-20261029-030. active
- B6 Best models for experiment scope (models, numbers, coordination); frugal for everything else. M-20261021 (`rules/models.md`). active
- B7 Experiments only with approved frozen spec via `tools/launch_run.py`; test splits single-use (test10/11 spent). AGENTS.md, `rules/experiments.md`. active
- B8 Tune on val only, ≥10 seeds, equal budgets, paired traces, correct Poisson process (own implementation), adapted DRe-SCale (Gwydion cited, not ported). M-20261022-033, M-20261029-017, `docs/cycle2_plan.md`. active
- B9 Per-cycle closeness % is only a progress indicator, not a result; each result file kept compact. M-20261019-029, M-20261020-025. active (narrowed)
- B10 Agents should acquire needed expertise (skills/papers: ML/data-analyst/dev) before experiments; on important tasks research best practice online and write the strategy before executing. M-20261029-017, M-20261021-040. active
- B11 Name models exactly: LSTM / LSTM+transfer / Dinos / «Dinos+Transfer V.2» — never bare «V.2»; test each model at its best val checkpoint; save convergence metrics. M-20261022-007, M-20261029-121. active
- B12 Many orig. loop-era items (500 CPU-h sandboxes, 22–23/10 windows, Opus-only engineer until 21/10, hourly crons) — superseded; cycle-2 budget is 160 CPU-h/7 days (R-20261029-001). superseded

## C. Approvals (what he wants asked, and what not)
- C1 Ask him only for real choices; he does not want approval requests «for everything» (it burns tokens: each answer wakes a paid job). M-20261030-052. active — see §H2
- C2 Never ask him to approve `sqlite3` (permanent deny-rule) or any command that is denied by settings. STATE §6, M-20261030-052. active
- C3 Real approvals that stay: new budgets/sandboxes, sudo, real cluster, QPU/IBM, installs, purchases, pushes outside rule, frozen specs. AGENTS.md. active
- C4 Check new rules against existing md files for contradictions and ask him with both texts (file:line) before writing. M-20261020-021. active
- C5 Never guess; ask in the dashboard (Αποφάσεις), not only in docs. CLAUDE.md rule 1. active
- C6 Don't ask him for terminal/VS Code actions while he is away. M-20261030-086/088. active

## D. Communication
- D1 Reply in Greek, short and direct; open with «Κώστα,» and sign «— Πάρις» (Codex: «— Πάρις (Codex)»); also after compaction. M-20261016-037, M-20261028-011, M-20261029-162. active
- D2 Codex also speaks Greek to him and uses the index/md files to access what was said. M-20261029-159. active
- D3 If he says «don't reply», set status done and post nothing. M-20261016-037. active
- D4 Plain language when he says he does not understand (avoid jargon walls). M-20261030-090. active
- D5 Coordinator must answer even while workers run (independent chat agent); reply fast. M-20261029-011/030. active
- D6 Remind him to discuss the oracle (oracle_Dstep is a heuristic, not a bound) and all `docs/paper_notes.md` §6 items when paper writing starts. M-20261022-077. active

## E. Git / GitHub
- E1 Push only to `KostasBitsakos/dinos_sofia_k8s_redis_scaling` (remote `github`); nowhere else; never `--force`, never secrets. M-20261029-147, R-20261029-002. active
- E2 Upload agreed code/models after the competition + joint review, automated, no «Compare & pull request» banners: `main` only plus annotated tags `cycle<N>-…`, via `tools/publish_release.py`. M-20261029-050/142, R-20261029-008, `docs/github_publishing.md`. active (supersedes «different branches», M-20261029-142)
- E3 Final models/code are uploaded before each new cycle. M-20261029-009. active

## F. Dashboard / UX
- F1 Mobile-first: responsive dashboard (no native app; Tailscale + home-screen shortcut); taps must work first time. M-20261029-118/126/159, M-20261030-063. active
- F2 «Πειράματα» tab: current cycle results, the paper model we compare against, first-cycle table + on-demand charts, understandable by anyone. M-20261029-017/236. active
- F3 «Γνώση» tab tidy, tree-like zoomable, designer-quality; remove duplicated/repeated info on all tabs. M-20261029-118, M-20261030-063. active
- F4 Usage bars: for Claude and Codex show used, remaining, time left, and tokens saved by our architecture/extensions — measured, not guessed; logo top-left, savings not above the logo; Claude's remaining shown like Codex's. M-20261029-225/288/295, M-20261030-063. active
- F5 Free-offer resets / limit notifications: remove if useless (removed by J228). M-20261030-063. done
- F6 Page must not reload every ~2 s / burn tokens (made async/10 s). M-20261030-077, J228. done (live after dashboard restart)
- F7 Dashboard changes: tests before apply, commit, tell him to F5. `rules/dashboard.md`. active

## G. Tokens, memory, md hygiene
- G1 Minimise tokens: scripts over LLM loops, cheapest adequate agent, token-saving tools allowed (report each install). M-20261021, M-20261029-286. active
- G2 Opening the chat must never burn the Claude 5 h window; investigate leaks; consider separate cheap chatter vs coordinator; show certain (not guessed) savings. M-20261029-286, M-20261030-063. active (J230 study)
- G3 Keep only needed information; compact md files with index; coordinator reads key excerpts only. M-20261029-009, M-20261030-001, M-20261030-094. active
- G4 One agent cleans redundant info so everything he said can be found via index/md files without repeating it — this file is that digest. M-20261030-094. active
- G5 Tutorials: owned by Codex, short non-tiring PDFs in dashboard «Tutorials» tab, conceptual not code; playbook `docs/tutorials/PLAYBOOK.md`; append conceptual Q&A to `docs/tutorial.md`. M-20261029-159, M-20261022-057/059. active
- G6 Venues carry CORE tier + last-3 acceptance rates from official sources; never estimated. M-20261017-114/117. active
- G7 Papers: Sofia paper is a source, DInos wins on disagreement; paper doesn't mention simulator F1 issue and doesn't restate DInos sim numbers. M-20261019-044, R-20261017-007. active
- G8 Cores: 0-3 dashboard, 4-7 agents/tests, 8-39 experiments; never pin the coordinator; no CPU-minute cap on tests. 21/10 (`docs/claude-memory/core-split.md`). active

## H. Contradictions / tensions (H1, H2, H4 answered 30/10 by R-20261030-006; H3, H5 still open)
- H1 Ordering target vs honest testing: A4/A5 (agents may change Dinos and Dinos+Transfer V.2 until numbers are «as I asked») vs `docs/cycle2_plan.md:14` «We test it; we do not engineer it» and AGENTS.md rule «never invent results»/val-only tuning, single-use test. Question: does «the numbers I asked for» = the ordering V.2 > … > HPA on the frozen protocol, with tuning allowed but the result reported either way? Not a contradiction in intent, but the plan text and the new instruction read differently.
- H2 Autonomy vs approvals: R-20261028-001/R-20261029-001 (full autonomy within 160 CPU-h, Claude+Codex approve child specs) and C1 (don't ask for everything) vs CLAUDE.md rule 2 / M-20261030-093 reply «each new stage needs your approval» (R-010 stages, test12). Question: which stage transitions (screen→next, test12) may the council start itself within the budget?
- ANSWER R-20261030-006 (30/10 23:04UTC): H1 «yes» = ordering V.2 > … > HPA on the frozen protocol, free tuning, honest reporting either way. H2 «yes» = the council may start stages itself within budget (exact stage list not given; frozen-spec/launcher/single-use test gates stay). H4: «everything concerning the experiments and reaching our goals» is pre-approved for the 4 days; does NOT cover security/sandbox/credential/push/spend-beyond-budget rules.
- H3 `max_workers`: M-20261029-066 says «max_workers 16 done»; DECISIONS C43 / STATE say the setting was last verified at 4 (dispatcher setting not changed by agents). Fact unverified, needs `tools/dispatcher.py` status read by the coordinator.
- H4 Unattended vs approvals needing his action: A2/C6 vs the standing need for his PIN/approval cards (frozen specs, restarts). Needs a plan for the 4 days (what is pre-approved).
- H5 Superseded but still written: `docs/claude-memory/experiment-loop.md` (hourly crons, 22/10 window), `tuning-engineer-opus.md`, `rules/models.md` Opus-only lines — old text without clear «superseded» in some lines. Candidates for condensing (not deleted).

## I. How to use
`grep -i "<topic>" docs/INDEX.md` finds this file. Before asking him something, grep it here (e.g. `grep -n "approval" docs/researcher_requirements.md`).
Add a line (and an M- pointer) only for NEW standing instructions; mark old ones superseded rather than deleting.
