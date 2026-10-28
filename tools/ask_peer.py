#!/usr/bin/env python3
"""Ask the other model (the co-researcher) a question. Works the same for Claude and for Codex.

  python3 tools/ask_peer.py ask  --prompt-file brief.md [--to codex|claude] [--key council-sim-v2] [--major]
  python3 tools/ask_peer.py submit ...same options...      -> prints P-id, returns at once
  python3 tools/ask_peer.py wait P-id [--timeout 540]      -> prints the answer (exit 0), "PENDING" (exit 3)

--to       default: the other model than the current coordinator ($QRL_COORDINATOR, set by the dispatcher)
--key      continue the peer's earlier conversation on the same topic (e.g. the cross-critique round of a council)
--major    stronger model / higher effort (major decisions only; say why in the thread)

The request is queued in .lab/dispatch.db and answered by tools/dispatcher.py outside any sandbox, read-only:
the peer can read files and search the web, never edit. If the dispatcher is not running (heartbeat older than 60 s),
`ask` runs the peer itself (only possible outside a sandbox).
Post the answer verbatim in the thread (labq.py post --author <peer> --kind contribution), then your synthesis.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dispatcher import OTHER, PROVIDERS, DispatchDB, dispatch_db_path, lab_root, serve_peer  # noqa: E402
from labdb import LabError  # noqa: E402


def _prompt(a):
    if a.prompt_file:
        with open(a.prompt_file, encoding="utf-8") as f:
            return f.read()
    return a.prompt or ""


def dispatcher_alive(root, max_age=60):
    hb = os.path.join(root, ".lab", "bridge_heartbeat")
    return os.path.exists(hb) and time.time() - os.path.getmtime(hb) < max_age


def wait(dd, pid, timeout):
    t_end = time.time() + timeout
    while True:
        r = dd.peer(pid)
        if r is None:
            sys.exit(f"Unknown peer request {pid}.")
        if r["status"] == "done":
            print(r["answer"] or "")
            return 0
        if r["status"] == "failed":
            print(f"PEER FAILED: {r['error']}")
            return 1
        if time.time() >= t_end:
            print(f"PENDING {pid}: still running; call again: python3 tools/ask_peer.py wait {pid}")
            return 3
        time.sleep(3)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ask", "submit"):
        s = sub.add_parser(name)
        g = s.add_mutually_exclusive_group(required=True)
        g.add_argument("--prompt-file")
        g.add_argument("--prompt")
        s.add_argument("--to", choices=PROVIDERS)
        s.add_argument("--key")
        s.add_argument("--major", action="store_true")
        s.add_argument("--timeout", type=int, default=540)
    s = sub.add_parser("wait")
    s.add_argument("id")
    s.add_argument("--timeout", type=int, default=540)
    a = ap.parse_args(argv)
    root = os.path.abspath(lab_root())
    dd = DispatchDB(dispatch_db_path(root))
    if a.cmd == "wait":
        return wait(dd, a.id, a.timeout)
    me = os.environ.get("QRL_COORDINATOR", "claude")
    to = a.to or OTHER.get(me, "codex")
    prompt = _prompt(a).strip()
    if not prompt:
        sys.exit("Empty prompt.")
    pid = dd.peer_submit(to, prompt, key=a.key, major=a.major, from_provider=me)
    if a.cmd == "submit":
        print(pid)
        return 0
    if not dispatcher_alive(root):
        req = dd.peer_claim(pid)
        if req:
            serve_peer(root, req)
    return wait(dd, pid, a.timeout)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LabError as e:
        sys.exit(str(e))
