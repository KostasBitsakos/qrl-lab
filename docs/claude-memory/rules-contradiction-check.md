---
name: rules-contradiction-check
description: "Before adding to rule/decision md files, check for contradictions and ask the researcher before writing"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-20T13:56:58.394Z
---

Κώστας (M-20261020-021, 2026-10-20): before adding anything to DECISIONS.md, PLAN.md, CLAUDE.md, AGENTS.md, skills or split rule files, check it against existing entries; if it contradicts or narrows one, report both texts (file:line) on the dashboard and wait for approve/reject. Several cooperating md files are fine.

**Why:** DECISIONS.md had grown chaotic, with silent supersessions (audit 2026-10-20).
**How to apply:** grep the rule files for the topic first; a conflict → `labq.py ask --kind approval`, don't write. Restructure proposal R-20261020-001 (docs/rules/*) pending.
