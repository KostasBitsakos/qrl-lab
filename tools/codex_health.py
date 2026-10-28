#!/usr/bin/env python3
"""Codex usage-limit detection. Records the Codex state under the `codex` key of .lab/health.json.

The patterns live in the PATTERNS table (extend the table, nothing else). `record(stdout, stderr)` is called by
tools/deputy.py after every `codex exec`, and by the coordinator for a Codex failure seen through the plugin:
    python3 tools/codex_health.py record < codex_output.txt        (limit text on stdin)
    python3 tools/codex_health.py ok                                (Codex works again)
Only the one matched line (max 300 chars) is stored. Nothing is executed.
"""
import json
import os
import re
import sys
import time

LAB = os.path.join(os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), ".lab")
MAX_LINE = 300

# (state, regex). Named group `when` = the reset text, verbatim, if the line has one.
PATTERNS = [
    ("limit", re.compile(r"(?i)(?:usage limit|rate limit|limit reached|quota (?:exceeded|exhausted)|too many requests)"
                         r"[^\n]*?\b(?:try again|resets?|retry)\s*(?:in|at|after|on)?\s*(?P<when>[^\n]{1,60}?)\s*[.\n]?$")),
    ("limit", re.compile(r"(?i)\b(?:try again|retry) (?:in|at|after) (?P<when>[^\n]{1,60}?)\s*\.?$")),
    ("limit", re.compile(r"(?i)(?:usage limit|rate limit|limit reached|quota (?:exceeded|exhausted)|\b429\b)")),
]


def detect(stdout="", stderr=""):
    """Pure. Returns {"state": "limit", "detail": reset text, "line": matched line} or None."""
    lines = [ln.strip() for ln in ((stderr or "") + "\n" + (stdout or "")).splitlines() if ln.strip()]
    best = None
    for state, rx in PATTERNS:
        for line in reversed(lines):
            m = rx.search(line)
            if m:
                when = (m.groupdict().get("when") or "").strip()
                if best is None or (when and not best["detail"]):
                    best = {"state": state, "detail": when, "line": line[:MAX_LINE]}
                if when:
                    break
    return best


def _health_path(lab):
    return os.path.join(lab, "health.json")


def _update(lab, codex):
    try:
        with open(_health_path(lab), encoding="utf-8") as f:
            cur = json.load(f)
    except (OSError, ValueError):
        cur = {}
    cur["codex"] = codex
    os.makedirs(lab, exist_ok=True)
    tmp = _health_path(lab) + ".cx.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False)
    os.replace(tmp, _health_path(lab))


def _previous(lab):
    try:
        with open(_health_path(lab), encoding="utf-8") as f:
            return json.load(f).get("codex") or {}
    except (OSError, ValueError):
        return {}


def record(stdout="", stderr="", lab=None, now=None):
    """Store the Codex state. Returns the stored dict (state "limit") or None when the text has no limit error."""
    lab = lab or LAB
    now = time.time() if now is None else now
    d = detect(stdout, stderr)
    if d is None:
        return None
    prev = _previous(lab)
    since = prev.get("since") if prev.get("state") == "limit" and prev.get("since") else now
    cur = dict(d, since=since, checked=now)
    _update(lab, cur)
    return cur


def mark_ok(lab=None, now=None):
    """Codex answered normally: clear the limit."""
    lab = lab or LAB
    now = time.time() if now is None else now
    if _previous(lab).get("state") == "limit":
        _update(lab, {"state": "ok", "detail": "", "line": "", "since": now, "checked": now})


def is_limited(lab=None):
    return _previous(lab or LAB).get("state") == "limit"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ok":
        mark_ok()
    elif len(sys.argv) > 1 and sys.argv[1] == "record":
        print(json.dumps(record(sys.stdin.read(), ""), ensure_ascii=False))
    else:
        sys.exit("usage: codex_health.py record|ok")
