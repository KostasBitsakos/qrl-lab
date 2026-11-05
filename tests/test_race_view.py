"""Dispatcher board authority and legacy Race fallback (M-20261029-167)."""
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import race_view

NOW = 20000


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def job(jid, lane='worker', status='running', **kw):
    return dict(id=jid, lane=lane, status=status, provider='codex', title='Tutorial <test>',
                created=iso(NOW-100), started=iso(NOW-90), ended=kw.pop('ended', None), **kw)


def test_parallel_workers_and_correct_coordinator():
    js = [job('J97'), job('J100'), job('C102', lane='chat')]
    stale = [dict(hook_event_name='SubagentStart', agent_id='J97', agent_type='codex-engineer', ts=NOW-20)]
    lanes = race_view.lanes(stale, now=NOW, jobs=js, coord_model='claude-opus')
    assert len(lanes) == 3
    assert {r['job_id'] for r in lanes} == {'C102', 'J97', 'J100'}
    assert lanes[0]['coord'] and lanes[0]['provider'] == 'Codex'
    assert all(r['model'] == '' and r['progress'] is None for r in lanes)
    h = race_view.render(lanes)
    assert 'Claude' not in h
    assert all(jid in h for jid in ('C102', 'J97', 'J100'))
    assert 'Tutorial &lt;test&gt;' in h and 'Tutorial <test>' not in h
    assert '3 στην πίστα' in h


def test_terminal_queue_and_cancel_requested():
    js = [job('J1', status='done', ended=iso(NOW-30)),
          job('J2', status='cancelled', ended=iso(NOW-20)),
          job('J3', status='failed', ended=iso(NOW-10)),
          job('J4', status='queued'), job('J5', cancel=1),
          job('J6', status='done', ended=iso(10))]
    lanes = race_view.lanes([], now=NOW, jobs=js, window=1000)
    assert {r['job_id'] for r in lanes} == {'J1', 'J2', 'J3', 'J4', 'J5'}
    assert next(r for r in lanes if r['job_id'] == 'J5')['reasons'] == ['ζητήθηκε ακύρωση']
    h = race_view.render(lanes)
    assert 'ακυρώθηκε' in h and 'σε ουρά' in h and 'ολοκληρώθηκε' in h
    assert '1 στην πίστα' in h


def test_active_not_truncated_or_aged_out_and_dedup():
    js = [job('J1'), job('J2'), job('J1')]
    lanes = race_view.lanes([], now=NOW+20000, jobs=js, max_lanes=1)
    assert len(lanes) == 2 and all(r['progress'] is None for r in lanes)
    assert race_view.lanes([], now=NOW, jobs=[]) == []


def test_database_snapshot_actual_attempt_and_unknown(tmp_path):
    path = tmp_path / 'dispatch.db'
    db = sqlite3.connect(path)
    db.executescript('''CREATE TABLE jobs(n INTEGER, id TEXT, lane TEXT, title TEXT, status TEXT,
        created TEXT, started TEXT, ended TEXT, cancel INTEGER, provider TEXT);
        CREATE TABLE tasks(id INTEGER, refs TEXT, provider TEXT, model TEXT);''')
    db.execute('INSERT INTO jobs VALUES (1, ?, ?, ?, ?, ?, ?, NULL, 0, ?)',
               ('C1', 'chat', 'test', 'running', iso(NOW-100), iso(NOW-90), 'claude'))
    db.execute('INSERT INTO jobs VALUES (2, ?, ?, ?, ?, ?, NULL, NULL, 0, ?)',
               ('J2', 'worker', 'queued', 'queued', iso(NOW-100), 'claude'))
    db.executemany('INSERT INTO tasks VALUES (?, ?, ?, ?)', [
        (1, '["C1"]', 'claude', 'old'), (2, '["C1"]', 'codex', None),
        (3, '["C10"]', 'claude', 'wrong'), (4, 'broken', 'claude', 'wrong'),
        (5, '{"J2":1}', 'claude', 'wrong')])
    db.commit()
    db.close()
    jobs = race_view.load_jobs(path)
    lanes = race_view.lanes([], now=NOW, jobs=jobs)
    assert lanes[0]['provider'] == 'Codex' and lanes[0]['model'] == ''
    assert lanes[1]['provider'] == 'άγνωστος πάροχος'
    assert 'provider' not in jobs[1]  # assigned provider never masquerades as execution


def test_unavailable_database_legacy_fallback(tmp_path):
    missing = tmp_path / 'missing.db'
    assert race_view.load_jobs(missing) is None and not missing.exists()
    malformed = tmp_path / 'bad.db'
    malformed.write_text('not sqlite')
    assert race_view.load_jobs(malformed) is None
    ev = [dict(hook_event_name='SubagentStart', agent_id='old', agent_type='engineer', ts=NOW-20)]
    lanes = race_view.lanes(ev, now=NOW, jobs=race_view.load_jobs(missing))
    assert any(r['role'] == 'engineer' for r in lanes)
