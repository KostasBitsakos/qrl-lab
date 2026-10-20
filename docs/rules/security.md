# Security and settings — active rules

Read-only research directories, no secrets, no push, no kubectl writes, no installs outside the venv, no purchases
or API keys: see AGENTS.md «Rules» and CLAUDE.md golden rules 4–6. Approvals: PLAN §6.

- Never overwrite settings the researcher or tools changed: merge edits into `.claude/settings.json`, keep plugins at user scope, put project-only toggles in `.claude/settings.local.json`. (2026-10-16, handoff standing rule 4)
- Approvals are enforced in the launcher; codex mcp-server dropped; acceptance tests A1–A8. (2026-10-16, D12; PLAN §13 D12)
- Bringing the Kubernetes cluster up needs per-item approval. (2026-10-16, handoff §1; PLAN §13 D11)
- A newer git from `ppa:git-core/ppa` (optional fix for pyright-lsp) needs sudo and per-item approval. (2026-10-16, handoff §1)
- Environment facts (VM, access, tool versions): archive.md, 2026-10-16 «environment facts».
