# Changelog

## v0.2 — 2026-10-16
Inputs: ChatGPT handoff "QRL_LAB_HANDOFF_FINAL_DASHBOARD_SETUP_2026-10-16", the official Codex plugin source
(v1.0.6), Claude Code docs (Remote Control, monitors, permission modes, memory).

Adopted from the ChatGPT review
- Removed `.mcp.json` (`codex mcp-server` is deprecated since codex-cli 0.149.1). Codex only through the official
  plugin.
- Approvals enforced at the execution boundary: `tools/launch_run.py` (approved request + frozen spec hash +
  attempts + kube context + wall-clock limit + stop requests).
- SQLite for messages, requests, runs and audit (`tools/labdb.py`), with atomic IDs and validated transitions;
  JSONL kept only for hook events.
- Dashboard with a tested two-way path (message → delivery → take → visible reply → status), not a JSONL viewer.
- Acceptance tests A1–A8 (PLAN §12) before claiming the system works.
- AGENTS.md now loaded by Claude (`@AGENTS.md` in CLAUDE.md).

Done differently from the ChatGPT suggestions, with reasons
- Codex is called through the plugin's own `codex:codex-rescue` subagent, not by scripting the companion runtime:
  outside the plugin the runtime keeps its state in /tmp, which would break `/codex:status` and `--resume`.
- `/codex:review` and `/codex:adversarial-review` cannot be called by the model (`disable-model-invocation`), so
  model-initiated reviews go through `codex-rescue` with a read-only prompt; the researcher can still type them.
- The monitor polls the database instead of tailing a JSONL file, so it can re-deliver after a restart and the
  dashboard can show online/offline from its heartbeat.

New
- `dashboard/app.py` (8 tabs, Greek UI), `.streamlit/config.toml` (localhost only), `tools/setup_dashboard_env.sh`.
- `tests/test_lab.py` (T0: plumbing, decisions, launcher, hook, dashboard via Streamlit AppTest).
- Skill `inbox`; skills `council` and `ask-user` rewritten for the plugin and the database.
- `settings.json`: auto permission mode; read-only access to the original directories; deny rules for kubectl
  mutations, Helm, edits to originals, `.lab/lab.db`, `.lab/specs/`, `sqlite3`, researcher-only CLI commands;
  `SessionStart` and `Notification` hooks (permission-wait banner).
- `docs/deadlines.json` (CCGrid 2027, verified CFP). PLAN F7: the Kubernetes API server is down.
- `sandbox/toy_run.py`, `sandbox/toy_spec.json` for acceptance test A5.

## v0.1 — 2026-10-15
Initial kit: PLAN.md, CLAUDE.md, AGENTS.md, five subagents, `council` and `ask-user` skills, hooks, lab-bridge
monitor, sanity script, setup scripts.
