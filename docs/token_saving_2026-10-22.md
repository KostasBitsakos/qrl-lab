# Token saving for Claude Code and Codex CLI (2026-10-22)

Author: scholar. Nothing was installed or changed. Facts were read on 2026-10-22 from the pages cited. "Unknown" means the page
did not state it. Third-party figures are marked as such and are not measured by us.

## Περίληψη για τον Κώστα

Κώστα, οι μεγαλύτερες εξοικονομήσεις είναι ρυθμίσεις χωρίς εγκατάσταση. Στο Claude: μοντέλο και effort ανά subagent,
καθαρισμός/compaction στα φυσικά σημεία, και CLAUDE.md κάτω από ~200 γραμμές. Στο Codex: `model_reasoning_effort`,
`tool_output_token_limit`, `model_auto_compact_token_limit`, `agents.default_subagent_model`, και περιορισμός MCP εργαλείων.
Οι εξωτερικοί βοηθοί (RTK, pyright LSP) θέλουν δική σου έγκριση. Τοπικό LLM και embedding index δεν τα προτείνω: μικρό όφελος,
πραγματικός κίνδυνος ποιότητας ή κλειδιά/υπηρεσίες. Η ανάπτυξη των ρυθμίσεων στο `.claude/settings.json` απαιτεί εσένα
(οι agents δεν επιτρέπεται να το επεξεργαστούν).

## Already in place or rejected (not re-proposed)

- Rejected 2026-10-20 (`docs/extensions_eval_2026-10-20.md`): Perplexity, HyperFrames, Claude in Chrome, Chrome DevTools MCP,
  Playwright MCP, Firecrawl.
- Already catalogued 2026-10-17 (memory): RTK, claude-mem, Serena. This report adds new facts on RTK only (Section B1).
- Current `.claude/settings.json`: `model: opus`, `effortLevel: medium`, subagent concurrency 3, spawn depth 1.
  Agents defined in `.claude/agents/`: Explore, engineer, writer, runner, scholar (per-agent `model`/`effort` frontmatter not
  re-checked here; the engineer should read the five files).

## A. Built-in settings and practices

### A1. Claude Code

| # | Practice | Source (official) | Stated saving | Effort | Risk | Approval |
|---|---|---|---|---|---|---|
| 1 | `model:` and `effort:` frontmatter per subagent (`haiku` for search/run, `sonnet` for code); override built-in Explore by defining a user/project subagent named `Explore` with `model: haiku`. Resolution order: per-invocation param, frontmatter, `CLAUDE_CODE_SUBAGENT_MODEL`, main model. | https://code.claude.com/docs/en/sub-agents ; https://code.claude.com/docs/en/costs | No figure. Page says Sonnet "costs less than Opus"; a switch to Opus also applies to subagents that inherit. | Low | Weaker model misses detail on hard tasks | Own `.claude/agents/*.md` edits: engineer. `settings.json` env: researcher (edit denied to agents). |
| 2 | Opus 5.5, Sonnet 5.5, Haiku 5.5 default to `medium` effort; `max` "may show diminishing returns". Keep `effortLevel` at `medium` or `low` for routine coordination; reserve `high`+ for design. Thinking tokens are billed as output and cannot be turned off on these models. | https://code.claude.com/docs/en/model-config ; costs page | No figure | Low | Shallower reasoning | Researcher (`/effort`, settings) |
| 3 | `/clear` between unrelated tasks; `/compact <focus>` at natural breaks rather than mid-task; "Compact instructions" section in CLAUDE.md. Resuming an old session then compacting is the most expensive case (cold cache). | costs page ; https://code.claude.com/docs/en/prompt-caching | No figure | Low | Lost context if summary is poor | No |
| 4 | Auto-compact window: `autoCompactWindow`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, `/autocompact` (100K to 1M). `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` keeps a 200K window. | https://code.claude.com/docs/en/model-config | No figure | Low | Earlier compaction loses detail | Researcher (settings) |
| 5 | Keep CLAUDE.md under ~200 lines; move workflow-specific text into skills (loaded on demand). Our CLAUDE.md imports AGENTS.md, so both count. `/usage` recommendations show e.g. "Trim CLAUDE.md, N tokens per request". | costs page | No figure | Low | Rules moved to skills may not be applied | Writer/engineer edit; CLAUDE.md is coordinator-owned, so ask |
| 6 | MCP tool definitions are deferred by default (tool search), so only names enter context; prefer CLI over MCP; disable unused servers via `/mcp`. Adding/removing a server or toggling a tool deny mid-session can invalidate the cache when tool search is off. | costs page ; https://code.claude.com/docs/en/prompt-caching | No figure | Low | None | No |
| 7 | Prompt cache hygiene: pick model and effort at session start; switching model re-reads the whole history uncached; each model has its own cache; subagents get only a 5-minute TTL on a subscription unless `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` / `subagentPromptCacheTtl` (v2.1.242+). A 1-hour TTL has a higher cache-write rate. | prompt-caching page | Docs give no net saving; whether 1h helps plan-limit accounting is unknown | Low | May cost more on short bursts | Researcher (env) |
| 8 | `/usage` (v2.1.222+ on plans): attribution per skill/subagent/plugin/MCP server, `Loops` rows for `/loop` tasks, and recommendations; `f` applies effort ones. Idle `/loop`, goal check-ins and scheduled tasks resend the full context each firing. The hourly experiment cron is therefore a recurring cost. | costs page | No figure | Low | None | No |
| 9 | Hooks that pre-filter output (docs example: grep `ERROR` from a long log instead of reading it). The repo's own scripts (`tools/labq.py`, metrics parsers) should print summaries, not full dumps. | costs page | Docs: "tens of thousands of tokens to hundreds" (illustrative, not measured) | Medium | Over-filtering hides errors | Hook in `settings.json`: researcher |
| 10 | `opusplan` alias: Opus in plan mode, Sonnet in execution. Each plan-mode toggle is a model switch and starts a fresh cache. | model-config and prompt-caching pages | No figure | Low | Cache rebuild on every toggle | Researcher |

Not recommended: agent teams (docs: roughly 7x tokens in plan mode; disabled by default).

### A2. Codex CLI (`~/.codex/config.toml`)

Docs moved to learn.chatgpt.com (developers.openai.com redirects with HTTP 308). Sources:
https://learn.chatgpt.com/docs/config-file/config-sample , https://learn.chatgpt.com/docs/config-file/config-reference ,
https://learn.chatgpt.com/docs/agent-configuration/agents-md . The reference page was read only up to character 100000 of 156747.

| # | Key / practice | What the docs say | Stated saving | Effort | Risk | Approval |
|---|---|---|---|---|---|---|
| 1 | `model_reasoning_effort` ("low/medium/high", levels depend on model; default unset); `plan_mode_reasoning_effort`; `model_verbosity` (low/medium/high, GPT-5 family) | Direct control of reasoning and text output size | Official: none. Third party (unverified, no method): medium to low saves "40-60%" on routine tasks (codex.danielvaughan.com, 2026-06-10, citing others) | Low | Weaker answers | Researcher (config.toml is outside `~/qrl-lab`) |
| 2 | `tool_output_token_limit` (sample value 12000, "tokens stored per tool output"; default not stated) | Caps what one tool output adds to history | No figure | Low | Truncated logs | Researcher |
| 3 | `model_auto_compact_token_limit` (sample 64000; unset uses model defaults). Third-party posts say values above ~90% of the window are ignored and key names differ between posts; check `codex --version` docs before use. | Controls when history is summarised | No figure | Low | Each compaction breaks the cached prefix (third party) | Researcher |
| 4 | `agents.default_subagent_model`, `agents.default_subagent_reasoning_effort`, `agents.max_concurrent_threads_per_session`; `review_model` for `/review` | Cheaper model and effort for spawned agents; fewer parallel threads | No figure | Low | Quality on hard reviews | Researcher |
| 5 | `mcp_servers.<id>.enabled_tools` / `disabled_tools` | Allow/deny list of exposed MCP tools | Third party only: 93-tool GitHub server cut to 3 tools, ~55,000 to ~3,000 tokens per turn (Scalekit "The MCP Tax", May 2026, cited secondhand) | Low | None | Researcher |
| 6 | `project_doc_max_bytes` (default 32768): AGENTS.md chain is embedded in the first turn; files closer to the cwd win; nested AGENTS.md load only along the path | Keep AGENTS.md short; put specialised rules in subdirectories | No figure | Low | Truncation if raised carelessly | Writer edits AGENTS.md; coordinator-owned, so ask |
| 7 | Profiles: separate files under `CODEX_HOME`, selected with `codex --profile <name>` (e.g. a `quick` low-effort profile and a `deep` one) | Matches our quick/review/major roles in `docs/DECISIONS.md` | No figure | Low | None | Researcher |
| 8 | `web_search` default is `"cached"` (OpenAI index); `hide_agent_reasoning` only hides display | Not a token saver; listed so nobody mistakes `hide_agent_reasoning` for one | none | - | - | - |
| 9 | Keep the prefix stable (no timestamps or mid-session AGENTS.md edits) to retain cache hits | Third-party posts only; I did not find an official Codex page on caching | Unknown | Low | None | No |

The GitHub releases page for openai/codex (latest 0.164.0-alpha.12, 22 Oct) carries no release notes on tokens, compaction or caching.

## B. Plugins, skills, MCP servers

### B1. RTK (rtk-ai/rtk) — both sides
- Repo https://github.com/rtk-ai/rtk . Licence: CLI Apache-2.0; `rtk-engine` and `rtk-proxy` BUSL-1.1 (source-available, internal use permitted); `rtk-oss` edition Apache-2.0 only. Last release known from memory: v1.0.1 on 14 Oct 2026 (not re-opened today).
- Saves: the README claims 60-90% reduction on common dev commands, "up to 90% smaller" bash output. It measures only the bash output the agent reads, estimates tokens as bytes/4, and says absolute token numbers are approximate. The whole-bill effect is smaller (self-reported, not independently verified).
- Mechanism: PreToolUse hook rewrites Bash commands (`rtk init -g`, Codex via `rtk init -g --codex`). Read/Grep/Glob bypass it.
- Risks: it rewrites every shell command the agents run, so it interacts with our `sudo_gate.py` PreToolUse hook (order and `updatedInput` conflicts untested); over-compressed test output could hide failures; telemetry is off by default and opt-in; a different crate named "rtk" exists (README says verify with `rtk gain`). Install from the project venv is not possible (Rust binary), so it touches the system.
- Approval: YES (install, new hook).

### B2. Official LSP code-intelligence plugin: `pyright-lsp` — Claude only
- Anthropic-maintained: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/pyright-lsp ; docs https://code.claude.com/docs/en/plugins/code-intelligence . Needs the `pyright-langserver` binary on PATH and `/plugin install pyright-lsp@claude-plugins-official`.
- Saves: docs say a "go to definition" call replaces a grep plus reading several candidate files, and type errors are reported after edits without running a compiler. No figure. Plugin skills/hooks append after the conversation and keep the cache; the LSP tool is one added tool definition.
- Risks: language server memory grows while indexing; false positives in monorepos; our code spans several worktrees (`code/`, `code-tuning*`), which may confuse root detection (untested). Pyright must be installed (pip/npm), outside the project rules unless in the venv.
- Approval: YES (plugin and package install).

### B3. Considered and not recommended
- zilliztech/claude-context (MIT, Zilliz, no GitHub releases): README claims "~40% token reduction under the condition of equivalent retrieval quality"; method not shown on the page. Needs Node 20+, an embedding provider (default OpenAI API key; Ollama listed) and a vector DB (Zilliz Cloud key or self-hosted Milvus). Rule 6 forbids keys; the fully-local option was not confirmed. NOT NOW.
- claude-mem, Serena: see 2026-10-17 memory (cloud paths / GPL-3.0 with shell tool). Unchanged.
- Skills: Anthropic's own advice is to move task-specific instructions from CLAUDE.md into skills. This is a practice (A1 #5), not an install.

## C. Local VM options (cores 4-7 only)

- Code search: Claude Code's Grep/Glob tools and `rg` already do exact search locally at zero token cost; the saving comes from asking specific questions and delegating search to a Haiku `Explore` subagent (A1 #1), not from a new index. A symbol-level LSP (B2) is the only code-intelligence route with an official source.
- Local small LLM for summarising (llama.cpp or Ollama): technically available. Ollama v0.40.8 (21 Oct) has `ollama launch claude` and `ollama launch codex` per its release notes (https://github.com/ollama/ollama/releases). llama.cpp latest tag b11819 (22 Oct, pre-release flag shown; https://github.com/ggml-org/llama.cpp/releases). Licences not shown on those pages.
  Quality risk (my assessment, not measured): summaries from a small local model can drop or invent numbers, which conflicts with golden rule 2 for anything that reaches the paper. CPU inference on 4 cores is slow, and routing the coordinator itself through a local model would change the research assistant's behaviour. Acceptable only for non-evidential chores (e.g. log digests that a script cannot do), and only after the researcher approves a tested model. NOT RECOMMENDED now.
- Scripts instead of LLMs: the project rule already says repetitive work goes to scripts. Extend `tools/labq.py pending` style outputs to print counts and one-liners.

## Ranking (top 5)

1. Per-subagent model and effort, Explore overridden with Haiku, medium effort kept (Claude A1 #1-2; Codex A2 #1, #4). Both sides. Official docs, no install. Saving unquantified by the docs.
2. Context hygiene: `/clear` at task boundaries, `/compact` at breaks, CLAUDE.md/AGENTS.md trimmed, `/usage` recommendations and Loops rows checked, hourly cron cost reviewed (A1 #3-5, #8; A2 #6). Both sides. No install.
3. Codex `config.toml` tuning: `tool_output_token_limit`, `model_auto_compact_token_limit`, `enabled_tools`/`disabled_tools`, profiles (A2 #2, #3, #5, #7). Codex. Researcher edits the file.
4. RTK shell-output filter (B1). Both sides. Self-reported 60-90% on bash output only; needs approval; test against `sudo_gate.py` first.
5. Official `pyright-lsp` plugin (B2). Claude. Needs approval; saving unquantified; test on one worktree first.

Not ranked: local LLM, claude-context.

## Open questions for the researcher
1. Do you want the engineer to read the five `.claude/agents/*.md` files and propose exact `model`/`effort` lines (no settings edit)?
2. Approve a trial of RTK on Claude only, for one session, with before/after `/usage` numbers?
3. May I check the installed Codex version's `config.toml` key names (`codex --help`) before you change limits? Third-party posts disagree on names.

## Sources
- https://code.claude.com/docs/en/costs
- https://code.claude.com/docs/en/prompt-caching
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/model-config
- https://code.claude.com/docs/en/mcp (tool-search section beyond char 100000 not read)
- https://code.claude.com/docs/en/plugins/code-intelligence
- https://learn.chatgpt.com/docs/config-file/config-sample
- https://learn.chatgpt.com/docs/config-file/config-reference
- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://github.com/openai/codex/releases
- https://github.com/rtk-ai/rtk
- https://github.com/zilliztech/claude-context
- https://github.com/ollama/ollama/releases
- https://github.com/ggml-org/llama.cpp/releases
- https://codex.danielvaughan.com/2026/06/10/codex-cli-token-consumption-diagnosis-reduction-quota-drain-practitioner-toolkit/ (third party)
