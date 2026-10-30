"""J228: measured dispatcher usage line and the phone tap-feedback script."""
import datetime as dt
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mobile_view  # noqa: E402
import token_metrics  # noqa: E402


def test_dispatcher_usage_sums_measured_tokens_only(tmp_path):
    (tmp_path / ".lab").mkdir()
    con = sqlite3.connect(tmp_path / ".lab" / "dispatch.db")
    con.execute("CREATE TABLE tasks (provider TEXT, started TEXT, input_tokens INTEGER, cached_tokens INTEGER,"
                " cache_write_tokens INTEGER, output_tokens INTEGER)")
    now = dt.datetime.now(dt.timezone.utc)
    old = (now - dt.timedelta(hours=30)).isoformat()
    new = now.isoformat()
    con.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?)", [
        ("claude", new, 10, 100, 5, 7), ("claude", new, 1, 2, 3, 4),
        ("claude", old, 999, 999, 999, 999),     # outside 24 h
        ("codex", new, None, None, None, None)])  # no usage reported: not counted as 0
    con.commit()
    con.close()
    assert token_metrics.dispatcher_usage(tmp_path, 24) == [
        {"provider": "claude", "n": 2, "inp": 11, "cached": 102, "cw": 8, "out": 11}]


def test_dispatcher_usage_missing_db_is_empty(tmp_path):
    assert token_metrics.dispatcher_usage(tmp_path, 24) == []


def test_tap_feedback_script_guards_double_tap():
    s = mobile_view.script()
    assert "qrl-pend" in s and "pointer-events:none" in s and "data-test-script-state" in s and "%(" not in s
