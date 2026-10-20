# Accepted decisions — dated log

Newest first, one or two lines per decision. The rules themselves live in [`docs/rules/`](rules/README.md)
(index, precedence, contradiction-check procedure, resolved conflicts). Codex role table: [`docs/rules/models.md`](rules/models.md).
Before adding a decision, follow the procedure in `docs/rules/README.md` (M-20261020-021).

- 2026-10-20 — M-20261020-027 (researcher): engineer on Opus only until the loop ends 2026-10-21; then routing by resources/task as before. → rules/models.md
- 2026-10-20 — M-20261020-025 (researcher): conflicts C1–C6 resolved as proposed in M-20261020-024 (later entries win; calibration paused; W1 deferred; closeness = progress indicator; engineer Opus for research code). → rules/README.md
- 2026-10-20 — R-20261020-001 (researcher): DECISIONS.md split into `docs/rules/`; conflicts C1–C6 listed there, awaiting researcher.
- 2026-10-20 — M-20261020-021 (researcher): contradiction check before adding rules; several cooperating md files allowed. → rules/README.md
- 2026-10-20 — M-20261020-015 (researcher): wider design latitude (inputs, reward, layers; sim need not match the real cluster), core of the work kept. → rules/experiments.md (C1, C2, C3)
- 2026-10-20 — M-20261020-013 (researcher): env variants allowed; tuning-loop implementation by engineer with opus, cross-checked. → rules/experiments.md, rules/models.md (C1, C4, C6)
- 2026-10-19 — M-20261019-048 (researcher): focus on reproducing the DInos picture; no quantum for now. → rules/research.md, rules/paused.md
- 2026-10-19 — M-20261019-044 (researcher): Sofia paper as a source; DInos wins on disagreement. → rules/research.md
- 2026-10-19 — M-20261019-037 (researcher): stronger models for the tuning loop, until 2026-10-21. → rules/models.md
- 2026-10-19 — M-20261019-029 (researcher): per-cycle closeness report. → rules/experiments.md (C5)
- 2026-10-17 — M-20261017-137 (researcher): tuning sandbox on `dinos-tuning` with guardrails. → rules/experiments.md (C1, C5)
- 2026-10-17 — R-20261017-018: SLO = 2 × single-pod p95 at 50 % load from calibration stage B. → rules/paused.md (C3)
- 2026-10-17 — R-20261017-017, council C-20261017-02: training reward = researcher's DInos reward via frozen adapter; classical scope; D5 paused. → rules/experiments.md, rules/paused.md (C2, C3)
- 2026-10-17 — M-20261017-114/117: venues always carry CORE tier and last-3 acceptance rates. → rules/research.md
- 2026-10-17 — M-20261017-005/006/007: mutual Claude/Codex fallback; limit messages and sudo tab in dashboard; simulation first, W0 then W1. → rules/models.md, rules/dashboard.md, rules/experiments.md (C4)
- 2026-10-17 — R-20261017-014: bounded exploratory W0 study; HPA reverse-engineered (M-20261017-068). → rules/archive.md, rules/experiments.md
- 2026-10-17 — R-20261017-011: IBM Quantum in this paper, inference only. → rules/paused.md
- 2026-10-17 — R-20261017-008 (D3): workloads W0+W1 train, W2 test, W3 adaptation. → rules/experiments.md (C4)
- 2026-10-17 — R-20261017-007 (D8): F1 not mentioned in the paper; no DInos sim numbers as comparison points. → rules/research.md
- 2026-10-17 — R-20261017-006 (D5): screen QC4 + QC1 (paused). → rules/paused.md
- 2026-10-16 — R-20261016-018: calibration with a stateless Deployment in namespace `qrl-calib` (paused). → rules/paused.md
- 2026-10-16 — R-20261016-016 + M-20261016-078: model routing, Codex roles, more OpenAI agents. → rules/models.md (C6)
- 2026-10-16 — R-20261016-013 (D2): Sim v2 design, option 1 of C-20261016-01. → rules/experiments.md, rules/archive.md
- 2026-10-16 — R-20261016-001 (D9): IBM account exists; no jobs for now. → rules/paused.md
- 2026-10-16 — handoff standing rules 1–5 and environment facts (D13). → rules/dashboard.md, rules/models.md, rules/security.md, rules/archive.md
- 2026-10-16 — D12: ChatGPT handoff adopted. → rules/security.md, rules/archive.md
