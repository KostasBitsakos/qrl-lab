#!/usr/bin/env python3
"""Explicit start/end log for agents the Claude hooks cannot tell apart (the Codex roles).

  agent_log.py start --agent codex-reviewer --model gpt-6.1-sol --effort medium --task "short text" [--label word] [--thread M-...]
  agent_log.py end <id> [--status done|failed]

Appends SubagentStart / SubagentStop records to .lab/events.jsonl (same format as lab_event_hook.py), so the
dashboard Agents tab shows each role in its own lane. No LLM tokens; never raises on I/O errors.
"""
import argparse
import json
import os
import re
import sys
import time
import uuid

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAX = 140
LABEL_MAX = 14
STOPWORDS = frozenset("""
a an the to of for and or in on at by with from into this that these those is are be do does please just new old
all any some more most my our your it its as via per vs use using make run check also then now
να για και το τον την του της των τα τους τις ένα μια μία ενός με σε από ως στο στη στην στον στα στους
είναι θα που ότι αυτό αυτή αυτά πως όπως ή
""".split())


PREFIX = re.compile(r"^\s*[\w\-]+(?::[\w\-]+)?:\s+")


def task_word(text, maxlen=LABEL_MAX):
    """One-word label from a task text: the first meaningful word (Greek or English), at most `maxlen` chars.

    A leading "agent-type:" prefix (as in the coordinator's Agent-tool summaries) is dropped. Stop words, numbers
    and one-letter tokens are skipped. Returns "" if nothing meaningful is left.
    """
    t = PREFIX.sub("", str(text or ""), count=1)
    for w in re.findall(r"[^\W\d_][\w\-]*", t):
        if len(w) > 1 and w.lower() not in STOPWORDS:
            return w[:maxlen]
    return ""


def clean_label(label, maxlen=LABEL_MAX):
    """Explicit --label: one or two words, at most `maxlen` characters in total."""
    return " ".join(str(label or "").split()[:2])[:maxlen].strip()


def events_path():
    root = os.environ.get("QRL_LAB_DIR") or KIT
    return os.path.join(root, ".lab", "events.jsonl")


def _append(rec):
    path = events_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def start(agent, model="", effort="", task="", thread="", now=None, label=""):
    aid = "log-" + uuid.uuid4().hex[:10]
    rec = {"hook_event_name": "SubagentStart", "agent_id": aid, "agent_type": agent, "model": model,
           "effort": effort, "task": str(task)[:MAX], "summary": str(task)[:MAX],
           "ts": round(time.time() if now is None else now, 3)}
    if thread:
        rec["thread"] = thread
    lab = clean_label(label) or task_word(task)
    if lab:
        rec["label"] = lab
    _append(rec)
    return aid


def end(aid, status="done", now=None):
    _append({"hook_event_name": "SubagentStop", "agent_id": aid, "status": status,
             "ts": round(time.time() if now is None else now, 3)})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--agent", required=True)
    s.add_argument("--model", default="")
    s.add_argument("--effort", default="")
    s.add_argument("--task", default="")
    s.add_argument("--label", default="", help="one or two words shown next to the dots (default: from --task)")
    s.add_argument("--thread", default="")
    e = sub.add_parser("end")
    e.add_argument("id")
    e.add_argument("--status", choices=("done", "failed"), default="done")
    a = p.parse_args(argv)
    if a.cmd == "start":
        print(start(a.agent, a.model, a.effort, a.task, a.thread, label=a.label))
    else:
        end(a.id, a.status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
