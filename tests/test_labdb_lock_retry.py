"""LabDB.tx(lock_wait_s) retries BEGIN on 'database is locked' (s59 supervisor crash, J169)."""
import os
import sqlite3
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from labdb import LabDB  # noqa: E402


def _held_lock(path, seconds):
    other = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    other.execute("BEGIN IMMEDIATE")
    t = threading.Timer(seconds, lambda: (other.execute("COMMIT"), other.close()))
    t.start()
    return t


def _db(tmp_path):
    db = LabDB(str(tmp_path / "lab.db"))
    db.conn.execute("PRAGMA busy_timeout=100")   # make the default path fail fast
    db.conn.execute("CREATE TABLE IF NOT EXISTS t(x)")
    return db


def test_default_tx_still_raises_on_held_lock(tmp_path):
    db = _db(tmp_path)
    t = _held_lock(db.path, 1.0)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        with db.tx() as c:
            c.execute("INSERT INTO t VALUES (1)")
    t.join()


def test_tx_with_lock_wait_commits_after_lock_released(tmp_path):
    db = _db(tmp_path)
    t = _held_lock(db.path, 1.5)
    t0 = time.monotonic()
    with db.tx(lock_wait_s=20) as c:
        c.execute("INSERT INTO t VALUES (2)")
    assert time.monotonic() - t0 >= 1.0
    assert db.conn.execute("SELECT x FROM t").fetchall()[0][0] == 2
    t.join()


def test_tx_lock_wait_is_bounded(tmp_path):
    db = _db(tmp_path)
    t = _held_lock(db.path, 4.0)
    t0 = time.monotonic()
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        with db.tx(lock_wait_s=1.0) as c:
            c.execute("INSERT INTO t VALUES (3)")
    assert time.monotonic() - t0 < 3.5
    t.join()
