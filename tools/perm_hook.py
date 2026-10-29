#!/usr/bin/env python3
"""Claude Code PermissionRequest hook: ask the researcher in the dashboard (Sudo tab) instead of only in the terminal.

Contract (verified in the installed Claude Code 2.1.302 binary): stdin JSON has hook_event_name="PermissionRequest",
tool_name, tool_input, cwd, permission_suggestions?. Stdout JSON
{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}} or
{... "decision": {"behavior": "deny", "message": "..."}}. No output + exit 0 = no decision, the terminal prompt appears.

Allow is produced only when the dashboard records state "approved" (for this request, or once for an earlier
headless denial of the exact same tool + command/path, see perm_store.take_approval). Any error, timeout or malformed input prints
nothing (fail-open-to-prompt, never auto-allow).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perm_store  # noqa: E402

WAIT_SECONDS = 90
POLL = 0.5


def out(behavior, message=""):
    d = {"behavior": behavior}
    if behavior == "deny":
        d["message"] = message
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": d}}


def handle(raw, root=None, wait=WAIT_SECONDS, poll=POLL, sleep=time.sleep):
    """-> dict to print, or None for 'no decision'."""
    try:
        ev = json.loads(raw)
        if not isinstance(ev, dict) or ev.get("hook_event_name") != "PermissionRequest" or not ev.get("tool_name"):
            return None
        # the researcher already approved this exact action after an earlier headless task denied it: allow it once
        if perm_store.take_approval(ev["tool_name"], ev.get("tool_input"), root):
            return out("allow")
        rid = perm_store.create(ev["tool_name"], ev.get("tool_input"), ev.get("cwd", ""), root)
    except Exception:
        return None
    try:
        deadline = time.time() + wait
        while True:
            rec = perm_store.read(rid, root)
            if rec and rec.get("state") == "approved":
                return out("allow")
            if rec and rec.get("state") == "denied":
                return out("deny", rec.get("message") or "Απορρίφθηκε από τον ερευνητή στο dashboard.")
            if time.time() >= deadline:
                break
            sleep(poll)
        perm_store.mark(rid, "timeout", root)
    except Exception:
        pass
    return None


def main():
    try:
        res = handle(sys.stdin.read())
    except Exception:
        res = None
    if res:
        print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
