#!/usr/bin/env python3
"""QRL-Lab dispatcher: the coordinator without an always-on LLM session.

Why: a coordinator session that stays open for days re-reads its whole history on every message, and after an idle
gap that history is written to the prompt cache again (the most expensive case). Here no model runs while nothing
happens. A plain Python loop (this file) watches the lab database and, only when there is work, starts ONE short
headless run of the chosen coordinator:
    claude -p ...        (Claude Code, Opus by default)        or        codex exec ...   (Codex)
Each run gets a small context pack: docs/STATE.md (the strategic handoff) + the recent messages of the thread +
the new input. Continuity lives in files and in the database, so either model can take over at any time.

Work items, in priority order:
  1. researcher messages from the dashboard (status new/delivered, or deferred earlier)
  2. researcher decisions on requests that the coordinator has not seen
  3. finished experiment batches (all runs of an approved request ended) -> one event, no polling by an LLM
  4. jobs the chat coordinator handed to parallel workers (tools/work.py spawn)
Peer requests (tools/ask_peer.py: "ask the other model") are served by a second thread, outside any sandbox.

Parallel work (v0.4): two lanes. The chat lane runs ONE coordinator at a time for researcher messages (and agents'
escalations), so the researcher can always talk to a coordinator. The worker lane runs up to `max_workers` jobs at
once (decisions, permission answers, run events, spawned jobs). Runs in parallel share the working tree; they reserve
files with tools/work.py claim and negotiate overlaps among themselves (tools/work.py say/agree). A heartbeat thread
keeps the dashboard's "online" signal fresh while runs are busy.

Coordinator choice: setting `coordinator` (claude|codex), changed by the researcher in the dashboard, or per message
with a leading "@claude" / "@codex". Failover: when the chosen one reports a usage limit, the same task is re-run by
the other one and the first is marked exhausted until its reset time.

Commands:
  dispatcher.py run                 main loop (systemd/tmux)
  dispatcher.py once                process at most one work item, then exit (tests, manual use)
  dispatcher.py status              settings, providers, recent tasks
  dispatcher.py set KEY VALUE       researcher only (agents are denied this)
  dispatcher.py clear PROVIDER      researcher only: mark a provider available again
  dispatcher.py exhaust PROVIDER M  researcher only: drill, treat a provider as out of quota for M minutes
Standard library only. Never executes text it reads from the database.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
from labdb import LabDB, LabError  # noqa: E402
import perm_store  # noqa: E402
import work as W  # noqa: E402
from researcher_text import researcher_text  # noqa: E402

PROVIDERS = ("claude", "codex")
OTHER = {"claude": "codex", "codex": "claude"}
LABEL = {"claude": "Claude", "codex": "Codex"}

DEFAULTS = {
    "coordinator": "claude",          # researcher's choice
    "failover": "1",                  # re-run a task with the other model when one hits its usage limit
    "paused": "0",                    # 1 = take no new work (nothing is spent)
    "allow_paid_credits": "0",        # 0 = if Claude reports it is drawing on paid credits, fail over instead
    "claude_model": "opus",
    "claude_effort": "medium",
    "codex_model": "",                # "" = whatever ~/.codex/config.toml says
    "codex_effort": "medium",
    "events_model": "",               # optional cheaper Claude model for run-finished events ("" = claude_model)
    "peer_claude_model": "sonnet",    # when Codex asks Claude
    "peer_claude_major_model": "opus",
    "peer_codex_model": "",           # when Claude asks Codex ("" = config default)
    "peer_codex_effort": "medium",
    "peer_codex_major_effort": "high",
    "max_workers": "2",               # parallel worker runs (the chat coordinator is extra: one at a time)
    "chat_budget_usd": "3",           # per chat-coordinator run (it delegates longer work to workers)
    "max_budget_usd": "5",            # per worker run (Claude --max-budget-usd; client-side estimate)
    "peer_budget_usd": "1.5",
    "task_timeout_min": "60",
    "peer_timeout_min": "15",
    "escalation_debounce_s": "1200",  # worker->coordinator notes wake the coordinator at most once per this (R-20261029-012)
    "resume_max_tokens": "120000",    # do not resume a session whose context grew beyond this; start fresh
    "codex_resume_window_s": "900",
    "thread_messages": "12",          # thread messages included in a fresh context pack
    "state_max_lines": "150",
}
RESEARCHER_KEYS = set(DEFAULTS)

QUOTA_RE = re.compile(
    r"(hit your (?:[\w']+ ){0,3}(?:limit|budget)|usage limit|limit reached|out of (?:extra )?usage|"
    r"out of usage credits|credit balance (?:is )?too low|usage credits are required|insufficient_quota|"
    r"exceeded your current quota|upgrade to (?:pro|plus|max))", re.I)
TRANSIENT_RE = re.compile(r"(rate limit|overloaded|temporarily unavailable|timed? ?out|connection|503|529)", re.I)
STATUS_LINE_RE = re.compile(r"\n?\s*STATUS:\s*(done|failed|waiting_approval)\s*$", re.I)
MENTION_RE = re.compile(r"^\s*@(claude|codex)\b[:,]?\s*", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT, updated_by TEXT);
CREATE TABLE IF NOT EXISTS providers(name TEXT PRIMARY KEY, state TEXT NOT NULL, until_ts REAL, note TEXT,
  updated_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(thread_id TEXT NOT NULL, provider TEXT NOT NULL, session_id TEXT NOT NULL,
  last_used REAL NOT NULL, ttl_s REAL NOT NULL, context_tokens INTEGER, PRIMARY KEY(thread_id, provider));
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, ended TEXT, kind TEXT,
  thread_id TEXT, refs TEXT, provider TEXT, model TEXT, session_id TEXT, resumed INTEGER, status TEXT,
  cost_usd REAL, input_tokens INTEGER, cached_tokens INTEGER, cache_write_tokens INTEGER, output_tokens INTEGER,
  duration_s REAL, note TEXT);
CREATE TABLE IF NOT EXISTS deferred(msg_id TEXT PRIMARY KEY, ts TEXT);
CREATE TABLE IF NOT EXISTS notified(kind TEXT NOT NULL, ref TEXT NOT NULL, ts TEXT, PRIMARY KEY(kind, ref));
CREATE TABLE IF NOT EXISTS peer_requests(id TEXT PRIMARY KEY, ts TEXT, from_provider TEXT, to_provider TEXT,
  key TEXT, major INTEGER, prompt TEXT, status TEXT, answer TEXT, error TEXT, cost_usd REAL, ts_done TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS limits(provider TEXT NOT NULL, window TEXT NOT NULL, status TEXT, utilization REAL,
  resets_at REAL, overage INTEGER, updated_at TEXT, PRIMARY KEY(provider, window));
"""


def lab_root():
    return os.environ.get("QRL_LAB_DIR") or os.getcwd()


def now_iso():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def dispatch_db_path(root=None):
    """`.lab/dispatch.db` of the lab root (own helper: independent of later changes to labdb.py)."""
    if os.environ.get("QRL_DISPATCH_DB"):
        return os.environ["QRL_DISPATCH_DB"]
    base = os.path.abspath(root or os.environ.get("QRL_LAB_DIR") or os.getcwd())
    return os.path.join(base, ".lab", "dispatch.db")


class DispatchDB:
    def __init__(self, path=None):
        self.path = path or dispatch_db_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.journal_mode = self.conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        self.conn.executescript(SCHEMA)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def audit(self, actor, action, detail=""):
        self.conn.execute("INSERT INTO audit(ts, actor, action, detail) VALUES (?,?,?,?)",
                          (now_iso(), actor, action, detail))

    # settings
    def get(self, key):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else DEFAULTS.get(key, "")

    def settings(self):
        out = dict(DEFAULTS)
        out.update({r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM settings")})
        return out

    def set(self, key, value, actor="researcher"):
        if key not in RESEARCHER_KEYS:
            raise LabError(f"Άγνωστη ρύθμιση {key}.")
        value = str(value).strip()
        if key == "coordinator" and value not in PROVIDERS:
            raise LabError("coordinator: claude ή codex.")
        if key in ("failover", "paused", "allow_paid_credits") and value not in ("0", "1"):
            raise LabError(f"{key}: 0 ή 1.")
        if key == "max_workers" and not (value.isdigit() and 1 <= int(value) <= 16):
            raise LabError("max_workers: 1–16.")
        with self.tx() as c:
            c.execute("INSERT INTO settings(key, value, updated_at, updated_by) VALUES (?,?,?,?) ON CONFLICT(key) DO"
                      " UPDATE SET value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                      (key, value, now_iso(), actor))
            c.execute("INSERT INTO audit(ts, actor, action, detail) VALUES (?,?,?,?)",
                      (now_iso(), actor, "set", f"{key}={value}"))

    # providers
    def provider(self, name):
        r = self.conn.execute("SELECT * FROM providers WHERE name=?", (name,)).fetchone()
        if r is None or (r["state"] == "exhausted" and (r["until_ts"] or 0) <= time.time()):
            return {"name": name, "state": "ok", "until_ts": None, "note": r["note"] if r else None}
        return dict(r)

    def available(self, name):
        return self.provider(name)["state"] == "ok"

    def mark_exhausted(self, name, until_ts, note):
        with self.tx() as c:
            c.execute("INSERT INTO providers(name, state, until_ts, note, updated_at) VALUES (?,?,?,?,?)"
                      " ON CONFLICT(name) DO UPDATE SET state=excluded.state, until_ts=excluded.until_ts,"
                      " note=excluded.note, updated_at=excluded.updated_at",
                      (name, "exhausted", until_ts, note[:300], now_iso()))
            c.execute("INSERT INTO audit(ts, actor, action, detail) VALUES (?,?,?,?)",
                      (now_iso(), "dispatcher", "exhausted", f"{name} until {fmt_ts(until_ts)}: {note[:200]}"))

    def clear(self, name, actor="researcher"):
        with self.tx() as c:
            c.execute("DELETE FROM providers WHERE name=?", (name,))
            c.execute("INSERT INTO audit(ts, actor, action, detail) VALUES (?,?,?,?)",
                      (now_iso(), actor, "clear", name))

    # usage windows reported by the CLI (Claude: five_hour, seven_day, ...)
    def save_limits(self, provider, infos):
        for li in infos or []:
            window = li.get("rateLimitType") or "unknown"
            util = li.get("utilization")
            self.conn.execute(
                "INSERT INTO limits(provider, window, status, utilization, resets_at, overage, updated_at)"
                " VALUES (?,?,?,?,?,?,?) ON CONFLICT(provider, window) DO UPDATE SET status=excluded.status,"
                # Missing utilization is unknown for this observation. Keeping the old
                # value would give it a new timestamp (and possibly a new reset window).
                " utilization=excluded.utilization, resets_at=excluded.resets_at,"
                " overage=excluded.overage, updated_at=excluded.updated_at",
                (provider, window, li.get("status"), float(util) if util is not None else None,
                 _epoch(li["resetsAt"]) if li.get("resetsAt") else None, int(bool(li.get("isUsingOverage"))),
                 now_iso()))

    def limits(self, provider=None):
        q, a = ("SELECT * FROM limits WHERE provider=? ORDER BY window", (provider,)) if provider else \
            ("SELECT * FROM limits ORDER BY provider, window", ())
        return [dict(r) for r in self.conn.execute(q, a)]

    # sessions
    def session(self, thread_id, provider):
        r = self.conn.execute("SELECT * FROM sessions WHERE thread_id=? AND provider=?",
                              (thread_id, provider)).fetchone()
        return dict(r) if r else None

    def save_session(self, thread_id, provider, session_id, ttl_s, context_tokens):
        if not session_id:
            return
        self.conn.execute("INSERT INTO sessions(thread_id, provider, session_id, last_used, ttl_s, context_tokens)"
                          " VALUES (?,?,?,?,?,?) ON CONFLICT(thread_id, provider) DO UPDATE SET"
                          " session_id=excluded.session_id, last_used=excluded.last_used, ttl_s=excluded.ttl_s,"
                          " context_tokens=excluded.context_tokens",
                          (thread_id, provider, session_id, time.time(), ttl_s, context_tokens))

    def drop_session(self, thread_id, provider):
        self.conn.execute("DELETE FROM sessions WHERE thread_id=? AND provider=?", (thread_id, provider))

    # tasks
    def task_start(self, kind, thread_id, refs, provider, model, session_id, resumed):
        cur = self.conn.execute(
            "INSERT INTO tasks(started, kind, thread_id, refs, provider, model, session_id, resumed, status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (now_iso(), kind, thread_id, json.dumps(refs), provider, model, session_id, int(resumed), "running"))
        return cur.lastrowid

    def task_end(self, task_id, status, res, duration_s, note=""):
        u = res.get("usage", {}) if res else {}
        self.conn.execute(
            "UPDATE tasks SET ended=?, status=?, session_id=COALESCE(?, session_id), cost_usd=?, input_tokens=?,"
            " cached_tokens=?, cache_write_tokens=?, output_tokens=?, duration_s=?, note=? WHERE id=?",
            (now_iso(), status, (res or {}).get("session_id"), (res or {}).get("cost"), u.get("input"),
             u.get("cached"), u.get("cache_write"), u.get("output"), round(duration_s, 1), note[:500], task_id))

    def recent_tasks(self, limit=20):
        return [dict(r) for r in self.conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,))]

    def running_task(self):
        r = self.conn.execute("SELECT * FROM tasks WHERE status='running' ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def totals(self, since_iso):
        q = ("SELECT provider, COUNT(*) AS n, SUM(COALESCE(cost_usd,0)) AS cost, SUM(COALESCE(input_tokens,0)) AS inp,"
             " SUM(COALESCE(cached_tokens,0)) AS cached, SUM(COALESCE(output_tokens,0)) AS out"
             " FROM tasks WHERE started >= ? GROUP BY provider")
        return [dict(r) for r in self.conn.execute(q, (since_iso,))]

    # deferred messages and notified events
    def defer(self, msg_ids):
        for m in msg_ids:
            self.conn.execute("INSERT OR IGNORE INTO deferred(msg_id, ts) VALUES (?,?)", (m, now_iso()))

    def undefer(self, msg_ids):
        for m in msg_ids:
            self.conn.execute("DELETE FROM deferred WHERE msg_id=?", (m,))

    def deferred_ids(self):
        return [r["msg_id"] for r in self.conn.execute("SELECT msg_id FROM deferred")]

    def is_notified(self, kind, ref):
        return self.conn.execute("SELECT 1 FROM notified WHERE kind=? AND ref=?", (kind, ref)).fetchone() is not None

    def mark_notified(self, kind, ref):
        self.conn.execute("INSERT OR IGNORE INTO notified(kind, ref, ts) VALUES (?,?,?)", (kind, ref, now_iso()))

    # peer requests
    def peer_submit(self, to_provider, prompt, key=None, major=False, from_provider=None):
        if to_provider not in PROVIDERS:
            raise LabError("--to: claude ή codex.")
        pid = "P-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        self.conn.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, key, major, prompt, status)"
                          " VALUES (?,?,?,?,?,?,?,?)",
                          (pid, now_iso(), from_provider, to_provider, key, int(bool(major)), prompt, "queued"))
        return pid

    def peer_claim(self, pid=None):
        with self.tx() as c:
            if pid:
                r = c.execute("SELECT * FROM peer_requests WHERE status='queued' AND id=?", (pid,)).fetchone()
            else:
                r = c.execute("SELECT * FROM peer_requests WHERE status='queued' ORDER BY ts LIMIT 1").fetchone()
            if r is None:
                return None
            c.execute("UPDATE peer_requests SET status='running' WHERE id=?", (r["id"],))
        return dict(r)

    def peer_finish(self, pid, status, answer=None, error=None, cost=None):
        self.conn.execute("UPDATE peer_requests SET status=?, answer=?, error=?, cost_usd=?, ts_done=? WHERE id=?",
                          (status, answer, error, cost, now_iso(), pid))

    def peer(self, pid):
        r = self.conn.execute("SELECT * FROM peer_requests WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------- helpers

def fmt_ts(ts):
    if not ts:
        return "-"
    return dt.datetime.fromtimestamp(ts).astimezone().strftime("%d/%m %H:%M")


def clip(text, n):
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + f" … (+{len(text) - n} chars)"


def parse_reset(text, now_ts=None):
    """Best effort: when does a usage limit reset? Returns a unix timestamp (default: one hour from now)."""
    now_ts = now_ts or time.time()
    t = text or ""
    lo, hi = now_ts + 300, now_ts + 8 * 86400
    m = re.search(r"(?:in|after)\s+((?:\d+\s*(?:days?|d|hours?|hrs?|h|minutes?|mins?|m)\s*,?\s*(?:and\s*)?)+)", t, re.I)
    if m:
        secs = 0
        for num, unit in re.findall(r"(\d+)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m)", m.group(1), re.I):
            u = unit.lower()
            secs += int(num) * (86400 if u.startswith("d") else 3600 if u.startswith("h") else 60)
        if secs:
            return min(max(now_ts + secs, lo), hi)
    m = re.search(r"(?:resets?|try again at|until)\s+(?:at\s+)?(?:(?P<mon>[A-Z][a-z]{2,8})\.?\s+(?P<day>\d{1,2}),?\s+"
                  r"(?:at\s+)?)?(?P<h>\d{1,2})(?::(?P<mi>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)?\s*(?:\((?P<tz>[^)]+)\))?",
                  t, re.I)
    if m:
        try:
            tz = None
            if m.group("tz"):
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(m.group("tz").strip())
            base = dt.datetime.fromtimestamp(now_ts, tz) if tz else dt.datetime.fromtimestamp(now_ts).astimezone()
            h, mi = int(m.group("h")), int(m.group("mi") or 0)
            ap = (m.group("ap") or "").lower().replace(".", "")
            if ap == "pm" and h < 12:
                h += 12
            if ap == "am" and h == 12:
                h = 0
            cand = base.replace(hour=h, minute=mi, second=0, microsecond=0)
            if m.group("mon"):
                mon = dt.datetime.strptime(m.group("mon")[:3].title(), "%b").month
                cand = cand.replace(month=mon, day=int(m.group("day")))
                if cand.timestamp() < now_ts - 86400:
                    cand = cand.replace(year=cand.year + 1)
            elif cand.timestamp() <= now_ts:
                cand += dt.timedelta(days=1)
            return min(max(cand.timestamp(), lo), hi)
        except Exception:
            pass
    return now_ts + 3600


def split_status(text):
    """The coordinator may end its final message with 'STATUS: done|failed|waiting_approval'."""
    text = (text or "").strip()
    m = STATUS_LINE_RE.search(text)
    if m:
        return text[:m.start()].rstrip(), m.group(1).lower()
    return text, "done"


def _retry_locked(fn, tries=20, wait=15.0):
    """Run fn, retrying while SQLite reports 'database is locked' (up to ~5 minutes)."""
    for i in range(tries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) or i == tries - 1:
                raise
            time.sleep(wait)


CHAT_KINDS = ("message", "escalation")


def lane_of(item):
    """'chat': the researcher's coordinator (one at a time); 'worker': everything that may run in parallel."""
    return "chat" if item["kind"] in CHAT_KINDS else "worker"


def item_key(item):
    """Identity of a work item, so the same item is never processed twice at once."""
    if item["kind"] == "perm_answer":
        return "perm_answer:" + item["thread_id"]
    if item.get("job_id"):
        return "job:" + item["job_id"]
    if item.get("event_ref"):
        return "run:" + item["event_ref"]
    ids = item["msg_ids"] + item["req_ids"] + list(item.get("perm_ids") or []) + \
        [str(i) for i in item.get("esc_ids") or []]
    return item["kind"] + ":" + ",".join(ids)


def which(name, configured=None):
    return configured or shutil.which(name) or name


# ---------------------------------------------------------------- providers

def _empty_result():
    return {"ok": False, "quota": False, "transient": False, "text": "", "error": "", "session_id": None,
            "cost": None, "usage": {}, "ttl_s": 300, "context_tokens": None, "reset_until": None, "denials": [],
            "paid_credit": None, "model": None, "limits": []}


def _resume_rejected(error, started):
    """Allow a fresh attempt only for explicit session lookup/validation failures.

    Unknown errors and failures after any observed work are deliberately not replayed.
    """
    return not started and bool(re.search(
        r"(?:no conversation found with session id|"
        r"(?:session|thread) id[^\n]{0,100}(?:not found|does not exist|invalid|expired)|"
        r"(?:invalid|expired) (?:session|thread) id)", error, re.I))


def _event_time(value):
    """Strict timestamp for legacy-event reconciliation; unknown never means now."""
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.timestamp() if stamp.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


_PROCS = {}  # job id -> running provider process (so a cancel can stop it)
_PROCS_LOCK = threading.Lock()


def _exec(cmd, cwd, env, timeout_s, job=None):
    """subprocess.run with the process registered under `job` while it runs."""
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env=env)
    if job:
        with _PROCS_LOCK:
            _PROCS[job] = p
    try:
        out, err = p.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise
    finally:
        if job:
            with _PROCS_LOCK:
                _PROCS.pop(job, None)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def stop_job(job):
    with _PROCS_LOCK:
        p = _PROCS.get(job)
    if p and p.poll() is None:
        p.terminate()
        return True
    return False


def run_claude(prompt, cwd, model, effort=None, session_id=None, system_append=None, budget=None, timeout_s=3600,
               peer=False, env=None, job=None):
    exe = which("claude", os.environ.get("QRL_CLAUDE_BIN"))
    # stream-json: besides the final result it carries rate_limit_event lines (window, utilization, reset time,
    # isUsingOverage = paid extra usage), which make failover exact instead of guessing from the error text.
    cmd = [exe, "-p", prompt, "--output-format", "stream-json", "--verbose", "--model", model,
           "--permission-prompts", "none"]
    if effort:
        cmd += ["--effort", effort]
    if budget:
        cmd += ["--max-budget-usd", str(budget)]
    if peer:  # read-only co-researcher: only reading and web tools exist in this run
        tools = "Read,Grep,Glob,WebSearch,WebFetch"
        cmd += ["--tools", tools, "--allowedTools", tools, "--permission-mode", "dontAsk"]
    else:
        cmd += ["--permission-mode", "auto"]
    if system_append:
        cmd += ["--append-system-prompt", system_append]
    if session_id:
        cmd += ["--resume", session_id]
    res = _empty_result()
    res["model"] = model
    try:
        p = _exec(cmd, cwd, env, timeout_s, job)
    except subprocess.TimeoutExpired:
        res.update(error=f"timeout after {timeout_s}s", transient=False)
        return res
    except OSError as e:
        res.update(error=f"cannot start claude: {e}")
        return res
    data, limits, started = None, [], False
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") in ("assistant", "user", "tool_use", "tool_result"):
            started = True
        if ev.get("type") == "rate_limit_event" and isinstance(ev.get("rate_limit_info"), dict):
            limits.append(ev["rate_limit_info"])
        elif ev.get("type") == "result" or ("result" in ev and "session_id" in ev):
            data = ev
    res["limits"] = limits
    if any(li.get("isUsingOverage") for li in limits):
        res["paid_credit"] = True
    if data is None:
        res["error"] = clip((p.stderr or p.stdout or f"exit {p.returncode}"), 800)
        res["quota"] = bool(QUOTA_RE.search(res["error"]))
        res["transient"] = not res["quota"] and bool(TRANSIENT_RE.search(res["error"]))
        res["resume_rejected"] = bool(session_id) and _resume_rejected(res["error"], started)
        return res
    text = data.get("result") or ""
    usage = data.get("usage") or {}
    cc = usage.get("cache_creation") or {}
    iters = usage.get("iterations") or []
    last = iters[-1] if iters else usage
    res.update(text=text, session_id=data.get("session_id"), cost=data.get("total_cost_usd"),
               denials=data.get("permission_denials") or [])
    res["usage"] = {"input": usage.get("input_tokens"), "cached": usage.get("cache_read_input_tokens"),
                    "cache_write": usage.get("cache_creation_input_tokens"), "output": usage.get("output_tokens")}
    res["context_tokens"] = sum(int(last.get(k) or 0) for k in
                                ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    res["ttl_s"] = 3600 if (cc.get("ephemeral_1h_input_tokens") or 0) > 0 else 300
    failed = bool(data.get("is_error")) or p.returncode != 0 or data.get("subtype") not in (None, "success")
    if failed:
        res["error"] = clip(text or p.stderr or data.get("subtype") or f"exit {p.returncode}", 800)
        rejected = [li for li in limits if li.get("status") == "rejected"]
        res["quota"] = bool(rejected) or bool(QUOTA_RE.search(res["error"]))
        res["transient"] = not res["quota"] and bool(TRANSIENT_RE.search(res["error"]))
        res["resume_rejected"] = bool(session_id) and _resume_rejected(
            res["error"], started or any(v for v in res["usage"].values()))
        if res["quota"]:
            resets = [_epoch(li.get("resetsAt")) for li in rejected if li.get("resetsAt")]
            res["reset_until"] = max(resets) if resets else parse_reset(res["error"])
    else:
        res["ok"] = True
    return res


def _epoch(v):
    """resetsAt may come as epoch seconds, epoch milliseconds or ISO text."""
    try:
        f = float(v)
        return f / 1000.0 if f > 1e12 else f
    except (TypeError, ValueError):
        try:
            return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return time.time() + 3600


def run_codex(prompt, cwd, model=None, effort=None, session_id=None, sandbox="workspace-write", network=True,
              timeout_s=3600, env=None, outdir=None, job=None):
    exe = which("codex", os.environ.get("QRL_CODEX_BIN"))
    outdir = outdir or os.path.join(cwd, ".lab", "tmp")
    os.makedirs(outdir, exist_ok=True)
    out_file = os.path.join(outdir, f"codex-last-{os.getpid()}-{threading.get_ident()}.txt")
    if os.path.exists(out_file):
        os.remove(out_file)
    cmd = [exe, "exec"] + (["resume", session_id] if session_id else [])
    cmd += ["--json", "-o", out_file, "--skip-git-repo-check",
            "-c", f'sandbox_mode="{sandbox}"', "-c", 'approval_policy="never"']
    if sandbox == "workspace-write":
        cmd += ["-c", f"sandbox_workspace_write.network_access={'true' if network else 'false'}"]
    if model:
        cmd += ["-m", model]
    if effort:
        cmd += ["-c", f'model_reasoning_effort="{effort}"']
    cmd += [prompt]
    res = _empty_result()
    res["model"] = model or "codex-default"
    try:
        p = _exec(cmd, cwd, env, timeout_s, job)
    except subprocess.TimeoutExpired:
        res["error"] = f"timeout after {timeout_s}s"
        return res
    except OSError as e:
        res["error"] = f"cannot start codex: {e}"
        return res
    thread_id, errors, failed_msg, usage, last_agent = None, [], None, {}, ""
    started = False
    for line in (p.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "turn.started" or (t or "").startswith("item."):
            started = True
        if t == "thread.started":
            thread_id = ev.get("thread_id")
        elif t == "turn.completed":
            u = ev.get("usage") or {}
            for k_out, k_in in (("input", "input_tokens"), ("cached", "cached_input_tokens"),
                                ("output", "output_tokens")):
                usage[k_out] = (usage.get(k_out) or 0) + int(u.get(k_in) or 0)
            usage["last_input"] = int(u.get("input_tokens") or 0)
        elif t == "turn.failed":
            err = ev.get("error") or {}
            failed_msg = err.get("message") if isinstance(err, dict) else str(err)
        elif t == "error":
            errors.append(str(ev.get("message", "")))
        elif t == "item.completed":
            item = ev.get("item") or {}
            if item.get("type") == "agent_message":
                last_agent = item.get("text") or item.get("content") or last_agent
    text = ""
    if os.path.exists(out_file):
        with open(out_file, encoding="utf-8") as f:
            text = f.read()
        os.remove(out_file)
    text = text or (last_agent if isinstance(last_agent, str) else "")
    res.update(session_id=thread_id or session_id, text=text, ttl_s=None)
    res["usage"] = {"input": usage.get("input"), "cached": usage.get("cached"), "cache_write": None,
                    "output": usage.get("output")}
    res["context_tokens"] = usage.get("last_input")
    if p.returncode != 0 or failed_msg:
        fatal = [e for e in errors if not e.startswith("Reconnecting")]
        res["error"] = clip(failed_msg or (fatal[-1] if fatal else "") or (errors[-1] if errors else "") or
                            p.stderr or f"exit {p.returncode}", 800)
        res["quota"] = bool(QUOTA_RE.search(res["error"]))
        res["transient"] = not res["quota"] and bool(TRANSIENT_RE.search(res["error"]))
        res["resume_rejected"] = bool(session_id) and _resume_rejected(
            res["error"], started or bool(usage) or bool(text))
        if res["quota"]:
            res["reset_until"] = parse_reset(res["error"])
    else:
        res["ok"] = True
    return res


# ---------------------------------------------------------------- the dispatcher

class Dispatcher:
    def __init__(self, root=None):
        self.root = os.path.abspath(root or lab_root())
        self.lab = LabDB(os.path.join(self.root, ".lab", "lab.db"))
        self.dd = DispatchDB(dispatch_db_path(self.root))
        self.work = W.Work(self.dd.conn, self.root)
        self.prompts = os.path.join(self.root, "prompts")
        self._last_index = 0.0

    def close(self):
        self.dd.close()
        try:
            self.lab.close()
        except Exception:
            pass

    # ---- context pack
    def _read(self, rel, limit=None):
        p = os.path.join(self.root, rel)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        return txt if limit is None else clip(txt, limit)

    def static_prompt(self):
        return self._read("prompts/coordinator.md") or ""

    def build_prompt(self, provider, item, fresh, note_lines):
        s = self.dd.settings()
        reply_id = item["reply_to"]
        job = item.get("job_id")
        role = "the chat coordinator" if lane_of(item) == "chat" else f"parallel worker {job}"
        head = (f"[QRL-Lab task · you are {role} ({LABEL[provider]}) · job {job or '-'} · thread {item['thread_id']} · "
                f"reply-to {reply_id} · author for your posts: coordinator · co-researcher: {OTHER[provider]}]")
        parts = [head]
        if provider == "codex":  # Codex has no system-prompt flag: the static part goes first (stable prefix)
            parts.insert(0, self.static_prompt())
        if fresh:
            state = self._read("docs/STATE.md")
            n_lines = len(state.splitlines()) if state else 0
            parts.append("## docs/STATE.md\n" + (state.strip() if state else "(missing: create it from the template "
                                                                              "in prompts/STATE.template.md)"))
            if n_lines > int(s["state_max_lines"]):
                note_lines.append(f"docs/STATE.md has {n_lines} lines: condense it to ≤{s['state_max_lines']}.")
            hist = self.lab.thread(item["thread_id"])
            hist = [m for m in hist if m["id"] not in item["msg_ids"]][-int(s["thread_messages"]):]
            if hist:
                lines = [f"- {m['id']} · {m['author']} · {m['kind']}: {clip(m['body'], 700)}" for m in hist]
                parts.append("## Thread so far (latest messages, clipped; full text: python3 tools/labq.py show <id>"
                             " --full)\n" + "\n".join(lines))
        if lane_of(item) == "chat":
            try:  # bounded memory lookup (J261): pointers only; failures never block the run
                import convo_context
                mem = convo_context.relevant(item["text"], self.root, max_chars=1500)
            except Exception:
                mem = ""
            if mem:
                parts.append("## Possibly relevant memory (pointers; check before claiming, and before appending to any md file run"
                             " `python3 tools/md_dedupe.py check <file> \"<text>\"`)\n" + mem)
        parts.append("## New input\n" + item["text"])
        others = self.work.summary_lines(exclude=job)
        parts.append("## Parallel work now (python3 tools/work.py status)\n" +
                     ("\n".join(others) if others else "No other job is running."))
        if note_lines:
            parts.append("## Notes from the dispatcher\n" + "\n".join(f"- {n}" for n in note_lines))
        return "\n\n".join(p for p in parts if p)

    # ---- work discovery
    def _system_thread(self):
        """Root message for events that belong to no thread (author 'dispatcher')."""
        r = self.lab.conn.execute("SELECT id FROM messages WHERE author='dispatcher' AND kind='status' AND"
                                  " id=thread_id ORDER BY ts DESC LIMIT 1").fetchone()
        if r:
            return r["id"]
        with self.lab.tx() as c:
            mid = LabDB._new_id(c, "messages", "id", "M")
            t = now_iso()
            c.execute("INSERT INTO messages(id, ts, thread_id, reply_to, author, kind, title, body, status, updated_at)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (mid, t, mid, None, "dispatcher", "status", "Συμβάντα συστήματος",
                       "Εδώ γράφει ο dispatcher για συμβάντα χωρίς δικό τους θέμα (τέλος πειραμάτων, αποφάσεις).",
                       None, t))
            LabDB._audit(c, "dispatcher", "system_thread", mid)
        return mid

    def find_work(self, lane=None, busy=()):
        """The first work item (of `lane`, if given) whose key is not in `busy` (items already being processed)."""
        for item in self._candidates():
            if (lane is None or lane_of(item) == lane) and item_key(item) not in busy:
                return item
        return None

    def _candidates(self):
        """Every pending work item, in priority order (a generator: callers stop at the first one they can take)."""
        # 1. researcher messages
        deferred = set(self.dd.deferred_ids())
        rows = [dict(r) for r in self.lab.conn.execute(
            "SELECT * FROM messages WHERE author='researcher' AND status IN ('new','delivered','acknowledged',"
            "'in_progress') ORDER BY ts, id")]
        rows = [m for m in rows if m["status"] in ("new", "delivered") or m["id"] in deferred]
        if rows:
            tid = rows[0]["thread_id"]
            batch = [m for m in rows if m["thread_id"] == tid]
            forced = None
            texts = []
            for m in batch:
                body = m["body"]
                mm = MENTION_RE.match(body)
                if mm:
                    forced = mm.group(1).lower()
                    body = body[mm.end():]
                if m.get("edit_note"):
                    body = LabDB.EDIT_NOTE + "\n" + body
                texts.append(f"{m['id']} ({m['kind']}): {body}")
            yield {"kind": "message", "thread_id": tid, "msg_ids": [m["id"] for m in batch],
                   "reply_to": batch[-1]["id"], "forced": forced, "text": "\n\n".join(texts), "req_ids": []}
        # 1b. agents' escalations to the chat coordinator (could not agree, or need the researcher)
        esc = self.work.escalations()
        if esc and self._escalations_due(esc):
            src = self.work.job(esc[0]["from_job"]) or {}
            tid = src.get("thread_id") if src.get("thread_id") and self.lab.message(src["thread_id"]) \
                else self._system_thread()
            lines = [f"- from {m['from_job']}: {m['body']}" for m in esc]
            yield {"kind": "escalation", "thread_id": tid, "msg_ids": [], "reply_to": src.get("reply_to") or tid,
                   "forced": None, "req_ids": [], "esc_ids": [m["id"] for m in esc],
                   "text": "Parallel jobs escalated to you (you may answer each with python3 tools/work.py say <job> "
                           "\"...\"; ask the researcher only if it is the researcher's call):\n" + "\n".join(lines)}
        # 2. decisions
        _, decs = self.lab.undelivered()
        for r in decs:
            tid = r["thread_id"] if r["thread_id"] and self.lab.message(r["thread_id"]) else self._system_thread()
            note = f' Researcher note: "{r["decision_text"]}"' if r["decision_text"] else ""
            text = (f"Researcher decision on {r['id']} [{r['kind']}/{r['scope']}] \"{r['title']}\": {r['state']}."
                    f"{note}\nAct only within what this decision allows (python3 tools/labq.py request {r['id']}),"
                    f" then report in this thread.")
            yield {"kind": "decision", "thread_id": tid, "msg_ids": [], "reply_to": tid, "forced": None,
                   "text": text, "req_ids": [r["id"]], "title": f"{r['id']}: {r['title']}"}
        # 2b. answers to blocked (headless) permission requests
        perm_store.withdraw_deny_rules(self.root)
        answers = perm_store.undelivered_answers(self.root)
        threads = {}
        for answer in answers:
            tid = answer.get("thread_id")
            tid = tid if tid and self.lab.message(tid) else self._system_thread()
            threads.setdefault(tid, []).append(answer)
        for tid, ans in threads.items():
            if any(j["origin"] == "perm_answer" and j["thread_id"] == tid for j in self.work.active()):
                continue
            last = self.dd.get("perm_last_wake:" + tid)
            if last and time.time() - float(last) < float(self.dd.get("escalation_debounce_s")):
                continue
            lines = [f"- {a['tool']}: {a['detail'][:300]} -> {'APPROVED' if a['state'] == 'approved' else 'DENIED'}"
                     + (f" ({a['message']})" if a.get("message") else "") for a in ans]
            text = ("The researcher answered permission requests that were blocked in an earlier headless task:\n"
                    + "\n".join(lines) + "\nIf approved, retry that action once only when no deny rule forbids it; "
                    "if denied, do not retry it. Report in this thread.")
            yield {"kind": "perm_answer", "thread_id": tid, "msg_ids": [], "reply_to": tid, "forced": None,
                   "text": text, "req_ids": [], "perm_ids": [a["id"] for a in ans]}
        # 3. finished experiment batches
        groups = {}
        for run in self.lab.runs(limit=500):
            groups.setdefault(run["request_id"], []).append(run)
        # The recent window discovers candidates, never the identity/completeness of a batch.
        # Otherwise each evicted old run changes event_ref and wakes the coordinator again.
        for rid in groups:
            groups[rid] = [dict(r) for r in self.lab.conn.execute(
                "SELECT * FROM runs WHERE request_id=?", (rid,))]
        initialized = self.dd.get("events_initialized") == "1"
        for rid, runs in sorted(groups.items(), key=lambda kv: max(r["created"] for r in kv[1])):
            if any(r["status"] in ("starting", "running") for r in runs):
                continue
            ref = rid + ":" + ",".join(sorted(r["run_id"] for r in runs))
            if self.dd.is_notified("runs", ref):
                continue
            # Repair legacy rolling-window refs only when all current runs predate
            # a recorded notice. A subset alone cannot distinguish a genuine new wave.
            prefix = rid + ":"
            run_ids = {r["run_id"] for r in runs}
            created = [_event_time(r["created"]) for r in runs]
            legacy = self.dd.conn.execute(
                "SELECT ref,ts FROM notified WHERE kind='runs' AND substr(ref,1,?)=?",
                (len(prefix), prefix))
            if all(created) and any(
                    set(n["ref"][len(prefix):].split(",")).issubset(run_ids)
                    and max(created) < (_event_time(n["ts"]) or 0) for n in legacy):
                self.dd.mark_notified("runs", ref)
                continue
            if not initialized:
                self.dd.mark_notified("runs", ref)
                continue
            req = self.lab.request(rid) or {}
            tid = req.get("thread_id") if req.get("thread_id") and self.lab.message(req["thread_id"]) \
                else self._system_thread()
            lines = [f"- {r['run_id']} entry {r['entry']} attempt {r['attempt']} {r['name'] or ''}: {r['status']},"
                     f" exit {r['exit_code']}, dir {r['run_dir']}" for r in sorted(runs, key=lambda r: r['entry'])]
            text = (f"All runs of approved request {rid} have ended:\n" + "\n".join(lines) +
                    "\nCheck the outputs (summaries by script, not by reading whole logs), report the results with "
                    "pointers, update docs/EXPERIMENTS.md and docs/STATE.md, and propose the next step. Do not start new "
                    "runs without an approval.")
            yield {"kind": "run_event", "thread_id": tid, "msg_ids": [], "reply_to": tid, "forced": None,
                    "text": text, "req_ids": [], "event_ref": ref}
        if not initialized:
            self.dd.conn.execute("INSERT OR REPLACE INTO settings(key, value, updated_at, updated_by)"
                                 " VALUES ('events_initialized','1',?,'dispatcher')", (now_iso(),))
        # 4. jobs handed to workers by the chat coordinator
        for j in self.work.queued_spawns():
            tid = j["thread_id"] if j["thread_id"] and self.lab.message(j["thread_id"]) else self._system_thread()
            text = f"Job {j['id']} from the chat coordinator ({j['created_by']}): {j['title']}\n\n{j['brief']}"
            if j["result"] == "interrupted":
                text += ("\n\n(An earlier attempt of this job was interrupted by a dispatcher restart: check "
                         "`git status` and the files it may have touched before you continue.)")
            yield {"kind": "job", "thread_id": tid, "msg_ids": [], "reply_to": j["reply_to"] or tid,
                   "forced": j["provider"], "text": text, "req_ids": [], "job_id": j["id"], "title": j["title"],
                   "parent_msgs": json.loads(j["parent_msgs"] or "[]")}

    # ---- one task
    def provider_order(self, item):
        s = self.dd.settings()
        first = item.get("forced") or s["coordinator"]
        order = [first]
        if s["failover"] == "1" and not item.get("forced"):
            order.append(OTHER[first])
        return [p for p in order if self.dd.available(p)], order

    def _post(self, reply_to, body, kind="status", author="coordinator"):
        try:
            self.lab.post(author, researcher_text(body), reply_to, kind=kind)
        except LabError as e:
            print(f"dispatcher: cannot post to {reply_to}: {e}", file=sys.stderr, flush=True)

    def _set_status(self, msg_ids, status):
        for mid in msg_ids:
            try:
                if (self.lab.message(mid) or {}).get("status") == "editing":
                    continue  # the researcher is editing it: the edit freeze wins over every dispatcher status
                self.lab.set_status(mid, status, actor="dispatcher")
            except LabError:
                pass

    def _journal(self, line):
        d = os.path.join(self.root, "docs", "journal")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, dt.date.today().isoformat() + ".md")
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8") as f:
            if new:
                f.write(f"# Journal {dt.date.today().isoformat()} (written by tools/dispatcher.py)\n\n")
            f.write(line.rstrip() + "\n")

    def _session_for(self, item, provider):
        if lane_of(item) != "chat":
            return None  # parallel workers never share (or resume) the thread's session
        s = self.dd.settings()
        sess = self.dd.session(item["thread_id"], provider)
        if not sess:
            return None
        ttl = sess["ttl_s"] if provider == "claude" else float(s["codex_resume_window_s"])
        age = time.time() - sess["last_used"]
        too_big = (sess["context_tokens"] or 0) > int(s["resume_max_tokens"])
        return sess["session_id"] if age < 0.9 * ttl and not too_big else None

    def _run_provider(self, provider, item, notes, session_id):
        s = self.dd.settings()
        timeout_s = int(float(s["task_timeout_min"]) * 60)
        prompt = self.build_prompt(provider, item, fresh=session_id is None, note_lines=list(notes))
        job = item.get("job_id")
        env = dict(os.environ, QRL_COORDINATOR=provider, QRL_LAB_DIR=self.root, QRL_JOB=job or "",
                   QRL_REPLY_TO=item["reply_to"] or "")
        budget = s["chat_budget_usd"] if lane_of(item) == "chat" else s["max_budget_usd"]
        if provider == "claude":
            model = (s["events_model"] or s["peer_claude_model"]) if item["kind"] == "perm_answer" else (
                s["events_model"] if item["kind"] == "run_event" and s["events_model"] else s["claude_model"])
            return run_claude(prompt, self.root, model, s["claude_effort"], session_id=session_id,
                              system_append=self.static_prompt(), budget=budget, timeout_s=timeout_s,
                              env=env, job=job)
        return run_codex(prompt, self.root, s["codex_model"] or None, s["codex_effort"] or None,
                         session_id=session_id, timeout_s=timeout_s, env=env, job=job)

    def _cancelled(self, item):
        return bool(item.get("job_id") and (self.work.job(item["job_id"]) or {}).get("cancel"))

    def _active_children(self, msg_ids, exclude=None):
        """Active worker jobs spawned while answering these researcher messages."""
        out = []
        for j in self.work.active("worker"):
            if j["id"] != exclude and set(json.loads(j["parent_msgs"] or "[]")) & set(msg_ids):
                out.append(j)
        return out

    def process(self, item):
        """One work item as one job (C<n> in the chat lane, J<n> for workers): claims are released at the end."""
        lane = lane_of(item)
        jid = item.get("job_id")
        if jid:
            self.work.set_status(jid, "running")
        else:
            lines = (item["text"] or "").strip().splitlines()
            first = item.get("title") or (lines[0] if lines else item["kind"])
            jid = self.work.create(lane, item["kind"], clip(first, 120), thread_id=item["thread_id"],
                                   reply_to=item["reply_to"], parent_msgs=item["msg_ids"], status="running")
            self.work.set_status(jid, "running")
            item["job_id"] = jid
        if item["kind"] == "perm_answer":
            self.dd.conn.execute("INSERT OR REPLACE INTO settings(key,value,updated_at,updated_by) VALUES (?,?,?,?)",
                                 ("perm_last_wake:" + item["thread_id"], str(time.time()), now_iso(), "dispatcher"))
        result = "failed"
        try:
            result = self._process(item)
        finally:
            # a locked database must not leave a ghost job/task marked running (30/10: J171/J172 stalled 4 h)
            _retry_locked(lambda: self._close_job(item, jid, result))
            parents = item.get("parent_msgs") or []
            if lane == "worker" and parents and result != "deferred" and not self._active_children(parents):
                for mid in parents:  # the last parallel job of a request is done: so is the request
                    if (self.lab.message(mid) or {}).get("status") == "in_progress":
                        self._set_status([mid], "done")
        return result

    def _close_job(self, item, jid, result):
        if item["kind"] == "job" and result == "deferred":
            self.dd.conn.execute("UPDATE jobs SET status='queued', started=NULL WHERE id=?", (jid,))
        else:
            self.work.set_status(jid, result if result in ("done", "failed", "deferred", "cancelled") else "failed")
        self.work.finish(jid)
        self.dd.conn.execute("UPDATE tasks SET status='interrupted', ended=? WHERE status='running' AND refs LIKE ?",
                             (now_iso(), f'%"{jid}"%'))

    def _process(self, item):
        available, wanted = self.provider_order(item)
        if item["msg_ids"]:
            for mid in item["msg_ids"]:
                try:
                    self.lab.take(mid, actor="dispatcher")
                except LabError:
                    pass
            self._set_status(item["msg_ids"], "in_progress")
            self.lab.clear_edit_note(item["msg_ids"])
        notes = []
        if item.get("forced") and item["kind"] == "job":
            notes.append(f"The chat coordinator assigned this job to {LABEL[item['forced']]}.")
        elif item.get("forced"):
            notes.append(f"The researcher asked for {LABEL[item['forced']]} for this message.")
        tried = []
        for provider in available:
            if tried:
                prev = tried[-1]
                notes.append(f"{LABEL[prev[0]]} stopped on this task ({clip(prev[1]['error'], 200)}). You take over:"
                             f" check the thread, `git status` and docs/STATE.md before continuing.")
            session_id = self._session_for(item, provider)
            res = self._attempt(provider, item, notes, session_id)
            if self._cancelled(item):
                self._post(item["reply_to"], f"⏹ Η εργασία {item['job_id']} σταμάτησε: ακυρώθηκε.")
                self._set_status(item["msg_ids"], "done")
                self._consume(item)
                self._journal(f"- {time.strftime('%H:%M')} {item['reply_to']} [{provider}] {item['job_id']} cancelled")
                return "cancelled"
            if res["ok"] and not self._paid_credit_stop(provider, res):
                self._finish_ok(provider, item, res)
                return "done"
            tried.append((provider, res))
            if res["ok"]:  # answered, but on paid credits: post the answer, then stop using Claude for a while
                until = time.time() + 3600
                self.dd.mark_exhausted(provider, until, "paid credits in use (allow_paid_credits=0)")
                self._finish_ok(provider, item, res)
                self._post(item["reply_to"], f"ℹ️ Ο {LABEL[provider]} απάντησε με πληρωμένα credits. Οι επόμενες "
                                             f"εργασίες πάνε στον {LABEL[OTHER[provider]]} ως "
                                             f"{dt.datetime.fromtimestamp(until, dt.timezone.utc):%d/%m %H:%M} "
                                             f"UTC (προσωρινή παύση μίας ώρας, όχι γνωστό reset ορίου· "
                                             f"η επιλογή συντονιστή δεν άλλαξε).")
                return "done"
            if res["quota"]:
                until = res["reset_until"] or time.time() + 3600
                self.dd.mark_exhausted(provider, until, res["error"])
                self._post(item["reply_to"], f"⚠️ Ο {LABEL[provider]} έφτασε το όριο χρήσης (ξανά διαθέσιμος περίπου "
                                             f"{fmt_ts(until)})." + (" Αναλαμβάνει ο " + LABEL[OTHER[provider]] + "."
                                                                     if len(available) > len(tried) else ""))
                continue
            # a non-quota failure: do not spend the other model's quota on a broken task
            self._post(item["reply_to"], f"❌ Η εκτέλεση από τον {LABEL[provider]} απέτυχε: {clip(res['error'], 400)}")
            self._set_status(item["msg_ids"], "failed")
            self.dd.undefer(item["msg_ids"])
            self._consume(item)  # never loop on a broken decision or event
            self._journal(f"- {time.strftime('%H:%M')} {item['reply_to']} [{provider}] FAILED: {clip(res['error'], 160)}")
            return "failed"
        # nobody could take it now
        if item["msg_ids"]:
            self.dd.defer(item["msg_ids"])
            self._set_status(item["msg_ids"], "acknowledged")
        waits = [self.dd.provider(p)["until_ts"] for p in wanted if not self.dd.available(p)]
        when = fmt_ts(min(w for w in waits if w)) if any(waits) else "-"
        if not tried or all(r["quota"] for _, r in tried):
            self._post(item["reply_to"], f"⏸ Κανένας διαθέσιμος συντονιστής τώρα ({', '.join(LABEL[p] for p in wanted)}"
                                         f" σε όριο). Το αίτημα περιμένει· συνεχίζει αυτόματα περίπου {when}.")
        return "deferred"

    def _escalations_due(self, esc):
        """Debounce (R-20261029-012): urgent notes (work.py say --urgent) and notes from jobs that already ended wake
        the coordinator at once; routine notes wait until the last escalation wake-up is escalation_debounce_s old."""
        for m in esc:
            src = self.work.job(m["from_job"]) or {}
            if m.get("kind") == "urgent" or src.get("status") not in ("queued", "running"):
                return True
        try:
            gap = float(self.dd.get("escalation_debounce_s") or 0)
        except ValueError:
            gap = float(DEFAULTS["escalation_debounce_s"])
        try:
            last = float(self.dd.get("escalation_last_wake") or 0)
        except ValueError:
            last = 0.0
        return time.time() - last >= gap

    def _consume(self, item):
        for pid in item.get("perm_ids") or []:
            perm_store.mark_delivered(pid, self.root)
        if item["req_ids"]:
            self.lab.mark_delivered(req_ids=item["req_ids"])
        if item.get("event_ref"):
            self.dd.mark_notified("runs", item["event_ref"])
        if item.get("esc_ids"):
            self.work.mark_read(item["esc_ids"])
            self.dd.conn.execute("INSERT OR REPLACE INTO settings(key, value, updated_at, updated_by)"
                                 " VALUES ('escalation_last_wake',?,?,'dispatcher')", (str(time.time()), now_iso()))

    def _paid_credit_stop(self, provider, res):
        return provider == "claude" and bool(res.get("paid_credit")) and self.dd.get("allow_paid_credits") != "1"

    def _attempt(self, provider, item, notes, session_id):
        model = None
        t0 = time.time()
        refs = item["msg_ids"] + item["req_ids"] + ([item["job_id"]] if item.get("job_id") else [])
        task_id = self.dd.task_start(item["kind"], item["thread_id"], refs, provider, model, session_id,
                                     bool(session_id))
        res = self._run_provider(provider, item, notes, session_id)
        if (not res["ok"] and session_id and res.get("resume_rejected")
                and not res["quota"] and not self._cancelled(item)):
            # Explicit pre-work resume rejection: retry once from the context pack.
            self.dd.drop_session(item["thread_id"], provider)
            self.dd.conn.execute("UPDATE tasks SET model=? WHERE id=?", (res.get("model"), task_id))
            self.dd.task_end(task_id, "retry_fresh", res, time.time() - t0, res["error"])
            self.dd.save_limits(provider, res.get("limits"))
            t0 = time.time()
            task_id = self.dd.task_start(item["kind"], item["thread_id"], refs, provider, model, None, False)
            session_id = None
            res = self._run_provider(provider, item, notes, None)
        if not res["ok"] and res["transient"] and not session_id and not self._cancelled(item):
            self.dd.conn.execute("UPDATE tasks SET model=? WHERE id=?", (res.get("model"), task_id))
            self.dd.task_end(task_id, "retry_transient", res, time.time() - t0, res["error"])
            self.dd.save_limits(provider, res.get("limits"))
            time.sleep(float(os.environ.get("QRL_TRANSIENT_WAIT", "60")))
            t0 = time.time()
            task_id = self.dd.task_start(item["kind"], item["thread_id"], refs, provider, model, None, False)
            res = self._run_provider(provider, item, notes, None)
        status = "done" if res["ok"] else ("quota" if res["quota"] else "failed")
        self.dd.conn.execute("UPDATE tasks SET model=? WHERE id=?", (res.get("model"), task_id))
        self.dd.task_end(task_id, status, res, time.time() - t0, res["error"])
        self.dd.save_limits(provider, res.get("limits"))
        res["duration_s"] = time.time() - t0
        return res

    def _finish_ok(self, provider, item, res):
        # Edit freeze: a running task cannot be killed safely (the provider call is a blocking subprocess), so when the
        # researcher began editing (or saved an edit) while it ran, its reply is discarded and the message is re-queued.
        cur = {m: (self.lab.message(m) or {}).get("status") for m in item["msg_ids"]}
        if any(st in ("editing", "new") for st in cur.values()):
            for mid, st in cur.items():
                if st == "editing":
                    self.lab.discard_running_edit(mid)
            self.dd.undefer(item["msg_ids"])
            self._journal(f"- {time.strftime('%H:%M')} {item['reply_to']} [{provider}] reply discarded: message edited while running")
            return
        text, status = split_status(res["text"])
        if res["denials"]:
            forbidden, parked = set(), set()
            for dn in res["denials"]:
                if not isinstance(dn, dict) or not dn.get("tool_name"):
                    continue
                tool, tin = dn["tool_name"], dn.get("tool_input")
                rule = perm_store.deny_rule(tool, tin, self.root)
                if rule:
                    forbidden.add(rule)
                elif perm_store.create(tool, tin, self.root, self.root, source="headless",
                                       thread_id=item["thread_id"]):
                    parked.add(tool)
            if forbidden:
                text += "\n\nΑπαγορεύονται από ρητό κανόνα (" + ", ".join(sorted(forbidden)) + "). " \
                        "Δεν δημιουργείται αίτημα έγκρισης και δεν θα επαναληφθούν."
            if parked:
                text += "\n\n🔐 Εκκρεμεί άδεια στο dashboard (Sudo) για: " + ", ".join(sorted(parked)) + "."
        cost = f" · ≈${res['cost']:.2f} (εκτίμηση)" if isinstance(res.get("cost"), (int, float)) else ""
        who = f" · {item['job_id']}" if lane_of(item) == "worker" and item.get("job_id") else ""
        footer = (f"\n\n— {LABEL[provider]} · {res.get('model') or ''}{who} · {int(res.get('duration_s', 0) // 60)}′"
                  f"{cost}")
        self._post(item["reply_to"], researcher_text(text or "(χωρίς κείμενο)", provider) + footer, kind="reply")
        if item["msg_ids"]:
            current = {m: (self.lab.message(m) or {}).get("status") for m in item["msg_ids"]}
            final = status if status != "done" else None
            if final is None and self._active_children(item["msg_ids"]):
                final = "in_progress"  # parallel workers are still on it; the last one closes the request
            for mid, st in current.items():
                if final:
                    self._set_status([mid], final)
                elif st not in ("waiting_approval", "failed", "done"):
                    self._set_status([mid], "done")
            self.dd.undefer(item["msg_ids"])
        self._consume(item)
        if lane_of(item) == "chat":
            ttl = res["ttl_s"] if res["ttl_s"] else float(self.dd.get("codex_resume_window_s"))
            self.dd.save_session(item["thread_id"], provider, res["session_id"], ttl, res["context_tokens"])
        first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
        self._journal(f"- {time.strftime('%H:%M')} {item['reply_to']} [{provider}/{res.get('model')}] {status}"
                      f"{cost} — {clip(first, 140)}")

    # ---- loop
    def heartbeat(self):
        try:
            with open(os.path.join(self.root, ".lab", "bridge_heartbeat"), "w") as f:
                f.write(str(time.time()))
        except OSError:
            pass

    def maybe_index(self):
        if time.time() - self._last_index < 120:
            return
        self._last_index = time.time()
        try:
            import build_md_index
            build_md_index.build_if_stale(self.root)
        except Exception as e:  # the index must never stop the dispatcher
            print(f"dispatcher: index: {type(e).__name__}: {e}", file=sys.stderr, flush=True)

    def recover(self):
        """After a crash: tasks left 'running' and their messages are retried; spawned jobs are queued again."""
        perm_store.withdraw_deny_rules(self.root)
        for t in [dict(r) for r in self.dd.conn.execute("SELECT * FROM tasks WHERE status='running'")]:
            self.dd.conn.execute("UPDATE tasks SET status='interrupted', ended=? WHERE id=?", (now_iso(), t["id"]))
            ids = [i for i in json.loads(t["refs"] or "[]") if i.startswith("M-")]
            self.dd.defer(ids)
        for j in self.work.active():
            if j["origin"] == "spawn" and not j["cancel"]:
                self.dd.conn.execute("UPDATE jobs SET status='queued', started=NULL, result='interrupted' WHERE id=?",
                                     (j["id"],))
            elif j["status"] == "running" or j["origin"] != "spawn":
                self.work.set_status(j["id"], "interrupted")  # its source item (message, decision...) is found again
        self.dd.conn.execute("DELETE FROM claims")  # nothing runs at start-up: every file is free

    def once(self):
        self.heartbeat()
        if self.dd.get("paused") == "1":
            return None
        item = self.find_work()
        if item is None:
            return None
        available, _ = self.provider_order(item)
        if not available:
            deferred = set(self.dd.deferred_ids())
            if not item["msg_ids"] or all(m in deferred for m in item["msg_ids"]):
                return None  # waiting for a reset; nothing new to say (decisions and events stay queued)
        return self.process(item)

    def run_forever(self, poll=2.0):
        self.recover()
        threading.Thread(target=peer_worker, args=(self.root,), daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        print(f"QRL dispatcher online in {self.root}", flush=True)
        self._busy = {}  # item key -> (lane, thread)
        self._busy_lock = threading.Lock()
        while True:
            try:
                self.maybe_index()
                self.tick()
                time.sleep(poll)
            except Exception as e:
                print(f"dispatcher warning: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                time.sleep(poll * 5)

    def _heartbeat_loop(self, every=5.0):
        """The 'online' signal must not depend on runs ending: it is written by its own thread."""
        while True:
            self.heartbeat()
            time.sleep(every)

    def tick(self):
        """Start what may start now: one chat run if none is running, workers up to max_workers. Never blocks."""
        for jid in self.work.cancel_requested():
            stop_job(jid)
        if self.dd.get("paused") == "1":
            return
        with self._busy_lock:
            for k in [k for k, (_, t) in self._busy.items() if not t.is_alive()]:
                del self._busy[k]
            busy = set(self._busy)
            lanes = [lane for lane, _ in self._busy.values()]
        if "chat" not in lanes:
            item = self.find_work("chat", busy)
            if item is not None and self._startable(item):
                self._spawn_thread("chat", item)
                busy.add(item_key(item))
        free = max(1, int(self.dd.get("max_workers") or 1)) - lanes.count("worker")
        while free > 0:
            item = self.find_work("worker", busy)
            if item is None or not self._startable(item):
                break
            self._spawn_thread("worker", item)
            busy.add(item_key(item))
            free -= 1

    def _startable(self, item):
        available, _ = self.provider_order(item)
        if available:
            return True
        deferred = set(self.dd.deferred_ids())
        if not item["msg_ids"] or all(m in deferred for m in item["msg_ids"]):
            return False  # waiting for a reset; nothing new to say (decisions and events stay queued)
        return True  # process() posts the "nobody available" notice once and defers the messages

    def _spawn_thread(self, lane, item):
        def run():
            d = Dispatcher(self.root)  # own database connections: sqlite connections are not shared across threads
            try:
                d.process(item)
            except Exception as e:
                print(f"dispatcher warning ({lane} {item_key(item)}): {type(e).__name__}: {e}", file=sys.stderr,
                      flush=True)
            finally:
                d.close()
        t = threading.Thread(target=run, daemon=True, name=f"{lane}:{item_key(item)}")
        with self._busy_lock:
            self._busy[item_key(item)] = (lane, t)
        t.start()


# ---------------------------------------------------------------- peers (ask the other model)

def serve_peer(root, req):
    with DispatchDB(dispatch_db_path(root)) as dd:
        return _serve_peer(root, req, dd)


def _serve_peer(root, req, dd):
    s = dd.settings()
    to = req["to_provider"]
    key = req["key"]
    sess = dd.session("peer:" + key, to) if key else None
    ttl = (sess["ttl_s"] if to == "claude" else float(s["codex_resume_window_s"])) if sess else 0
    session_id = sess["session_id"] if (sess and time.time() - sess["last_used"] < 0.9 * ttl
                                      and (sess["context_tokens"] or 0) <= int(s["resume_max_tokens"])) else None
    timeout_s = int(float(s["peer_timeout_min"]) * 60)
    with open(os.path.join(root, "prompts", "peer.md"), encoding="utf-8") as f:
        peer_rules = f.read()
    prompt = peer_rules + "\n\n## Request from the coordinator\n" + req["prompt"]
    t0 = time.time()
    task_id = dd.task_start("peer", "peer:" + (key or req["id"]), [req["id"]], to, None, session_id, bool(session_id))
    if to == "claude":
        model = s["peer_claude_major_model"] if req["major"] else s["peer_claude_model"]
        res = run_claude(prompt, root, model, "high" if req["major"] else "medium", session_id=session_id,
                         budget=s["peer_budget_usd"], timeout_s=timeout_s, peer=True)
    else:
        res = run_codex(prompt, root, s["peer_codex_model"] or None,
                        s["peer_codex_major_effort"] if req["major"] else s["peer_codex_effort"],
                        session_id=session_id, sandbox="read-only", timeout_s=timeout_s)
    status = "done" if res["ok"] else ("quota" if res["quota"] else "failed")
    dd.conn.execute("UPDATE tasks SET model=? WHERE id=?", (res.get("model"), task_id))
    dd.task_end(task_id, status, res, time.time() - t0, res["error"])
    dd.save_limits(to, res.get("limits"))
    if res["quota"]:
        dd.mark_exhausted(to, res["reset_until"] or time.time() + 3600, res["error"])
    if res["ok"]:
        if key:
            dd.save_session("peer:" + key, to, res["session_id"], res["ttl_s"] or float(s["codex_resume_window_s"]),
                            res["context_tokens"])
        dd.peer_finish(req["id"], "done", answer=res["text"], cost=res["cost"])
    else:
        dd.peer_finish(req["id"], "failed", error=res["error"] or "unknown error", cost=res["cost"])
    return res


def peer_worker(root, poll=2.0):
    dd = DispatchDB(dispatch_db_path(root))
    while True:
        try:
            req = dd.peer_claim()
            if req is None:
                time.sleep(poll)
                continue
            if not dd.available(req["to_provider"]):
                p = dd.provider(req["to_provider"])
                dd.peer_finish(req["id"], "failed",
                               error=f"{LABEL[req['to_provider']]} is at its usage limit until {fmt_ts(p['until_ts'])}")
                continue
            serve_peer(root, req)
        except Exception as e:
            print(f"peer worker warning: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            time.sleep(poll * 5)


# ---------------------------------------------------------------- CLI

WINDOW_LABEL = {"five_hour": "5ω", "seven_day": "7ημ", "seven_day_opus": "7ημ Opus", "seven_day_sonnet": "7ημ Sonnet"}


def limits_text(dd, provider):
    parts = []
    for li in dd.limits(provider):
        util = f"{li['utilization'] * 100:.0f}%" if li["utilization"] is not None else li["status"] or "?"
        reset = f" (reset {fmt_ts(li['resets_at'])})" if li["resets_at"] else ""
        paid = " 💳" if li["overage"] else ""
        parts.append(f"{WINDOW_LABEL.get(li['window'], li['window'])} {util}{reset}{paid}")
    return " · ".join(parts)


def single_instance(root):
    path = os.path.join(root, ".lab", "dispatcher.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Another dispatcher is already running (lock .lab/dispatcher.lock).")
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def print_status(root):
    dd = DispatchDB(dispatch_db_path(root))
    s = dd.settings()
    print(f"coordinator={s['coordinator']} failover={s['failover']} paused={s['paused']} "
          f"allow_paid_credits={s['allow_paid_credits']}")
    print(f"claude: model={s['claude_model']} effort={s['claude_effort']} | codex: model={s['codex_model'] or 'default'}"
          f" effort={s['codex_effort']}")
    for p in PROVIDERS:
        st = dd.provider(p)
        extra = f" until {fmt_ts(st['until_ts'])}" if st["state"] != "ok" else ""
        print(f"{p}: {st['state']}{extra}  {limits_text(dd, p)}")
    hb = os.path.join(root, ".lab", "bridge_heartbeat")
    if os.path.exists(hb):
        print(f"heartbeat: {int(time.time() - os.path.getmtime(hb))} s ago")
    print(f"max_workers={s['max_workers']}  active jobs:")
    for line in W.Work(dd.conn, root).summary_lines() or ["  (none)"]:
        print("  " + line)
    for t in dd.recent_tasks(10):
        cost = f"${t['cost_usd']:.2f}" if t["cost_usd"] is not None else "-"
        print(f"  #{t['id']} {t['started']} {t['kind']} {t['provider']}/{t['model']} {t['status']} {cost}"
              f" {t['refs']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=None, help="lab directory (default: $QRL_LAB_DIR or cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("once")
    sub.add_parser("status")
    s = sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")
    s = sub.add_parser("clear")
    s.add_argument("provider", choices=PROVIDERS)
    s = sub.add_parser("exhaust", help="drill: treat a provider as out of quota for N minutes")
    s.add_argument("provider", choices=PROVIDERS)
    s.add_argument("minutes", type=float)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root or lab_root())
    if a.cmd == "run":
        lock = single_instance(root)  # noqa: F841  (kept open for the life of the process)
        Dispatcher(root).run_forever()
    elif a.cmd == "once":
        d = Dispatcher(root)
        d.recover()
        print(d.once() or "idle")
        req = d.dd.peer_claim()
        if req:
            serve_peer(root, req)
    elif a.cmd == "status":
        print_status(root)
    elif a.cmd == "set":
        DispatchDB(dispatch_db_path(root)).set(a.key, a.value)
        print(f"{a.key} = {a.value}")
    elif a.cmd == "clear":
        with DispatchDB(dispatch_db_path(root)) as dd:
            dd.clear(a.provider)
        print(f"{a.provider} marked available")
    elif a.cmd == "exhaust":
        until = time.time() + a.minutes * 60
        with DispatchDB(dispatch_db_path(root)) as dd:
            dd.mark_exhausted(a.provider, until, "drill by the researcher")
        print(f"{a.provider} treated as out of quota until {fmt_ts(until)} (drill)")


if __name__ == "__main__":
    try:
        main()
    except LabError as e:
        sys.exit(str(e))
