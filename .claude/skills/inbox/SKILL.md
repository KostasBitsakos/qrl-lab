---
name: inbox
description: Handle a researcher message from the QRL-Lab dashboard (a QRL-INBOX notification) - pick it up, do the work or route it, and post a visible reply in the same thread with a final status. Use for every QRL-INBOX line.
---

# Handle a dashboard message

1. **Take it**: `python3 tools/labq.py take <M-id>`. This prints the thread and marks the message acknowledged.
2. **Classify** and act:
   - *Question about the project or results* → answer from PLAN.md, run data or files, with pointers.
   - *Question about the existing code* (`CODE QUESTION`) → delegate the search to `Explore` (Haiku) with a precise
     brief; answer with `path:line` evidence and what remains unknown.
   - *Proposal / idea* (`PROPOSAL`) → assess it against PLAN §8–§9. If it changes the research (model, simulator,
     reward, workload, baselines, claims), run skill `council` and file the decision card with `ask-user`.
   - *Task request* → do it if PLAN §6 and existing approvals cover it; otherwise file an approval with `ask-user`
     and set the message to `waiting_approval`.
   - *Instruction about how we work* → confirm, and record it in `docs/DECISIONS.md` if it is a standing decision.
3. **Interim reply** if the work will take more than a few minutes:
   write `.lab/outbox/<M-id>-ack.md` (two lines: what you started, when to expect an answer), then
   `python3 tools/labq.py post --reply-to <M-id> --body-file .lab/outbox/<M-id>-ack.md --kind status --status in_progress`.
4. **Codex contribution** (when consulted): post its answer verbatim (or the first ~4000 characters plus the file
   path of the rest) with `--author codex --kind contribution`.
5. **Final reply** in Greek, written to `.lab/outbox/<M-id>.md`, short, with these parts as needed:
   - **Απάντηση / τι βρήκαμε** (with evidence pointers)
   - **Claude** and **Codex** views when both were involved, and **Διαφωνίες** if they disagree
   - **Τι χρειάζομαι από σένα** (with the request id, if any)
   Then: `python3 tools/labq.py post --reply-to <M-id> --body-file .lab/outbox/<M-id>.md --status done`
   (or `--status waiting_approval` / `--status failed` with the reason in the text).
6. `PushNotification` only if the researcher must act (blocking request) or long work finished.

Never leave a taken message without a reply and a final status. Never paste secrets or long logs into a reply:
point to the file instead.
