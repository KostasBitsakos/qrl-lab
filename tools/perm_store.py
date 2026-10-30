#!/usr/bin/env python3
"""Store of terminal permission requests (Claude Code PermissionRequest hook <-> dashboard Sudo tab).

One JSON file per request in .lab/perm/<id>.json: {id, ts, tool, description, detail, cwd, state, decided_at, message}.
state: pending -> approved | denied (written only by `decide`, called from the dashboard) | timeout | gone.
An approved 'headless' record is consumed once by the hook when the coordinator retries that exact action (take_approval).
Atomic writes (tmp + rename). Pure helpers, no Streamlit.
"""
import json
import fnmatch
import fcntl
import functools
import inspect
import hashlib
import shlex
from contextlib import contextmanager
import os
import time
import uuid

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAX_DETAIL = 4000


def perm_dir(root=None):
    d = os.path.join(root or os.environ.get("QRL_LAB_DIR") or KIT, ".lab", "perm")
    os.makedirs(d, exist_ok=True)
    return d


def _path(rid, root=None):
    if not rid or not all(c.isalnum() or c in "-_" for c in rid):
        raise ValueError("bad id")
    return os.path.join(perm_dir(root), rid + ".json")


def _write(rec, root=None):
    p = _path(rec["id"], root)
    tmp = p + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    os.replace(tmp, p)


def read(rid, root=None):
    try:
        with open(_path(rid, root), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def describe(tool, tin):
    """-> (short Greek description, exact command/path). Never raises."""
    tin = tin if isinstance(tin, dict) else {}
    if tool == "Bash":
        cmd = str(tin.get("command") or "")
        why = tin.get("description")
        base = f"Εντολή shell: {why}" if why else "Εντολή shell στο terminal του συντονιστή"
        return base, cmd
    path = tin.get("file_path") or tin.get("notebook_path") or tin.get("path") or ""
    if tool in ("Write",):
        return "Δημιουργία/αντικατάσταση αρχείου", str(path)
    if tool in ("Edit", "MultiEdit", "NotebookEdit"):
        return "Τροποποίηση αρχείου", str(path)
    if tool == "Read":
        return "Ανάγνωση αρχείου", str(path)
    if tool in ("WebFetch", "WebSearch"):
        return "Πρόσβαση στο διαδίκτυο", str(tin.get("url") or tin.get("query") or "")
    return f"Χρήση εργαλείου {tool}", json.dumps(tin, ensure_ascii=False, default=str)


@contextmanager
def _locked(root=None):
    # Serialize read/check/write across parallel headless jobs and dashboard decisions.
    with open(os.path.join(perm_dir(root), ".store.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _serialized(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        bound = inspect.signature(fn).bind(*args, **kwargs)
        with _locked(bound.arguments.get("root")):
            return fn(*args, **kwargs)
    return wrapped


def deny_rule(tool, tin, root=None):
    """Conservative local deny classifier, never an authorization mechanism.

    Match shell components as well as the complete command, including chained
    commands. Unknown syntax remains subject to the provider's real permissions.
    """
    try:
        with open(os.path.join(root or os.environ.get("QRL_LAB_DIR") or KIT, ".claude", "settings.json"), encoding="utf-8") as f:
            rules = json.load(f).get("permissions", {}).get("deny", [])
    except FileNotFoundError:
        return None
    _, detail = describe(tool, tin)
    candidates = [detail]
    if tool == "Bash":
        try:
            lex = shlex.shlex(detail, posix=True, punctuation_chars=";&|()<>\n")
            lex.whitespace = " \t\r"
            lex.whitespace_split = True
            words = list(lex)
            part = []
            for word in words + [";"]:
                if word and all(c in ";&|()<>\n" for c in word):
                    if part:
                        candidates.append(" ".join(part))
                        part = []
                else:
                    part.append(word)
        except ValueError:
            pass
    for rule in rules:
        if rule == tool:
            return rule
        if not rule.startswith(tool + "(") or not rule.endswith(")"):
            continue
        pattern = rule[len(tool) + 1:-1]
        # Claude's legacy prefix syntax Bash(command:*) is still in use.
        if pattern.endswith(":*"):
            pattern = pattern[:-2] + " *"
        for candidate in candidates:
            if fnmatch.fnmatchcase(candidate, pattern) or (
                    pattern.endswith(" *") and candidate == pattern[:-2]):
                return rule
    return None


def withdraw_deny_rules(root=None):
    """Withdraw pending/undelivered legacy denials without scheduling paid work."""
    withdrawn = []
    with _locked(root):
        for fn in os.listdir(perm_dir(root)):
            if not fn.endswith(".json"):
                continue
            rec = read(fn[:-5], root)
            if not rec or not (rec.get("state") == "pending" or
                               (not rec.get("delivered") and rec.get("state") == "approved")):
                continue
            key = {"Bash": "command", "WebFetch": "url", "WebSearch": "query"}.get(rec.get("tool"), "path")
            tin = {key: rec.get("detail", "")}
            rule = deny_rule(rec.get("tool", ""), tin, root)
            if rule:
                rec.update(state="withdrawn_deny_rule", delivered=True, deny_rule=rule, withdrawn_at=time.time())
                _write(rec, root)
                withdrawn.append(rec["id"])
    return withdrawn


def create(tool, tin, cwd="", root=None, source="hook", thread_id=""):
    """source 'hook': live PermissionRequest (hook waits ~90 s). 'headless': a denial recorded by the dispatcher after a
    headless task; stays pending until the researcher answers, then the answer is delivered with the next task."""
    if deny_rule(tool, tin, root):
        return None
    desc, detail = describe(tool, tin)
    fingerprint = hashlib.sha256((str(tool) + "\0" + detail).encode()).hexdigest()
    with _locked(root):
        for fn in os.listdir(perm_dir(root)):
            if not fn.endswith(".json"):
                continue
            old = read(fn[:-5], root)
            if old and old.get("tool") == str(tool) and (old.get("fingerprint") == fingerprint or (
                    "fingerprint" not in old and len(detail) <= MAX_DETAIL and old.get("detail") == detail)):
                if old.get("state") == "pending" or (
                        source == "headless" and old.get("source") == "headless" and
                        old.get("state") in ("approved", "denied") and
                        time.time() - old.get("decided_at", 0) < 300):
                    return old["id"]
        rec = {"source": source, "thread_id": thread_id or "", "delivered": source != "headless",
               "id": time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6], "ts": time.time(),
               "tool": str(tool), "description": desc, "detail": detail[:MAX_DETAIL], "cwd": str(cwd or ""),
               "state": "pending", "fingerprint": fingerprint}
        _write(rec, root)
        return rec["id"]


@_serialized
def decide(rid, approve, message="", root=None):
    """Dashboard only. Returns False if the request is not pending any more."""
    rec = read(rid, root)
    if not rec or rec.get("state") != "pending":
        return False
    rec.update(state="approved" if approve else "denied", decided_at=time.time(), message=message or "")
    _write(rec, root)
    return True


APPROVAL_TTL = 24 * 3600


@_serialized
def take_approval(tool, tin, root=None, ttl=APPROVAL_TTL):
    """One-shot use of a researcher approval given to a headless (dispatcher) denial, so the retry in the next task
    really runs (M-20261029-003). Matches the exact tool and command/path only; approvals older than `ttl` are ignored.
    Each approval is used at most once (O_EXCL marker file, safe across parallel jobs). -> record id or None."""
    if deny_rule(tool, tin, root):
        return None
    _, detail = describe(tool, tin)
    fingerprint = hashlib.sha256((str(tool) + "\0" + detail).encode()).hexdigest()
    d = perm_dir(root)
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        rec = read(fn[:-5], root)
        if not rec or rec.get("source") != "headless" or rec.get("state") != "approved" or rec.get("used"):
            continue
        if rec.get("tool") != str(tool) or not (rec.get("fingerprint") == fingerprint or (
                "fingerprint" not in rec and len(detail) < MAX_DETAIL and rec.get("detail") == detail)):
            continue
        if time.time() - float(rec.get("decided_at") or 0) > ttl:
            continue
        try:
            os.close(os.open(os.path.join(d, rec["id"] + ".used"), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        rec.update(used=True, used_at=time.time())
        _write(rec, root)
        return rec["id"]
    return None


@_serialized
def mark(rid, state, root=None):
    rec = read(rid, root)
    if rec and rec.get("state") == "pending":
        rec["state"] = state
        _write(rec, root)


def pending(root=None, max_age=300):
    out = []
    for fn in os.listdir(perm_dir(root)):
        if fn.endswith(".json"):
            rec = read(fn[:-5], root)
            if rec and rec.get("state") == "pending" and (rec.get("source") == "headless"
                                                          or time.time() - rec.get("ts", 0) < max_age):
                out.append(rec)
    return sorted(out, key=lambda r: r["ts"])


def undelivered_answers(root=None):
    """Answered headless requests whose answer the dispatcher has not yet passed to the coordinator."""
    recs = [read(fn[:-5], root) for fn in os.listdir(perm_dir(root)) if fn.endswith(".json")]
    return sorted([r for r in recs if r and r.get("source") == "headless" and not r.get("delivered")
                   and r.get("state") in ("approved", "denied")], key=lambda r: r["ts"])


@_serialized
def mark_delivered(rid, root=None):
    rec = read(rid, root)
    if rec:
        rec["delivered"] = True
        _write(rec, root)


def recent(root=None, limit=10):
    recs = [read(fn[:-5], root) for fn in os.listdir(perm_dir(root)) if fn.endswith(".json")]
    recs = [r for r in recs if r and r.get("state") != "pending"]
    return sorted(recs, key=lambda r: -r["ts"])[:limit]
