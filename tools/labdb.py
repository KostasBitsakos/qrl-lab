"""QRL-Lab state store (SQLite, standard library only).

One database, `.lab/lab.db`, holds everything the dashboard, the coordinator and the run launcher must agree on:
  messages   the conversation between the researcher and the agents (two-way)
  requests   approvals / questions / proposals the agents file for the researcher, with validated decisions
  runs       experiment runs started by tools/launch_run.py (only with a matching approval)
  audit      who changed what, when

Every write happens in a short IMMEDIATE transaction, so IDs are unique and state changes are atomic even when the
dashboard, the coordinator and a running experiment touch the database at the same time.
State changes are validated here, not in the callers: an invalid transition raises LabError.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager

SCHEMA_VERSION = 2

MESSAGE_STATUSES = ("new", "delivered", "acknowledged", "in_progress", "waiting_approval", "done", "failed", "editing")
CODEX_MODELS = ("gpt-6-luna", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra",
                "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
CODEX_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
CODEX_MODEL_EFFORTS = {model: CODEX_EFFORTS[:-1] if model.endswith("luna") else CODEX_EFFORTS
                      for model in CODEX_MODELS}
# Keep historical values readable/sendable while accepting explicit Codex routing.
CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1")
REQ_MODELS = ("haiku", "sonnet", "opus", "codex") + CLAUDE_MODELS + CODEX_MODELS
REQ_MODELS = REQ_MODELS + tuple("coordinator:" + m for m in CLAUDE_MODELS + ("gpt-6-luna", "gpt-6-sol", "gpt-6-astra"))
REQ_EFFORTS = CODEX_EFFORTS + ("med",)
PAPER_THREAD_TITLE = "Paper — συγγραφή"
VENUES_THREAD_TITLE = "Συζήτηση συνεδρίων"
VENUES_TAG = "[VENUES]"  # the coordinator routes messages starting with this tag to the scholar
PAPER_WRITERS = {"writer-sonnet": "writer · Sonnet", "writer-opus": "writer · Opus",
                 "codex-researcher": "codex-researcher · gpt-6.1-sol"}
PAPER_REVIEWERS = {"codex-reviewer": "codex-reviewer · gpt-6.1-sol", "codex-architect": "codex-architect · gpt-6-astra",
                   "scholar": "scholar (citations)", "writer-opus": "writer · Opus"}
MESSAGE_KINDS = ("message", "proposal", "code_question", "reply", "contribution", "status")
REQUEST_KINDS = ("approval", "question", "proposal", "info")
REQUEST_SCOPES = ("sim", "real", "qpu", "research", "external", "sudo", "other")
RUN_STATUSES = ("starting", "running", "done", "failed", "stopped")

# Allowed researcher decisions per request kind, and the state each one leads to.
DECISIONS = {
    "approval": {"approve": "approved", "reject": "rejected", "changes": "changes_requested"},
    "proposal": {"approve": "approved", "reject": "rejected", "changes": "changes_requested"},
    "question": {"answer": "answered"},
    "info": {"ack": "acknowledged"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  reply_to TEXT,
  author TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT,
  body TEXT NOT NULL,
  status TEXT,
  updated_at TEXT NOT NULL,
  delivered_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_messages_thread ON messages(thread_id, ts);
CREATE INDEX IF NOT EXISTS ix_messages_status ON messages(status);
CREATE TABLE IF NOT EXISTS message_edits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  old_body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_message_edits ON message_edits(message_id, id);
CREATE TABLE IF NOT EXISTS thread_title_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  old_title TEXT
);
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  author TEXT NOT NULL,
  kind TEXT NOT NULL,
  scope TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  options TEXT NOT NULL,
  blocking INTEGER NOT NULL DEFAULT 0,
  cost TEXT,
  links TEXT,
  thread_id TEXT,
  spec_path TEXT,
  spec_hash TEXT,
  state TEXT NOT NULL DEFAULT 'open',
  decision_text TEXT,
  decided_at TEXT,
  decision_delivered INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_requests_state ON requests(state);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  spec_hash TEXT NOT NULL,
  entry INTEGER NOT NULL,
  attempt INTEGER NOT NULL,
  name TEXT,
  scope TEXT NOT NULL,
  cmd TEXT NOT NULL,
  cwd TEXT NOT NULL,
  run_dir TEXT NOT NULL,
  code_sha TEXT,
  status TEXT NOT NULL,
  pid INTEGER,
  exit_code INTEGER,
  stop_requested INTEGER NOT NULL DEFAULT 0,
  created TEXT NOT NULL,
  started TEXT,
  ended TEXT
);
CREATE INDEX IF NOT EXISTS ix_runs_request ON runs(request_id, entry);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  detail TEXT
);
"""


class LabError(Exception):
    """An invalid request or state transition. The message is safe to show to the user."""


def lab_root():
    return os.environ.get("QRL_LAB_DIR") or os.getcwd()


def lab_dir(root=None):
    return os.path.join(root or lab_root(), ".lab")


def db_path(root=None):
    return os.path.join(lab_dir(root), "lab.db")


def now():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def canonical_hash(obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class LabDB:
    def __init__(self, path=None):
        self.path = path or db_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        if self.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
            self.conn.execute("PRAGMA journal_mode=WAL")
        if not self._schema_current():
            self.conn.executescript(SCHEMA)
            self._migrate()
            self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    def _schema_current(self):
        """Read-only fast path: opening an initialized DB must not need a writer lock."""
        try:
            version = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if not version or version[0] != str(SCHEMA_VERSION):
                return False
            expected = {(kind.lower(), name) for kind, name in
                        re.findall(r"CREATE (TABLE|INDEX) IF NOT EXISTS (\w+)", SCHEMA)}
            existing = {tuple(row) for row in self.conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'index')")}
            if not expected <= existing:
                return False
            for table, wanted in self.MIGRATIONS.items():
                columns = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
                if not wanted.keys() <= columns:
                    return False
            return True
        except sqlite3.Error:
            return False

    # column -> type, per table; added idempotently to databases created by older versions
    MIGRATIONS = {
        "messages": {"model": "TEXT", "req_model": "TEXT", "req_effort": "TEXT",
                     "req_writers": "TEXT", "req_reviewers": "TEXT",
                     "edited_at": "TEXT", "edit_count": "INTEGER NOT NULL DEFAULT 0",
                     "edit_delivered": "INTEGER NOT NULL DEFAULT 0",
                     "edit_prev_status": "TEXT", "edit_note": "INTEGER NOT NULL DEFAULT 0"},
        "requests": {"proposals": "TEXT", "recommended": "INTEGER"},
    }

    def _migrate(self):
        """Idempotent, additive migrations for databases created by older versions."""
        for table, wanted in self.MIGRATIONS.items():
            for col, typ in wanted.items():
                if col in {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}:
                    continue
                try:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                except sqlite3.OperationalError:
                    if col not in {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}:
                        raise  # lost a race with another process that added it: fine

    def close(self):
        self.conn.close()

    @contextmanager
    def tx(self, lock_wait_s=0.0):
        """Write transaction. lock_wait_s > 0: keep retrying BEGIN on 'database is locked' (bounded backoff) up to
        about that many seconds (the last attempt may add one busy_timeout); nothing has run yet, so a retried BEGIN
        is side-effect free."""
        deadline = time.monotonic() + lock_wait_s
        delay = 0.5
        while True:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as e:
                busy = getattr(e, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                if not (busy or "locked" in str(e)) or time.monotonic() >= deadline:
                    raise
                time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
                delay = min(delay * 2, 30.0)
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    # ---------- helpers ----------
    @staticmethod
    def _new_id(c, table, col, prefix):
        day = dt.date.today().strftime("%Y%m%d")
        like = f"{prefix}-{day}-%"
        row = c.execute(f"SELECT {col} FROM {table} WHERE {col} LIKE ? ORDER BY {col} DESC LIMIT 1", (like,)).fetchone()
        n = int(row[0].rsplit("-", 1)[1]) + 1 if row else 1
        return f"{prefix}-{day}-{n:03d}"

    @staticmethod
    def _audit(c, actor, action, target=None, detail=None):
        c.execute("INSERT INTO audit(ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                  (now(), actor, action, target, detail))

    @staticmethod
    def _row(r):
        return dict(r) if r is not None else None

    # ---------- messages ----------
    def researcher_send(self, body, kind="message", thread_id=None, title=None, reply_to=None,
                        req_model=None, req_effort=None, attachments=None, root=None,
                        req_writers=None, req_reviewers=None):
        """attachments: [(filename, bytes)] saved under docs/uploads/<new message id>/ and listed in the body."""
        body = (body or "").strip()
        if not body and not attachments:
            raise LabError("Το μήνυμα είναι κενό.")
        if kind not in ("message", "proposal", "code_question"):
            raise LabError(f"Άγνωστος τύπος μηνύματος: {kind}")
        req_model, req_effort = req_model or None, req_effort or None
        if req_model is not None and req_model not in REQ_MODELS:
            raise LabError(f"Άγνωστο μοντέλο: {req_model}")
        if req_effort is not None and req_effort not in REQ_EFFORTS:
            raise LabError(f"Άγνωστη ένταση: {req_effort}")
        effective_model = req_model[len("coordinator:"):] if str(req_model).startswith("coordinator:") else req_model
        effective_model = "gpt-6-luna" if effective_model == "haiku" else effective_model
        if effective_model in CODEX_MODEL_EFFORTS and req_effort == "ultra" and req_effort not in CODEX_MODEL_EFFORTS[effective_model]:
            raise LabError(f"Η ένταση ultra δεν υποστηρίζεται από το {req_model}.")
        for given, allowed, what in ((req_writers, PAPER_WRITERS, "συγγραφέας"), (req_reviewers, PAPER_REVIEWERS, "reviewer")):
            for x in given or []:
                if x not in allowed:
                    raise LabError(f"Άγνωστος {what}: {x}")
        req_writers = json.dumps(list(req_writers)) if req_writers is not None else None
        req_reviewers = json.dumps(list(req_reviewers)) if req_reviewers is not None else None
        with self.tx() as c:
            if thread_id and not c.execute("SELECT 1 FROM messages WHERE thread_id=? LIMIT 1", (thread_id,)).fetchone():
                raise LabError(f"Δεν υπάρχει θέμα {thread_id}.")
            mid = self._new_id(c, "messages", "id", "M")
            if attachments:
                import shutil
                import uploads
                root_dir = root or lab_root()
                try:
                    body = uploads.body_with_attachments(body, uploads.save_uploads(attachments, root_dir, mid))
                except BaseException:
                    shutil.rmtree(os.path.join(root_dir, "docs", "uploads", uploads.sanitize_filename(mid)),
                                  ignore_errors=True)
                    raise
            t = now()
            c.execute("INSERT INTO messages(id, ts, thread_id, reply_to, author, kind, title, body, status, updated_at,"
                      " req_model, req_effort, req_writers, req_reviewers) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (mid, t, thread_id or mid, reply_to, "researcher", kind, title, body, "new", t,
                       req_model, req_effort, req_writers, req_reviewers))
            self._audit(c, "researcher", "send", mid, kind)
        return mid

    def ensure_thread(self, title, body):
        """Id of the thread whose root message has this title; created (coordinator status note, no delivery) if missing."""
        with self.tx() as c:
            r = c.execute("SELECT id FROM messages WHERE id=thread_id AND title=? LIMIT 1", (title,)).fetchone()
            if r:
                return r["id"]
            mid = self._new_id(c, "messages", "id", "M")
            t = now()
            c.execute("INSERT INTO messages(id, ts, thread_id, reply_to, author, kind, title, body, status, updated_at)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?)", (mid, t, mid, None, "coordinator", "status", title, body, None, t))
            self._audit(c, "coordinator", "thread", mid, title)
            return mid

    def post(self, author, body, reply_to, kind="reply", set_status=None, model=None):
        """An agent writes into a thread. reply_to must be an existing message id."""
        body = (body or "").strip()
        if not body:
            raise LabError("Empty body.")
        raw_body = None
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from replytext import readable  # agents sometimes pass codex/claude JSON output verbatim
        text, was_json = readable(body)
        if was_json:
            raw_body, body = body, text.strip()
        if author == "researcher":
            raise LabError("Agents cannot post as the researcher.")
        if kind not in MESSAGE_KINDS:
            raise LabError(f"Unknown kind {kind}.")
        if set_status and set_status not in MESSAGE_STATUSES:
            raise LabError(f"Unknown status {set_status}.")
        with self.tx() as c:
            parent = c.execute("SELECT * FROM messages WHERE id=?", (reply_to,)).fetchone()
            if parent is None:
                raise LabError(f"Unknown message {reply_to}.")
            mid = self._new_id(c, "messages", "id", "M")
            t = now()
            c.execute("INSERT INTO messages(id, ts, thread_id, reply_to, author, kind, title, body, status, updated_at, model)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (mid, t, parent["thread_id"], reply_to, author, kind, None, body, None, t,
                       (model or "").strip() or None))
            if set_status:
                target = reply_to if parent["author"] == "researcher" else parent["thread_id"]
                c.execute("UPDATE messages SET status=?, updated_at=? WHERE id=? AND author='researcher'",
                          (set_status, t, target))
            self._audit(c, author, "post", mid, f"reply_to={reply_to} status={set_status}")
        if raw_body is not None:
            rawdir = os.path.join(lab_dir(), "raw")
            os.makedirs(rawdir, exist_ok=True)
            with open(os.path.join(rawdir, f"{mid}.json"), "w", encoding="utf-8") as f:
                f.write(raw_body)
        return mid

    def take(self, mid, actor="coordinator"):
        """The coordinator picks up a researcher message: returns it and marks it acknowledged."""
        with self.tx() as c:
            m = c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
            if m is None:
                raise LabError(f"Unknown message {mid}.")
            if m["author"] == "researcher" and m["status"] in ("new", "delivered"):
                c.execute("UPDATE messages SET status='acknowledged', updated_at=? WHERE id=?", (now(), mid))
                self._audit(c, actor, "take", mid)
            thread = [dict(r) for r in c.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY ts, id",
                                                 (m["thread_id"],))]
        return dict(m), thread

    def set_status(self, mid, status, actor="coordinator"):
        if status not in MESSAGE_STATUSES:
            raise LabError(f"Unknown status {status}.")
        with self.tx() as c:
            n = c.execute("UPDATE messages SET status=?, updated_at=? WHERE id=? AND author='researcher'",
                          (status, now(), mid)).rowcount
            if n != 1:
                raise LabError(f"{mid} is not a researcher message.")
            self._audit(c, actor, "status", mid, status)

    def threads(self, limit=50):
        rows = self.conn.execute(
            "SELECT thread_id, MIN(ts) AS started, MAX(ts) AS last, COUNT(*) AS n,"
            " (SELECT title FROM messages m2 WHERE m2.id = m.thread_id) AS title,"
            " (SELECT body FROM messages m2 WHERE m2.id = m.thread_id) AS first_body,"
            " (SELECT status FROM messages m2 WHERE m2.id = m.thread_id) AS root_status,"
            " (SELECT kind FROM messages m2 WHERE m2.id = m.thread_id) AS root_kind"
            " FROM messages m GROUP BY thread_id ORDER BY last DESC, MAX(rowid) DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def search_threads(self, text):
        """Thread ids whose title or any message body contains `text`, ignoring case and Greek accents."""
        import unicodedata

        def norm(s):
            return "".join(c for c in unicodedata.normalize("NFD", (s or "").casefold())
                           if unicodedata.category(c) != "Mn")
        q = norm(text.strip())
        return {r[0] for r in self.conn.execute("SELECT thread_id, title, body FROM messages")
                if q in norm(r[1]) or q in norm(r[2])}

    def thread(self, thread_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM messages WHERE thread_id=? ORDER BY ts, id", (thread_id,))]

    def message(self, mid):
        return self._row(self.conn.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone())

    def researcher_open(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM messages WHERE author='researcher' AND status NOT IN ('done','failed') ORDER BY ts")]

    # ---------- requests ----------
    def ask(self, kind, title, body, author="coordinator", scope="other", options=None, blocking=False,
            cost=None, links=None, thread_id=None, spec=None, spec_store_dir=None, proposals=None, recommended=None):
        if kind not in REQUEST_KINDS:
            raise LabError(f"Unknown request kind {kind}.")
        if scope not in REQUEST_SCOPES:
            raise LabError(f"Unknown scope {scope}.")
        if not (title or "").strip() or not (body or "").strip():
            raise LabError("Title and body are required.")
        allowed = list(DECISIONS[kind].keys())
        options = [o for o in (options or allowed) if o]
        bad = [o for o in options if o not in allowed]
        if bad:
            raise LabError(f"Options {bad} are not valid for kind {kind}; allowed: {allowed}.")
        if spec is not None and kind != "approval":
            raise LabError("A run spec can only be attached to an approval request.")
        proposals = [p.strip() for p in (proposals or []) if p and p.strip()]
        if len(proposals) > 3:
            raise LabError("At most 3 proposals per request.")
        if recommended is not None and not (proposals and 1 <= int(recommended) <= len(proposals)):
            raise LabError("--recommended must be the number (1-based) of one of the proposals.")
        with self.tx() as c:
            rid = self._new_id(c, "requests", "id", "R")
            spec_path = spec_hash = None
            if spec is not None:
                validate_spec(spec)
                if spec.get("scope") != scope:
                    raise LabError(f"Spec scope {spec.get('scope')!r} differs from request scope {scope!r}.")
                spec_hash = canonical_hash(spec)
                store = spec_store_dir or os.path.join(os.path.dirname(self.path), "specs")
                os.makedirs(store, exist_ok=True)
                spec_path = os.path.join(store, f"{rid}.json")
                with open(spec_path, "w", encoding="utf-8") as f:
                    json.dump(spec, f, indent=2, ensure_ascii=False, sort_keys=True)
                os.chmod(spec_path, 0o444)
            c.execute("INSERT INTO requests(id, ts, author, kind, scope, title, body, options, blocking, cost, links,"
                      " thread_id, spec_path, spec_hash, proposals, recommended) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (rid, now(), author, kind, scope, title.strip(), body.strip(), json.dumps(options),
                       int(bool(blocking)), cost, json.dumps(links or []), thread_id, spec_path, spec_hash,
                       json.dumps(proposals, ensure_ascii=False) if proposals else None,
                       int(recommended) if recommended is not None else None))
            self._audit(c, author, "ask", rid, f"{kind}/{scope}")
        return rid

    def decide(self, rid, decision, text="", actor="researcher"):
        if actor != "researcher":
            raise LabError("Only the researcher decides.")
        with self.tx() as c:
            r = c.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
            if r is None:
                raise LabError(f"Δεν υπάρχει αίτημα {rid}.")
            if r["state"] != "open":
                raise LabError(f"Το {rid} έχει ήδη κλείσει ({r['state']}).")
            allowed = json.loads(r["options"])
            if decision not in allowed:
                raise LabError(f"Η απόφαση «{decision}» δεν επιτρέπεται για το {rid} (επιτρέπονται: {allowed}).")
            text = (text or "").strip()
            if decision in ("changes", "answer") and not text:
                raise LabError("Γράψε τι αλλαγές ή ποια απάντηση θέλεις.")
            state = DECISIONS[r["kind"]][decision]
            c.execute("UPDATE requests SET state=?, decision_text=?, decided_at=?, decision_delivered=0 WHERE id=?",
                      (state, text, now(), rid))
            self._audit(c, actor, "decide", rid, f"{decision}: {text[:200]}")
        return state

    def withdraw(self, rid, actor="coordinator", reason=""):
        with self.tx() as c:
            n = c.execute("UPDATE requests SET state='withdrawn', decision_text=?, decided_at=?, decision_delivered=1"
                          " WHERE id=? AND state='open'", (reason, now(), rid)).rowcount
            if n != 1:
                raise LabError(f"{rid} is not open.")
            self._audit(c, actor, "withdraw", rid, reason)

    def request(self, rid):
        return self._row(self.conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone())

    def requests(self, state=None, limit=200):
        if state:
            q, a = "SELECT * FROM requests WHERE state=? ORDER BY ts DESC LIMIT ?", (state, limit)
        else:
            q, a = "SELECT * FROM requests ORDER BY ts DESC LIMIT ?", (limit,)
        return [dict(r) for r in self.conn.execute(q, a)]

    # ---------- delivery to the coordinator (used by the monitor) ----------
    def undelivered(self, include_unacked=False):
        statuses = ("new", "delivered") if include_unacked else ("new",)
        q = "SELECT * FROM messages WHERE author='researcher' AND status IN (%s) ORDER BY ts" % ",".join("?" * len(statuses))
        msgs = [dict(r) for r in self.conn.execute(q, statuses)]
        decs = [dict(r) for r in self.conn.execute(
            "SELECT * FROM requests WHERE state NOT IN ('open','withdrawn') AND decision_delivered=0 ORDER BY decided_at")]
        return msgs, decs

    def mark_delivered(self, msg_ids=(), req_ids=()):
        with self.tx() as c:
            for mid in msg_ids:
                c.execute("UPDATE messages SET status=CASE WHEN status='new' THEN 'delivered' ELSE status END,"
                          " delivered_count=delivered_count+1, updated_at=? WHERE id=?", (now(), mid))
            for rid in req_ids:
                c.execute("UPDATE requests SET decision_delivered=1 WHERE id=?", (rid,))

    # ---------- edit freeze (R-20261028-002 item 3) ----------
    EDIT_NOTE = "[edited by the researcher: re-read the whole message and check your answer against it before replying]"

    def begin_edit(self, mid):
        """Freeze a researcher message while he edits it: status 'editing' (the dispatcher skips it; a task already
        running on it has its reply discarded). The previous status is kept for cancel."""
        with self.tx() as c:
            m = c.execute("SELECT status FROM messages WHERE id=? AND author='researcher'", (mid,)).fetchone()
            if not m:
                raise LabError(f"{mid} is not a researcher message.")
            if m["status"] == "editing":
                return
            c.execute("UPDATE messages SET edit_prev_status=?, status='editing', updated_at=? WHERE id=?",
                      (m["status"], now(), mid))
            self._audit(c, "researcher", "edit_begin", mid, None)

    def cancel_edit(self, mid):
        """Back to the status before editing; a message that was never answered goes back to the queue ('new')."""
        with self.tx() as c:
            m = c.execute("SELECT status, edit_prev_status FROM messages WHERE id=? AND author='researcher'",
                          (mid,)).fetchone()
            if not m or m["status"] != "editing":
                return
            prev = m["edit_prev_status"] or "new"
            if prev not in ("done", "failed", "waiting_approval"):
                prev = "new"
            c.execute("UPDATE messages SET status=?, updated_at=? WHERE id=?", (prev, now(), mid))

    def discard_running_edit(self, mid):
        """The dispatcher threw away a reply for a message under edit: when the edit ends it must be re-queued."""
        with self.tx() as c:
            c.execute("UPDATE messages SET edit_prev_status='new' WHERE id=? AND status='editing'", (mid,))

    def clear_edit_note(self, mids):
        with self.tx() as c:
            for mid in mids:
                c.execute("UPDATE messages SET edit_note=0 WHERE id=?", (mid,))

    def save_edit(self, mid, new_body):
        """End of an edit: body updated, status 'new', the coordinator gets EDIT_NOTE in front of the message."""
        new_body = (new_body or "").strip()
        changed = self.edit_message(mid, new_body)
        if not changed:
            self.cancel_edit(mid)
            return False
        with self.tx() as c:
            c.execute("UPDATE messages SET status='new', edit_note=1, edit_delivered=edit_count, updated_at=? WHERE id=?",
                      (now(), mid))
        return True

    # ---------- edits of the researcher's own messages ----------
    def edit_message(self, mid, new_body, actor="researcher"):
        """Only the researcher (the dashboard) may edit, and only his own messages. The previous text is kept in
        message_edits (the first row is the original). Returns True when the text changed."""
        if actor != "researcher":
            raise LabError("Μόνο ο ερευνητής μπορεί να επεξεργαστεί τα μηνύματά του.")
        new_body = (new_body or "").strip()
        if not new_body:
            raise LabError("Το μήνυμα δεν μπορεί να μείνει κενό.")
        with self.tx() as c:
            m = c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
            if not m:
                raise LabError(f"Δεν υπάρχει μήνυμα {mid}.")
            if m["author"] != "researcher":
                raise LabError("Επεξεργασία επιτρέπεται μόνο σε μηνύματα του ερευνητή.")
            if new_body == m["body"]:
                return False
            t = now()
            c.execute("INSERT INTO message_edits(message_id, ts, old_body) VALUES (?,?,?)", (mid, t, m["body"]))
            seen_by_nobody = m["status"] == "new"  # not delivered yet: the delivery itself carries the new text
            c.execute("UPDATE messages SET body=?, edited_at=?, edit_count=edit_count+1,"
                      " edit_delivered=CASE WHEN ? THEN edit_count+1 ELSE edit_delivered END WHERE id=?",
                      (new_body, t, int(seen_by_nobody), mid))
            self._audit(c, "researcher", "edit", mid, None)
        return True

    def rename_thread(self, thread_id, new_title, actor="researcher"):
        """Researcher-only (dashboard; deliberately no labq command). The title lives on the root message; the old
        title (possibly NULL = derived from the first line) is kept in thread_title_history. True if changed."""
        if actor != "researcher":
            raise LabError("Μόνο ο ερευνητής μπορεί να μετονομάσει θέματα.")
        new_title = " ".join((new_title or "").split())
        if not new_title:
            raise LabError("Ο τίτλος δεν μπορεί να είναι κενός.")
        with self.tx() as c:
            m = c.execute("SELECT title FROM messages WHERE id=? AND thread_id=?", (thread_id, thread_id)).fetchone()
            if not m:
                raise LabError(f"Δεν υπάρχει θέμα {thread_id}.")
            if m["title"] == new_title:
                return False
            c.execute("INSERT INTO thread_title_history(thread_id, ts, old_title) VALUES (?,?,?)",
                      (thread_id, now(), m["title"]))
            c.execute("UPDATE messages SET title=? WHERE id=?", (new_title, thread_id))
            self._audit(c, "researcher", "rename_thread", thread_id, None)
        return True

    def title_history(self, thread_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT ts, old_title FROM thread_title_history WHERE thread_id=? ORDER BY id", (thread_id,))]

    def edit_history(self, mid):
        return [dict(r) for r in self.conn.execute(
            "SELECT ts, old_body FROM message_edits WHERE message_id=? ORDER BY id", (mid,))]

    def undelivered_edits(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM messages WHERE author='researcher' AND edit_count>edit_delivered ORDER BY edited_at")]

    def mark_edits_delivered(self, mids):
        with self.tx() as c:
            for mid in mids:
                c.execute("UPDATE messages SET edit_delivered=edit_count WHERE id=?", (mid,))

    # ---------- runs ----------
    def runs(self, limit=200):
        return [dict(r) for r in self.conn.execute("SELECT * FROM runs ORDER BY created DESC LIMIT ?", (limit,))]

    def run(self, run_id):
        return self._row(self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())

    def request_stop(self, run_id, actor="researcher"):
        with self.tx() as c:
            n = c.execute("UPDATE runs SET stop_requested=1 WHERE run_id=? AND status IN ('starting','running')",
                          (run_id,)).rowcount
            if n != 1:
                raise LabError(f"Το {run_id} δεν τρέχει.")
            self._audit(c, actor, "stop_request", run_id)

    def audit(self, limit=100):
        return [dict(r) for r in self.conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    def record_agent_action(self, actor, action, target, detail):
        """Record structured deputy execution metadata without changing approvals or runs."""
        with self.tx() as c:
            self._audit(c, actor, action, target, json.dumps(detail, ensure_ascii=False))


def paper_requests(reqs, paper_tid):
    """Requests belonging to the paper thread (thread_id match) or titled "Paper (..."."""
    return [r for r in reqs if r.get("thread_id") == paper_tid or str(r.get("title") or "").startswith("Paper (")]


def map_choice(req, choice, note=""):
    """Map a dashboard radio choice to (decision, text) for LabDB.decide. choice is 'p1'..'p3', 'yes', 'no' or 'own'.
    The result is still validated by decide(); this only translates."""
    allowed = json.loads(req["options"])
    note = (note or "").strip()
    props = json.loads(req.get("proposals") or "[]")
    positive = "approve" if "approve" in allowed else ("answer" if "answer" in allowed else None)
    if choice.startswith("p") and choice[1:].isdigit():
        n = int(choice[1:])
        if not 1 <= n <= len(props) or positive is None:
            raise LabError("Μη έγκυρη επιλογή πρότασης.")
        text = f"Επιλέχθηκε η Πρόταση {n}: {props[n - 1]}"
        return positive, text + (f" — σχόλιο: {note}" if note else "")
    if choice == "yes":
        if "approve" not in allowed:
            raise LabError("Η έγκριση δεν επιτρέπεται για αυτό το αίτημα.")
        return "approve", note or "Ναι / έγκριση"
    if choice == "no":
        if "reject" not in allowed:
            raise LabError("Η απόρριψη δεν επιτρέπεται για αυτό το αίτημα.")
        return "reject", note or "Όχι / απόρριψη"
    if choice == "own":
        if not note:
            raise LabError("Γράψε τη δική σου πρόταση.")
        dec = "changes" if "changes" in allowed else ("answer" if "answer" in allowed else None)
        if dec is None:
            raise LabError("Δεν επιτρέπεται δική σου πρόταση για αυτό το αίτημα.")
        return dec, f"Δική μου πρόταση: {note}"
    raise LabError("Διάλεξε μία επιλογή.")


def validate_spec(spec):
    """A run spec is what an approval covers. Keep it explicit; the launcher refuses anything else."""
    if not isinstance(spec, dict):
        raise LabError("Spec must be a JSON object.")
    for key in ("name", "scope", "cwd", "entries"):
        if key not in spec:
            raise LabError(f"Spec is missing '{key}'.")
    if spec["scope"] not in ("sim", "real", "qpu"):
        raise LabError("Spec scope must be sim, real or qpu.")
    if not isinstance(spec["entries"], list) or not spec["entries"]:
        raise LabError("Spec needs a non-empty 'entries' list.")
    for i, e in enumerate(spec["entries"]):
        if not isinstance(e, dict) or not isinstance(e.get("cmd"), list) or not e["cmd"] or \
                not all(isinstance(x, str) for x in e["cmd"]):
            raise LabError(f"Entry {i} needs 'cmd' as a non-empty list of strings (no shell strings).")
    limits = spec.get("limits", {})
    if not isinstance(limits, dict) or not isinstance(limits.get("wall_clock_hours"), (int, float)) \
            or limits["wall_clock_hours"] <= 0:
        raise LabError("Spec needs limits.wall_clock_hours > 0.")
    if spec["scope"] == "real":
        real = spec.get("real") or {}
        for key in ("kube_context", "namespace", "rollback"):
            if not real.get(key):
                raise LabError(f"A real-environment spec needs real.{key}.")
    att = spec.get("max_attempts", 1)
    if not isinstance(att, int) or att < 1 or att > 3:
        raise LabError("max_attempts must be 1, 2 or 3.")
    return True
