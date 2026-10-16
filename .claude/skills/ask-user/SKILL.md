---
name: ask-user
description: File a question, proposal or approval request for the researcher in the dashboard (Αποφάσεις tab) and notify their phone when it blocks work. Use whenever a decision belongs to the researcher (PLAN §6), when a council card is ready, when a fact is missing, and for every experiment approval (with a run spec).
---

# Ask the researcher

1. Write the body to `.lab/outbox/<short-name>.md`, in Greek, under 250 words: what you need and why now, the
   options, your recommendation, the cost (CPU-h / QPU-s / days / tokens), evidence pointers (run ids, council
   folder, `path:line`).
2. File it:
   ```bash
   python3 tools/labq.py ask --kind approval|question|proposal|info --title "<short title>" \
     --body-file .lab/outbox/<short-name>.md [--scope sim|real|qpu|research|external|other] \
     [--blocking] [--cost "<text>"] [--link <path>] [--thread <M-id>] [--spec <spec.json>]
   ```
   It prints the request id (`R-...`). Decisions allowed: approval/proposal → approve, reject, changes;
   question → answer (text); info → ack.
3. **Experiments**: every run needs `--kind approval --scope sim|real|qpu --spec <file>`. The spec is frozen at
   filing time; editing it later invalidates the approval. Template:
   ```json
   {"name": "screen-QC1-W0", "scope": "sim", "cwd": "code/timeseries/Pytorch",
    "entries": [{"name": "seed0", "seed": 0, "cmd": ["../../.venv/bin/python", "train.py", "--seed", "0"]}],
    "max_parallel": 1, "max_attempts": 1, "limits": {"wall_clock_hours": 6},
    "real": {"kube_context": "<ctx>", "namespace": "<ns>", "rollback": "<how to undo>"}}
   ```
   (`real` only for scope real.) After approval: `python3 tools/launch_run.py start --request R-... --all`.
4. If `--blocking`, call `PushNotification` with one line: `"[QRL] <title> — περιμένει απόφαση (R-...)"`.
5. Continue with work that does not depend on the answer. The decision arrives as a `QRL-DECISION` notification;
   `python3 tools/labq.py pending` lists what is open.

Never treat silence, a comment, or a decision on a different request as approval. Never decide on the
researcher's behalf (agents are denied `labq.py decide` and `labq.py say`).
