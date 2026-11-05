import datetime as dt
import importlib.util
import sqlite3
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("cost_report", Path(__file__).resolve().parents[1] / "tools" / "cost_report.py")
cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)


def make_db(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, started TEXT, kind TEXT, provider TEXT, cost_usd REAL)")
    c.executemany("INSERT INTO tasks(started, kind, provider, cost_usd) VALUES (?,?,?,?)", [
        ("2026-11-01T10:00:00+00:00", "message", "claude", 0.5),
        ("2026-11-01T11:00:00+00:00", "message", "claude", 0.25),
        ("2026-11-01T12:00:00+00:00", "job", "codex", None),
        ("2026-11-02T09:00:00+00:00", "run_event", "claude", 1.0),
        ("2026-10-01T09:00:00+00:00", "message", "claude", 9.0),  # outside the window
    ])
    c.commit(); c.close()


def test_groups_by_day_and_kind(tmp_path):
    db = tmp_path / "d.db"; make_db(db)
    rows = cr.report(db, days=7, today=dt.date(2026, 11, 3))
    got = {(r["day"], r["kind"]): (r["runs"], r["claude"], r["codex"], r["usd"], r["no_cost"]) for r in rows}
    assert got == {("2026-11-01", "job"): (1, 0, 1, 0.0, 1),
                   ("2026-11-01", "message"): (2, 2, 0, 0.75, 0),
                   ("2026-11-02", "run_event"): (1, 1, 0, 1.0, 0)}
    text = cr.render(rows)
    assert "total" in text and "1.75" in text


def test_read_only(tmp_path):
    db = tmp_path / "d.db"; make_db(db)
    with pytest.raises(sqlite3.OperationalError):
        cr.connect_ro(db).execute("DELETE FROM tasks")
