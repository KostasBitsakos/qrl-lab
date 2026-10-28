# Plan: Codex deputy coordinator handover

Scope: codex-deputy
Depth: tree 2
Mode: orchestrated

## Contract

- Interfaces: dashboard messages persist `req_model`/`req_effort`; deputy honors them; live views derive coordinator identity from health/events, never a hard-coded provider.
- Ownership: three disjoint leaves below; experiment leaf may summarize completed c18 data but must not launch/stop/mutate runs or model code.
- Dependencies: leaves 1.1.1–1.1.3 are independent; root integration follows all three.
- Host launch mode: Codex native subagents.
- Wave policy: launch all three leaves together, maximum three child agents.
- Toolchain: Python 3, project `.venv`, bash-compatible checks, repository root `/home/ubuntu/qrl-lab`.
- Conventions: Greek researcher-facing text; explicit Codex role/model/effort; preserve existing DB compatibility.
- Manual review: root agent reviews dashboard semantics, deputy write authority boundaries, and experiment non-interference.

## Current contract inventory

Contract revision: 2. Revision 2 adds the researcher's 21:50 UTC branch-isolation, paired-agent, lessons and cost-routing requirements.

| ID | Required outcome or constraint | Owner | Observing gate or manual review | Disposition | Revision |
|---|---|---|---|---|---|
| C1 | Chat composer exposes all supported Codex models and effort levels | leaf-1.1.1 | leaf-1.1.1:G1 | ACTIVE | 1 |
| C2 | Agents/brain/race show the actual active coordinator, role and model | leaf-1.1.1 | leaf-1.1.1:G2 | ACTIVE | 1 |
| C3 | Deputy runs with write capability inside approved project rules and honors requested routing | leaf-1.1.2 | leaf-1.1.2:G1,G2 | ACTIVE | 1 |
| C4 | Missing CLI produces a clear recoverable dashboard state, not the old misleading queue message | leaf-1.1.2 | leaf-1.1.2:G3 | ACTIVE | 1 |
| C5 | Every deputy action is visible in the event/audit trail for Claude handoff | leaf-1.1.2 | leaf-1.1.2:G4 | ACTIVE | 1 |
| C6 | Completed c18 state and exact next loop action are independently audited without touching live experiments | leaf-1.1.3 | leaf-1.1.3:G1,G2 | ACTIVE | 1 |
| C7 | Existing experiments, drivers, branches and results are not altered by UI/fallback work | root | root:G3 manual review | ACTIVE | 1 |
| C8 | Outstanding researcher requests for the Agents tab are inventoried and either implemented or explicitly handed off | leaf-1.1.1 | leaf-1.1.1:G3 | ACTIVE | 1 |
| C9 | Researcher receives corrected dashboard reply after verification | root | root:G4 manual review | ACTIVE | 1 |
| C10 | Any continued loop work uses two new branches/worktrees descended separately from the two current competing branches | leaf-1.2.1, leaf-1.2.2 | node-1.2:N2 | ACTIVE | 2 |
| C11 | Each new branch receives one best-model architect/implementer and a separate best-model reviewer under the existing experiment protocol | leaf-1.2.1–1.2.4 | node-1.2:N1,N3 | ACTIVE | 2 |
| C12 | Each branch records hypotheses, changes, failures, results and reusable lessons in new isolated files for later Claude/Codex merge review | leaf-1.2.1–1.2.4 | node-1.2:N4 | ACTIVE | 2 |
| C13 | No new experimental run uses cores or budget until current c18 is complete and reconciled; design/code may proceed in isolated worktrees | root, node-1.2 | node-1.2:N5 manual review | ACTIVE | 2 |
| C14 | Routine work uses Luna/low; expensive models are reserved for experiment architecture, implementation and consequential review | root | root:G5 manual review | ACTIVE | 2 |

## State vocabulary

Leaf states: WAITING, READY, IN-FLIGHT, VERIFIED, ABANDONED. Branch states: OPEN, VERIFIED, ABANDONED.

## Tree

- 1 Codex deputy handover .............. GATES.md
  - 1.1 Implementation and audit ........ gates/node-1.1.md
    - 1.1.1 Dashboard routing and identity ...... gates/leaf-1.1.1.md
    - 1.1.2 Deputy execution and reliability .... gates/leaf-1.1.2.md
    - 1.1.3 Experiment-loop audit ............... gates/leaf-1.1.3.md
  - 1.2 Isolated Codex continuation ...... gates/node-1.2.md
    - 1.2.1 Primary-branch architect ............ gates/leaf-1.2.1.md
    - 1.2.2 Astra-branch architect .............. gates/leaf-1.2.2.md
    - 1.2.3 Primary-branch reviewer ............. gates/leaf-1.2.3.md
    - 1.2.4 Astra-branch reviewer ............... gates/leaf-1.2.4.md

## Leaf dispatch table

| Leaf | Owns | Needs | Tier | Planned wave | State |
|---|---|---|---|---|---|
| 1.1.1 | dashboard/app.py, tools/agent_models.py, tools/race_view.py, tools/brain_view.py, tests/test_agent_models.py, tests/test_brain_view.py, tests/test_dashboard_codex_routing.py, docs/agents_tab_audit.md | - | judgment | 1 | IN-FLIGHT |
| 1.1.2 | tools/deputy.py, tools/labdb.py, tests/test_lab.py, tests/test_deputy_write.py, docs/deputy_handoff.md | - | judgment | 1 | IN-FLIGHT |
| 1.1.3 | .lab/codex-handoff/c18_audit.md, .lab/tuning/cycles/c18_rung2.md | - | judgment | 1 | VERIFIED |
| 1.2.1 | code-tuning-codex/**, .lab/tuning/codex-branches/primary/design.md, .lab/tuning/codex-branches/primary/lessons.md | 1.1.3 | judgment | 2 | READY |
| 1.2.2 | code-tuning-astra-codex/**, .lab/tuning/codex-branches/astra/design.md, .lab/tuning/codex-branches/astra/lessons.md | 1.1.3 | judgment | 2 | READY |
| 1.2.3 | .lab/tuning/codex-branches/primary/review.md | 1.2.1 | judgment | 3 | WAITING |
| 1.2.4 | .lab/tuning/codex-branches/astra/review.md | 1.2.2 | judgment | 3 | WAITING |

## Status log

Events are appended to `.unlazy/codex-deputy/status.log`.
