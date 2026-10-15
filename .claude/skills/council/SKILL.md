---
name: council
description: Structured Claude–Codex discussion (blind proposals, cross-critique, one revision, synthesis into a decision card) for decisions that change the research - new model architectures or quantum candidates, simulator or reward changes, workloads, baselines, publication claims. Use before proposing any of these to the researcher.
---

# Council: Claude and Codex agree on the best idea

Goal: two independent minds, one decision card for the researcher. Cap the cost: 2 rounds unless the researcher asks for more.

## 0. Brief
Create `.lab/council/<id>/brief.md` (id = `C-YYYYMMDD-NN`): the question, constraints (PLAN §1, §6, deadline),
the evidence available with file pointers, and what "better" means (metrics from PLAN §9). Under 300 words.

## 1. Blind proposals
- Write **your own** proposal to `.lab/council/<id>/claude.md` **before** reading Codex's.
- Ask Codex for its proposal on the same brief, read-only:
  - Preferred: MCP tool `codex` (from `codex mcp-server`). Check its input schema first; use a read-only sandbox,
    cwd `~/qrl-lab`, the model from the table below. Keep the returned thread id.
  - Fallback: `/codex:rescue --fresh --wait --model <m> --effort <e> <prompt>`.
  - Prompt: "Read AGENTS.md and the brief at <path>. Give your proposal: idea, evidence, main risk, and the
    experiment that would prove you wrong. Under 400 words."
- Save Codex's answer to `.lab/council/<id>/codex.md`.

## 2. Cross-critique and revision
- Send Claude's proposal to Codex (`codex-reply` on the same thread, or `/codex:rescue --resume`):
  "Critique this proposal concretely, then give your revised proposal."
- Write your critique of Codex's proposal and your revision to `.lab/council/<id>/claude-r2.md`.

## 3. Synthesis → decision card
Write `.lab/council/<id>/card.md`:
- **Recommendation** (one paragraph) and the options the researcher can choose.
- **Where both agree** / **where they disagree** (with each side's argument in one line).
- **Cost**: CPU-hours, QPU seconds, engineering days, tokens (rough).
- **Risks** and the cheapest experiment that settles the disagreement.
Then file it with skill `ask-user` (kind `proposal`, blocking if work depends on it).

## Models
| Item | Claude side | Codex side |
|---|---|---|
| normal | coordinator as is | GPT-6 Sol, effort medium |
| major (architecture, simulator/reward, publication gate, final claims) | coordinator, effort high | GPT-6 Astra, effort high |
Use the model ids your Codex account actually lists (`/model` in Codex). Log the choice.

Never present a council outcome as a decision. The researcher decides.
