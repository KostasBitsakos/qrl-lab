#!/usr/bin/env python3
"""Lightweight health watcher for the coordinator session (no LLM, no network).

Every INTERVAL seconds it reads the visible text of the coordinator's tmux window (`tmux capture-pane -p`) and
classifies it with the regex table PATTERNS below (extend the table, nothing else). The result goes to
.lab/health.json (the dashboard shows it as a banner) and every state change is appended to .lab/events.jsonl.
Only the one matched line (max 300 chars) is stored, never the pane. Nothing read from the pane is executed.

Run:  python3 tools/health_watch.py            (loop)      python3 tools/health_watch.py --once
"""
import json
import os
import re
import subprocess
import sys
import time

LAB = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SESSION = "lab"
WINDOW = "coordinator"  # tools/start-coordinator.sh: the window that is not `dashboard` / `health`
INTERVAL = float(os.environ.get("QRL_HEALTH_INTERVAL", "20"))
TAIL_LINES = 25  # only the bottom of the screen counts, so old scrolled-up text does not keep a state alive
MAX_LINE = 300
SHELLS = ("bash", "sh", "zsh", "fish", "dash")  # the window falls back to `exec bash` when claude exits

# Highest priority first. Each entry: (state, compiled regex). A named group `when` is captured verbatim.
PATTERNS = [
    ("limit", re.compile(r"(?i)(?:usage limit|limit reached|limit will reset|out of (?:extra )?usage)"
                         r"[^\n]*?\bresets?\s*(?:at\s*)?(?P<when>[^\n│|]{1,40}?)\s*(?:[│|]|$)")),
    ("limit", re.compile(r"(?i)(?:usage limit|limit reached)")),
    ("permission", re.compile(r"(?i)\bDo you want to\b")),
    ("permission", re.compile(r"(?i)needs your permission")),
    ("permission", re.compile(r"^[\s│❯>]*1\.\s*Yes\b")),
    ("api_error", re.compile(r"(?i)API Error")),
    ("api_error", re.compile(r"(?i)\boverloaded\b")),
    ("api_error", re.compile(r"(?i)rate[ _-]?limit")),
]


def detect(pane_text, window_exists=True, pane_cmd=None):
    """Pure classifier. Returns {"state": ok|down|limit|permission|api_error, "detail": str, "line": str}."""
    if not window_exists:
        return {"state": "down", "detail": "το tmux window δεν υπάρχει", "line": ""}
    if pane_cmd and pane_cmd.strip().lower() in SHELLS:
        return {"state": "down", "detail": f"το window τρέχει μόνο {pane_cmd.strip()}", "line": ""}
    lines = [ln.rstrip() for ln in (pane_text or "").splitlines() if ln.strip()][-TAIL_LINES:]
    for state, rx in PATTERNS:
        for line in reversed(lines):
            m = rx.search(line)
            if m:
                when = (m.groupdict().get("when") or "").strip()
                return {"state": state, "detail": when, "line": line.strip()[:MAX_LINE]}
    return {"state": "ok", "detail": "", "line": ""}


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def sample():
    """Read the real tmux window. Returns (pane_text, window_exists, pane_cmd)."""
    rc, out = _run(["tmux", "list-windows", "-t", SESSION, "-F", "#W"])
    if rc != 0 or WINDOW not in out.split():
        return "", False, None
    target = f"{SESSION}:{WINDOW}"
    _, text = _run(["tmux", "capture-pane", "-p", "-t", target])
    _, cmd = _run(["tmux", "display-message", "-p", "-t", target, "#{pane_current_command}"])
    return text, True, cmd.strip() or None


def _atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def step(result, lab=LAB, now=None):
    """Update health.json from one detection; append an event when the state changes. Returns the stored dict."""
    now = time.time() if now is None else now
    path = os.path.join(lab, "health.json")
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    changed = prev.get("state") != result["state"]
    since = now if changed or not prev.get("since") else prev["since"]
    cur = {"state": result["state"], "detail": result["detail"], "line": result["line"], "since": since,
           "checked": now}
    os.makedirs(lab, exist_ok=True)
    _atomic_write(path, cur)
    if changed:
        ev = {"ts": now, "hook_event_name": "HealthState", "summary": f"{prev.get('state', '-')} -> {result['state']}"
              + (f" ({result['detail']})" if result["detail"] else ""), "state": result["state"]}
        with open(os.path.join(lab, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return cur


def main():
    once = "--once" in sys.argv
    while True:
        try:
            cur = step(detect(*sample()))
            if once:
                print(json.dumps(cur, ensure_ascii=False))
        except Exception as e:  # never die: the next cycle may work
            print(f"health_watch warning: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        if once:
            return
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
