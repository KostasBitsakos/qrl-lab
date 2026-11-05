"""B2 acceptance (v0.5.1 §4/§5): pace/limits -> wait or other provider; safety refusal -> 0 retries; STATE 8 KB note.
No model is called. The dispatcher parts run with fake usage data in a temporary lab."""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import dispatcher as D  # noqa: E402
import governor as G  # noqa: E402

NOW = 1_800_000_000.0
S = {k: D.DEFAULTS[k] for k in ("pace_margin_pct", "optional_hard_pct", "five_hour_max_pct", "chat_hard_pct",
                                "usage_stale_h", "unknown_daily_runs")}


def w(pct, reset, age=60):
    return dict(pct=pct, reset=reset, as_of=NOW - age, source="t")


def wins(five, week, week_elapsed=0.5):
    return {"five_hour": w(five, NOW + 3600), "seven_day": w(week, NOW + (1 - week_elapsed) * G.WEEK_S)}


def test_pace():
    assert abs(G.pace_pct(NOW + 3.5 * 86400, NOW) - 50) < 1e-9
    assert G.pace_pct(NOW - 1, NOW) is None and G.pace_pct(None, NOW) is None


def test_optional_follows_pace_and_hard_limits():
    assert G.decide("optional", wins(10, 59), NOW, S)[0] == "go"        # 59 <= 50 + 10
    assert G.decide("optional", wins(10, 61), NOW, S)[0] == "wait"      # above pace + margin
    assert G.decide("optional", wins(10, 91, 0.99), NOW, S)[0] == "wait"  # >= optional_hard_pct even if pace is high
    assert G.decide("optional", wins(85, 10), NOW, S)[0] == "wait"      # 5 h window >= 85
    assert G.decide("optional", wins(84, 10), NOW, S)[0] == "go"


def test_chat_until_97():
    assert G.decide("chat", wins(50, 96), NOW, S)[0] == "go"
    assert G.decide("chat", wins(50, 97), NOW, S)[0] == "wait"
    assert G.decide("chat", wins(97, 10), NOW, S)[0] == "wait"


def test_unknown_or_stale_is_conservative():
    stale = wins(10, 10)
    stale["seven_day"]["as_of"] = NOW - 7 * 3600                           # > 6 h
    assert G.decide("optional", stale, NOW, S, running_optional=0)[0] == "go"
    assert G.decide("optional", stale, NOW, S, running_optional=1)[0] == "wait"
    assert G.decide("optional", {}, NOW, S, running_optional=1)[0] == "wait"
    assert G.decide("optional", {}, NOW, S, running_optional=0, runs_today=40)[0] == "wait"   # daily cap
    assert G.decide("optional", {}, NOW, S, running_optional=0, runs_today=39)[0] == "go"
    expired = wins(10, 99)
    expired["seven_day"]["reset"] = NOW - 5                                # window ended: unknown, not 99 %
    assert G.decide("optional", expired, NOW, S, running_optional=0)[0] == "go"
    assert G.decide("chat", {}, NOW, S)[0] == "go"                         # unknown never blocks the chat


# ---- dispatcher integration (fake usage via patched governor.windows)
def make(tmp_path, monkeypatch):
    monkeypatch.setenv("QRL_LAB_DIR", str(tmp_path))
    monkeypatch.setenv("QRL_DISPATCH_DB", str(tmp_path / "dispatch.db"))
    (tmp_path / ".lab").mkdir()
    d = D.Dispatcher(str(tmp_path))
    return d


def job(kind="job", forced=None):
    return {"kind": kind, "thread_id": "T", "msg_ids": [], "req_ids": [], "forced": forced}


def test_over_pace_goes_to_other_provider_or_waits(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    hot = wins(10, 80, 0.2)   # far above pace
    cool = wins(10, 5, 0.5)
    table = {"claude": hot, "codex": cool}
    with patch.object(G, "windows", side_effect=lambda p, *a, **k: table[p]):
        assert d.provider_order(job())[0] == ["codex"]                        # unforced: switches provider
        assert d.provider_order(job(forced="claude")) == ([], ["claude"])     # pinned: waits
        assert d._admit(job(forced="claude")) is False and "7ημ" in d.gov_reason
        # the governor never changes provider state: only a real limit error does
        assert d.dd.provider("claude")["state"] == "ok" and d.dd.available("claude")
        table["codex"] = hot
        assert d.provider_order(job())[0] == []
        assert d._admit(job()) is False                                       # silent wait, nothing posted
        assert d.provider_order(job("message"))[0] == ["claude", "codex"]     # chat is never stranded
        assert d.dd.available("claude") and d.dd.available("codex")


def test_governor_off_switch(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    d.dd.set("governor_enabled", "0")
    with patch.object(G, "windows", return_value=wins(99, 99, 0.1)):
        assert d.provider_order(job())[0] == ["claude", "codex"]


def test_unknown_usage_one_optional_job_per_provider(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    with patch.object(G, "windows", return_value={}):
        assert d._admit(job(forced="claude")) is True       # reserves a 'starting' row
        assert d._admit(job(forced="claude")) is False      # same provider: the slot is taken
        assert d._admit(job(forced="codex")) is True        # the other provider is idle: per-provider rule
        assert d._admit(job(forced="codex")) is False


def test_reserve_counts_by_lane_not_by_kind(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    def row(lane, status, kind="x"):
        d.dd.conn.execute("INSERT INTO tasks(started, kind, provider, status, lane) VALUES (?,?,?,?,?)",
                          (D.now_iso(), kind, "claude", status, lane))
    row("chat", "running", "message")                         # chat does not count
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is not None
    row("worker", "running", "perm_answer")                   # any non-chat lane counts, whatever its kind
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is None
    d.dd.conn.execute("DELETE FROM tasks WHERE lane='worker'")
    row("peer", "running", "peer")
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is None
    d.dd.conn.execute("DELETE FROM tasks WHERE lane='peer' OR status='starting'")
    row(None, "running", "decision")                          # rows from before B2 (no lane) count as optional
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is None
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=None) is not None   # no rule -> still recorded


def test_two_threads_ask_for_the_last_slot_exactly_one_gets_it(tmp_path, monkeypatch):
    import threading
    make(tmp_path, monkeypatch)
    for rnd in range(10):
        got, barrier = [], threading.Barrier(2)
        def worker(lane):
            with D.DispatchDB(str(tmp_path / "dispatch.db")) as dd:   # its own connection, like worker and peer threads
                barrier.wait()
                got.append(dd.reserve("job", "T", [], f"p{rnd}", lane, cap=1))
        ts = [threading.Thread(target=worker, args=(ln,)) for ln in ("worker", "peer")]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert sorted(g is None for g in got) == [False, True], got
    with D.DispatchDB(str(tmp_path / "dispatch.db")) as dd:
        assert dd.conn.execute("SELECT COUNT(*) FROM tasks WHERE status='starting'").fetchone()[0] == 10


def test_reservation_is_released_and_aged_out(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    tid = d.dd.reserve("job", "T", [], "claude", "worker", cap=1)
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is None
    d.dd.release(tid)
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is not None
    d.dd.conn.execute("UPDATE tasks SET started=? WHERE status='starting'", ((D.dt.datetime.now().astimezone() - D.dt.timedelta(hours=1)).isoformat(timespec="seconds"),))
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is not None   # an orphan 'starting' row expires


def test_percentage_without_reset_pace_unknown_but_limits_apply():
    no_reset = {"five_hour": w(10, NOW + 3600), "seven_day": dict(w(50, None))}
    v, _, cap, daily = G.assess("optional", no_reset, NOW, S)
    assert v == "go" and cap == 1 and daily == 40                    # conservative: pace cannot be computed
    no_reset["seven_day"]["pct"] = 91
    assert G.assess("optional", no_reset, NOW, S)[0] == "wait"       # 90 % hard limit still applies
    no_reset["seven_day"]["pct"] = 50
    no_reset["five_hour"]["pct"] = 85
    assert G.assess("optional", no_reset, NOW, S)[0] == "wait"       # 85 % five-hour limit still applies


def test_safety_refusal_is_never_retried(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    item = {"kind": "job", "thread_id": "T", "msg_ids": [], "req_ids": []}
    refusal = dict(D._empty_result(), transient=True, error="I can't help with that: safety policy")
    transient = dict(D._empty_result(), transient=True, error="overloaded")
    ok_ = dict(D._empty_result(), ok=True)
    conn = dict(D._empty_result(), transient=True, error="connect ECONNREFUSED: connection refused")
    assert not D.REFUSAL_RE.search(conn["error"]) and D.REFUSAL_RE.search("Permission denied by policy")
    assert not D.REFUSAL_RE.search("EACCES: permission denied, open 'x'")
    monkeypatch.setenv("QRL_TRANSIENT_WAIT", "0")
    with patch.object(D.time, "sleep"), patch.object(d, "_run_provider", side_effect=[refusal, ok_]) as run:
        assert not d._attempt("claude", item, [], None)["ok"] and run.call_count == 1
    with patch.object(D.time, "sleep"), patch.object(d, "_run_provider", side_effect=[transient, ok_]) as run:
        assert d._attempt("claude", item, [], None)["ok"] and run.call_count == 2
    with patch.object(D.time, "sleep"), patch.object(d, "_run_provider", side_effect=[conn, ok_]) as run:
        assert d._attempt("claude", item, [], None)["ok"] and run.call_count == 2   # "connection refused" IS retried
    d.dd.set("max_retries", "0")
    with patch.object(D.time, "sleep"), patch.object(d, "_run_provider", side_effect=[transient, ok_]) as run:
        assert not d._attempt("claude", item, [], None)["ok"] and run.call_count == 1


def test_peer_requests_of_held_provider_stay_queued(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    for pid, to in (("P1", "claude"), ("P2", "codex")):
        d.dd.conn.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, key, major, prompt, status)"
                          " VALUES (?,?,?,?,?,?,?,?)", (pid, f"2026-11-05T00:00:0{pid[1]}", "x", to, None, 0, "q", "queued"))
    assert d.dd.peer_claim(skip=("claude",))["id"] == "P2"
    assert d.dd.peer_claim(skip=("claude",)) is None
    assert d.dd.peer_claim()["id"] == "P1"


def test_codex_usage_is_read_from_rollout_logs(tmp_path, monkeypatch):
    now = time.time()
    d = tmp_path / "sessions" / "2026" / "11"
    d.mkdir(parents=True)
    rec = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now - 30)),
           "payload": {"type": "token_count", "rate_limits": {
               "primary": {"used_percent": 7.0, "window_minutes": 300, "resets_at": now + 3600},
               "secondary": {"used_percent": 31.0, "window_minutes": 10080, "resets_at": now + 3.5 * 86400}}}}
    (d / "rollout-x.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    monkeypatch.setattr(G, "CODEX_GLOB", str(tmp_path / "sessions" / "**" / "rollout-*.jsonl"))
    G._codex_memo.clear()
    got = G.windows("codex", now=now, ttl=0)
    assert got["five_hour"]["pct"] == 7.0 and got["seven_day"]["pct"] == 31.0
    assert 49 < G.pace_pct(got["seven_day"]["reset"], now) < 51
    assert G.decide("optional", got, now, S)[0] == "go"             # 31 <= 50 + 10
    rec["payload"]["rate_limits"]["secondary"]["used_percent"] = 70.0       # a later Codex run reports more use
    rec["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now - 5))
    (d / "rollout-x.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert G.windows("codex", now=now, ttl=0)["seven_day"]["pct"] == 70.0   # no restart needed: read at decision time
    assert G.decide("optional", G.windows("codex", now=now, ttl=0), now, S)[0] == "wait"
    monkeypatch.setattr(G, "CODEX_GLOB", str(tmp_path / "none" / "*.jsonl"))
    G._codex_memo.clear()
    assert G.windows("codex", now=now, ttl=0) == {}                          # no log -> unknown, never a guess


# ---- review round 2: epochs, sweeper, admission of retries/failover, peer cleanup, one assessment, off switch
def _iso_epoch(epoch, offset_h):
    tz = D.dt.timezone(D.dt.timedelta(hours=offset_h))
    return D.dt.datetime.fromtimestamp(epoch, tz).isoformat(timespec="seconds")


def test_time_comparisons_use_epochs_not_strings(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    now = time.time()
    # 100 s ago written at UTC-12 and 1000 s ago written at UTC+14: as STRINGS the second sorts "later" than the first
    for age, off in ((100, -12), (1000, 14)):
        d.dd.conn.execute("INSERT INTO tasks(started, kind, provider, status, lane) VALUES (?,?,?,?,?)",
                          (_iso_epoch(now - age, off), "job", "claude", "starting", "worker"))
    assert _iso_epoch(now - 1000, 14) > _iso_epoch(now - 100, -12)            # the trap
    # hold 300 s: only the 100 s row is young enough to count -> one slot taken, cap 2 admits, cap 1 refuses
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=1) is None
    assert d.dd.reserve("job", "T", [], "claude", "worker", cap=2) is not None
    # daily cap: both rows are < 24 h old, whatever their offset
    assert d.dd.reserve("job", "T", [], "claude", "worker", daily_cap=3) is None


def test_sweeper_frees_dead_rows_and_launcher_cannot_claim_a_swept_row(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    now = time.time()
    jid = d.work.create("worker", "spawn", "J", "b", status="running")
    stale = _iso_epoch(now - 4000, 2)
    c = d.dd.conn
    c.execute("INSERT INTO tasks(started, kind, refs, provider, status, lane) VALUES (?,?,?,?,?,?)",
              (stale, "job", json.dumps([jid]), "claude", "starting", "worker"))                 # 1: starting, dead
    c.execute("INSERT INTO tasks(started, kind, refs, provider, status, lane) VALUES (?,?,?,?,?,?)",
              (stale, "job", json.dumps([jid]), "claude", "running", "worker"))                  # 2: running past timeout
    c.execute("INSERT INTO tasks(started, kind, refs, provider, status, lane) VALUES (?,?,?,?,?,?)",
              (_iso_epoch(now - 30, 2), "job", "[]", "claude", "running", "worker"))              # 3: alive, young
    for pid, age, status in (("P-run", 400, "running"), ("P-old", 4000, "queued"), ("P-new", 30, "queued")):
        c.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, prompt, status) VALUES (?,?,?,?,?,?)",
                  (pid, _iso_epoch(now - age, -5), "x", "codex", "q", status))
    assert d.sweep(now) == 4
    st = {r["id"]: r["status"] for r in c.execute("SELECT id, status FROM tasks")}
    assert st == {1: "released", 2: "interrupted", 3: "running"}
    assert d.work.job(jid)["status"] == "queued"                                    # the job is back in the queue
    ps = {r["id"]: r["status"] for r in c.execute("SELECT id, status FROM peer_requests")}
    assert ps == {"P-run": "queued", "P-old": "failed", "P-new": "queued"}          # claimed-never-served re-queued; hold limit
    assert "held back" in c.execute("SELECT error FROM peer_requests WHERE id='P-old'").fetchone()[0]
    assert d.dd.claim_start(1, [], None, False) is False                            # a launcher cannot take a swept row
    assert d.dd.conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()[0] == "released"


def _busy_row(d, provider):
    d.dd.conn.execute("INSERT INTO tasks(started, kind, provider, status, lane) VALUES (?,?,?,?,?)",
                      (D.now_iso(), "job", provider, "running", "worker"))


def test_retry_and_failover_attempts_are_admitted(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    item = {"kind": "job", "thread_id": "T", "msg_ids": [], "req_ids": [], "reply_to": "T", "job_id": "J9", "forced": None}
    transient = dict(D._empty_result(), transient=True, error="overloaded")
    with patch.object(G, "windows", return_value={}):       # unknown usage: cap 1 per provider
        # retry: during the backoff another job takes the freed slot -> the retry is denied, the item re-queued
        with patch.object(D.time, "sleep", side_effect=lambda *_: _busy_row(d, "claude")), \
                patch.object(d, "_run_provider", return_value=transient) as run:
            res = d._attempt("claude", item, [], None)
        assert res.get("gov_denied") and run.call_count == 1
        # failover: the other provider's slot is occupied -> not run at all
        _busy_row(d, "codex")
        with patch.object(d, "_run_provider") as run:
            assert d._attempt("codex", item, [], None).get("gov_denied") and run.call_count == 0
    # _process turns a denied attempt into a silent re-queue
    with patch.object(d, "_attempt", return_value=dict(D._empty_result(), gov_denied=True)):
        item["reserved"] = {"provider": "claude", "task": d.dd.reserve("job", "T", [], "claude", "worker")}
        assert d._process(item) == "deferred"


def test_peer_exception_after_claim_frees_the_slot_and_the_request(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    def req(pid, to):
        d.dd.conn.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, prompt, status)"
                          " VALUES (?,?,?,?,?,?)", (pid, D.now_iso(), "x", to, "q", "queued"))
    req("P1", "codex")
    def boom(root, r, tid=None):                          # the run starts (row 'running'), then something breaks
        assert d.dd.claim_start(tid, [r["id"]], None, False)
        raise RuntimeError("boom")
    with patch.object(G, "windows", return_value={}), patch.object(D, "serve_peer", boom):
        try:
            D._peer_cycle(str(tmp_path), d.dd)
            assert False, "must re-raise"
        except RuntimeError:
            pass
        assert d.dd.conn.execute("SELECT status FROM tasks WHERE lane='peer'").fetchone()[0] == "interrupted"
        row = d.dd.conn.execute("SELECT status, error FROM peer_requests WHERE id='P1'").fetchone()
        assert row[0] == "failed" and "boom" in row[1]
        assert d.dd.reserve("peer", "T", [], "codex", "peer", cap=1) is not None      # the slot is free again
        # an exception between claim and reservation re-queues the request
        d.dd.conn.execute("DELETE FROM tasks")
        req("P2", "codex")
        with patch.object(d.dd, "reserve", side_effect=sqlite3.OperationalError("locked")):
            try:
                D._peer_cycle(str(tmp_path), d.dd)
            except sqlite3.OperationalError:
                pass
        assert d.dd.conn.execute("SELECT status FROM peer_requests WHERE id='P2'").fetchone()[0] == "queued"


def test_blocked_peer_is_skipped_and_later_requests_are_served(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    for i, (pid, to) in enumerate((("P1", "codex"), ("P2", "claude"))):
        d.dd.conn.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, prompt, status)"
                          " VALUES (?,?,?,?,?,?)", (pid, f"2026-11-05T00:00:0{i}Z", "x", to, "q", "queued"))
    _busy_row(d, "codex")                                 # codex has its one slot taken (unknown usage -> cap 1)
    served = []
    with patch.object(G, "windows", return_value={}), \
            patch.object(D, "serve_peer", lambda root, r, tid=None: served.append(r["id"])):
        assert D._peer_cycle(str(tmp_path), d.dd) is True
    assert served == ["P2"]                               # the claude request behind the blocked codex one was served
    assert d.dd.conn.execute("SELECT status FROM peer_requests WHERE id='P1'").fetchone()[0] == "queued"


def test_one_usage_assessment_per_decision_and_off_switch(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    with patch.object(G, "windows", return_value={}) as win:
        assert d._admit(job()) is True
        assert win.call_count <= 2                        # one per provider considered, none repeated
        win.reset_mock()
        D._peer_cycle(str(tmp_path), d.dd)
        assert win.call_count == 2                        # peers: one per provider per cycle
    d.dd.set("governor_enabled", "0")
    with patch.object(G, "windows", side_effect=AssertionError("governor must not be consulted")):
        assert d._admit(job()) is True and d._admit(job()) is True      # no cap with the governor off
        item = dict(job(), reply_to="T", job_id="J1")
        assert d._task_begin(item, "claude", [], None, None) is not None
        d.dd.conn.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, prompt, status)"
                          " VALUES ('P9', ?, 'x', 'codex', 'q', 'queued')", (D.now_iso(),))
        with patch.object(D, "serve_peer", lambda root, r, tid=None: None):
            assert D._peer_cycle(str(tmp_path), d.dd) is True
