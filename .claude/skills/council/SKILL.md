---
name: council
description: Structured Claude–Codex discussion (blind proposals, cross-critique, one revision, decision card) for decisions that change the research - quantum candidates, model architecture, simulator or reward, workloads, baselines, publication claims - and for researcher proposals that would change any of these.
---

# Council: Claude and Codex look for the best idea together

Goal: two independent views, one decision card for the researcher, disagreements kept visible. Two rounds maximum
unless the researcher asks for more. Codex calls run **one at a time** (`--resume` continues the latest thread).

## 0. Brief
`.lab/council/<C-id>/brief.md` (id `C-YYYYMMDD-NN`): the question, constraints (PLAN §1, §6, deadline), evidence with
file pointers, what "better" means (PLAN §9 metrics). Under 300 words. Link the dashboard thread if there is one.

## 1. Blind proposals
- Write **your** proposal to `.lab/council/<C-id>/claude.md` **before** reading Codex's.
- Ask Codex with the Agent tool, `subagent_type: "codex:codex-rescue"`, prompt:
  `--fresh --model <model> --effort <effort> READ-ONLY: research and review only, do not edit files. Read AGENTS.md
  and .lab/council/<C-id>/brief.md. Give your proposal: idea, evidence, main risk, and the experiment that would
  prove you wrong. Under 400 words.`
- Save the answer verbatim to `.lab/council/<C-id>/codex.md`.

## 2. Cross-critique and revision
- Codex: `--resume --model <model> --effort <effort> READ-ONLY: ... Read .lab/council/<C-id>/claude.md. Critique it
  concretely, then give your revised proposal.` → save to `codex-r2.md`.
- You: critique Codex's proposal and revise yours → `claude-r2.md`.

## 3. Decision card
`.lab/council/<C-id>/card.md`: **Recommendation** and the options; **Where both agree**; **Where they disagree**
(one line per side); **Cost** (CPU-h, QPU-s, engineering days, tokens); **Risks** and the cheapest experiment that
settles the disagreement. Then:
- file it with skill `ask-user` (`--kind proposal --scope research --link .lab/council/<C-id>/card.md`, blocking if
  work depends on it);
- if a dashboard thread started it, post Codex's final view as `--author codex --kind contribution` and your
  summary as coordinator in that thread.

## Models
| Item | Codex |
|---|---|
| normal | `--model gpt-6-sol --effort medium` |
| major (architecture, simulator/reward, publication gate, final claims) | `--model gpt-6-astra --effort high` |
Use model ids that the researcher's Codex account actually lists; if a call fails on the model, retry once without
`--model` and say so in the card. Never present a council outcome as a decision: the researcher decides.
