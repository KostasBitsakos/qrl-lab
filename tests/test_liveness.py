"""Final infra round: explicit liveness (owner + heartbeat) for task rows, recover() at start-up, fast sweeper."""
import json
import os
import sys
import threading
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import dispatcher as D  # noqa: E402


def make(tmp_path, monkeypatch, **settings):
    monkeypatch.setenv("QRL_LAB_DIR", str(tmp_path))
    monkeypatch.setenv("QRL_DISPATCH_DB", str(tmp_path / "dispatch.db"))
    (tmp_path / ".lab").mkdir(exist_ok=True)
    D.LIVE_TASKS.clear()          # task ids restart at 1 in every fresh test database
    d = D.Dispatcher(str(tmp_path))
    d.dd.set("governor_enabled", "1")
    for k, v in settings.items():
        d.dd.set(k, v)
    return d


def row(d, tid):
    return d.dd.conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()


def test_crash_after_reserve_slot_is_free_after_restart(tmp_path, monkeypatch):
    d1 = make(tmp_path, monkeypatch)
    t = d1.dd.reserve("job", "T", ["J1"], "codex", "worker", cap=1)
    assert t and d1.dd.reserve("job", "T", ["J2"], "codex", "worker", cap=1) is None, "the slot is taken"
    d2 = D.Dispatcher(str(tmp_path))            # the process died after the reserve; a new one starts
    d2.recover()
    assert row(d2, t)["status"] == "interrupted"
    assert d2.dd.reserve("job", "T", ["J2"], "codex", "worker", cap=1) is not None, "free after restart"


def test_sweeper_frees_a_dead_row_in_minutes_not_hours(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch, task_timeout_min="600")      # a 10 h timeout must not delay the sweep
    now = time.time()
    jid = d.work.create("worker", "spawn", "J", "b", status="running")
    c = d.dd.conn
    ins = lambda status, owner, beat, refs="[]": c.execute(
        "INSERT INTO tasks(started, kind, refs, provider, status, lane, owner, beat) VALUES (?,?,?,?,?,?,?,?)",
        (D.now_iso(), "job", refs, "claude", status, "worker", owner, beat)).lastrowid
    alive = ins("running", D.PROC_OWNER, now - 30)
    D.LIVE_TASKS[alive] = threading.current_thread()                            # a live thread of this process owns it
    dead = ins("running", D.PROC_OWNER, now - 400, json.dumps([jid]))          # nobody owns it any more
    gone = ins("running", "999999:1", now)                                      # owner process does not exist
    other = ins("running", f"{os.getppid()}:1", now - 5000)                     # another LIVE process (e.g. inline ask_peer)
    legacy = ins("running", None, None)                                         # older code: only the slow rule applies
    assert d.sweep(now) == 2
    st = {r["id"]: r["status"] for r in c.execute("SELECT id, status FROM tasks")}
    assert st == {alive: "running", dead: "interrupted", gone: "interrupted", other: "running", legacy: "running"}
    assert d.work.job(jid)["status"] == "queued", "its job is queued again"


def test_heartbeat_keeps_live_rows_and_not_rows_of_dead_threads(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    t = d.dd.reserve("job", "T", ["J1"], "claude", "worker")
    assert d.dd.claim_start(t, ["J1"], None, False)
    d.dd.conn.execute("UPDATE tasks SET beat=? WHERE id=?", (time.time() - 1000, t))
    assert d.sweep() == 0, "a late heartbeat alone (process paused) never frees a row whose thread is alive"
    d.dd.beat()                                                     # this (alive) thread owns it: refreshed
    assert time.time() - row(d, t)["beat"] < 5 and d.sweep() == 0
    box = {}

    def worker():                                                   # a thread that claims a row and then dies
        t2 = d.dd.reserve("job", "T", ["J2"], "claude", "worker")
        d.dd.claim_start(t2, ["J2"], None, False)
        box["id"] = t2
    th = threading.Thread(target=worker)
    th.start(); th.join()
    d.dd.conn.execute("UPDATE tasks SET beat=? WHERE id=?", (time.time() - 1000, box["id"]))
    d.dd.beat()                                                     # its thread is gone: not refreshed
    assert time.time() - row(d, box["id"])["beat"] > 900
    assert d.sweep() == 1 and row(d, box["id"])["status"] == "interrupted" and row(d, t)["status"] == "running"


def test_ended_rows_are_disowned_and_slots_reusable(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    t = d.dd.reserve("job", "T", [], "claude", "worker", cap=1)
    d.dd.claim_start(t, [], None, False)
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is None
    d.dd.task_end(t, "done", {}, 1.0)
    assert t not in D.LIVE_TASKS and d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is not None


def test_recover_requeues_unstarted_peers_and_fails_running_ones(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    c = d.dd.conn
    for pid in ("P-never", "P-running"):
        c.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, prompt, status) VALUES (?,?,?,?,?,?)",
                  (pid, D.now_iso(), "claude", "codex", "q", "running"))
    c.execute("INSERT INTO tasks(started, kind, refs, provider, status, lane) VALUES (?,?,?,?,?,?)",
              (D.now_iso(), "peer", json.dumps(["P-running"]), "codex", "running", "peer"))
    D.Dispatcher(str(tmp_path)).recover()
    ps = {r["id"]: (r["status"], r["error"]) for r in c.execute("SELECT id, status, error FROM peer_requests")}
    assert ps["P-never"][0] == "queued"
    assert ps["P-running"][0] == "failed" and "restarted" in ps["P-running"][1]


def test_recover_keeps_rows_of_a_live_foreign_owner(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    c = d.dd.conn
    ins = lambda owner, status="running", refs="[]": c.execute(
        "INSERT INTO tasks(started, kind, refs, provider, status, lane, owner, beat) VALUES (?,?,?,?,?,?,?,?)",
        (D.now_iso(), "peer", refs, "codex", status, "peer", owner, time.time())).lastrowid
    inline = ins(f"{os.getppid()}:1", refs=json.dumps(["P-inline"]))           # an inline ask_peer that is still executing
    old = ins("999999:1")                                                       # the previous dispatcher, dead
    c.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, prompt, status) VALUES (?,?,?,?,?,?)",
              ("P-inline", D.now_iso(), "claude", "codex", "q", "running"))
    D.Dispatcher(str(tmp_path)).recover()
    st = {r["id"]: r["status"] for r in c.execute("SELECT id, status FROM tasks")}
    assert st == {inline: "running", old: "interrupted"}
    assert c.execute("SELECT status FROM peer_requests WHERE id='P-inline'").fetchone()[0] == "running"
    # the slot of the live inline peer still counts against the cap
    assert d.dd.reserve("peer", "T", [], "codex", "peer", cap=1) is None


def test_sweep_transition_is_conditional(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    jid = d.work.create("worker", "spawn", "J", "b", status="running")
    t = d.dd.conn.execute("INSERT INTO tasks(started, kind, refs, provider, status, lane, owner, beat) VALUES (?,?,?,?,?,?,?,?)",
                          (D.now_iso(), "job", json.dumps([jid]), "claude", "running", "worker", D.PROC_OWNER, 0)).lastrowid
    real = d.dd.conn

    class Racy:                      # the owner finishes the row between the sweeper's SELECT and its UPDATE
        def __init__(self, conn):
            self._c = conn
        def execute(self, sql, *a):
            if sql.startswith("UPDATE tasks SET status='interrupted'"):
                self._c.execute("UPDATE tasks SET status='done' WHERE id=?", (t,))
            return self._c.execute(sql, *a)
    d.dd.conn = Racy(real)
    assert d.sweep() == 0, "the row had finished: nothing freed, its job not requeued"
    d.dd.conn = real
    assert d.work.job(jid)["status"] == "running"


def test_sweep_during_completion_does_not_fail_the_run(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    t = d.dd.reserve("peer", "T", ["P-x"], "codex", "peer")
    d.dd.claim_start(t, ["P-x"], None, False)
    d.dd.conn.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, prompt, status) VALUES (?,?,?,?,?,?)",
                      ("P-x", D.now_iso(), "claude", "codex", "q", "running"))
    real, seen = d.dd.conn, []

    class Mid:                       # a sweep runs exactly when the terminal update is about to be written
        def execute(self, sql, *a):
            if sql.startswith("UPDATE tasks SET ended=?, status=?"):
                seen.append(d.sweep())
            return real.execute(sql, *a)
    d.dd.conn = Mid()
    d.dd.task_end(t, "done", {}, 1.0)
    d.dd.conn = real
    assert seen == [0] and row(d, t)["status"] == "done" and t not in D.LIVE_TASKS
    assert real.execute("SELECT status FROM peer_requests WHERE id='P-x'").fetchone()[0] == "running"
