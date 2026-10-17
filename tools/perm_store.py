#!/usr/bin/env python3
"""Store of terminal permission requests (Claude Code PermissionRequest hook <-> dashboard Sudo tab).

One JSON file per request in .lab/perm/<id>.json: {id, ts, tool, description, detail, cwd, state, decided_at, message}.
state: pending -> approved | denied (written only by `decide`, called from the dashboard) | timeout | gone.
Atomic writes (tmp + rename). Pure helpers, no Streamlit.
"""
import json
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


def create(tool, tin, cwd="", root=None):
    desc, detail = describe(tool, tin)
    rec = {"id": time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6], "ts": time.time(), "tool": str(tool),
           "description": desc, "detail": detail[:MAX_DETAIL], "cwd": str(cwd or ""), "state": "pending"}
    _write(rec, root)
    return rec["id"]


def decide(rid, approve, message="", root=None):
    """Dashboard only. Returns False if the request is not pending any more."""
    rec = read(rid, root)
    if not rec or rec.get("state") != "pending":
        return False
    rec.update(state="approved" if approve else "denied", decided_at=time.time(), message=message or "")
    _write(rec, root)
    return True


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
            if rec and rec.get("state") == "pending" and time.time() - rec.get("ts", 0) < max_age:
                out.append(rec)
    return sorted(out, key=lambda r: r["ts"])


def recent(root=None, limit=10):
    recs = [read(fn[:-5], root) for fn in os.listdir(perm_dir(root)) if fn.endswith(".json")]
    recs = [r for r in recs if r and r.get("state") != "pending"]
    return sorted(recs, key=lambda r: -r["ts"])[:limit]
