# Agents tab request audit — 2026-10-21

Scope: researcher messages in `.lab/lab.db`, read with SQLite `mode=ro`, and the event consumers in
`dashboard/app.py`, `tools/agent_models.py`, `tools/brain_view.py`, and `tools/race_view.py`.
Message status alone is not treated as proof of implementation. This audit covers Agents requests and their
adjacent routing controls; experiment work is outside this change.

| Researcher message | Requested behavior | Implementation or precise handoff |
|---|---|---|
| M-20261016-067 | Show every ChatGPT role used for each task, rather than one generic Codex | Agents has separate Codex quick/reviewer/researcher/architect/deputy/engineer roles. `agent_models.resolve` uses actual event model, matching explicit log, matching tool call, then clearly marked frontmatter default; absent evidence says unknown. Bare plugin events remain generic when the role was not logged. |
| M-20261017-005/006; M-20261016-021 | Temporary Codex coordination during Claude limits, Codex workers, accurate outage notices | Current coordinator identity now comes from deputy start/stop model/effort and provider health; Agents, race and brain use the same resolver. No historical Claude model is shown as current during an outage. Execution authority, routing and handoff trail are owned by `tools/deputy.py` / `docs/deputy_handoff.md` in the sibling runtime change. |
| M-20261017-007 | One meaningful task label beside timeline dots, once for each shared task; 1980s car race | Existing `race_view.annotate` assigns one label per task group, and the timeline writes it beside the final point of the group. Race renderer provides animated pixel cars. Kept intact. |
| M-20261017-012 item 2 | Wide enough race track for all agents | Existing race uses a lane per run, a scrollable component and adaptive track sizing. Current deputy is rendered once as coordinator, avoiding duplicate live cars. At most 16 worker lanes are shown (active first), plus coordinator; unlimited simultaneous lanes are not claimed. |
| M-20261017-059 | More lateral movement with more activity; obstacles and dodging when tasks encounter trouble | Existing `race_view.derive` computes movement from logged activity and obstacles from failed/retried/slow tasks and the correct provider health. Animation stays CSS-based. Codex coordinator now checks Codex health, so Claude's limit does not falsely obstruct it. |
| M-20261017-064 | Working agents must move, idle ones must stop | Existing running cars move; idle/finished cars park. Deputy coordinator is now running only between a recent actual start and its stop; a Claude tool event cannot make the Codex deputy look busy after it finishes. |
| M-20261017-073 | Sidebar brain: visible agent neurons, brief message edges, stable refresh and tabs | Existing brain derives activity and pulses from real starts/stops/tools/posts. Coordinator labels now show actual provider, role, model and effort; both compact and expanded brain use the resolver. `codex-engineer` is a distinct neuron. Existing fragment refresh, tab query persistence and home logo remain in place. |
| M-20261017-094 | Two words describing coordinator/worker task on the cars | Existing `race_view.two_words` derives descriptions from task text. Deputy coordinator now supplies its actual logged task instead of stale Claude tool text. |
| M-20261021-014/016 | Remove fixed Sonnet/Claude assertions; display actual model and role per task | Existing per-task resolver retained. Current coordinator card and race now use observed deputy model/effort and role, with no fixed Claude/Πάρις coordinator label. Task table keeps separate role/model/effort columns; fixed labels name roles only. |
| M-20261021-049 | Explain why only two Opus cars appear | M-20261021-050 explains that experiment processes are not agent sessions. Race continues to reflect logged agent work rather than inventing cars for simulator processes. New Codex implementation work is represented by the explicit `codex-engineer` role. |
| M-20261021-063/066 | Codex must appear as temporary coordinator everywhere, including “Now,” timeline and race | Implemented shared identity in card, brain and race; timeline labels are provider-neutral for the historical main-session lane and have a separate codex-deputy lane. Historical Claude activity is not relabeled Codex. The current card shows actual provider, role, model and effort. Unknown stays explicit when no deputy start exists. |
| M-20261021-075; prior promise M-20261021-074 | Expose available Codex models and efforts in composer; do not defer UI work as read-only | Composer now includes all seven visible models reported by the VM's `codex debug models`: gpt-6-luna, gpt-6-sol, gpt-6.1-sol, gpt-6-astra, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna. Efforts are low/medium/high/xhigh/max, plus ultra for non-luna models. Switching models normalizes invalid old widget selections. Claude/auto and generic Codex remain; legacy `med` is preserved. Text and voice both pass the same selected fields to LabDB. Runtime execution and logging are covered by the sibling change. |

Adjacent requests with remaining work outside this leaf's ownership:

| Source | Existing behavior and precise handoff |
|---|---|
| M-20261019-019, Architecture tab routing overrides | `tools/topology_view.py` still defines four Codex models and only low/medium/high, independently of the composer. Owner of topology controls should reuse the verified seven-model catalogue and model-specific efforts, preserve `docs/agent_routing.json` compatibility, and extend `tests/test_topology_view.py`; this audit does not claim those controls are upgraded. |
| M-20261021-016, usage rings and free offers | Sidebar already uses `usage_limits` for Claude/Codex usage windows and resets and an offers catalogue. This change does not independently validate provider quota availability or free offers; absence of live evidence must remain unknown. |
| M-20261021-063, automatic Codex-only dispatch during Claude exhaustion | Dashboard is an observer and does not itself launch agents. Deputy prompt/routing policy and audit logging belong to runtime; actual task scheduling still requires explicit logged agent calls. No UI display is evidence that such a call happened. |

Verification: focused tests exercise every model/effort pair through an isolated DB, legacy routing, real composer
submission and model switching in Streamlit AppTest, Codex coordinator card rendering, deputy running/stopped states,
Claude recovery, unknown identity, unrelated Codex workers, and compact/full brain plus race rendering. Existing
`tests/test_lab.py` supplies broader task labels, race animation/obstacles, tab persistence and dashboard regression
coverage. No experiment, driver, run specification or result was changed by this leaf.
