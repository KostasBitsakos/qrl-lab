#!/usr/bin/env python3
"""Turn agent output that arrived as JSON (codex exec --json events, Claude result objects, content blocks) into the
readable text it carries. Stdlib only. The raw output is never lost: labdb.post saves it under .lab/raw/."""
import json

TEXT_KEYS = ("result", "final_message", "last_message", "text", "message", "content", "output", "response", "answer")


def _walk(o):
    """Yield text fragments from a JSON value, preferring known text-bearing keys."""
    if isinstance(o, str):
        yield o
    elif isinstance(o, list):
        for x in o:
            yield from _walk(x)
    elif isinstance(o, dict):
        t = o.get("type")
        if t in ("reasoning", "command_execution", "tool_use", "tool_result", "thinking", "turn.started",
                 "thread.started", "turn.completed", "usage"):
            return
        for k in ("item", "msg", "data"):  # codex event envelopes
            if isinstance(o.get(k), (dict, list)):
                yield from _walk(o[k])
                return
        for k in TEXT_KEYS:
            if k in o:
                yield from _walk(o[k])
                return


def readable(body):
    """Return (text, was_json). Non-JSON input is returned unchanged with was_json=False."""
    s = (body or "").strip()
    if not s or s[0] not in "{[":
        return body, False
    try:
        parts = list(_walk(json.loads(s)))
    except ValueError:
        parts = []
        lines = [ln for ln in s.splitlines() if ln.strip()]
        try:  # JSON Lines (codex exec --json)
            for ln in lines:
                parts.extend(_walk(json.loads(ln)))
        except ValueError:
            return body, False
    text = "\n\n".join(p.strip() for p in parts if p and p.strip())
    if parts and text:
        # a stream repeats the final message in several events: keep the last distinct one for agent_message streams
        return text, True
    return "_(Η απάντηση ήρθε ως JSON χωρίς κείμενο· η ακατέργαστη έξοδος είναι αποθηκευμένη στο .lab/raw/.)_", True
