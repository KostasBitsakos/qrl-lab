#!/usr/bin/env python3
"""Parallel work: jobs, file claims and agent-to-agent negotiation (QRL-Lab v0.4).

Every headless run started by tools/dispatcher.py is a job: the chat coordinator (C<n>, talks to the researcher) and
any number of workers (J<n>, do the longer work in parallel). Runs see their own id in $QRL_JOB.

  work.py status                              active jobs, their files and goals
  work.py spawn --title T (--brief B | --brief-file F) [--to claude|codex]
                                              chat coordinator: hand work to a new parallel worker (prints J<n>)
  work.py claim PATH... [--note why] [--wait S]
                                              reserve files/directories BEFORE editing them; exit 2 = conflict
  work.py release [PATH...]                   give files back (all when none given; the dispatcher also releases at end)
  work.py say JOB|coordinator TEXT            message another job (or escalate to the chat coordinator)
  work.py agree JOB TEXT                      record the agreement reached with JOB (also posted for the researcher)
  work.py inbox [--wait S]                    read messages addressed to you
  work.py commit [--worktree PATH] -m MSG     git commit only the files you claimed (serialised between jobs)
  work.py cancel JOB                          chat coordinator: stop a worker (e.g. the researcher changed their mind)

Every command except `inbox` also prints messages waiting for you, so a busy job sees a negotiation request on its
next call. Standard library only; the state lives in .lab/dispatch.db (tables jobs, claims, agent_msgs).
"""
import argparse
import fcntl
import os
import subprocess
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labdb import LabError  # noqa: E402

ACTIVE = ("queued", "running")
CONFLICT_EXIT = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(n INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, created TEXT, lane TEXT,
  origin TEXT, created_by TEXT, thread_id TEXT, reply_to TEXT, parent_msgs TEXT, title TEXT, brief TEXT, provider TEXT,
  status TEXT, started TEXT, ended TEXT, cancel INTEGER DEFAULT 0, result TEXT);
CREATE TABLE IF NOT EXISTS claims(path TEXT NOT NULL, job TEXT NOT NULL, ts TEXT, note TEXT, PRIMARY KEY(path, job));
CREATE TABLE IF NOT EXISTS agent_msgs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, from_job TEXT, to_job TEXT,
  kind TEXT, body TEXT, read INTEGER DEFAULT 0);
"""


def ensure_schema(conn):
    conn.executescript(SCHEMA)


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def norm_path(root, p):
    """A claim key: path relative to the lab root, no trailing slash ('.' = the whole lab)."""
    ap = os.path.realpath(os.path.join(root, p))
    rootr = os.path.realpath(root)
    if ap != rootr and not ap.startswith(rootr + os.sep):
        raise LabError(f"{p}: outside the lab ({root}).")
    return os.path.relpath(ap, rootr)


def overlaps(a, b):
    return a == b or a == "." or b == "." or a.startswith(b + "/") or b.startswith(a + "/")


class Work:
    """Job board on the dispatch database connection `conn` (sqlite3, autocommit, Row factory)."""

    def __init__(self, conn, root):
        self.conn = conn
        self.root = root
        ensure_schema(conn)

    @contextmanager
    def _tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    # jobs
    def create(self, lane, origin, title, brief="", thread_id=None, reply_to=None, parent_msgs=None, provider=None,
               created_by="dispatcher", status="queued"):
        import json
        prefix = "C" if lane == "chat" else "J"
        with self._tx() as c:
            cur = c.execute("INSERT INTO jobs(created, lane, origin, created_by, thread_id, reply_to, parent_msgs, title,"
                            " brief, provider, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (_now(), lane, origin, created_by, thread_id, reply_to, json.dumps(parent_msgs or []),
                             (title or "").strip()[:200], brief or "", provider, status))
            jid = f"{prefix}{cur.lastrowid}"
            c.execute("UPDATE jobs SET id=? WHERE n=?", (jid, cur.lastrowid))
        return jid

    def job(self, jid):
        r = self.conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return dict(r) if r else None

    def active(self, lane=None):
        q = "SELECT * FROM jobs WHERE status IN ('queued','running')" + (" AND lane=?" if lane else "") + " ORDER BY n"
        return [dict(r) for r in self.conn.execute(q, (lane,) if lane else ())]

    def queued_spawns(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM jobs WHERE status='queued' AND origin='spawn' ORDER BY n")]

    def set_status(self, jid, status, result=None):
        col = "started" if status == "running" else "ended"
        self.conn.execute(f"UPDATE jobs SET status=?, {col}=?, result=COALESCE(?, result) WHERE id=?",
                          (status, _now(), result, jid))

    def request_cancel(self, jid):
        j = self.job(jid)
        if not j or j["status"] not in ACTIVE:
            raise LabError(f"{jid}: no active job.")
        if j["status"] == "queued":
            self.conn.execute("UPDATE jobs SET status='cancelled', cancel=1, ended=? WHERE id=?", (_now(), jid))
        else:
            self.conn.execute("UPDATE jobs SET cancel=1 WHERE id=?", (jid,))

    def cancel_requested(self):
        return [r["id"] for r in self.conn.execute("SELECT id FROM jobs WHERE status='running' AND cancel=1")]

    # claims
    def claims(self, jid=None):
        q = "SELECT * FROM claims" + (" WHERE job=?" if jid else "") + " ORDER BY ts"
        return [dict(r) for r in self.conn.execute(q, (jid,) if jid else ())]

    def claim(self, jid, paths, note=""):
        """Atomic: all paths or none. Returns [] when granted, else the conflicting claims of other active jobs."""
        keys = [norm_path(self.root, p) for p in paths]
        with self._tx() as c:
            held = [dict(r) for r in c.execute(
                "SELECT claims.* FROM claims JOIN jobs ON jobs.id=claims.job WHERE claims.job<>? AND"
                " jobs.status IN ('queued','running')", (jid,))]
            conflicts = [h for h in held if any(overlaps(k, h["path"]) for k in keys)]
            if conflicts:
                return conflicts
            for k in keys:
                c.execute("INSERT OR REPLACE INTO claims(path, job, ts, note) VALUES (?,?,?,?)", (k, jid, _now(), note))
        return []

    def release(self, jid, paths=None):
        if not paths:
            self.conn.execute("DELETE FROM claims WHERE job=?", (jid,))
            return
        for p in paths:
            self.conn.execute("DELETE FROM claims WHERE job=? AND path=?", (jid, norm_path(self.root, p)))

    def drop_stale_claims(self):
        self.conn.execute("DELETE FROM claims WHERE job NOT IN (SELECT id FROM jobs WHERE status IN ('queued','running'))")

    # messages
    def say(self, frm, to, body, kind="note"):
        self.conn.execute("INSERT INTO agent_msgs(ts, from_job, to_job, kind, body) VALUES (?,?,?,?,?)",
                          (_now(), frm, to, kind, body.strip()))

    def inbox(self, jid, mark=True):
        rows = [dict(r) for r in self.conn.execute(
            "SELECT * FROM agent_msgs WHERE to_job=? AND read=0 ORDER BY id", (jid,))]
        if mark and rows:
            self.conn.execute(f"UPDATE agent_msgs SET read=1 WHERE id IN ({','.join('?' * len(rows))})",
                              [r["id"] for r in rows])
        return rows

    def escalations(self):
        """Unread messages to the chat coordinator (agents that could not agree, or need the researcher)."""
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM agent_msgs WHERE to_job='coordinator' AND read=0 ORDER BY id")]

    def mark_read(self, ids):
        for i in ids:
            self.conn.execute("UPDATE agent_msgs SET read=1 WHERE id=?", (i,))

    def finish(self, jid):
        """End of a run: release its files; tell the senders of messages it never read."""
        self.release(jid)
        for m in self.inbox(jid):
            if m["from_job"] not in ("dispatcher", "coordinator"):
                self.say("dispatcher", m["from_job"],
                         f"{jid} finished without reading your message; its files are free now. Your message was: "
                         f"{m['body'][:300]}", kind="notice")

    def summary_lines(self, exclude=None):
        out = []
        for j in self.active():
            if j["id"] == exclude:
                continue
            files = ", ".join(c["path"] for c in self.claims(j["id"])) or "-"
            brief = " ".join((j["brief"] or "").split())[:240]
            out.append(f"- {j['id']} [{j['status']}, {j['provider'] or 'auto'}] {j['title']} · files: {files}"
                       + (f" · goal: {brief}" if brief else ""))
        return out


# ---------------------------------------------------------------- CLI

def _open(root):
    from dispatcher import DispatchDB, dispatch_db_path
    dd = DispatchDB(dispatch_db_path(root))
    return dd, Work(dd.conn, root)


def _me():
    return os.environ.get("QRL_JOB") or "researcher"


def _print_inbox(w, me, header=True):
    msgs = w.inbox(me)
    if msgs:
        if header:
            print(f"\n📨 {len(msgs)} message(s) for {me} — answer with: python3 tools/work.py say <job> \"...\"")
        for m in msgs:
            print(f"[{m['ts'][11:16]}] {m['from_job']} → {me} ({m['kind']}): {m['body']}")
    return msgs


def _conflict_text(w, conflicts):
    lines = ["CONFLICT: these files are claimed by another job that is running in parallel:"]
    for jid in sorted({c["job"] for c in conflicts}):
        j = w.job(jid) or {}
        paths = ", ".join(c["path"] for c in conflicts if c["job"] == jid)
        lines.append(f"- {jid} ({j.get('title', '?')}): {paths}")
        if j.get("brief"):
            lines.append(f"  its goal: {' '.join(j['brief'].split())[:500]}")
    lines.append("Negotiate (see 'Parallel work' in your prompt): python3 tools/work.py say <job> \"what you need to "
                 "change and why\", then python3 tools/work.py inbox --wait 120. Agree on the option that best serves "
                 "BOTH researcher requests, record it with work.py agree, or wait with: work.py claim <paths> --wait 600")
    return "\n".join(lines)


def _post_agreement(root, w, me, other, text):
    """Agreements are visible to the researcher in the thread of each job involved."""
    try:
        from labdb import LabDB
        lab = LabDB(os.path.join(root, ".lab", "lab.db"))
    except Exception:
        return
    done = set()
    for jid in (me, other):
        j = w.job(jid) or {}
        target = j.get("reply_to")
        if target and target not in done:
            done.add(target)
            try:
                lab.post("coordinator", f"🤝 Συμφωνία {me} ↔ {other}: {text}", target, kind="status")
            except LabError:
                pass


def commit_scope(root, paths, worktree=None):
    """Resolve claims to literal files, never a nested repository/gitlink."""
    root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, worktree or "."))
    norm_path(root, target)  # also rejects symlink escapes

    def git(*args):
        p = subprocess.run(["git", *args], cwd=target, capture_output=True, text=True)
        if p.returncode:
            raise LabError(p.stderr.strip() or "Git worktree validation failed")
        return p.stdout

    if os.path.realpath(git("rev-parse", "--show-toplevel").strip()) != target:
        raise LabError("--worktree must name a Git worktree root.")
    selected = []
    for path in paths:
        absolute = os.path.join(root, norm_path(root, path))
        if absolute == target or absolute.startswith(target + os.sep):
            selected.append(os.path.relpath(absolute, target))
    if not selected:
        raise LabError("You hold no claims beneath the selected worktree.")
    candidates = set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")) - {""}
    files = sorted(p for p in candidates if any(overlaps(p, q) for q in selected))
    gitlinks = {record.split("\t", 1)[1] for record in git("ls-files", "--stage", "-z").split("\0")
                if record.startswith("160000 ")}
    for path in files:
        norm_path(target, path)
        if path in gitlinks:
            raise LabError(f"Refusing to stage nested worktree/submodule gitlink: {path}")
        # Even an untracked nested repository must never be staged as a gitlink.
        parent = os.path.dirname(os.path.join(target, path))
        while not os.path.isdir(parent):
            parent = os.path.dirname(parent)
        probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=parent,
                               capture_output=True, text=True)
        if probe.returncode or os.path.realpath(probe.stdout.strip()) != target:
            raise LabError(f"Claim crosses a nested repository: {path}")
    return target, [":(literal)" + p for p in files]


def git_commit(root, paths, message, worktree=None):
    lock_path = os.path.join(root, ".lab", "git.lock")
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            target, scoped = commit_scope(root, paths, worktree)
            if not scoped:
                return subprocess.CompletedProcess([], 0, "nothing to commit in your claimed files\n", "")
            p = subprocess.run(["git", "add", "-A", "--"] + scoped, cwd=target,
                               capture_output=True, text=True)
            if p.returncode:
                return p
            p = subprocess.run(["git", "diff", "--cached", "--name-only", "--"] + scoped,
                               cwd=target, capture_output=True, text=True)
            if p.returncode:
                return p
            if not p.stdout.strip():
                return subprocess.CompletedProcess([], 0, "nothing to commit in your claimed files\n", "")
            return subprocess.run(["git", "commit", "--only", "-m", message, "--"] + scoped,
                                  cwd=target, capture_output=True, text=True)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def main(argv=None):
    ap = argparse.ArgumentParser(description="QRL-Lab parallel work board")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("spawn")
    s.add_argument("--title", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--brief")
    g.add_argument("--brief-file")
    s.add_argument("--to", choices=("claude", "codex"))
    s.add_argument("--reply-to", help="message the worker reports to (default: the one you are answering)")
    s = sub.add_parser("claim")
    s.add_argument("paths", nargs="+")
    s.add_argument("--note", default="")
    s.add_argument("--wait", type=int, default=0, help="seconds to wait for the files to be free")
    s = sub.add_parser("release")
    s.add_argument("paths", nargs="*")
    s = sub.add_parser("say")
    s.add_argument("to")
    s.add_argument("text")
    s = sub.add_parser("agree")
    s.add_argument("other")
    s.add_argument("text")
    s = sub.add_parser("inbox")
    s.add_argument("--wait", type=int, default=0)
    s = sub.add_parser("commit")
    s.add_argument("-m", "--message", required=True)
    s.add_argument("--worktree", help="Git worktree root within the lab (default: lab root)")
    s = sub.add_parser("cancel")
    s.add_argument("job")
    a = ap.parse_args(argv)
    from dispatcher import lab_root
    root = os.path.abspath(lab_root())
    dd, w = _open(root)
    me = _me()
    rc = 0
    if a.cmd == "status":
        lines = w.summary_lines()
        print("\n".join(lines) if lines else "No active jobs.")
    elif a.cmd == "spawn":
        if me != "researcher" and not me.startswith("C"):
            raise LabError("Only the chat coordinator spawns workers; ask it with: work.py say coordinator \"...\"")
        brief = a.brief
        if a.brief_file:
            with open(a.brief_file, encoding="utf-8") as f:
                brief = f.read()
        if not (brief or "").strip():
            raise LabError("Empty brief.")
        mine = w.job(me) or {}
        reply_to = a.reply_to or mine.get("reply_to") or os.environ.get("QRL_REPLY_TO")
        if not reply_to:
            raise LabError("--reply-to is required outside a dispatcher run.")
        import json
        jid = w.create("worker", "spawn", a.title, brief, thread_id=mine.get("thread_id"), reply_to=reply_to,
                       parent_msgs=json.loads(mine.get("parent_msgs") or "[]"), provider=a.to, created_by=me)
        print(f"{jid} queued: it starts as soon as a worker slot is free and reports in the thread.")
    elif a.cmd == "claim":
        t_end = time.time() + a.wait
        while True:
            conflicts = w.claim(me, a.paths, a.note)
            if not conflicts:
                print("OK claimed: " + ", ".join(norm_path(root, p) for p in a.paths))
                break
            if time.time() >= t_end:
                print(_conflict_text(w, conflicts))
                rc = CONFLICT_EXIT
                break
            _print_inbox(w, me)
            time.sleep(5)
    elif a.cmd == "release":
        w.release(me, a.paths)
        print("released")
    elif a.cmd == "say":
        if a.to != "coordinator" and not w.job(a.to):
            raise LabError(f"Unknown job {a.to}.")
        w.say(me, a.to, a.text)
        print(f"sent to {a.to}")
    elif a.cmd == "agree":
        if not w.job(a.other):
            raise LabError(f"Unknown job {a.other}.")
        w.say(me, a.other, "AGREED: " + a.text, kind="agreement")
        _post_agreement(root, w, me, a.other, a.text)
        print("agreement recorded and posted")
    elif a.cmd == "inbox":
        t_end = time.time() + a.wait
        while True:
            if _print_inbox(w, me, header=False):
                break
            if time.time() >= t_end:
                print("(no messages)")
                break
            time.sleep(3)
    elif a.cmd == "commit":
        paths = [c["path"] for c in w.claims(me)]
        if not paths:
            raise LabError("You hold no claims: claim the files you changed first.")
        p = git_commit(root, paths, a.message, a.worktree)
        print((p.stdout or "") + (p.stderr or ""))
        rc = p.returncode
    elif a.cmd == "cancel":
        if me != "researcher" and not me.startswith("C"):
            raise LabError("Only the chat coordinator or the researcher cancels a job.")
        w.request_cancel(a.job)
        print(f"{a.job}: cancel requested")
    if a.cmd != "inbox" and me != "researcher":
        _print_inbox(w, me)
    dd.close()
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LabError as e:
        sys.exit(str(e))
