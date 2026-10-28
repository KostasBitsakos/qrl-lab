# Acting Codex deputy

During a researcher-approved handover while Claude is unavailable, `tools/deputy.py` handles dashboard messages
as `codex-deputy`, with the Codex CLI's `workspace-write` sandbox and `approval_policy="never"`. It can implement
the requested project work inside `~/qrl-lab`. Existing rules and approvals still apply: experiment/model/run
changes require explicit scope approval, launches use `tools/launch_run.py` and its approved frozen spec, and
sudo, real-cluster mutations, QPU jobs and external publication retain their separate approval boundaries.
The deputy does not execute sudo, cluster mutations or QPU jobs. This is an application guardrail, not a new
OS security boundary; it does not override project policies or existing approvals.

The message being handled supplies `req_model` and `req_effort`; later or earlier thread messages cannot override
them. Supported models are the account's visible `codex debug models` choices: `gpt-6-luna`, `gpt-6.1-sol`,
`gpt-6-sol`, `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`. Efforts are `low`, `medium`, `high`,
`xhigh`, `max` and `ultra`; the two luna models do not support `ultra`. `med` remains an alias for `medium`.
Legacy Claude selections map to Codex: `haiku` → luna/low, `sonnet` → 6.1-sol/medium, `opus` → astra/high.
An explicit effort overrides those defaults. The legacy `codex` selection uses automatic routing, which stays
bounded to 6-luna/low for short simple messages and 6.1-sol/medium otherwise. Explicit models default to low for
luna, high for astra, medium otherwise. Automatic routing with an explicit `ultra` effort uses 6.1-sol, which
supports it. Invalid choices fail validation rather than entering CLI arguments.

CLI discovery checks PATH, then executable nvm installations in numeric version order; it supplies an executable
Node runtime even when the watchdog has a clean PATH. A missing CLI/Node, timeout, empty answer or nonzero CLI exit
sets the message to `failed`, visibly asks for a Codex retry, and records the outcome. Ordinary edits are not
automatically deferred to Claude. A response ending in `NEEDS_APPROVAL: yes` sets `waiting_approval` and adds the
specific approval boundary to `.lab/deputy_queue.jsonl`. The old `NEEDS_EXECUTION:` marker is accepted for existing
clients, but new prompts use the precise approval marker.

Every action writes role/model/effort/task start and end records to `.lab/events.jsonl` and the database audit.
Claude should read `.lab/deputy_handoff.md` (concise per-action outcomes, checks and next steps), its structured
companion `.lab/deputy_handoff.jsonl`, and any approval queue entries before resuming. Each dashboard reply also
labels its actual model and effort. When Claude returns, the deputy posts a stop note and consumes the handover
approval; no new actions run under that consumed approval.
