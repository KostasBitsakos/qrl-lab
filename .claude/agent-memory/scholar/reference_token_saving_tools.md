---
name: token-saving-tools
description: Verified (2026-10-17) token-saving add-ons and built-in features for Claude Code/Codex; sources and risks
metadata:
  type: reference
---

Verified by opening pages on 2026-10-17 (savings figures are self-reported):
- rtk-ai/rtk: shell-output filter, hook via `rtk init -g [--codex]`, Apache-2.0 (engine/proxy BUSL-1.1), v1.0.1 on 14 Oct 2026.
- thedotmack/claude-mem: persistent memory plugin, Apache-2.0, v13.41.0; optional cloud paths (hosted observer, cmem.ai sync) send data off VM.
- oraios/serena: symbol-level MCP, GPL-3.0, has execute_shell_command.
- Built-ins: code.claude.com/docs/en/costs and /memory. The Codex CLI page (learn.chatgpt.com/docs/codex/cli) says nothing about tokens or /compact.
Output was delivered to .lab/outbox/M-20261017-026.md and extensions_catalog.json category "tokens".
2026-10-21 re-check (docs): settings/env verified at code.claude.com/docs/en/{costs,env-vars,model-config,prompt-caching}: CLAUDE_CODE_AUTO_COMPACT_WINDOW/autoCompactWindow, BASH_MAX_OUTPUT_LENGTH, CLAUDE_CODE_MAX_OUTPUT_TOKENS, CLAUDE_CODE_SUBAGENT_MODEL, effortLevel, CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL (subagents get 5m TTL even on subscription), idleCompaction, /usage shows attribution+recommendations. Codex: developers.openai.com/codex/config-sample (tool_output_token_limit, model_auto_compact_token_limit, model_reasoning_effort).
2026-10-22: full report docs/token_saving_2026-10-22.md. Codex docs moved to learn.chatgpt.com (developers.openai.com 308-redirects); config-reference has agents.default_subagent_model, enabled_tools/disabled_tools, tool_output_token_limit. Claude subagent `model`/`effort` frontmatter; override Explore with haiku. claude-context needs keys+vector DB (rejected). Ollama v0.40.8 has `ollama launch claude|codex`.
Tool quirk: WebFetch of GitHub releases pages shows dates reliably; the main README often does not.
