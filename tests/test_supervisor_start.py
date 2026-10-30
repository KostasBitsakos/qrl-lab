"""Exercise live-child lock paths using temporary DBs and fake processes only."""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import launch_run as L
from labdb import LabDB, LabError


def test_show_readonly_missing_ambiguous_and_exact(tmp_path, monkeypatch):
    path = tmp_path / 'status.db'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE runs(run_id TEXT,status TEXT,pid INT,exit_code INT,started TEXT,ended TEXT)')
    conn.executemany('INSERT INTO runs VALUES (?,?,?,?,?,?)', [('one', 'running', 42, None, 'start', None),
                                                             ('other', 'done', 43, 0, 'start', 'end')])
    conn.commit()
    before = path.read_bytes()
    real_connect = sqlite3.connect
    uris = []
    def connect(database, **kw):
        uris.append(database)
        return real_connect(database, **kw)
    monkeypatch.setattr(L.sqlite3, 'connect', connect)
    assert L.show_run('one', path)['pid'] == 42
    assert L.show_run('oth', path)['exit_code'] == 0
    with pytest.raises(LabError, match='Ambiguous'):
        L.show_run('o', path)
    with pytest.raises(LabError, match='Unknown'):
        L.show_run('missing', path)
    with pytest.raises(sqlite3.OperationalError):
        L.show_run('one', tmp_path / 'missing.db')
    assert all(u.endswith('?mode=ro') for u in uris)
    assert path.read_bytes() == before
    assert not (tmp_path / 'missing.db').exists()
    conn.close()


@pytest.mark.parametrize('mode', ['release', 'stop', 'wall', 'deadline', 'read_failure', 'expiry', 'transient_read'])
def test_supervisor_keeps_checks_during_start_lock(tmp_path, monkeypatch, mode):
    db = LabDB(str(tmp_path / 'lab.db'))
    # Minimal fixture: no experiment payload or approved spec is launched.
    db.conn.execute('CREATE TABLE start_probe(pid INT, started TEXT)')
    meta = {'limits': {'wall_clock_hours': 0 if mode == 'wall' else 1}, 'entry_spec': {}, 'scope': 'test'}
    if mode == 'expiry':
        meta['sandbox'] = {'cores': [4], 'seed_env': '', 'expires': '2000-01-01T00:00:00+00:00',
                           'repo': 'fixture', 'cpus': 1}
        meta['request_id'] = 'fixture'
    (tmp_path / 'spec_entry.json').write_text(json.dumps(meta))
    run = {'run_dir': str(tmp_path), 'cmd': '[]', 'cwd': str(tmp_path), 'stop_requested': mode == 'stop'}
    reads = [0]
    def read(_):
        reads[0] += 1
        if reads[0] > 1 and (mode == 'read_failure' or (mode == 'transient_read' and reads[0] == 2)):
            raise sqlite3.OperationalError('database is locked')
        return run
    monkeypatch.setattr(db, 'run', read)
    monkeypatch.setattr(L, 'LabDB', lambda: db)
    monkeypatch.setattr(L, 'lab_root', lambda: str(tmp_path))
    other = sqlite3.connect(db.path, isolation_level=None)
    other.execute('BEGIN IMMEDIATE')
    # Start write uses the same table/SQL shape, but fixture stores only pid/time.
    db.conn.execute('PRAGMA busy_timeout=0')
    real_tx = db.tx
    ended_before_identity_wait = []
    from contextlib import contextmanager
    @contextmanager
    def tx(**kw):
        with real_tx(**kw) as c:
            proxy = Mock()
            def execute(sql, args):
                if proc.returncode is not None:
                    ended_before_identity_wait.append(L.now())
                    clock[0] += 100  # record-lock delay after the child has exited must not extend accounting
                return c.execute('INSERT INTO start_probe VALUES (?,?)', args[:2])
            proxy.execute.side_effect = execute
            yield proxy
    monkeypatch.setattr(db, 'tx', tx)
    proc = Mock(pid=999999, returncode=None)
    proc.poll.side_effect = lambda: proc.returncode
    proc.wait.side_effect = lambda: setattr(proc, 'returncode', -15)
    monkeypatch.setattr(L.subprocess, 'Popen', lambda *a, **kw: proc)
    calls = []
    def kill(pid, sig):
        calls.append((pid, sig))
        proc.returncode = -15
    monkeypatch.setattr(L.os, 'killpg', kill)
    clock = [0]
    monkeypatch.setattr(L, 'now', lambda: L.dt.datetime.fromtimestamp(1800000000 + clock[0], L.dt.timezone.utc).isoformat())
    monkeypatch.setattr(L.time, 'monotonic', lambda: clock[0])
    def sleep(_):
        clock[0] += 5
        if mode in ('release', 'transient_read'):
            other.execute('COMMIT')
            if db.conn.execute('SELECT COUNT(*) FROM start_probe').fetchone()[0]:
                proc.returncode = 0
        if clock[0] > 100:
            raise AssertionError('supervision not bounded')
    # Release just once; subsequent poll finishes the fake child.
    released = [False]
    def nap(seconds):
        if mode in ('release', 'transient_read') and released[0]:
            clock[0] += 5
            proc.returncode = 0
        else:
            sleep(seconds)
            released[0] = mode in ('release', 'transient_read')
    monkeypatch.setattr(L.time, 'sleep', nap)
    monkeypatch.setattr(L, 'START_LOCK_WAIT_S', 10)
    def finish(*a, **kw):
        calls.append(('finish', a[3], a[5]))
        if ended_before_identity_wait:
            assert kw['ended'] == ended_before_identity_wait[0]
            assert kw['ended'] != L.now()
    monkeypatch.setattr(L, 'finish_run', finish)
    # Final identity write occurs only after reaping; release lock at proc.wait.
    def wait():
        if other.in_transaction:
            other.execute('COMMIT')
        proc.returncode = -15
    proc.wait.side_effect = wait
    try:
        L.supervise('fixture')
        assert reads[0] >= 2
        assert calls[-1][0] == 'finish'
        if mode in ('release', 'transient_read'):
            assert calls[-1][1] == 'done' and len(calls) == 1
        else:
            assert calls[0][0] == proc.pid
            assert calls[-1][1] == 'stopped'
            assert calls[-1][2]
        assert db.conn.execute('SELECT COUNT(*) FROM start_probe').fetchone()[0] == 1
    finally:
        other.close()
        db.close()
