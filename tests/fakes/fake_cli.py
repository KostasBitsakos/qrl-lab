#!/usr/bin/env python3
"""Stand-in for `claude` and `codex` in tests (no network, no tokens).

Called as  fake_cli.py claude <args...>  or  fake_cli.py codex <args...>  (through small wrappers).
Each call pops the first JSON line of $FAKE_DIR/<cli>.queue, e.g. {"mode": "ok", "text": "...", "session": "s1"}.
Modes: ok, quota, error, paid (Claude: ok but drawing on paid credits). argv is appended to $FAKE_DIR/<cli>.calls.
"""
import json
import os
import sys


def pop(cli):
    q = os.path.join(os.environ["FAKE_DIR"], f"{cli}.queue")
    with open(q, encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    if not lines:
        return {"mode": "error", "text": "fake queue empty"}
    with open(q, "w", encoding="utf-8") as f:
        f.writelines(lines[1:])
    return json.loads(lines[0])


def log(cli, argv):
    with open(os.path.join(os.environ["FAKE_DIR"], f"{cli}.calls"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": argv, "env_coord": os.environ.get("QRL_COORDINATOR")}) + "\n")


def claude(argv):
    step = pop("claude")
    log("claude", argv)
    sid = step.get("session") or (argv[argv.index("--resume") + 1] if "--resume" in argv else "sess-new")
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 30000, "cache_read_input_tokens": 5000,
             "output_tokens": 800, "cache_creation": {"ephemeral_1h_input_tokens": 30000,
                                                       "ephemeral_5m_input_tokens": 0},
             "iterations": [{"input_tokens": 10, "cache_read_input_tokens": 5000,
                             "cache_creation_input_tokens": step.get("context", 30000)}],
             }
    out = {"type": "result", "subtype": "success", "is_error": False, "result": step.get("text", "ok"),
           "session_id": sid, "total_cost_usd": step.get("cost", 0.42), "usage": usage, "permission_denials":
               step.get("denials", [])}
    import time
    code = 0
    limit = {"status": "allowed", "rateLimitType": "five_hour", "utilization": 0.42,
             "resetsAt": int(time.time()) + 3 * 3600, "isUsingOverage": False}
    if step["mode"] == "quota":
        out.update(is_error=True, result=step.get("text", "You've hit your session limit · resets 3:50pm "
                                                         "(Europe/Athens)"))
        limit.update(status="rejected", utilization=1.0, resetsAt=int(time.time()) + 7200)
        code = 1
    elif step["mode"] == "error":
        out.update(is_error=True, result=step.get("text", "API Error: 400 invalid request"))
        code = 1
    elif step["mode"] == "paid":
        limit.update(status="allowed_warning", isUsingOverage=True)
    if argv[argv.index("--output-format") + 1] == "stream-json":
        print(json.dumps({"type": "system", "subtype": "init", "session_id": sid}))
        if not step.get("no_limits"):
            print(json.dumps({"type": "rate_limit_event", "rate_limit_info": limit, "session_id": sid}))
    print(json.dumps(out))
    return code


def codex(argv):
    step = pop("codex")
    log("codex", argv)
    tid = argv[argv.index("resume") + 1] if "resume" in argv else step.get("session", "thread-new")
    out_file = argv[argv.index("-o") + 1]
    print(json.dumps({"type": "thread.started", "thread_id": tid}))
    print(json.dumps({"type": "turn.started"}))
    if step["mode"] == "quota":
        print(json.dumps({"type": "error", "message": "Reconnecting... 1/5"}))
        print(json.dumps({"type": "turn.failed", "error": {"message": step.get(
            "text", "You've hit your usage limit. Try again in 2 hours 5 minutes.")}}))
        return 1
    if step["mode"] == "error":
        print(json.dumps({"type": "turn.failed", "error": {"message": step.get("text", "sandbox error")}}))
        return 1
    text = step.get("text", "ok")
    print(json.dumps({"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": text}}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 20000, "cached_input_tokens": 15000,
                                                          "output_tokens": 700}}))
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    which = sys.argv[1]
    sys.exit(claude(sys.argv[2:]) if which == "claude" else codex(sys.argv[2:]))
