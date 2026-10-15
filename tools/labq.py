#!/usr/bin/env python3
"""Request/inbox queue between QRL-Lab agents and the researcher.

  requests.jsonl  agents -> researcher   (questions, proposals, approval requests)
  inbox.jsonl     researcher -> agents   (answers and free proposals; the coordinator is notified per line)

Usage:
  labq.py ask --kind approval --title "..." --body-file f.md [--options approve,reject,changes] [--blocking] [--cost "..."]
  labq.py pending                      # requests without an answer
  labq.py reply R-... approve "text"   # answer a request from the command line (the dashboard does the same)
  labq.py say "free text"              # new message/proposal to the coordinator
"""
import argparse
import datetime as dt
import json
import os
import sys

ROOT = os.environ.get("QRL_LAB_DIR") or os.getcwd()
LAB = os.path.join(ROOT, ".lab")
REQ = os.path.join(LAB, "requests.jsonl")
INBOX = os.path.join(LAB, "inbox.jsonl")
KINDS = ("approval", "question", "proposal", "info")
DECISIONS = ("approve", "reject", "changes")


def now():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def read(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def append(path, obj):
    os.makedirs(LAB, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def next_id(prefix, items):
    day = dt.date.today().strftime("%Y%m%d")
    n = sum(1 for x in items if str(x.get("id", "")).startswith(f"{prefix}-{day}-")) + 1
    return f"{prefix}-{day}-{n:03d}"


def cmd_ask(a):
    if a.body_file:
        with open(a.body_file, encoding="utf-8") as f:
            body = f.read()
    else:
        body = a.body or ""
    req = {
        "id": next_id("R", read(REQ)),
        "ts": now(),
        "from": a.sender,
        "kind": a.kind,
        "title": a.title,
        "body": body,
        "options": [o.strip() for o in a.options.split(",")] if a.options else [],
        "blocking": a.blocking,
        "cost": a.cost,
        "links": a.link or [],
    }
    append(REQ, req)
    print(req["id"])


def answered_ids():
    return {m.get("reply_to") for m in read(INBOX) if m.get("reply_to")}


def cmd_pending(_):
    done = answered_ids()
    open_reqs = [r for r in read(REQ) if r.get("id") not in done and r.get("kind") != "info"]
    if not open_reqs:
        print("no pending requests")
    for r in open_reqs:
        flag = "BLOCKING " if r.get("blocking") else ""
        print(f'{r["id"]}  {flag}[{r.get("kind")}] {r.get("title")}')


def cmd_reply(a):
    ids = {r.get("id") for r in read(REQ)}
    if a.request_id not in ids:
        sys.exit(f"unknown request id: {a.request_id}")
    msg = {"id": next_id("I", read(INBOX)), "ts": now(), "reply_to": a.request_id,
           "decision": a.decision, "text": a.text or ""}
    append(INBOX, msg)
    print(msg["id"])


def cmd_say(a):
    msg = {"id": next_id("I", read(INBOX)), "ts": now(), "reply_to": None, "decision": None, "text": a.text}
    append(INBOX, msg)
    print(msg["id"])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ask")
    s.add_argument("--kind", choices=KINDS, required=True)
    s.add_argument("--title", required=True)
    g = s.add_mutually_exclusive_group()
    g.add_argument("--body-file")
    g.add_argument("--body")
    s.add_argument("--options", default="")
    s.add_argument("--blocking", action="store_true")
    s.add_argument("--cost", default="")
    s.add_argument("--link", action="append")
    s.add_argument("--from", dest="sender", default="coordinator")
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("pending")
    s.set_defaults(func=cmd_pending)

    s = sub.add_parser("reply")
    s.add_argument("request_id")
    s.add_argument("decision", choices=DECISIONS)
    s.add_argument("text", nargs="?", default="")
    s.set_defaults(func=cmd_reply)

    s = sub.add_parser("say")
    s.add_argument("text")
    s.set_defaults(func=cmd_say)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
