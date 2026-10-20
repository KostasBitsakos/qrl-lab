# Rules index

The accepted decisions of `docs/DECISIONS.md` (dated log) are kept here as active rules, split by topic
(researcher, M-20261020-021; restructure approved in R-20261020-001).

| File | Content |
|---|---|
| [models.md](models.md) | model routing, Claude/Codex roles, fallback |
| [experiments.md](experiments.md) | simulator, reward, workloads, tuning loop, seeds |
| [research.md](research.md) | paper claims, sources, venues, focus |
| [dashboard.md](dashboard.md) | dashboard channel and dashboard changes |
| [security.md](security.md) | settings, read-only paths, approvals |
| [paused.md](paused.md) | paused items (not dropped) with their revive condition |
| [archive.md](archive.md) | superseded entries and history/environment facts, verbatim, newest first |

## Precedence
- A later dated decision wins over an earlier one.
- CLAUDE.md / AGENTS.md safety rules always win.
- Items marked **CONFLICT — awaiting researcher** are not resolved by the date rule: an earlier and a later entry
  disagree and the text does not say which wins. They are listed below until the researcher decides.

## Procedure before adding a rule (researcher, 2026-10-20, M-20261020-021)
Before adding anything to the rule/decision md files (DECISIONS.md, PLAN.md, CLAUDE.md, AGENTS.md, skills, and these
split files), check it against what is already written. If it contradicts or narrows an earlier entry, report the
conflict to the researcher (dashboard, with both texts and file:line) and wait for approve/reject before writing.
Splitting the rules into several md files that reference each other is allowed if it keeps them clearer.
Format used in these files: one line per rule, with date + source id (M-/R-/D-) and expiry if any.

## Open conflicts (awaiting researcher)
- **C1** Tuning sandbox guardrails (2026-10-17, M-20261017-137): "tune agents (...), not the simulator/reward/SLO (those
  change only from calibration evidence)" vs 2026-10-20 M-20261020-013 (env variants allowed) and M-20261020-015
  (inputs, reward, layers, simulator need not be accurate to the real cluster). → experiments.md
- **C2** Reward = researcher's DInos reward through a frozen adapter (2026-10-17, R-20261017-017) vs M-20261020-015
  (council may change the reward). → experiments.md
- **C3** "Realism: literature review + calibration stage B before any final result" (R-20261017-017) and "training under
  reward=dinos waits for the stage-B SLO" (R-20261017-018) vs M-20261020-015 ("the simulator need not be accurate to the
  real cluster") and the calibration being paused. → experiments.md, paused.md
- **C4** Workloads W0 = researcher's sine + noise + spike, then W1 (2026-10-17, M-20261017-005/006/007; R-20261017-008)
  vs M-20261020-013 (variants: more sinusoid noise, stronger/more spikes) and M-20261019-048 (goal now: sinusoidal
  input only). → experiments.md
- **C5** "Absolute numbers of the old simulator (F1) are not a target; the target is the same qualitative ranking and
  curves" (M-20261017-137) vs the per-cycle closeness % that scores DERP and DInos magnitudes against 2.2e5 / 3.8e6
  (M-20261019-029). → experiments.md
- **C6** Routing "engineer → Sonnet; Opus only for simulator or circuit design" (R-20261016-016) vs "implementation
  work in the tuning loop goes to the engineer with `model: opus`" (M-20261020-013, no expiry stated), while the related
  M-20261019-037 expires 2026-10-21. → models.md
