#!/usr/bin/env python3
"""Explicit start/end log for agents the Claude hooks cannot tell apart (the Codex roles).

  agent_log.py start --agent codex-reviewer --model gpt-6.1-sol --effort medium --task "short text" [--thread M-...]
  agent_log.py end <id> [--status done|failed]

Appends SubagentStart / SubagentStop records to .lab/events.jsonl (same format as lab_event_hook.py), so the
dashboard Agents tab shows each role in its own lane. No LLM tokens; never raises on I/O errors.
"""
import argparse
import json
import os
import sys
import time
import uuid

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAX = 140


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


def start(agent, model="", effort="", task="", thread="", now=None):
    aid = "log-" + uuid.uuid4().hex[:10]
    rec = {"hook_event_name": "SubagentStart", "agent_id": aid, "agent_type": agent, "model": model,
           "effort": effort, "task": str(task)[:MAX], "summary": str(task)[:MAX],
           "ts": round(time.time() if now is None else now, 3)}
    if thread:
        rec["thread"] = thread
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
    s.add_argument("--thread", default="")
    e = sub.add_parser("end")
    e.add_argument("id")
    e.add_argument("--status", choices=("done", "failed"), default="done")
    a = p.parse_args(argv)
    if a.cmd == "start":
        print(start(a.agent, a.model, a.effort, a.task, a.thread))
    else:
        end(a.id, a.status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
