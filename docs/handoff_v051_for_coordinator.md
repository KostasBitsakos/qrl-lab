# Handoff v0.5.1 → coordinator (Πάρις), 6/11/2026

Read with `docs/STATE.md`. Full comparison with the original plan (16 changes, 5 omissions, 7 additions):
`docs/V051_changes_from_original_plan.md`. Details and known issues: `CHANGELOG_v05.md`.

## State
- B0–B7 are merged in master (75c56e2) and live: dispatcher and dashboard restarted 6/11, governor ON (`governor_enabled`=1).
- Rollback if needed (researcher decides): `git reset --hard dfe5bcb` + `systemctl --user restart qrl-dispatcher qrl-dashboard`.
- **B7 freeze until the CCGrid abstract (24/11):** «αφορά μόνο υποδομή (dispatcher, dashboard, tools, κανόνες)· η έρευνα, τα πειράματα και το paper συνεχίζουν κανονικά». Infrastructure: only fixes the researcher asks for.
- Test baseline: 24 known failures + `test_spiky_guard::test_exact_child_not_arbitrary_code` (date-based, expired sandbox).

## What the dispatcher now does by script (you are NOT woken for these)
- Clean batch end → a summary is posted in the request's thread (`[run-summary …]`). You are woken only for a failed batch.
- Approved frozen `sim` spec → launched by the dispatcher (up to `max_parallel`). `real`/`qpu` approvals still reach you.
- Worker escalation: urgent → a `question` card for the researcher; routine → a status line. You no longer get an escalation wake-up.
- Approved config card → applied by the dispatcher (validated, audited). Propose with
  `python3 tools/dispatcher.py propose KEY VALUE --reason "…"`; never edit settings yourself.
- A Codex job's claimed files are committed by the dispatcher (only those, blob-checked). A job that ran only on one provider is
  flagged solo and gets one read-only review from the other provider when it returns.

## What you can use
- `work.py spawn … --role research|work|light|quick` selects the worker model from the `role_*` settings (Codex names are empty:
  the config default applies until the researcher sets them in the Σύστημα tab).
- Prompts now carry «Related» (kb.py query) for messages > 80 characters. STATE.md limit is 8 KB (`state_max_bytes`): when you update
  it, keep it short and move old text to `docs/archive/` with pointers.
- The governor decides admission of optional runs by pace (share of the week passed). A held job stays queued; do not retry or
  mark providers exhausted yourself.

## Open items for you
1. **Worker model chosen by the researcher** (M-20261102-049): `work.py spawn` still does not pass his per-message model choice to the
   worker. Not part of v0.5.1; do it only when he says so (it is a fix, allowed under the freeze).
2. The 24 h poisson_ms experiment (J332 draft, `.lab/c330/codex/`): needs council/implementation before freeze, then a frozen card.
   Nothing starts without his approval.
3. Not implemented from the plan: `claude_max_runs`/`codex_max_runs`/`max_subagents`, `on_done`/`review` fields in approval cards.
   Ask before adding.

## Known issues (not blocking)
Orphan `starting` run after a crash holds a parallel slot; a status message can be lost after a crash between state and post;
governor-held jobs have no time limit; the last fixes of B2 and B3–B6 were not re-reviewed by Codex.
