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
        assert d.provider_order(job(), running_local=0)[0] == ["codex"]       # unforced: switches provider
        assert d.provider_order(job(forced="claude"), running_local=0) == ([], ["claude"])  # pinned: waits
        assert d._startable(job(forced="claude")) is False and "7ημ" in d.gov_reason
        table["codex"] = hot
        assert d.provider_order(job(), running_local=0)[0] == []
        assert d._startable(job()) is False                                   # silent wait, nothing posted
        assert d.provider_order(job("message"), running_local=0)[0] == ["claude", "codex"]  # chat is never stranded


def test_governor_off_switch(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    d.dd.set("governor_enabled", "0")
    with patch.object(G, "windows", return_value=wins(99, 99, 0.1)):
        assert d.provider_order(job(), running_local=0)[0] == ["claude", "codex"]


def test_unknown_usage_one_optional_job_at_a_time(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    with patch.object(G, "windows", return_value={}):
        assert d._startable(job(), 0) is True
        assert d._startable(job(), 1) is False


def test_safety_refusal_is_never_retried(tmp_path, monkeypatch):
    d = make(tmp_path, monkeypatch)
    item = {"kind": "job", "thread_id": "T", "msg_ids": [], "req_ids": []}
    refusal = dict(D._empty_result(), transient=True, error="I can't help with that: safety policy")
    transient = dict(D._empty_result(), transient=True, error="overloaded")
    ok_ = dict(D._empty_result(), ok=True)
    monkeypatch.setenv("QRL_TRANSIENT_WAIT", "0")
    with patch.object(D.time, "sleep"), patch.object(d, "_run_provider", side_effect=[refusal, ok_]) as run:
        assert not d._attempt("claude", item, [], None)["ok"] and run.call_count == 1
    with patch.object(D.time, "sleep"), patch.object(d, "_run_provider", side_effect=[transient, ok_]) as run:
        assert d._attempt("claude", item, [], None)["ok"] and run.call_count == 2
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
