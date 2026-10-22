# Dashboard — active rules

Dashboard protocol (pending messages, replies, statuses, decisions): see CLAUDE.md «Dashboard protocol».

- The dashboard is the only channel; the terminal and phone app are fallbacks for permission prompts and emergencies (CLAUDE.md: if the researcher writes there, answer there). (2026-10-16, handoff standing rule 1)
- Dashboard changes are requested in the dashboard; the `engineer` implements them. Before applying, run `tests/test_lab.py` and add tests for the new feature, then commit. If the dashboard breaks, revert with git at once. Tell the researcher to press F5 after each change. (2026-10-16, handoff standing rule 2)
- The dashboard shows exact limit messages for both Claude and Codex, with the reset time. (2026-10-17, M-20261017-005/006/007)
- Sudo requests are approved from a dashboard tab. (2026-10-17, M-20261017-005/006/007)
- Write to the researcher in Greek, short and direct: see CLAUDE.md golden rule 8. (2026-10-16, handoff standing rule 5)
- Chat model selector (2026-10-21, M-20261021-072/088): honour req_model/req_effort from `labq take`. `coordinator:<model>` = the coordinator handles the message but delegates the answer to that model (Claude subagent or Codex) and says in the reply which model answered; a plain model id = answer from that model directly; default = coordinator's own model.
- Structured message option (2026-10-22, M-20261022-015): every chat composer (main, paper, venues, extensions) has a toggle «Δομημένο md (script)», default off, remembered per chat. When on, `tools/msg_structure.py` (deterministic, no LLM) turns the message into Markdown (original verbatim on top, points P1..Pn as exact slices, questions, ids/paths) and a preview offers «Αποστολή» (send the md) or «Ακύρωση / στείλε το αρχικό».
- Extensions tab (2026-10-22, M-20261022-020): every installed/catalog item shows a target label «Claude», «Codex» or «Claude + Codex» (from where it lives; Codex side read read-only, names only); the request form has a target radio and the message prefix is `[EXT-SEARCH · <target>]`.
- Limit notifications (2026-10-22, M-20261022-063): the sidebar «ειδοποιήσεις ορίων» shows human Greek messages (`tools/notif_format.py`: provider colour, severity icon, relative time + Europe/Athens reset time), only the last 24 h and not dismissed; «✕» / «Καθαρισμός όλων» persist ids in `.lab/notifications_dismissed.json`; `.lab/offers_watch_events.jsonl` is the audit log and is never deleted.
