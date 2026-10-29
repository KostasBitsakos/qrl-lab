---
description: Active rules for model routing, Codex roles and model/effort table, engineer model choice
---
# Models and agents — active rules

Routing defaults and the Codex call procedure: see docs/rules/interactive.md «Routing» and «Codex» (moved from CLAUDE.md 2026-10-28); researcher overrides in
`docs/agent_routing.json` win (CLAUDE.md).

- Every task uses the cheapest model that does it well. (2026-10-16, R-20261016-016)
- Claude side: Explore → Haiku; engineer → Sonnet; Opus only for simulator or circuit design; scripts for repetitive work. (2026-10-16, R-20261016-016) **Resolved (2026-10-20, M-20261020-025): C6: engineer on Opus for all research/simulator code; Sonnet only for small dashboard changes** **Narrowed (2026-10-20, M-20261020-027): Opus only while the tuning loop runs (expires 2026-10-21 23:59 UTC); afterwards pick the most suitable agent per task by resources, as before (R-20261016-016 routing).**
- Implementation work in the tuning loop goes to the engineer with `model: opus`; every implementation is checked by the other side (Codex review or Claude) before its results are used. No expiry stated. (2026-10-20, M-20261020-013) **Resolved (2026-10-20, M-20261020-025): C6: engineer on Opus for all research/simulator code; Sonnet only for small dashboard changes** **Narrowed (2026-10-20, M-20261020-027): Opus only while the tuning loop runs (expires 2026-10-21 23:59 UTC); afterwards pick the most suitable agent per task by resources, as before (R-20261016-016 routing).**
- Stronger models without further approval for experiments/paper/implementation work: deep reviews by Claude Opus (high) and Codex gpt-6-astra (high); simulator/reward implementation by the engineer with model opus. **Expires 2026-10-21** (end of the tuning loop). (2026-10-19, M-20261019-037)
- Codex roles run through the ChatGPT subscription via the Codex CLI; no API keys. Models from `codex debug models`; luna and 6.1-sol were tested with one call each on 2026-10-16. (2026-10-16, R-20261016-016)
- Codex role table (referenced by CLAUDE.md): (2026-10-16, R-20261016-016)

| Role | Model / effort |
|---|---|
| codex-quick (simple questions) | `gpt-6-luna` / low |
| codex-reviewer (code/results review) | `gpt-6.1-sol` / medium |
| codex-researcher (literature/venues second opinion, read-only, verified sources) | `gpt-6.1-sol` / medium |
| codex-architect (council: simulator, models, paper claims) | `gpt-6-astra` / high, with the reason logged |

- Default to Codex roles for every review, second opinion, literature or venue cross-check, and draft that needs no file edits; Claude agents handle file edits and runs. (2026-10-16, M-20261016-078) **Superseded in part (2026-10-21, researcher): Codex may also take engineer (file-edit) work after Claude-Codex discussion, when it is the cheaper adequate agent.**
- The researcher runs ChatGPT app tools by hand (Deep Research, agent mode) and uploads results to the dashboard (📎); the coordinator integrates them. (2026-10-16, M-20261016-078)
- When the researcher asks for Codex, Codex must actually be consulted and its answer shown as Codex (`--author codex`); never substitute your own answer or only offer to ask. (2026-10-16, handoff standing rule 3)
- Mutual fallback: when Claude or Codex hits a usage limit, the other takes over temporarily; they communicate through the dashboard thread and `.lab/deputy_queue.jsonl`. (2026-10-17, M-20261017-005/006/007)
- When Codex leads, it hands tasks to its cheaper models (luna/sol); crucial work stays with the specialist agent that owns it. (2026-10-17, M-20261017-005/006/007)
- When Codex is limited, Codex roles fall back to Claude agents (reviewer → Claude Sonnet); full mapping in CLAUDE.md. (2026-10-17, M-20261017-005/006/007)
- Opus engineer scope (2026-10-21, researcher, clarifies M-20261020-013/027): `model: opus` is only for the tuning-loop experiment implementation (the main objective). Everything else — dashboard, tools, docs — goes to the cheapest adequate agent, Claude (Haiku/Sonnet) or Codex (luna/sol, implementation mode), chosen after a short Claude-Codex discussion. Weekly Claude usage is the binding constraint: prefer Codex for implementation when it is adequate.
- Fallback for the most important scope (2026-10-21, researcher): experiments, models, their coordination, architecture/implementation discussion and numbers get the best models; if Claude Opus runs short of usage, engineering for this scope goes to Codex `gpt-6-astra` (high) — whichever is better and has enough resources. All other tasks: be frugal until the experiments end.
- Per-task model choice across vendors (2026-10-29, M-20261029-028): for every new task the coordinator picks the best model from Claude
  (Haiku/Sonnet/Opus/Fable) or Codex (gpt-6-luna/6-sol/6.1-sol/6-astra) by quality for the task, speed and cost; when one
  vendor is near or at its usage limit (dispatcher `limits` table, journal) it routes to the other. `work.py spawn --to`
  selects the vendor; the dispatcher's failover re-runs on the other on a limit. Codex CLI default model must be one the
  ChatGPT account supports (29/10: `gpt-5.1-codex-max` in ~/.codex/config.toml failed; gpt-6-sol and gpt-6.1-sol tested OK).
