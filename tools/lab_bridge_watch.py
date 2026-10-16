#!/usr/bin/env python3
"""Monitor command of the lab-bridge plugin: delivers dashboard input to the running coordinator session.

Claude Code runs this for the whole interactive session and turns every line it prints into a notification
for the coordinator. It prints one line per:
  - researcher message from the dashboard (status 'new'), then marks it 'delivered';
  - researcher decision on a request that the coordinator has not seen yet.
On start it also re-delivers messages that were delivered but never taken (e.g. the session restarted).
It writes .lab/bridge_heartbeat every cycle, so the dashboard can show whether the coordinator is online.
It never executes anything it reads.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labdb import LabDB, lab_dir  # noqa: E402

POLL_SECONDS = float(os.environ.get("QRL_BRIDGE_POLL", "2"))
CLIP = 300


def one_line(text, n=CLIP):
    t = " ⏎ ".join(s.strip() for s in (text or "").strip().splitlines() if s.strip())
    return t if len(t) <= n else t[:n] + " …"


def emit_message(m):
    kind = {"message": "message", "proposal": "PROPOSAL", "code_question": "CODE QUESTION"}.get(m["kind"], m["kind"])
    redo = " (re-delivery)" if m["status"] == "delivered" else ""
    print(f"QRL-INBOX {kind} {m['id']} thread={m['thread_id']}{redo}: \"{one_line(m['body'])}\" "
          f"-> handle with: python3 tools/labq.py take {m['id']}", flush=True)


def emit_decision(r):
    text = f" note: \"{one_line(r['decision_text'], 200)}\"" if r["decision_text"] else ""
    print(f"QRL-DECISION {r['id']} [{r['kind']}/{r['scope']}] \"{one_line(r['title'], 80)}\" -> {r['state']}{text}",
          flush=True)


def heartbeat():
    try:
        p = os.path.join(lab_dir(), "bridge_heartbeat")
        with open(p, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def cycle(db, first):
    msgs, decs = db.undelivered(include_unacked=first)
    for m in msgs:
        emit_message(m)
    for r in decs:
        emit_decision(r)
    if msgs or decs:
        db.mark_delivered([m["id"] for m in msgs], [r["id"] for r in decs])


def main():
    db = LabDB()
    print("QRL-BRIDGE online: dashboard messages and decisions will arrive here.", flush=True)
    first = True
    while True:
        try:
            cycle(db, first)
            first = False
        except Exception as e:  # a locked DB or a transient error must not kill the bridge
            print(f"QRL-BRIDGE warning: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        heartbeat()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
