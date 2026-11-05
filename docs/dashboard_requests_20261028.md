---
description: Researcher requests of 2026-10-28 (M-20261028-006): checks done (items 1, 2a-c, 4) and the dashboard work plan (items 2d, 3, 5-8)
---
# Requests M-20261028-006 (2026-10-28)

## Done / checked
- **1 Plugins/MCP for this project only**: `.claude/settings.local.json` → `disableClaudeAiConnectors: true`,
  `enabledPlugins["data@synced"]: false` (backup `.lab/settings.local.json.bak-20261028`). The user-scope toggles of
  M-20261028-004 were removed from `~/.claude/settings.json`, so other projects keep their connectors.
  Verified with `claude mcp list`: in `~/qrl-lab` "No MCP servers configured"; in `/tmp` Gmail/Drive/Calendar/data are listed.
- **2a experiments**: nothing ran after 24/10; 0 files changed after 25/10 in `.lab/tuning`, `code/`,
  `code-tuning/tuning`, `code-tuning-astra/tuning`; worktree HEADs are 5eae972 (23/10) and 16d9bf4 (22/10); the v0.3
  commit db8e593 touched only `.claude`, docs, tools, dashboard, prompts, tests and deploy (no simulator or launcher code).
- **2b/2c knowledge**: kept in `docs/STATE.md`, `docs/DECISIONS.md`, `docs/rules/`, `docs/claude-memory/` (14 files),
  `docs/paper_notes.md`, `docs/EXPERIMENTS.md`; every message stays in the lab db (`labq.py show <id> --full`).
  Gap found and fixed: `docs/INDEX.md` skipped all of `.lab/`, i.e. the cycle results that STATE points to
  (`.lab/tuning/cycles/*`, councils, Codex handoffs). `tools/build_md_index.py` now indexes `.lab/tuning`,
  `.lab/council`, `.lab/codex-handoff` (152 → 276 files). `.lab/outbox` (372 reply drafts) stays out on purpose.
  Remaining gap: no per-thread digest; long threads are only searchable as raw messages.
- **4 open sessions**: on the VM, one interactive `claude` (VS Code terminal pts/3, started 28/10 18:50 UTC) and the
  dispatcher's one-shot `claude -p`. Cloud sessions on claude.ai/code are not visible from the VM.

## Plan for the dashboard items (needs the researcher's OK; implementer `engineer`, Sonnet)
1. **2d «Γνώση» tab**: tree of every folder with md files, built from `docs/index.json`; each file shows its
   description; central entry points (STATE, INDEX, DECISIONS, rules/README) highlighted; a diagram of how a
   coordinator finds information (STATE → INDEX grep → file).
2. **3 Edit freeze**: while a sent message is being edited it gets status `editing`; the dispatcher skips it (and
   stops a running task on it); on Enter it goes back to `new` with a note «edited: re-read and check your answer
   before replying».
3. **5 Sidebar**: redesign the «who is awake / tokens» strip in plain Greek (cards, colour, reset time, one-line
   explanation).
4. **6 Token savings**: show only measured numbers (bytes of CLAUDE/AGENTS, tool-definition count, prompts per task
   from the dispatcher log) and label the rest as an estimate. A percentage "with certainty" for total savings is
   not measurable without per-call usage data.
5. **7 Right click on a tab**: each tab gets a link `?tab=<name>` (tabs already bind to the query string), so right
   click → «open in new tab» works.
6. **8 Approvals from the dashboard**: all approvals already go through the Decisions tab and sudo through
   `tools/sudo_grant.py` (a sudo grep in this task was blocked: "no active grant"). What cannot be done from the
   dashboard: Claude's own permission prompts in headless mode (they are denied automatically); the fix is to
   route them as Decisions too.

## Implemented (R-20261028-002, approved 2026-10-29; engineer Sonnet)
- 2d «🗂️ Γνώση» tab dd26185 (`tools/knowledge_view.py`) · 3 edit freeze 0bfce32 (`editing` status; a running task
  cannot be killed, its reply is discarded and the message re-queued) · 5 sidebar cards 81bd1a8 · 6 measured token
  savings 574c9a9 (disabled connector count unknown from settings; total % labelled not measurable) · 7 right-click
  7f0a0bc (`tools/tab_links.py`, JS not browser-tested) · 8 headless denials → pending approvals 1bfe9cc
  (`perm_store.py`; an approval informs the agent; if the run is still denied a permission allow rule in
  `.claude/settings.json` would be needed — not changed).
- Needs: restart dashboard + dispatcher, F5, manual browser check of right-click.
