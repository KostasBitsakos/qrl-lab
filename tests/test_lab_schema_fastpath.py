"""Initialized databases can be opened even while another connection holds a write lock."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import labdb


def seed(conn, *, migrations=True):
    conn.executescript('BEGIN;\n'+labdb.SCHEMA)
    if migrations:
        for table, cols in labdb.LabDB.MIGRATIONS.items():
            for col, typ in cols.items():
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
    conn.execute('INSERT INTO meta VALUES (?,?)',('schema_version',str(labdb.SCHEMA_VERSION)))
    conn.commit()


def test_current_schema_opens_under_writer_lock_without_writes(tmp_path):
    path=tmp_path/'lab.db'
    writer=sqlite3.connect(path)
    seed(writer)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute('BEGIN IMMEDIATE')
    try:
        db=labdb.LabDB(str(path))
        assert db.conn.total_changes==0
        assert db._schema_current()
        db.close()
    finally:
        writer.rollback();writer.close()


def test_missing_schema_objects_and_migrations_are_repaired(tmp_path, monkeypatch):
    conn=sqlite3.connect(':memory:',isolation_level=None)
    seed(conn,migrations=False)
    conn.execute('DROP TABLE thread_title_history')
    conn.execute('DROP INDEX ix_requests_state')
    monkeypatch.setattr(labdb.sqlite3,'connect',lambda *args,**kwargs:conn)
    db=labdb.LabDB(str(tmp_path/'lab.db'))
    assert db._schema_current()
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='thread_title_history'").fetchone()
    db.close()


def test_fresh_db_keeps_full_initialization(tmp_path, monkeypatch):
    conn=sqlite3.connect(':memory:',isolation_level=None)
    monkeypatch.setattr(labdb.sqlite3,'connect',lambda *args,**kwargs:conn)
    db=labdb.LabDB(str(tmp_path/'lab.db'))
    assert db._schema_current()
    mid=db.researcher_send('schema initialized')
    assert db.message(mid)['body']=='schema initialized'
    db.close()
