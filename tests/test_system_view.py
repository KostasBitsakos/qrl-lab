"""B1 acceptance (v0.5.1 §4): every DEFAULTS key is shown; 0 model calls; usage expiry -> unknown; composer auto."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import agent_models  # noqa: E402
import dispatcher as D  # noqa: E402
import system_view as sv  # noqa: E402

NOW = 1_800_000_000.0


def make_dbs(tmp):
    d, lab = tmp / "dispatch.db", tmp / "lab.db"
    c = sqlite3.connect(d)
    c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT, updated_by TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, started TEXT, kind TEXT, refs TEXT, provider TEXT,"
              " model TEXT, status TEXT, cost_usd REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS providers(name TEXT PRIMARY KEY, state TEXT NOT NULL, until_ts REAL, note TEXT, updated_at TEXT)")
    c.execute("INSERT INTO settings VALUES ('claude_model','sonnet','2026-11-03','researcher')")
    c.executemany("INSERT INTO tasks(started, kind, refs, provider, model, status, cost_usd) VALUES (?,?,?,?,?,?,?)", [
        ("2026-11-02T23:34:03+00:00", "message", json.dumps(["M-1", "C1"]), "claude", "opus", "done", 0.26),
        ("2026-11-02T23:35:00+00:00", "message", json.dumps(["M-2", "C2"]), "claude", "sonnet", "done", 0.10),
        ("2026-11-02T23:36:00+00:00", "job", json.dumps(["J1"]), "codex", "codex-default", "done", None),
        ("2026-11-02T23:37:00+00:00", "message", json.dumps(["M-3"]), "codex", "codex-default", "done", None),
    ])
    c.commit(); c.close()
    c = sqlite3.connect(lab)
    c.execute("CREATE TABLE messages(id TEXT PRIMARY KEY, ts TEXT, req_model TEXT, body TEXT)")
    c.executemany("INSERT INTO messages VALUES (?,?,?,?)", [("M-1", "1", "opus", "γεια"), ("M-2", "2", None, "τι νέα"),
                                                            ("M-3", "3", "sonnet", "@codex: κοίτα")])
    c.commit(); c.close()
    return d, lab


def test_every_default_key_has_meta_and_row(tmp_path):
    d, _ = make_dbs(tmp_path)
    assert set(D.DEFAULTS) <= set(sv.SETTINGS_META)
    rows = sv.settings_rows(d)
    assert [r["key"] for r in rows] == list(D.DEFAULTS)
    cm = next(r for r in rows if r["key"] == "claude_model")
    assert cm["value"] == "sonnet" and cm["source"] == "βάση" and cm["default"] == D.DEFAULTS["claude_model"]


def test_routing_and_real_tasks(tmp_path):
    d, lab = make_dbs(tmp_path)
    s = sv.effective(sv.settings_rows(d))
    kinds = {r["event"] for r in sv.routing_rows(s)}
    assert set(sv.KINDS) <= kinds
    t = {r["id"]: r for r in sv.recent_tasks(d, lab, s=s)}
    assert "req_model=opus" in t[1]["why"]           # the Opus run came from the message selector
    assert "ρύθμιση `claude_model`" in t[2]["why"]
    assert "@codex" in t[4]["why"]                    # an explicit @mention beats the selector


def test_claude_model_for_matches_old_dispatcher_logic():
    s = dict(D.DEFAULTS, events_model="", peer_claude_model="sonnet", claude_model="opus")
    assert D.claude_model_for(s, "perm_answer")[0] == "sonnet"
    assert D.claude_model_for(s, "run_event")[0] == "opus"
    assert D.claude_model_for(dict(s, events_model="haiku"), "run_event")[0] == "haiku"
    assert D.claude_model_for(s, "message", "haiku") == ("haiku", "req_model")


def test_usage_freshest_and_expired_unknown():
    status = {"as_of": NOW - 600, "seven_day": {"used_percentage": 14.0, "resets_at": NOW + 3600},
              "five_hour": {"used_percentage": 2.0, "resets_at": NOW - 10},
              "_dispatcher": {"limits": [{"window": "seven_day", "utilization": 0.2, "resets_at": NOW + 3600,
                                          "updated_at": NOW - 60}]}}
    rows = {r["window"]: r for r in sv.claude_usage(status, NOW)}
    assert rows["7ημ"]["pct"] == "20%" and rows["7ημ"]["source"] == "dispatch.db.limits"   # newer wins
    assert rows["5ω"]["pct"] == sv.UNKNOWN                                                 # expired, not 100 %
    old_rejection = {"_dispatcher": {"limits": [{"window": "seven_day", "utilization": 1.0, "status": "rejected",
                                                 "resets_at": NOW - 86400, "updated_at": NOW - 90000}]}}
    assert sv.claude_usage(old_rejection, NOW)[0]["pct"] == sv.UNKNOWN
    assert sv.codex_usage([], NOW)[0]["pct"] == sv.UNKNOWN
    cx = sv.codex_usage([{"slot": "secondary", "used_percent": 62.0, "resets_at": NOW - 1, "as_of": NOW - 9e4}], NOW)
    assert cx[0]["pct"] == sv.UNKNOWN


def test_zero_model_calls(tmp_path, monkeypatch):
    d, lab = make_dbs(tmp_path)
    calls = []

    def spy(args, *a, **k):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(subprocess, "run", spy)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Popen")))
    monkeypatch.setattr(D, "run_claude", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
    monkeypatch.setattr(D, "run_codex", lambda *a, **k: (_ for _ in ()).throw(AssertionError("codex")))
    s = sv.effective(sv.settings_rows(d))
    sv.routing_rows(s); sv.recent_tasks(d, lab, s=s); sv.rate_rows(d, NOW)
    sv.services(NOW, heartbeat=str(tmp_path / "none"), db=d)
    assert calls and all(c[0] in ("systemctl", "crontab") for c in calls)


def test_read_only(tmp_path):
    d, _ = make_dbs(tmp_path)
    import pytest
    with pytest.raises(sqlite3.OperationalError):
        sv.connect_ro(d).execute("DELETE FROM settings")


def test_composer_default_is_auto():
    assert next(iter(agent_models.model_choices(None))) is None


def test_missing_claude_telemetry_is_unknown():
    rows = sv.claude_usage(None, NOW)
    assert [r["window"] for r in rows] == ["5ω", "7ημ"] and all(r["pct"] == sv.UNKNOWN for r in rows)


def test_paths_follow_dispatch_db_override(monkeypatch, tmp_path):
    monkeypatch.setenv("QRL_DISPATCH_DB", str(tmp_path / "x.db"))
    assert sv.paths(str(tmp_path))["dispatch"] == str(tmp_path / "x.db")


def test_unreadable_db_is_flagged(tmp_path):
    rows = sv.settings_rows(str(tmp_path / "missing.db"))
    assert rows and all(r["source"] == "ΒΑΣΗ ΜΗ ΑΝΑΓΝΩΣΙΜΗ" for r in rows)


def test_failed_commands_are_not_counted(tmp_path, monkeypatch):
    d, _ = make_dbs(tmp_path)
    monkeypatch.setattr(sv, "_cmd", lambda args, timeout=5: (False, "boom"))
    st = {r["name"]: r["state"] for r in sv.services(NOW, heartbeat=str(tmp_path / "none"), db=d)}
    assert st["crontab"].startswith("μη διαθέσιμο") and st["systemd timers (user)"].startswith("μη διαθέσιμο")
