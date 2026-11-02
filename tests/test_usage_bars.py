"""Sidebar tokens-left / where-it-goes bars (J319); temporary DB only."""
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import token_metrics as tm


def _root(tmp_path, rows):
    (tmp_path / ".lab").mkdir()
    con = sqlite3.connect(tmp_path / ".lab/dispatch.db")
    con.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, started TEXT, kind TEXT, provider TEXT, model TEXT,"
                " input_tokens INTEGER, cache_write_tokens INTEGER, output_tokens INTEGER)")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    con.executemany("INSERT INTO tasks(started,kind,provider,model,input_tokens,cache_write_tokens,output_tokens)"
                    " VALUES(?,?,?,?,?,?,?)", [(now, *r) for r in rows])
    con.commit(); con.close()
    return tmp_path


def test_lower_bound_and_unknowns():
    assert tm.remaining_lower_bound(1000, 50.0) == 1000
    assert tm.remaining_lower_bound(1000, 25.0) == 3000
    assert tm.remaining_lower_bound(1000, None) is None
    assert tm.remaining_lower_bound(1000, 2.0) is None
    assert tm.remaining_lower_bound(0, 50.0) is None


def test_bars_render(tmp_path):
    root = _root(tmp_path, [("chat", "claude", "opus", 100, 100, 100), ("worker", "claude", "sonnet", 50, 0, 50)])
    html = tm.sidebar_bars_html(root, "claude", [dict(label="5ω", pct=50.0), dict(label="7ημ", pct=None)], "Claude")
    assert "5ω: απομένουν ~400 tokens (πολύ χονδρική εκτίμηση)" in html
    assert "7ημ: απομένουν άγνωστο" in html
    assert "chat · opus" in html and "75%" in html and "worker · sonnet" in html


def test_missing_db_is_unknown(tmp_path):
    html = tm.sidebar_bars_html(tmp_path, "codex", [dict(label="5ω", pct=40.0)], "Codex")
    assert "άγνωστο" in html and "η βάση δεν διαβάζεται" in html
