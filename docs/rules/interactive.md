---
description: Interactive-session rules moved out of CLAUDE.md on 2026-10-28 (M-20261028-004): dashboard protocol, Codex plugin calls, routing
---
# Interactive sessions — full rules (moved verbatim from CLAUDE.md, 2026-10-28, M-20261028-004)

Read this when you are in an interactive session (terminal, claude.ai/code, app) or before delegating/calling Codex.
Dispatcher tasks follow `prompts/coordinator.md`. Pre-trim copy: `.lab/CLAUDE.md.bak-20261028`.

## Dashboard protocol
- **At the start of every session** (and after a usage-limit pause): run `python3 tools/labq.py pending`, then read
  and handle every open researcher message and decision, oldest first, before anything else (researcher, 2026-10-16).
- At session start also read `.lab/deputy_queue.jsonl` and the Codex deputy's posts (model «gpt-6.1-sol · αναπληρωτής» or «gpt-6-luna · αναπληρωτής»);
  queued items need your execution.
- Questions for the researcher go in the chat or the Decisions tab, with `~/` paths so they render as links.
  Never only in docs files.
- A notification starting `QRL-INBOX` is a researcher message → follow skill `inbox`. Every message gets a visible
  reply in its thread (`python3 tools/labq.py post ...`), and its status always ends as done, failed or
  waiting_approval. If work takes more than a few minutes, post a short interim reply with `--status in_progress`.
- `QRL-DECISION` is a researcher decision → act only within what it allows, then say in the related thread what you did.
- Questions, proposals and approval requests for the researcher → skill `ask-user` (never only in chat).
- If the researcher writes in the terminal or app instead, answer there.

## Codex (OpenAI) — a co-researcher, not only a reviewer
- Call Codex only through the Agent tool with `subagent_type: "codex:codex-rescue"` (official plugin).
  Prompt prefix: `--fresh` (new thread) or `--resume` (continue the latest Codex thread), then `--model` and
  `--effort`: pick the role in `docs/DECISIONS.md` (quick `gpt-6-luna`/low, review `gpt-6.1-sol`/medium, major `gpt-6-astra`/high with a logged reason), then
  `READ-ONLY: research and review only, do not edit files.` unless it is approved implementation work.
- Before and after every Codex call run `python3 tools/agent_log.py start --agent <role> --model <m> --effort <e> --task "..."` and `agent_log.py end <id> [--status failed]`, with its role (codex-quick, codex-reviewer, codex-researcher, codex-architect).
- If Codex is limited (banner, `.lab/health.json` key `codex`; report a failure with `tools/codex_health.py record`),
  route Codex roles to Claude: reviewer → Claude Sonnet, researcher → `scholar`, quick → Haiku.
- Run Codex calls one at a time (`--resume` follows the latest thread in this repo).
- Post Codex's answer into the thread with `--author codex --kind contribution`, then your own synthesis as
  coordinator: where you agree, where you disagree, what you recommend. Decisions that change the research go
  through skill `council`.

## Routing (save tokens)
- Code/log/directory search → `Explore` (Haiku). Do not read big files yourself.
- Approved runs → `runner` (Haiku). Implementation, tests, dashboard → `engineer` (Sonnet; `model: opus` only for
  circuit or simulator design, with a reason). Literature, citations, venues → `scholar`. Paper text → `writer`.
- Repetitive work (metrics, plots, parsing, monitoring) → a script, never an LLM loop. Max 3 concurrent subagents.
- **Researcher overrides**: if `docs/agent_routing.json` exists (written from the dashboard «Αρχιτεκτονική» tab), its
  `{role: {model, effort}}` entries override the defaults above and in `docs/DECISIONS.md`: pass them as `model`/`effort`
  to the Agent tool, or as `--model`/`--effort` to Codex. Read it before every delegation.

