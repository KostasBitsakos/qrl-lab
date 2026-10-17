---
name: inbox
description: Handle a researcher message from the QRL-Lab dashboard (a QRL-INBOX notification) - pick it up, do the work or route it, and post a visible reply in the same thread with a final status. Use for every QRL-INBOX line.
---

# Handle a dashboard message

1. **Take it**: `python3 tools/labq.py take <M-id>`. This prints the thread and marks the message acknowledged.
   **Routing**: the QRL-INBOX line may carry `[model=<haiku|sonnet|opus|codex|auto> effort=<low|med|high>]`
   (also stored as `req_model`/`req_effort` on the message). If the model is not `auto`, do not answer yourself:
   delegate the reply to a subagent of that model via the Agent tool `model` param (`haiku`, `sonnet`, `opus`);
   for `codex` use `codex:codex-rescue` with `--effort <low|medium|high>` (med = medium). Give the subagent the full
   thread (from `labq.py take`), then post its answer (Greek, short) with `--model` set to the model that wrote it
   (e.g. "Haiku 4.5", "Sonnet 5.5", "Opus 5.5", "gpt-6-sol"). `auto` (or no tag) = you decide as usual.
   **Codex limited** (`.lab/health.json` key `codex` has state `limit`, or a Codex call just failed with a usage
   limit: pipe its output to `python3 tools/codex_health.py record`): do not call Codex, use Claude instead:
   reviewer → Sonnet, researcher → `scholar`, quick → Haiku; say so in the reply.
   Effort is a hint for depth: low = short answer, high = careful, verified answer.
   **Paper thread** («Paper — συγγραφή»): the line may carry `[paper writers=<ids> reviewers=<ids>]` (stored as
   `req_writers`/`req_reviewers`). Writer ids: `writer-sonnet`, `writer-opus`, `codex-researcher`; reviewer ids:
   `codex-reviewer`, `codex-architect`, `scholar` (citations), `writer-opus`. Delegate the drafting in `paper/` to the
   selected writers and then the review to the selected reviewers (log each Codex role with `tools/agent_log.py`).
   Post each contribution with its author and model (`--author`, `--model`, `--kind contribution`), then your own
   summary of the changes made in `paper/`, with a link to the compiled PDF (`paper/build/...pdf`, via `tools/paper_build.py`).
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
Pass `--model` on every `labq.py post` (free text; the dashboard shows it next to the author). Examples: the
   coordinator `--model "Opus 5.5"`, Codex `--model gpt-6-sol`.
6. `PushNotification` only if the researcher must act (blocking request) or long work finished.

Never leave a taken message without a reply and a final status. Never paste secrets or long logs into a reply:
point to the file instead.
When you ask the researcher to look at files, write their absolute or `~/` paths (optionally `:line`) so the dashboard renders them as links to the 📁 Αρχεία tab.

At session start also read `.lab/deputy_queue.jsonl` and the posts by `codex` with model «<gpt-6.1-sol|gpt-6-luna> · αναπληρωτής» (the read-only deputy that answered while you were unavailable); handle every queued item that needs execution.
