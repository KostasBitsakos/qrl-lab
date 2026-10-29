---
description: Awake/asleep rules when Claude or Codex hits its limit - full coordination, solo notes, single-purpose branches, joint merge review
---
# Handoff when one coordinator "sleeps" (researcher, 2026-10-23)
Convention: **awake** = the coordinator (Claude or Codex) that currently has usage left and works; **asleep** = the one that hit its usage
limit and cannot work until its reset.
1. The awake one takes FULL coordination and execution, with write rights inside ~/qrl-lab (answers the researcher, runs approved
   experiments via tools/launch_run.py, edits code and lab files). Approvals that were always required stay required (new budgets/sandboxes,
   sudo, real cluster, QPU, installs, git push).
2. The awake one keeps detailed notes for a joint review (.lab/codex-handoff/<who>_solo_<date>.md): what it did, produced, tested, why,
   with pointers (commits, run ids, summaries).
3. Agent strength follows the existing criteria per task (docs/rules/models.md, docs/DECISIONS.md, docs/agent_routing.json).
4. Experiments and code: working alone, the awake one opens NEW single-purpose branches from our existing branches (both the Claude and
   the Codex versions) and works only there, with notes. When both are awake again: first a discussion/analysis of everything the awake one
   did and verified; they agree what to keep in the original branches (merge all, some, or none); then they delete the single-purpose
   branches (and their worktrees) created during the solo period.
The deputy request (tools/deputy.py BODY) states these rules; the sleeping side hands off before stopping (queue + handoff note).
5. Same rules for both: when Codex coordinates it works under exactly the same rules and information as Claude
   (AGENTS.md, prompts/coordinator.md, docs/STATE.md, docs/rules/*, docs/DECISIONS.md, skills in .claude/skills) and in every
   role Claude takes. Every solo action goes to the notes of rule 2; on Claude's return both review them and agree what stays. (2026-10-29, M-20261029-028)
