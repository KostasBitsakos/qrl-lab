---
name: token-saving
description: Researcher wants token-saving skills/plugins used and installed when useful
metadata:
  node_type: memory
  type: feedback
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-21T13:01:15.389Z
---

Κώστας, 2026-10-21: always use skills/addons/plugins that cut model tokens — local memory, computations done on the VM by scripts, caching, etc. — and install further relevant ones if they help (category approval given; still report each install with what it does and verify it is official/trustworthy).
**Why:** Claude weekly limit warning («on pace to hit your weekly limit») with 5 days left.
**How to apply:** prefer scripts over LLM loops, cheapest adequate agent ([[core-split]] for CPU), Codex for implementation when adequate; check docs/extensions_eval_2026-10-20.md before proposing tools already rejected. Related: [[engineer-test-cpu]].
- Researcher M-20261021-063: when Claude limits run out, the coordinator must hand off tasks properly (by requirements) before stopping; agents tab must show the acting coordinator (Codex deputy), not a hard-coded Claude.
