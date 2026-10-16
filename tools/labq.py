#!/usr/bin/env python3
"""QRL-Lab message and approval CLI (agents' side of the dashboard). Run from ~/qrl-lab.

Conversation (researcher <-> agents):
  labq.py take M-...                         pick up a researcher message: prints the thread, marks it acknowledged
  labq.py show M-...                         print a thread without changing anything
  labq.py post --reply-to M-... --body-file f.md [--author coordinator|codex|agent:<name>] [--model 'Opus 5.5']
               [--kind reply|contribution|status] [--status in_progress|waiting_approval|done|failed]
  labq.py status M-... done                  set the status of a researcher message

Requests (agents -> researcher):
  labq.py ask --kind approval|question|proposal|info --title "..." --body-file f.md
              [--scope sim|real|qpu|research|external|other] [--options approve,reject,changes]
              [--blocking] [--cost "..."] [--link path] [--thread M-...] [--spec spec.json]
  labq.py request R-...                      show a request and its decision
  labq.py withdraw R-... "reason"
  labq.py pending                            open requests and open researcher messages

Researcher only (from your own terminal; agents are denied these in .claude/settings.json):
  labq.py say "text" [--kind message|proposal|code_question] [--thread M-...]
  labq.py decide R-... approve|reject|changes|answer|ack ["text"]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labdb import LabDB, LabError  # noqa: E402

AUTHOR_LABEL = {"researcher": "Κώστας", "coordinator": "Συντονιστής", "codex": "Codex"}


def _body(a):
    if getattr(a, "body_file", None):
        with open(a.body_file, encoding="utf-8") as f:
            return f.read()
    return getattr(a, "body", None) or ""


def _print_thread(thread, full_id=None, clip=600):
    for m in thread:
        who = AUTHOR_LABEL.get(m["author"], m["author"])
        if dict(m).get("model"):
            who += f" · {m['model']}"
        st = f" [{m['status']}]" if m["status"] else ""
        body = m["body"]
        if m["id"] != full_id and len(body) > clip:
            body = body[:clip] + f" … (+{len(body) - clip} chars; labq.py show {m['id']} --full)"
        print(f"--- {m['id']} · {m['ts']} · {who} · {m['kind']}{st}")
        print(body)


def cmd_take(a, db):
    m, thread = db.take(a.id)
    print(f"thread {m['thread_id']} ({len(thread)} messages). Reply with: "
          f"python3 tools/labq.py post --reply-to {m['id']} --body-file <file> --status done")
    _print_thread(thread, full_id=m["id"])


def cmd_show(a, db):
    m = db.message(a.id)
    if not m:
        raise LabError(f"Unknown message {a.id}")
    thread = db.thread(m["thread_id"])
    _print_thread(thread, full_id=a.id, clip=10**9 if a.full else 600)


def cmd_post(a, db):
    print(db.post(a.author, _body(a), a.reply_to, kind=a.kind, set_status=a.status, model=a.model))


def cmd_status(a, db):
    db.set_status(a.id, a.status)
    print("ok")


def cmd_ask(a, db):
    spec = None
    if a.spec:
        with open(a.spec, encoding="utf-8") as f:
            spec = json.load(f)
    rid = db.ask(a.kind, a.title, _body(a), author=a.author, scope=a.scope,
                 options=[o.strip() for o in a.options.split(",")] if a.options else None,
                 blocking=a.blocking, cost=a.cost, links=a.link, thread_id=a.thread, spec=spec)
    print(rid)


def cmd_request(a, db):
    r = db.request(a.id)
    if not r:
        raise LabError(f"Unknown request {a.id}")
    for k in ("id", "ts", "kind", "scope", "state", "title", "decision_text", "decided_at", "spec_hash", "spec_path"):
        print(f"{k}: {r[k]}")
    print("---")
    print(r["body"])


def cmd_withdraw(a, db):
    db.withdraw(a.id, reason=a.reason)
    print("ok")


def cmd_pending(a, db):
    reqs = db.requests(state="open")
    msgs = db.researcher_open()
    if not reqs and not msgs:
        print("nothing pending")
    for r in reqs:
        flag = "BLOCKING " if r["blocking"] else ""
        print(f"request {r['id']}  {flag}[{r['kind']}/{r['scope']}] {r['title']}")
    for m in msgs:
        first = m["body"].strip().splitlines()[0][:100] if m["body"].strip() else ""
        print(f"message {m['id']}  [{m['status']}] {first}")


def cmd_say(a, db):
    print(db.researcher_send(a.text, kind=a.kind, thread_id=a.thread))


def cmd_decide(a, db):
    print(db.decide(a.id, a.decision, a.text, actor="researcher"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("take"); s.add_argument("id"); s.set_defaults(func=cmd_take)
    s = sub.add_parser("show"); s.add_argument("id"); s.add_argument("--full", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("post")
    s.add_argument("--reply-to", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--body-file"); g.add_argument("--body")
    s.add_argument("--author", default="coordinator")
    s.add_argument("--model", default=None, help="free text, e.g. 'Opus 5.5' or 'gpt-6-sol'")
    s.add_argument("--kind", default="reply", choices=["reply", "contribution", "status"])
    s.add_argument("--status", choices=["in_progress", "waiting_approval", "done", "failed"])
    s.set_defaults(func=cmd_post)

    s = sub.add_parser("status"); s.add_argument("id")
    s.add_argument("status", choices=["acknowledged", "in_progress", "waiting_approval", "done", "failed"])
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("ask")
    s.add_argument("--kind", required=True, choices=["approval", "question", "proposal", "info"])
    s.add_argument("--title", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--body-file"); g.add_argument("--body")
    s.add_argument("--scope", default="other", choices=["sim", "real", "qpu", "research", "external", "other"])
    s.add_argument("--options", default="")
    s.add_argument("--blocking", action="store_true")
    s.add_argument("--cost", default=None)
    s.add_argument("--link", action="append")
    s.add_argument("--thread", default=None)
    s.add_argument("--spec", default=None)
    s.add_argument("--author", default="coordinator")
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("request"); s.add_argument("id"); s.set_defaults(func=cmd_request)
    s = sub.add_parser("withdraw"); s.add_argument("id"); s.add_argument("reason", nargs="?", default="")
    s.set_defaults(func=cmd_withdraw)
    s = sub.add_parser("pending"); s.set_defaults(func=cmd_pending)

    s = sub.add_parser("say"); s.add_argument("text")
    s.add_argument("--kind", default="message", choices=["message", "proposal", "code_question"])
    s.add_argument("--thread", default=None)
    s.set_defaults(func=cmd_say)

    s = sub.add_parser("decide"); s.add_argument("id")
    s.add_argument("decision", choices=["approve", "reject", "changes", "answer", "ack"])
    s.add_argument("text", nargs="?", default="")
    s.set_defaults(func=cmd_decide)

    a = p.parse_args()
    db = LabDB()
    try:
        a.func(a, db)
    except LabError as e:
        sys.exit(f"error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
