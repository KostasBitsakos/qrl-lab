---
name: tutorials-request
description: "Researcher wants conceptual tutorials on his WORK (models, k8s, Redis, simulations, related work), not on code — readable by him and others"
metadata:
  node_type: memory
  type: project
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-22T19:36:59.220Z
---

Κώστας, 2026-10-22 (M-20261022-057/059): at some point he will ask for detailed, understandable tutorials about his work — DInos/Dinos models, DDQN/LSTM/transfer, Kubernetes, Redis, the simulations, related work — for himself and other readers. NOT code tutorials.
**Why:** to understand and share the research; no plugin helps materially (docs/tutorial_tools_2026-10-22.md).
**How to apply:** when he asks, write docs/tutorial_style.md (audience, goals, intuition before formulas, one diagram per idea, real examples with run-id pointers, sources), use the writer agent on a strong model, then a fresh-agent "beginner" read test + Codex technical check; format pending his answer (proposed: shareable HTML page). Related: [[next-cycle-baseline-poisson]].
- tutorial Q&A file: ~/qrl-lab/docs/tutorial.md — append every conceptual question the researcher asks (M-20261023-023).

Update 2026-10-29 (M-20261029-159): tutorials are now OWNED BY CODEX (spawn with `work.py spawn --to codex`). Codex
first writes `docs/tutorials/PLAYBOOK.md` (best practices) — every future tutorial job must read it first. Output:
short, non-tiring PDFs, downloadable from the dashboard «📚 Tutorials» tab (J97).
