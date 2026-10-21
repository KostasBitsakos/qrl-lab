# Dashboard — active rules

Dashboard protocol (pending messages, replies, statuses, decisions): see CLAUDE.md «Dashboard protocol».

- The dashboard is the only channel; the terminal and phone app are fallbacks for permission prompts and emergencies (CLAUDE.md: if the researcher writes there, answer there). (2026-10-16, handoff standing rule 1)
- Dashboard changes are requested in the dashboard; the `engineer` implements them. Before applying, run `tests/test_lab.py` and add tests for the new feature, then commit. If the dashboard breaks, revert with git at once. Tell the researcher to press F5 after each change. (2026-10-16, handoff standing rule 2)
- The dashboard shows exact limit messages for both Claude and Codex, with the reset time. (2026-10-17, M-20261017-005/006/007)
- Sudo requests are approved from a dashboard tab. (2026-10-17, M-20261017-005/006/007)
- Write to the researcher in Greek, short and direct: see CLAUDE.md golden rule 8. (2026-10-16, handoff standing rule 5)
- Chat model selector (2026-10-21, M-20261021-072/088): honour req_model/req_effort from `labq take`. `coordinator:<model>` = the coordinator handles the message but delegates the answer to that model (Claude subagent or Codex) and says in the reply which model answered; a plain model id = answer from that model directly; default = coordinator's own model.
