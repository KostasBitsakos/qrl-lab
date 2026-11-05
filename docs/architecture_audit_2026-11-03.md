---
description: Full audit of the QRL-Lab agent architecture (dispatcher, dashboard, DBs, knowledge layer, skills, hooks, overlaps) as input for a clean redesign
---
# QRL-Lab: architecture audit for a clean redesign (2026-11-03)

Written by Claude Code (Opus 5.5) from the live VM: code in `~/qrl-lab`, the three SQLite databases, systemd/cron,
the dashboard messages, and the Claude Code transcripts of the sessions that built the dispatcher. Every claim has a
pointer (file:line, commit, message id `M-…`, request `R-…`, job `J…`/`C…`). Numbers are from the databases on
2026-11-03 unless marked otherwise. Costs are the CLIs' own client-side **estimates** (API-equivalent USD), not bills.

> **Σύνοψη στα ελληνικά (για τον ερευνητή).** Το σύστημα χτίστηκε σε 5 στρώσεις μέσα σε 18 μέρες (v0.1 → v0.4 +
> knowledge base). Κάθε νέα στρώση μπήκε **πάνω** στην προηγούμενη και δεν την αντικατέστησε. Γι' αυτό: (1) υπάρχουν
> 3–4 μηχανισμοί για το ίδιο πράγμα (επιλογή μοντέλου, εγκρίσεις, μνήμη/ευρετήρια, παρακολούθηση ορίων). (2) Ο
> dispatcher έχει 25 ρυθμίσεις, αλλά το dashboard δείχνει μόνο 4. Οι άλλες αλλάζουν μόνο από το τερματικό, και οι
> πράκτορες απαγορεύεται να τις αλλάξουν. Αυτός είναι ο λόγος που ο συντονιστής σού έλεγε «τρέξ' το εσύ», σε 41
> μηνύματα. (3) Η καρτέλα «Αρχιτεκτονική» γράφει ρυθμίσεις μοντέλων που ο dispatcher **δεν διαβάζει ποτέ**. (4)
> Κομμάτια του παλιού συστήματος (tmux συντονιστής, health_watch, deputy, watchdog, lab-bridge) δεν τρέχουν πια.
> Το dashboard όμως ακόμα τα διαβάζει ή τα χειρίζεται. Η §10 έχει τη λίστα. Η §14 έχει τι ζητάς εσύ από τη νέα
> αρχιτεκτονική, με τα δικά σου λόγια.

---

## 0. What the designer (Claude Fable) is asked to produce

A **clean target architecture** for QRL-Lab that the researcher will use from now on, plus a migration plan from
what exists today. Hard requirements are in §14. In short:
- one place where the researcher sees and changes **every** control (no more «run this in the terminal»),
- one coordinator to talk to at all times, with parallel workers behind it,
- low, predictable token cost (no always-on LLM, no runaway fan-out),
- one source of truth per concern (model routing, approvals, memory/index, usage limits),
- Claude and Codex interchangeable (failover when one hits its limit),
- research safety gates kept (frozen-spec experiment approvals, read-only original dirs, no secrets, no kubectl writes).

Deliverables wanted: component diagram, data model (which DB/file owns what), control-plane table (every knob, where it
lives, who may change it, how the dashboard exposes it), what to delete/merge, migration steps with tests, and the
rules files (AGENTS.md/CLAUDE.md/prompts) rewritten to match.

---

## 1. Context

- **Researcher:** Kostas, a PhD student. Greek speaker, works from a laptop (VS Code Remote-SSH) and from an iPhone
  (Tailscale → dashboard). Non-specialist in agent infrastructure. They say themselves that they do not know why
  the dispatcher was added or what it does.
- **Research:** a hybrid quantum–classical extension of the DInos Kubernetes+Redis autoscaler (Deep RL). Currently in
  simulation (cycle 2 experiments). Quantum work is paused. Paper target: end of Nov 2026 (`docs/PLAN.md` §1, §11).
- **Machine:** one Ubuntu VM (`~/qrl-lab`), CPUs 0–3 reserved for the dashboard, 8–39 for experiments
  (`deploy/qrl-dashboard.service`). Read-only original code in `~/simulations ~/redis ~/k8s ~/prometheus-grafana`.
- **Providers:** a Claude subscription (Claude Code CLI 2.1.30x; 5-hour + weekly limits; extra paid credits exist,
  so overage costs money) and a ChatGPT/Codex subscription (codex-cli, default model `gpt-6.1-sol`/medium in
  `~/.codex/config.toml`).
- **Git:** `~/qrl-lab` has 270 commits, plus separate worktrees per experiment branch (`code/`, `code-poisson*`,
  `code-tuning*`). Push only to the researcher's GitHub repo, after a joint Claude+Codex review (`AGENTS.md`).

---

## 2. How the architecture evolved (why it is tangled)

| When | Version | What was added | What it replaced (in theory) | What really happened |
|---|---|---|---|---|
| 15/10 | v0.1 | PLAN/CLAUDE/AGENTS.md, 5 subagents, `council`+`ask-user` skills, hooks, **lab-bridge monitor** | — | `CHANGELOG.md` |
| 16/10 | v0.2 | `labdb.py` (SQLite `.lab/lab.db`), Streamlit dashboard (8 tabs), `launch_run.py` approval gate, Codex via official plugin, `sqlite3` deny rule | JSONL inbox | The coordinator is **one always-on Claude session in tmux** (`tools/start-coordinator.sh`) fed by the lab-bridge plugin. Around it: `health_watch.py` (scrapes the tmux pane), `watchdog.sh` (cron), `deputy.py` (Codex deputy when Claude is down), hourly LLM check-ins (`.lab/…` loops). |
| 16–23/10 | – | Dashboard grows to 22 tabs, sudo grants, perm hook, usage rings, offers watcher, extensions catalog, statusline, extra-credits estimator | — | Each feature was requested in the dashboard and built by the coordinator. |
| 23/10 | crisis 1 | Weekly Claude limit hit; ~$15.6 extra credits in ~1.5 h (session since 16/10, **282 MB history**, hourly checks on a cold cache) | — | Session «111» (`4056e025…`). Researcher: «tokens θα καιω μονο αν γραφω εδω … ή … στο dashboard;» |
| 26–28/10 | **v0.3** | `tools/dispatcher.py`: a Python loop, 0 tokens while idle, one headless `claude -p` / `codex exec` per work item, bounded context pack (STATE.md + thread), Claude↔Codex failover, `ask_peer.py`, `build_md_index.py`, systemd units, `install_v03.py` | the always-on tmux coordinator, cron, health_watch, deputy, hourly LLM polling | Designed **outside this VM** and delivered as zip "kits" (`docs/COORDINATION.md` §7). Installed on 28/10 by session `0472b420…` («ολοκλήρωσε την αναβάθμιση αυτού του VM στη v0.3»). The old pieces were **stopped, not removed**. |
| 29/10 | **v0.4** | Parallel lanes: 1 chat coordinator (`C<n>`) + up to `max_workers` workers (`J<n>`); `tools/work.py` job board (file claims, agent↔agent negotiation, own-file commits) | the single-task loop | Researcher, M-thread of 29/10: «θελω να μπορω να μιλαω συνεχως σε εναν συντονιστη … οσο αλλοι πρακτορες δουλευουν παραλληλα». Commit `7df2e9c`, cap 1–16 `7f645ab`. |
| 30/10 | crisis 2 | 40 parallel Opus runs, 63 approval cards, Claude 5 h at 99 %, system stuck 06:10–09:30 | — | §11. Fixes: `claude_model=sonnet`, `resume_max_tokens=40000`, `max_workers=2`, perm-answer batching (`2a69203`), lock retries (`fe1fdbc`). |
| 30/10–2/11 | kb | graphify trial (J225), `tools/kb.py` (SQLite FTS5 + graphify AST graph, `8b0cc2e`), «retrieval first» rule in AGENTS.md (`1e65a30`), knowledge-graph tab, token-savings sidebar (J319/J322) | grep over `docs/INDEX.md` | Now there are **two** indexes (§6). |

**Pattern:** each crisis was fixed by **adding** a layer or a setting. Nothing was consolidated, and the rules files
were patched in place (CLAUDE.md was trimmed once on 28/10, M-20261028-004).

---

## 3. What is actually running now (verified 2026-11-03)

| Component | How | State |
|---|---|---|
| `qrl-dispatcher.service` (`tools/dispatcher.py run`) | systemd user unit, `Restart=on-failure`, max 5 starts / 10 min | **running** since 2/11 ~20:50 |
| `qrl-dashboard.service` (Streamlit `dashboard/app.py`, 127.0.0.1:8501, CPUs 0–3) | systemd user unit | **running** |
| Tailscale Serve → 8501 | phone access (tailnet only), `docs/MOBILE.md` | on |
| `codex app-server` daemon | Codex app/VS Code extension infrastructure | running (not part of the lab) |
| cron: `tools/cycle2_daily.py` 15–17 h | crontab (J72) | **stale**: its own comment says "auto-removes after 2026-11-02", and it is still in crontab |
| tmux session `lab` (old coordinator, health, deputy windows) | `tools/start-coordinator.sh` | **not running** |
| `health_watch.py`, `watchdog.sh`, `deputy.py`, `offers_watch.py`, lab-bridge plugin | old v0.2 tooling | **not running** (`.lab/health.json`, `heartbeat`, `offers_watch.heartbeat` last written 28/10; `deputy_state.json` 21/10) |
| `web_terminal.py` (127.0.0.1:8502, token) | started on demand from the dashboard «⌨️ Terminal» tab | on demand |

No Claude session is open except the researcher's interactive one.

---

## 4. The dispatcher: what it is, why it exists, what it does

### 4.1 Why it exists
On 23/10 the coordinator was one Claude Code session that had stayed open since 16/10 (history of 282 MB). Every tool call
re-sends the whole history. After an idle gap the cache expires and the whole history is written to cache again,
which is the most expensive case. Hourly LLM check-ins made this worse. The result was that the weekly limit was
reached, plus ~$15.6 of paid credits in 1.5 h (`CHANGELOG_v03.md` "Problem"; `docs/COORDINATION.md` §1).
**The dispatcher's only job: no model runs while nothing happens, and each run starts small.**

### 4.2 Loop (`tools/dispatcher.py`, 1509 lines, stdlib only)
```
dashboard ──writes──► .lab/lab.db (messages, requests, runs)
                           │  polled by
tools/dispatcher.py run ───┤  (Python loop, heartbeat thread → .lab/bridge_heartbeat)
                           │  work items, by priority:
                           │   1 researcher message (new/delivered/deferred)     → chat lane   (C<n>, one at a time)
                           │   2 researcher decision on a request                 → worker lane (J<n>, ≤ max_workers)
                           │   3 experiment batch finished (all runs of a request) → worker lane
                           │   4 job spawned by the chat coordinator (work.py spawn)→ worker lane
                           │   + worker escalations to the coordinator (debounced 20′)  → chat lane
                           │   + permission answers (perm cards decided in Sudo tab)    → worker lane, batched per thread
                           ▼
           claude -p --output-format stream-json … --max-budget-usd …   OR   codex exec --json -s workspace-write …
           prompt = prompts/coordinator.md role + docs/STATE.md + last 12 thread messages + new input + "Parallel work now"
                           ▼
           final text → posted into the thread with a footer «— Claude · sonnet · 3′ · ≈$0.40»; one journal line
           (docs/journal/<day>.md); tasks row in .lab/dispatch.db
```
- **Session reuse:** a chat follow-up in the same thread resumes the previous session only while the cache is warm
  (Claude ~54′ on subscription, ~4′ on credits; Codex 15′) **and** context < `resume_max_tokens`. Otherwise it
  starts fresh. Workers never resume (`CHANGELOG_v03.md` v0.4).
- **Failover:** if a usage-limit error is detected (regex `QUOTA_RE`, `dispatcher.py:93`, and Claude's
  `rate_limit_event`), the same task is re-run by the other provider. The first one is marked `exhausted` until its
  reset time. If Claude reports overage and `allow_paid_credits=0`, work goes to Codex for 1 h.
- **Coordinator choice:** setting `coordinator`, or a per-message `@claude`/`@codex` prefix, or the dashboard
  composer's model dropdown (`messages.req_model`, `route_request()` `dispatcher.py:102`; honoured since J322 `adbb0ba`).
- **Peer consultation:** `tools/ask_peer.py` queues a read-only question to the other model in `dispatch.db`
  (`peer_requests`), answered by a second dispatcher thread outside the Codex sandbox (52 requests, Claude side $1.83).
- **Permissions in headless runs:** Claude runs with auto mode and `--permission-prompts none`. Anything that would
  ask is denied and parked as a card in `.lab/perm/<id>.json` (shown in the «🔐 Sudo» tab). Approving a card wakes
  a new (batched) run that retries the action (`perm_store.take_approval`). Deny rules (e.g. `sqlite3`) cannot be
  approved away (J221 fix, `2a69203`).
- **Commands:** `run | once | status | set KEY VALUE | clear PROVIDER | exhaust PROVIDER MIN`. `set/clear/exhaust`
  are denied to both agents: by `.claude/settings.json` for Claude, and by `~/.codex/rules/qrl-lab.rules` for Codex.

### 4.3 Settings (`DEFAULTS`, `dispatcher.py:64-90`; stored in `.lab/dispatch.db` table `settings`)
| Key | Default | **Current** | In dashboard? |
|---|---|---|---|
| coordinator | claude | claude | ✅ radio |
| failover | 1 | 1 | ✅ toggle |
| paused | 0 | 0 | ✅ toggle |
| allow_paid_credits | 0 | 0 | ✅ toggle |
| claude_model | opus | **sonnet** (researcher, 30/10) | ❌ (but the per-message dropdown overrides it, so recent chat runs show `opus`) |
| claude_effort | medium | medium | ❌ |
| codex_model / codex_effort | "" / medium | "" (→ gpt-6.1-sol) / medium | ❌ |
| events_model | "" | "" | ❌ |
| peer_claude_model / peer_claude_major_model | sonnet / opus | same | ❌ |
| peer_codex_model / effort / major_effort | "" / medium / high | same | ❌ |
| **max_workers** | 2 | 2 (was 16 on 29/10) | ❌, the most asked-for knob (M-20261029-010/012/021/034/053/065, M-20261102-030) |
| chat_budget_usd / max_budget_usd / peer_budget_usd | 3 / 5 / 1.5 | same | ❌ |
| task_timeout_min / peer_timeout_min | 60 / 15 | same | ❌ |
| escalation_debounce_s | 1200 | same | ❌ |
| resume_max_tokens | 120000 | **40000** | ❌ |
| codex_resume_window_s, thread_messages, state_max_lines | 900, 12, 150 | same | ❌ |

`coord_panel.py` (114 lines) exposes 4 of the 25 keys. The rest exist only as a terminal command that the agents are
**forbidden** to run. This is the root of «το dashboard μου λέει πως μπορεί να τα αλλάξει, τελικά δεν μπορεί» (§10.1).

### 4.4 Provider state now
`providers`: claude `exhausted` until 30/10 11:27 (note "paid credits in use"), codex `exhausted` until 29/10. Both
dates are in the past, and `status` prints both as `ok`, so the rows are stale but harmless. `limits`: Claude 5 h window
`allowed`.

---

## 5. Data stores

| Store | Owner (writer) | Tables / content (rows) | Notes |
|---|---|---|---|
| `.lab/lab.db` | `tools/labdb.py` (dashboard, `labq.py`, `launch_run.py`) | messages 1116 · requests 102 · runs 1881 · audit 5617 · message_edits 10 · thread_title_history 0 | the researcher↔agents channel + experiment launcher; agents are denied `sqlite3` and must use `labq.py`/`launch_run.py` |
| `.lab/dispatch.db` | `tools/dispatcher.py`, `tools/work.py`, `ask_peer.py`, `coord_panel.py` | settings 6 · providers 2 · sessions 34 · tasks 390 · jobs 334 · claims 0 · agent_msgs 360 · peer_requests 52 · limits 1 · notified 42 · deferred 0 · audit 24 | dispatcher state, job board, cost log |
| `.lab/kb/kb.db` (12.8 MB) + `.lab/kb/graphify-out/graph.json` + `.lab/kb/corpus/` (9.8 MB copy) | `tools/kb.py refresh` | chunks/fts 10575 (FTS5), graph 11657 nodes / 23121 edges | retrieval index over code+docs incl. read-only dirs; built 2/11 19:22, manual refresh |
| `~/qrl-lab/lab.db` (root, 73 KB) | nobody | all tables, **0 rows** | stray duplicate from 21/10, together with root `events.jsonl`, `health.json`, `health_watch.*` (same date): created by a run with the wrong cwd |
| `.lab/j147/timing-copy.db` | J147 | copy | leftover |
| `.lab/perm/*.json` (203) | `perm_store.py` | approved 98 · withdrawn 63 · timeout 41 · pending 1 | permission cards |
| `.lab/events.jsonl` | `lab_event_hook.py` (every Claude hook event), `agent_log.py` | hook stream | feeds «🤖 Πράκτορες» tab and sidebar «brain» |
| `.lab/usage/claude.json`, `extra_credits*.json` | `claude_statusline.py`, `extra_credits.py` | rate-limit snapshot, credit estimate | a second source for limits, besides `dispatch.db.limits` |
| `.lab/*` misc. | many | `inbox.jsonl` (16/10), `deputy_queue.jsonl` (21/10), `health.json` (28/10), `notifications_dismissed.json`, `dismissed_banners.json`, `access*.json`, `outages.jsonl`, `offers_*`, ~90 per-job folders `c*/ j*/` with briefs and outputs | about half are v0.2 leftovers |
| Docs in git | agents | see §6 | |

---

## 6. Knowledge / memory layer (the «δέντρο/γράφημα γνώσης»)

### 6.1 Hand-written / agent-written Markdown (in git)
| File | Role | Size |
|---|---|---|
| `docs/PLAN.md` | source of truth for the research plan (§1–§13) | 606 lines |
| `docs/STATE.md` | **the handoff** every dispatcher run gets in its prompt; ≤150 lines | 108 lines (34 KB, so lines are very long) |
| `docs/DECISIONS.md` | dated log of accepted decisions | 113 |
| `docs/rules/*.md` (11 files) | active rules split by topic (models, experiments, research, dashboard, security, paused, handoff, interactive, kb, archive) + precedence and conflicts C1–C6 (`docs/rules/README.md`) | ~340 |
| `docs/researcher_requirements.md` | researcher requirements with ids, e.g. H3 max_workers fact unverified | 87 |
| `docs/EXPERIMENTS.md` | experiment-batch registry | – |
| `docs/journal/<day>.md` | one line per dispatcher task (by script) | – |
| `docs/COORDINATION.md`, `CHANGELOG*.md`, `SETUP*.md`, `docs/token_practices.md`, `docs/kb_eval.md`, `docs/MOBILE.md`, `docs/RECOVERY.md` … | design / ops notes | – |
| `AGENTS.md` (shared), `CLAUDE.md` (Claude, imports AGENTS.md), `prompts/coordinator.md` (dispatcher runs), `prompts/peer.md` | instructions | 3.3 KB, 1.6 KB, 76 lines |
| `docs/claude-memory/` | copy of Claude's auto-memory so Codex can read it (by `build_md_index.py`) | modified, uncommitted |

The repo has **1523 `.md` files** in total (many per-run notes under worktrees and `.lab`).

### 6.2 Generated indexes. There are three, and they overlap.
1. **`docs/INDEX.md` + `docs/index.json`** (`tools/build_md_index.py`, v0.3): one line per `.md` (path, title,
   description from front-matter, date). The dispatcher rebuilds it with `--if-stale`. Agents are told to
   `grep -i <topic> docs/INDEX.md` and never read it whole (`AGENTS.md`, `prompts/coordinator.md`). Rules say «never
   edit» it.
2. **`tools/kb.py`** (J314, 2/11): SQLite FTS5 over code+docs chunks + **graphify** (installed in a separate venv
   `~/.venvs/graphify`, run with `GRAPHIFY_BACKEND=none`, so AST only and no LLM) for call/import edges.
   `kb.py query|callers|stats|scan|refresh`. AGENTS.md now says «retrieval first: kb.py query before reading files».
   The refresh is **manual** ("run refresh if the index is older than your target file"). Measured: 14–15/15 answers
   with ~4.6k tokens vs grep ~11.4k (`docs/kb_eval.md`; bytes/4 estimates). graphify's own Claude hooks were **not**
   installed (M-20261030-059/061).
3. **`tools/convo_context.py`**: «bounded memory for the conversant». It matches a message against `docs/index.json`,
   DECISIONS, researcher_requirements, requests and past messages (accent-insensitive prefixes). It overlaps with
   both of the above.

Plus `tools/md_dedupe.py` (duplicate check before appending to shared md files), and Claude's own auto-memory.

### 6.3 Dashboard views of the knowledge
- «🗂️ Γνώση» tab: `knowledge_tree.py` (zoomable HTML/SVG tree of md files from `docs/index.json`, mobile-first,
  M-20261029-118) + `knowledge_view.py` (folder tree + lookup-path diagram) + **graph knowledge** sub-tab
  `kb_graph_view.py` (force-directed graph of graphify's file-level edges, J322).
- «📁 Αρχεία» tab: file viewer with `?path=` deep links (`file_view.py`, `tab_links.py`).
- Sidebar «brain» (`brain_view.py`): neurons per agent role, lit by `.lab/events.jsonl`.
- Sidebar «token savings» estimate (`token_savings.py` + `dashboard/token_savings.json`). Its per-event savings are
  **assumptions** (stated in its docstring).

---

## 7. Agents, skills, plugins, hooks, permissions

### 7.1 Who can act
| Actor | Started by | Model source | Permissions |
|---|---|---|---|
| Chat coordinator `C<n>` («Πάρις») | dispatcher | `claude_model`/`coordinator`/dropdown/@mention | Claude: `.claude/settings.json` auto mode, headless denials → cards. Codex: workspace-write sandbox, `.git` read-only, so **Codex cannot commit** |
| Workers `J<n>` | dispatcher (from spawn / decision / run event / perm answer) | same + `--to codex` on spawn | same |
| Peer (ask_peer) | dispatcher peer thread | `peer_*` settings | read-only |
| Subagents inside a Claude run | Agent tool | `.claude/agents/*.md` front-matter: Explore=haiku, runner=haiku, engineer/scholar/writer=sonnet; **overrides** from `docs/agent_routing.json` (file does not exist now) | inherit |
| Codex via plugin `codex:codex-rescue` | interactive Claude sessions only (`docs/rules/interactive.md`) | `--model/--effort` in prompt per DECISIONS roles (luna/sol/astra) | plugin |
| Interactive Claude (terminal, VS Code, claude.ai/code) | researcher | user settings | same project settings; `perm_hook.py` routes prompts to the Sudo tab (90 s wait) |
| `deputy.py` (Codex deputy) | old health_watch | – | **dead path** (v0.2) |

### 7.2 Project skills (`.claude/skills/`)
`ask-user` (file a question/approval for the researcher), `inbox` (handle a dashboard message: written for the old
QRL-INBOX notification flow), `council` (Claude+Codex blind proposals → cross-critique), `drl-tuning`,
`poisson-workload`, `rl-eval-protocol` (domain know-how), `find-skills` (third-party vercel-labs, **untracked**
`??`; it is in `skills-lock.json`). User-level: the `unlazy` completion-gate skill (memory says vetted, no Stop hook).
The «🧩 Επεκτάσεις» tab lists a catalog from `.lab/extensions_catalog.json` and installed items (`installed_view.py`).

### 7.3 Plugins / MCP
User level: `codex@openai-codex` (enabled), `pyright-lsp` (enabled); `data`, `agent-memory`, etc. are disabled. Project
`settings.local.json`: `enabledMcpjsonServers: ["codex"]`, **but `.mcp.json` was renamed `.mcp.json.disabled` in v0.2**
(codex mcp-server deprecated), so this is a dead setting. `disableClaudeAiConnectors: true` (M-20261028-005).

### 7.4 Hooks (`.claude/settings.json`)
`lab_event_hook.py` runs on SessionStart, SubagentStart/Stop, **PreToolUse, PostToolUse**, Notification, Stop: a
Python process per tool call, in every headless run too (no tokens; latency only). `sudo_gate.py` (PreToolUse/Bash:
sudo only with an open grant from `sudo_grant.py`). `perm_hook.py` (PermissionRequest → Sudo tab, interactive only).

### 7.5 Permission layers. There are six, and each has its own source of truth.
1. `.claude/settings.json` allow/ask/deny (incl. `sqlite3` deny since v0.2, `git push github` allow since R-20261029-003,
   dispatcher `set/clear` denied), and `defaultMode: auto` + the auto-mode classifier (it refused agents' attempts to
   edit settings or raise `max_workers`: M-20261029-065, "researcher-only").
2. `~/.codex/rules/qrl-lab.rules` (execpolicy) + Codex sandbox.
3. Headless perm cards (`.lab/perm`, Sudo tab) → retry runs.
4. `sudo_gate.py` + time-limited grants (`sudo_grant.py`, Sudo tab).
5. Research approvals: `labq.py ask` → «Αποφάσεις» tab → `launch_run.py` frozen-spec gate.
6. Text rules in AGENTS.md / CLAUDE.md / prompts / docs/rules (e.g. «never change settings unless asked»).

---

## 8. Dashboard (`dashboard/app.py` 3221 lines + ~40 `tools/*_view.py` / `*_ui.py`)

22 tabs (`app.py:1096`): Home/chat · Αποφάσεις · 🤖 Πράκτορες · 📈 Πειράματα · ⚖️ Council · 🖥️ Πόροι · ☸️ Kubernetes ·
📡 Prometheus · 📊 Grafana · 📁 Αρχεία · 📝 Paper · 🎓 Συνέδρια · 🧾 Ιστορικό · 🔐 Sudo · 🧩 Επεκτάσεις · 🔌 Διακοπές ·
🧭 Ιστορικό αλλαγών · 🧠 Μοντέλα (RL models spec from `docs/models.json`, not agent models) · 🏛️ Αρχιτεκτονική ·
⌨️ Terminal · 🗂️ Γνώση · 📚 Tutorials. Sidebar: coordinator panel, usage rings, limits notifications, brain, token
estimate.

### What the dashboard can change itself (direct writes)
- messages (send, edit, rename thread), with model/effort dropdown and a «structured md» toggle;
- decisions on requests (`LabDB.decide`, `app.py:881`, `2818-2830`);
- perm cards approve/deny (`perm_store.decide`, `app.py:1075`, `2769`); sudo grants;
- 4 dispatcher settings + «provider available again» (`coord_panel.py`);
- `docs/agent_routing.json` (Αρχιτεκτονική tab, `topology_ui.py`);
- banner/notification dismissals; web terminal start/stop; uploads.

### What it cannot change, though it is often asked for
Every other dispatcher setting (max_workers, models, efforts, budgets, timeouts, resume limit), `.claude/settings.json`
(allow/deny, hooks), `~/.codex/config.toml` and rules, systemd units, crontab, prompts, git push/branch deletion.
For each of these, a dashboard request goes to an agent. The agent is forbidden to do it and replies «run X yourself»
(§10.1). Only the embedded Terminal tab bridges the gap, and it is a raw shell.

### How dashboard features get built
The researcher asks in chat → coordinator spawns a worker → worker edits `dashboard/app.py` → dashboard restart. The
v0.2 rule «engineer implements, run tests/test_lab.py, F5» (`docs/rules/dashboard.md`) predates the dispatcher.
`dashboard/app.py` is the most contended file in parallel claims.

---

## 9. Control-plane map: every knob and where it lives

| Concern | Places that decide it today | Who may change | Dashboard? |
|---|---|---|---|
| Which provider coordinates | `dispatch.db settings.coordinator`; `@claude/@codex`; composer dropdown `req_model`; failover state `providers` | researcher | partly |
| Which model/effort per role | `claude_model/effort`, `codex_*`, `events_model`, `peer_*` (dispatch.db); `.claude/agents/*.md` front-matter; `docs/agent_routing.json` (Αρχιτεκτονική tab); `docs/rules/models.md` + DECISIONS C6; CLAUDE.md routing text; `~/.codex/config.toml`; `.claude/settings.json "model": "opus", effortLevel medium` | mixed | Αρχιτεκτονική tab writes a file **the dispatcher ignores** |
| Parallelism | `max_workers`; `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=3` (settings env); «max 3 concurrent subagents» (CLAUDE.md) | researcher (terminal) | ❌ |
| Cost caps | `chat/max/peer_budget_usd`; `allow_paid_credits`; claude.ai account spend limit; `resume_max_tokens` | researcher | 1 of 5 |
| Usage-limit info | `dispatch.db.limits` (from stream-json); `.lab/usage/claude.json` (statusline); `usage_limits.py` (Codex rollout logs); `extra_credits.py`; `offers_watch.py` (dead); `.lab/health.json` codex key (dead) | scripts | yes, from several sources at once |
| Permissions | 6 layers, §7.5 | researcher | cards/grants only |
| Memory/handoff | STATE.md, DECISIONS.md, PLAN.md, rules/*, researcher_requirements.md, journal, EXPERIMENTS.md, claude-memory mirror, auto-memory | agents | read-only views |
| Retrieval | INDEX.md/index.json; kb.db+graphify; convo_context; grep | scripts | Γνώση tab |
| Liveness | `.lab/bridge_heartbeat` (dispatcher heartbeat thread; name from v0.2 lab-bridge); `.lab/heartbeat`, `health.json` (dead) | scripts | yes |
| Restart / recovery | systemd; `boot_recover.sh`; `watchdog.sh` (cron, removed?); `start-coordinator.sh` (fallback in COORDINATION §6) | researcher | ❌ |

---

## 10. Overlaps, contradictions, dead parts (the core problem)

### 10.1 "The dashboard says it can change it, then tells me to do it in the terminal"
Evidence: 41 coordinator replies point the researcher to the terminal or to settings (search of `lab.db` messages).
Examples: max_workers (M-20261029-010, -012, -021, -034, -053, -065, M-20261102-030), the perm hook in settings.json
(M-20261017-023, -109), the `sqlite3 -readonly` allow (M-20261030-036…-051, M-20261031-001), deleting GitHub branches
(M-20261029-149), «I run on Sonnet and can't switch model from inside, resend with Opus in the dropdown»
(M-20261102-007). **Cause:** every control-plane change is reserved to the researcher, which is correct, but the only
researcher-side surface for it is the terminal. The safety rule is right; the missing piece is a researcher-authenticated
control surface in the dashboard.

### 10.2 Model routing: 7 sources, and they disagree
The dispatcher uses `claude_model=sonnet`. The composer dropdown overrides it per message (recent chat tasks ran
`opus`). The Αρχιτεκτονική tab writes `docs/agent_routing.json`, which only *interactive* sessions read
(`docs/rules/interactive.md`); `dispatcher.py` never reads it (grep: no match). Subagent models come from
`.claude/agents/*.md`. DECISIONS/models.md have role rules (C6: engineer Opus for research code). `.claude/settings.json`
says `model: opus`. The Codex model lives in `~/.codex/config.toml`.

### 10.3 Two coordination systems coexist
v0.2 pieces are still wired in but inactive: the `inbox` skill (QRL-INBOX notifications from lab-bridge), the
«Dashboard protocol» in `docs/rules/interactive.md` (run `labq.py pending` at session start, read `deputy_queue.jsonl`),
`deputy.py`, `health_watch.py`, `watchdog.sh`, `start-coordinator.sh` (still the documented rollback),
`term_prompt.py` (sends keys to tmux `lab:0`, which does not exist), `codex_health.py`, `.lab/health.json` banners,
the lab-bridge monitors folder. The dashboard still reads several of these (`read_health`, health/codex banners,
`app.py` has 12 references to deputy/health_watch).

### 10.4 Two ways to call Codex, two different rule sets
Dispatcher `codex exec` (workspace-write, cannot commit, rules file) vs the plugin `codex:codex-rescue` inside
interactive Claude (AGENTS/interactive.md: `agent_log.py start/end`, role-model table). `ask_peer.py` is a third,
read-only path. `docs/rules/handoff.md` (awake/asleep, solo branches, council on return) was written for the v0.2
deputy and is still in force.

### 10.5 Three retrieval indexes
INDEX.md (grep), kb.py (FTS5+graph, manual refresh), and convo_context. AGENTS.md says «kb first» while
`prompts/coordinator.md` still says «grep INDEX.md». kb's corpus is a 9.8 MB copy that goes stale between refreshes.

### 10.6 Several limit/usage trackers
`dispatch.db.limits`, statusline snapshot, `usage_limits.py`, `extra_credits.py`, sidebar rings, `token_metrics.py`,
`token_savings.py` (assumed numbers), `offers_watch.py` (dead). The dashboard shows a mix of measured and assumed numbers.

### 10.7 Approvals: 3 tabs, 6 layers (§7.5)
The 30/10 collapse came from their interaction: a deny rule + the perm-card feature + one worker run per approval.

### 10.8 Rules sprawl
Rules live in AGENTS.md, CLAUDE.md, prompts/coordinator.md, 11 `docs/rules/*.md`, DECISIONS.md, PLAN.md, skills,
researcher_requirements.md, and the STATE.md «μην ξανακάνεις» section. `docs/rules/README.md` needs a contradiction
procedure (C1–C6) precisely because of this. Signature/language rules appear in 3 places.

### 10.9 Hygiene
44 uncommitted paths in `~/qrl-lab` (incl. STATE/DECISIONS/EXPERIMENTS, tools, tests, `code-*` submodule-like
worktrees). One commit (`e92d223`, `1e65a30`) swept in other jobs' uncommitted work. Root-level stray `lab.db` etc.
Expired cron line. Stale `providers` rows. `tests/test_exp_view.py` failing since at least 29/10 (cause not checked).
`.lab` has ~90 per-job folders, never cleaned.

---

## 11. Incidents and lessons

1. **23/10, cost of the always-on session.** Weekly limit, ~$15.6 credits in 1.5 h. Cause: an open-ended session with
   a cold cache and hourly checks. → v0.3. *Lesson:* never keep an LLM session open as a daemon.
2. **29/10, false «Συντονιστής offline».** The heartbeat was written only between tasks (`dispatcher.py:912` at the
   time). → heartbeat thread.
3. **30/10, collapse** (session `d4231116…`, M-20261030-053):
   - `sqlite3` deny since v0.2 + agents trying `sqlite3` to inspect a stuck experiment → denials;
   - approval cards (R-20261028-002 item 8) turned each denial into a card;
   - each approval became **a separate worker run** (no batching). With `max_workers=16` this meant 40 Opus runs in ~10 min (~$13);
   - Opus chat resumed up to 120k context: ~$1.09/message, one message read 1.6 M cache tokens ($3.17);
   - a `database is locked` at 05:59 left ghost jobs J171/J172 «running» and stalled everything ~4 h.
   - Fixes: `max_workers=2`, `claude_model=sonnet` + `resume_max_tokens=40000` (~$0.17/message), 63 cards withdrawn,
     batching and no cards for deny rules (`2a69203`), banner collapse (`1b0106d`), lock retries (`fe1fdbc`).
   - *Lessons:* fan-out must be bounded by cost, not only by count. A safety denial must never create paid work.
     Settings that matter must be visible.
4. Escalations from workers to the coordinator cost $28 in 22 runs before the 20′ debounce (R-20261029-012).

## 12. Cost data (dispatch.db `tasks`, 28/10–2/11, Claude estimates; Codex reports no cost)
| Kind | Claude runs | Claude ≈$ | avg | Codex runs |
|---|---|---|---|---|
| message (chat) | 82 | 45.2 | 0.55 | 14 |
| job (spawned) | 31 | 31.7 | 1.09 | 33 |
| escalation | 22 | 28.1 | 1.27 | 32 |
| perm_answer | 63 | 16.7 | 0.27 | 3 |
| decision | 33 | 14.1 | 0.47 | 1 |
| run_event | 27 | 10.4 | 0.38 | 5 |
| peer | 10 | 1.8 | 0.18 | 34 |
| **total** | 268 | **148.1** | | 122 |

Per day: 28/10 $6 · **29/10 $94** · 30/10 $27 · 31/10 $5 · 1/11 $7 · 2/11 $9. Since 31/10 (after the fixes) the cost is
$5–9/day. The 5 h Claude window empties at roughly $25–30 of Opus-equivalent (estimate from 30/10). 50 % of all runs are
"overhead" kinds (escalation, perm_answer, run_event, decision), not researcher requests.

---

## 13. What works well (keep)
- An event-driven loop with zero idle cost, headless bounded runs, and continuity in files/DB rather than in sessions.
- Claude↔Codex failover and peer consultation, with the same rules for both.
- `labdb.py`: atomic IDs, validated transitions, audit; `launch_run.py`: the frozen-spec approval gate.
- File claims + own-file commits for parallel agents (`work.py`).
- `STATE.md` as a bounded handoff; the per-task journal; the cost footer on every reply.
- Phone access via Tailscale; dashboard bound to 127.0.0.1.
- Tests with fake CLIs (`tests/test_dispatcher.py` 20 tests, `tests/test_lab.py`) that spend no tokens.

---

## 14. The researcher's requirements, in their own words
- «θελω να μπορω να μιλαω συνεχως σε εναν συντονιστη και να ζηταω πραματα οσο αλλοι πρακτορες δουλευουν παραλληλα»
  and «θα συζητουν μεταξυ τους αν προκυψει να πειραξουν τα ιδια αρχεια και θα φτανουν στη βελτιστη αποφαση» (29/10).
- Do not burn tokens: «μην καταναλωσεις καθολου tokens» (23/10); «το claude γιατι καιει τα τοκενς τοσο γρηγορα;;; …
  πρεπει να λυθει αυτο αμεσα» (30/10).
- Work from the phone; the dashboard must never be blocked by approval prompts (30/10).
- No surprise approval prompts: «δεν ειχα δωσει ποτε τετοια εντολη» (30/10).
- Today (3/11): «μπλεξαμε πολυ την αρχιτεκτονικη … καποια πραματα δουλευουν, καποια οχι, καποια αλληλοκαλυπτονται.
  … απο το dashboard δεν εχω … προσβαση στο τι κανει και τι μπορω να αλλαξω στον dispacher … αλλαγες που κανω στο
  dashboard μαλλον καταληγουν να φτιαχνουμε πραματα που κανουν ακριβως οτι και το dispacher ειτε παραλληλα ειτε
  αλληλοαναιρουμενα.»
- Standing rules that must survive: Greek, short and direct replies to the researcher, signed «— Πάρις»; never guess
  numbers; experiments only via approved frozen specs; no edits to original dirs; no secrets; no kubectl writes;
  push only to the researcher's repo after a joint review; quantum claims rules (`AGENTS.md`).

## 15. Questions the new design should answer
1. Single control plane: one table of settings (dispatcher + models + permissions summary), editable in the dashboard
   behind an explicit researcher action, with audit and validation. Should agents be able to *propose* a change as a
   one-click card instead of «run this in the terminal»?
2. One model-routing source read by every path (dispatcher, subagents, Codex, peer).
3. Should interactive sessions exist at all in the new design, or be just another client of the same dispatcher?
4. Which overhead work items (escalation, perm_answer, run_event, decision) should be scripts instead of LLM runs?
5. Cost governor: a budget per hour/day across all lanes (not per run), and fan-out limited by remaining 5 h quota.
6. One retrieval layer (merge INDEX.md, kb.py, convo_context) with automatic refresh.
7. One permissions story: what is denied, what is pre-approved, what becomes a card, and never «card → paid retry» for a hard deny.
8. A consolidated rules hierarchy (one file per audience: shared rules, coordinator prompt, worker prompt), and a
   deletion list for v0.2 leftovers (§10.3, §10.9).
9. The dashboard: 22 tabs, of which several are rarely used. Which tabs should stay, which should merge, and should
   dashboard changes be built by agents at all, or frozen?
10. Migration that keeps `.lab/lab.db` history, runs, approvals and git intact, with tests before each switch.

## 16. Pointers
- Design docs: `docs/COORDINATION.md`, `CHANGELOG_v03.md`, `CHANGELOG.md`, `SETUP_v03.md`, `docs/token_practices.md`.
- Code: `tools/dispatcher.py`, `tools/work.py`, `tools/ask_peer.py`, `tools/labdb.py`, `tools/labq.py`,
  `tools/launch_run.py`, `tools/perm_store.py`, `tools/perm_hook.py`, `tools/sudo_gate.py`, `tools/kb.py`,
  `tools/build_md_index.py`, `tools/convo_context.py`, `dashboard/app.py`, `dashboard/coord_panel.py`,
  `tools/topology_ui.py`.
- Config: `.claude/settings.json`, `.claude/settings.local.json`, `.claude/agents/`, `.claude/skills/`,
  `deploy/*.service`, `deploy/codex-qrl-lab.rules`, `~/.codex/config.toml`, `~/.config/qrl-lab/env`.
- Instructions: `AGENTS.md`, `CLAUDE.md`, `prompts/coordinator.md`, `prompts/peer.md`, `docs/rules/`.
- Claude Code transcripts (`~/.claude/projects/`): `-home-ubuntu/4056e025-…` (session «111», token costs, 23–26/10);
  `-home-ubuntu-qrl-lab/0472b420-…` (v0.3 install, 28/10); `-home-ubuntu/d4231116-…` (v0.4 parallel work and the
  30/10 crisis); `-home-ubuntu-qrl-lab/7456dd5b-…` (the old always-on coordinator, 16–22/10).
