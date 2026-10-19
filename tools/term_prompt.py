#!/usr/bin/env python3
"""Answer the coordinator's terminal permission dialog from the dashboard (R-20261019-002).

Sends exactly one key to tmux `lab:0`: "1" (option 1, which must start with "Yes" and not be an always-allow
option) or Escape. Before sending, the pane is captured again and the bottom dialog must hash to the same value
as the one the researcher saw. Every click is appended to .lab/events.jsonl. Nothing else is ever sent.
PIN gating is done by the caller (dashboard), which only shows the buttons when unlocked.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_watch  # noqa: E402

TARGET = "lab:0"
ALWAYS = re.compile(r"(?i)(?:don'?t ask again|always|for (?:this )?session|and don'?t|all (?:edits|commands))")


def prompt_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def capture():
    r = subprocess.run(["tmux", "capture-pane", "-p", "-t", TARGET], capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""


def send(key):
    r = subprocess.run(["tmux", "send-keys", "-t", TARGET, key], capture_output=True, text=True, timeout=10)
    return r.returncode == 0


def option1_line(prompt_text):
    for ln in (prompt_text or "").splitlines():
        if health_watch.OPT1.search(ln):
            return ln.strip()
    return ""


def option1_ok(prompt_text):
    ln = option1_line(prompt_text)
    return bool(ln) and not ALWAYS.search(ln)


def _log(rec):
    path = os.path.join(os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                        ".lab", "events.jsonl")
    rec = {"hook_event_name": "TermPromptClick", "ts": time.time(), **rec}
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def current():
    """(prompt_text, hash) of the live bottom dialog in lab:0, or ("", "")."""
    res = health_watch.detect(capture())
    if res.get("state") == "permission":
        t = res.get("prompt_text", "")
        return t, prompt_hash(t)
    return "", ""


def answer(action, seen_hash, who="?", unlocked=False):
    """action: 'approve' | 'deny'. Returns (ok, message)."""
    key = {"approve": "1", "deny": "Escape"}.get(action)
    base = {"who": who, "action": action, "prompt_hash": seen_hash, "key": key}
    if key is None:
        return False, "Άγνωστη ενέργεια."
    if not unlocked:
        _log({**base, "result": "refused: PIN locked"})
        return False, "Χρειάζεται PIN· δεν στάλθηκε τίποτα."
    text, h = current()
    if not h or h != seen_hash:
        _log({**base, "result": "refused: prompt changed or gone"})
        return False, "Η ερώτηση άλλαξε ή δεν υπάρχει πια· δεν στάλθηκε τίποτα."
    if action == "approve" and not option1_ok(text):
        _log({**base, "result": "refused: option 1 is not a plain Yes"})
        return False, "Η επιλογή 1 δεν είναι απλό «Yes» (μόνο αυτή τη φορά)· δεν στάλθηκε τίποτα. Απάντησε στο terminal."
    ok = send(key)
    _log({**base, "result": "sent" if ok else "tmux send-keys failed"})
    return ok, ("Στάλθηκε: " + key) if ok else "Αποτυχία tmux send-keys."
