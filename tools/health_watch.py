#!/usr/bin/env python3
"""Lightweight health watcher for the coordinator session (no LLM, no network).

Every INTERVAL seconds it reads the visible text of the coordinator's tmux window (`tmux capture-pane -p`) and
classifies it with the regex table PATTERNS below (extend the table, nothing else). The result goes to
.lab/health.json (the dashboard shows it as a banner) and every state change is appended to .lab/events.jsonl.
Only the matched line (max 300 chars) is stored; for a permission dialog also ~15 lines of the dialog block
(`prompt_text`), never the whole pane. Permission is recognised only from the bottom dialog block. Nothing read from the pane is executed.

Run:  python3 tools/health_watch.py            (loop)      python3 tools/health_watch.py --once
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LAB = os.path.join(os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), ".lab")
SESSION = "lab"
WINDOW = "coordinator"  # tools/start-coordinator.sh: the window that is not `dashboard` / `health`
INTERVAL = float(os.environ.get("QRL_HEALTH_INTERVAL", "20"))
TAIL_LINES = 25  # only the bottom of the screen counts, so old scrolled-up text does not keep a state alive
MAX_LINE = 300
STALE_AFTER = 120  # seconds; an older health.json is from a previous run of the watcher
SHELLS = ("bash", "sh", "zsh", "fish", "dash")  # the window falls back to `exec bash` when claude exits

# Highest priority first. Each entry: (state, compiled regex). A named group `when` is captured verbatim.
PATTERNS = [
    ("limit", re.compile(r"(?i)(?:usage limit|limit reached|limit will reset|out of (?:extra )?usage|hit your [\w-]+ limit)"
                         r"[^\n]*?\bresets?\s*(?:at\s*)?(?P<when>[^\n│|·]{1,40}?)\s*(?:[│|·]|$)")),
    # Only Claude Code's own UI wording, anchored, so tool output that merely mentions these words
    # (git logs, file contents) does not trigger a false banner.
    ("limit", re.compile(r"(?i)^[\s│⎿>]*(?:claude )?(?:your )?(?:usage limit (?:has been )?reached|[\w-]+ limit reached|out of (?:extra )?usage|you(?:'|’)?ve hit your [\w-]+ limit)")),
    ("api_error", re.compile(r"^[\s│⎿>]*API Error\b")),
]

# Permission dialog: recognised only as the LAST block of the capture. The last "1. Yes" option line must be followed
# by nothing but option lines, box borders and Claude Code's dialog hint line. Text in scrollback or tool output is
# always followed by the normal input box / footer / more output, so it never matches.
OPT1 = re.compile(r"^[\s│❯>]*1\.\s*Yes\b")
OPTN = re.compile(r"^[\s│❯>]*[2-9]\.\s+\S")
QUESTION = re.compile(r"(?i)^[\s│❯>]*(?:Do you want to\b|Claude needs your permission)")
BORDER = re.compile(r"^[\s│╭╮╰╯─┌┐└┘├┤\-]*$")
HINT = re.compile(r"(?i)(?:esc to cancel|enter to confirm|tab to amend|ctrl\+e to explain|to navigate)")
CONTEXT_LINES = 15


def _dialog(lines):
    """Return (matched_line, prompt_text) when `lines` end in a real permission dialog, else None."""
    idx = [i for i, ln in enumerate(lines) if OPT1.search(ln)]
    if not idx:
        return None
    i = idx[-1]
    tail = lines[i + 1:]
    if not all(OPTN.search(t) or BORDER.match(t) or HINT.search(t) or len(t) - len(t.lstrip()) >= 4 for t in tail):
        return None  # something else (input box, footer, output) follows: not a live dialog
    if not any(OPTN.search(t) for t in tail):
        return None  # a dialog has at least option 2
    q = next((j for j in range(i, max(-1, i - 12), -1) if QUESTION.search(lines[j])), i)
    block = lines[max(0, q - 2):][:CONTEXT_LINES]
    return lines[q].strip()[:MAX_LINE], "\n".join(b[:200] for b in block)


def _explicit_out(line):
    import extra_credits
    return extra_credits.is_explicit_out(line)


def detect(pane_text, window_exists=True, pane_cmd=None, extra_active=False):
    """Pure classifier. Returns {"state": ok|down|limit|extra|permission|api_error, "detail": str, "line": str}."""
    if not window_exists:
        return {"state": "down", "detail": "το tmux window δεν υπάρχει", "line": ""}
    if pane_cmd and pane_cmd.strip().lower() in SHELLS:
        return {"state": "down", "detail": f"το window τρέχει μόνο {pane_cmd.strip()}", "line": ""}
    lines = [ln.rstrip() for ln in (pane_text or "").splitlines() if ln.strip()][-TAIL_LINES:]
    def scan(table):
        for state, rx in table:
            for line in reversed(lines):
                m = rx.search(line)
                if m:
                    when = (m.groupdict().get("when") or "").strip()
                    return {"state": state, "detail": when, "line": line.strip()[:MAX_LINE]}
        return None
    r = scan(PATTERNS[:2])
    if r:
        if extra_active and r["state"] == "limit" and not _explicit_out(r["line"]):
            r["state"] = "extra"  # Claude keeps working on purchased credits (researcher 2026-10-23); deputy.py ignores it
        return r
    dlg = _dialog(lines)
    if dlg:
        return {"state": "permission", "detail": "", "line": dlg[0], "prompt_text": dlg[1]}
    r = scan(PATTERNS[2:])
    if r:
        return r
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
    # The window command is `bash -c "claude ...; exec bash"`, so tmux always reports a shell. Claude is running
    # iff that shell has a child process; after claude exits the shell is replaced by `exec bash` (no children).
    _, info = _run(["tmux", "display-message", "-p", "-t", target, "#{pane_pid} #{pane_current_command}"])
    parts = info.split()
    if len(parts) == 2 and parts[0].isdigit():
        rc, _ = _run(["pgrep", "-P", parts[0]])
        return text, True, (None if rc == 0 else parts[1])
    return text, True, None


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
    stale = now - float(prev.get("checked", 0) or 0) > STALE_AFTER  # watcher was not running (reboot): do not inherit
    since = now if changed or stale or not prev.get("since") else prev["since"]
    cur = {"state": result["state"], "detail": result["detail"], "line": result["line"], "since": since,
           "checked": now}
    if result["state"] == "permission":
        cur["prompt_text"] = result.get("prompt_text", "")
    if prev.get("codex"):  # written by tools/codex_health.py; this watcher only watches the coordinator window
        cur["codex"] = prev["codex"]
    os.makedirs(lab, exist_ok=True)
    _atomic_write(path, cur)
    if changed:
        ev = {"ts": now, "hook_event_name": "HealthState", "summary": f"{prev.get('state', '-')} -> {result['state']}"
              + (f" ({result['detail']})" if result["detail"] else ""), "state": result["state"]}
        with open(os.path.join(lab, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return cur


def log_error(msg, lab=LAB):
    """Append to .lab/health_watch.log (the tmux window has vanished twice without a trace, 2026-10-17)."""
    try:
        os.makedirs(lab, exist_ok=True)
        with open(os.path.join(lab, "health_watch.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} {msg}\n")
    except OSError:
        pass


def heartbeat(lab=LAB, now=None):
    """.lab/health_watch.heartbeat = {"ts", "pid"}; tools/watchdog.sh restarts the window when it goes stale."""
    try:
        _atomic_write(os.path.join(lab, "health_watch.heartbeat"),
                      {"ts": time.time() if now is None else now, "pid": os.getpid()})
    except OSError:
        pass


def _on_signal(signum, _frame):
    log_error(f"received signal {signum}, exiting")
    sys.exit(0)


def main():
    once = "--once" in sys.argv
    if not once:
        import atexit
        import signal
        log_error("started")
        atexit.register(log_error, "exiting")
        for s in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(s, _on_signal)
    while True:
        heartbeat()
        try:
            try:
                import extra_credits
                extra = extra_credits.status("claude")["active"]
            except Exception:  # noqa: BLE001
                extra = False
            cur = step(detect(*sample(), extra_active=extra))
            try:
                import deputy  # Codex deputy: file the request / start the window (never fatal)
                deputy.tick(LAB)
            except Exception as e:
                log_error(f"deputy tick: {type(e).__name__}: {e}\n{traceback.format_exc()}")
                print(f"deputy tick warning: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            if once:
                print(json.dumps(cur, ensure_ascii=False))
        except Exception as e:  # never die: the next cycle may work
            log_error(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            print(f"health_watch warning: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        if once:
            return
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
