#!/usr/bin/env python3
"""Backend of the dashboard tab «🔐 Sudo». Pure helpers plus thin wrappers around tools/sudo_grant.py.

It does NOT touch the security logic of sudo_grant.py / sudo_gate.py: it only builds the same command line the
researcher could type, and runs it (`run` is injectable, tests mock it). See PLAN section 7 for the residual risk
(the dashboard and the agents run as the same Unix user).

Request convention (scope `sudo`): every line of the body that starts with `sudo ` (optionally after `$ `, `- `,
or backticks) is a command the coordinator wants to run. The programs of the grant are derived from those lines
with sudo_gate.sudo_programs, never typed by the dashboard user.
"""
import json
import os
import re
import subprocess
import sys

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sudo_gate import GRANT, NEVER, sudo_programs  # noqa: E402

DEFAULT_MINUTES = 30
MAX_MINUTES = 240  # same cap as sudo_grant.py
SCRIPT = os.path.join(KIT, "tools", "sudo_grant.py")
_LEAD = re.compile(r"^[\s>*\-`$]+")


def lab_path(*parts):
    return os.path.join(os.environ.get("QRL_LAB_DIR") or KIT, ".lab", *parts)


def parse_request(body):
    """-> {"commands": [str], "programs": [sorted str], "refused": [programs in NEVER], "unparsed": [commands]}."""
    commands, programs, unparsed = [], set(), []
    for raw in (body or "").splitlines():
        line = _LEAD.sub("", raw).rstrip("` \t")
        if not line.startswith("sudo "):
            continue
        commands.append(line)
        progs = sudo_programs(line)
        if progs is None:
            unparsed.append(line)
        else:
            programs.update(progs)
    return {"commands": commands, "programs": sorted(programs), "refused": sorted(programs & NEVER),
            "unparsed": unparsed}


def clamp_minutes(m):
    try:
        m = int(m)
    except (TypeError, ValueError):
        m = DEFAULT_MINUTES
    return max(1, min(m, MAX_MINUTES))


def open_command(rid, programs, minutes):
    """The exact argv (list) the researcher can also run by hand."""
    return ["python3", "tools/sudo_grant.py", "open", rid,
            "--programs", ",".join(programs), "--minutes", str(clamp_minutes(minutes))]


def sudo_available(run=subprocess.run):
    """True when `sudo -n` works without a password for this user."""
    try:
        return run(["sudo", "-n", "true"], capture_output=True, text=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _grant(args, run):
    r = run([sys.executable, SCRIPT, *args], capture_output=True, text=True, timeout=30, cwd=KIT)
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()


def open_grant(rid, programs, minutes, run=subprocess.run):
    """Run `sudo_grant.py open` from the dashboard process. Returns (ok, message). Refuses without programs."""
    if not programs:
        return False, "no programs derived from the request"
    if set(programs) & NEVER:
        return False, "refused: " + ", ".join(sorted(set(programs) & NEVER))
    return _grant(["open", rid, "--programs", ",".join(programs), "--minutes", str(clamp_minutes(minutes))], run)


def close_grant(run=subprocess.run):
    return _grant(["close"], run)


def status(run=subprocess.run):
    """Text of `sudo_grant.py status` ("no grant" when none)."""
    ok, msg = _grant(["status"], run)
    return msg if ok else f"status failed: {msg}"


def audit_tail(n=50, path=None):
    """Last n entries of .lab/sudo_audit.jsonl, newest first. Bad lines are skipped."""
    path = path or lab_path("sudo_audit.jsonl")
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out[::-1]
