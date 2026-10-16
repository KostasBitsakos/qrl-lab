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
import sqlite3
from contextlib import contextmanager

SCHEMA_VERSION = 2

MESSAGE_STATUSES = ("new", "delivered", "acknowledged", "in_progress", "waiting_approval", "done", "failed")
REQ_MODELS = ("haiku", "sonnet", "opus", "codex")
REQ_EFFORTS = ("low", "med", "high")
PAPER_THREAD_TITLE = "Paper — συγγραφή"
PAPER_WRITERS = {"writer-sonnet": "writer · Sonnet", "writer-opus": "writer · Opus",
                 "codex-researcher": "codex-researcher · gpt-6.1-sol"}
PAPER_REVIEWERS = {"codex-reviewer": "codex-reviewer · gpt-6.1-sol", "codex-architect": "codex-architect · gpt-6-astra",
                   "scholar": "scholar (citations)", "writer-opus": "writer · Opus"}
MESSAGE_KINDS = ("message", "proposal", "code_question", "reply", "contribution", "status")
REQUEST_KINDS = ("approval", "question", "proposal", "info")
REQUEST_SCOPES = ("sim", "real", "qpu", "research", "external", "other")
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
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    # column -> type, per table; added idempotently to databases created by older versions
    MIGRATIONS = {
        "messages": {"model": "TEXT", "req_model": "TEXT", "req_effort": "TEXT",
                     "req_writers": "TEXT", "req_reviewers": "TEXT"},
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
    def tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
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
