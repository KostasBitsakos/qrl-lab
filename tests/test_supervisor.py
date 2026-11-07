"""J383 supervisor: crash / clean-exit / stall / retry-budget / service cases, plus driver.resume guards. No real launches."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import importlib.util  # noqa: E402

import supervisor as S  # noqa: E402

NOW = 1_800_000_000.0


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def mk(tmp, name='run', state='RUNNING', alive_pids=(), resumes=0, stop=False, age=10):
    out = tmp / name
    out.mkdir()
    (out / 'parent-spec.json').write_text('{}')
    (out / 'receipt.json').write_text(json.dumps(dict(request='R-1', session='abcdef012345', phase='GO',
                                                      pids=dict(drive=11, watch=12), resumes=resumes)))
    (out / 'state.json').write_text(json.dumps(dict(state=state, ts=iso(NOW - age), reason='x')))
    (out / 'watch-ready.json').write_text(json.dumps(dict(ts=iso(NOW - age))))
    if stop:
        (out / 'STOP').write_text('x')
    return out


class Env:
    def __init__(self, tmp, alive=()):
        self.alive, self.sent, self.asks, self.resumes, self.tmp = set(alive), [], [], [], tmp
        self.resume_ok = True
        self.units = {}
        self.restarts = []

    def tick(self, targets, now=NOW, rows=(), **kw):
        return S.tick(now=now, targets=targets, rows_fn=lambda r: list(rows), alive=lambda p: p in self.alive,
                      poster=lambda b: self.sent.append(b) or f'M-{len(self.sent)}',
                      asker=lambda t, b: self.asks.append(t) or 'R-x',
                      resumer=lambda o, r: self.resumes.append((o, r)) or (self.resume_ok, 'msg'),
                      unit_fn=lambda u: self.units.get(u, 'active'), restarter=lambda u: self.restarts.append(u) or True,
                      mem_path=self.tmp / 'mem.json', services=kw.pop('services', ()), journal=lambda m, now=None: [],
                      beat_path=self.tmp / 'nobeat', **kw)


def test_healthy_is_silent(tmp_path):
    e = Env(tmp_path, alive={11, 12})
    e.tick([mk(tmp_path)])
    assert not e.sent and not e.resumes


def test_clean_exit_after_done_is_not_an_alarm(tmp_path):
    """The J380 false alarm: driver gone, state DONE. First seen already DONE -> silent; seen RUNNING then DONE -> one 'finished'."""
    out = mk(tmp_path, state='DONE')
    e = Env(tmp_path)
    e.tick([out])
    assert not e.sent and not e.resumes and not e.asks
    out2 = mk(tmp_path, name='run2')
    e.alive = {11, 12}
    e.tick([out2])
    (out2 / 'state.json').write_text(json.dumps(dict(state='DONE', ts=iso(NOW))))
    e.alive = set()
    e.tick([out2], now=NOW + 120)
    e.tick([out2], now=NOW + 240)
    assert len(e.sent) == 1 and 'DONE' in e.sent[0] and not e.resumes and not e.asks


def test_crash_needs_two_polls_then_resumes_once(tmp_path):
    out = mk(tmp_path, alive_pids=())
    e = Env(tmp_path, alive={12})            # driver dead, watch alive
    e.tick([out])
    assert not e.resumes and len(e.sent) == 1 and 'Επιβεβαίωση' in e.sent[0]   # immediate alert, no action yet
    e.tick([out], now=NOW + 120)
    assert e.resumes == [(str(out), 'R-1')] and len(e.sent) == 2 and 'ΕΠΙΤΥΧΗΣ' in e.sent[1] and not e.asks


def test_resume_failure_escalates_without_retry_loop(tmp_path):
    out = mk(tmp_path)
    e = Env(tmp_path)
    e.resume_ok = False
    e.tick([out])
    e.tick([out], now=NOW + 120)
    assert len(e.resumes) == 1 and len(e.asks) == 1 and 'ΑΠΕΤΥΧΕ' in e.sent[1]


def test_retry_budget_max_two_then_ask(tmp_path):
    out = mk(tmp_path, resumes=2)            # driver already counted 2 resumes
    e = Env(tmp_path)
    e.tick([out])
    e.tick([out], now=NOW + 120)
    assert not e.resumes and len(e.asks) == 1


def test_supervisor_side_budget(tmp_path):
    out = mk(tmp_path)
    e = Env(tmp_path)
    for i in range(6):
        e.tick([out], now=NOW + 120 * i)
    assert len(e.resumes) == S.MAX_RESUMES and len(e.asks) == 1


@pytest.mark.parametrize('kw', [dict(stop=True), dict(state='STOPPED')])
def test_stop_file_or_stopped_never_auto_resumes(tmp_path, kw):
    out = mk(tmp_path)
    e = Env(tmp_path, alive={11, 12})
    e.tick([out])                                   # supervisor first sees it healthy
    if kw.get('stop'):
        (out / 'STOP').write_text('x')
    else:
        (out / 'state.json').write_text(json.dumps(dict(state='STOPPED', ts=iso(NOW), reason='x')))
    e.alive = set()
    e.tick([out], now=NOW + 120)
    e.tick([out], now=NOW + 240)
    assert not e.resumes and len(e.asks) == 1 and len(e.sent) == 1    # deduped, ask once


def test_stall_alert_only(tmp_path):
    out = mk(tmp_path)
    log = tmp_path / 'o.log'
    log.write_text('x')
    os.utime(log, (NOW - 7200, NOW - 7200))
    rows = [dict(status='running', run_dir=str(tmp_path), pid=5, run_id='r1', name='t/t')]
    (tmp_path / 'output.log').write_text('x')
    os.utime(tmp_path / 'output.log', (NOW - 7200, NOW - 7200))
    e = Env(tmp_path, alive={11, 12, 5})
    e.tick([out], rows=rows)
    assert len(e.sent) == 1 and 'κολλημένο' in e.sent[0] and not e.resumes and len(e.asks) == 1


def test_fresh_output_is_not_a_stall(tmp_path):
    out = mk(tmp_path)
    (tmp_path / 'output.log').write_text('x')
    os.utime(tmp_path / 'output.log', (NOW - 60, NOW - 60))
    rows = [dict(status='running', run_dir=str(tmp_path), pid=5, run_id='r1', name='t/t')]
    e = Env(tmp_path, alive={11, 12, 5})
    e.tick([out], rows=rows)
    assert not e.sent


def test_dead_run_payload_asks(tmp_path):
    out = mk(tmp_path)
    rows = [dict(status='running', run_dir=str(tmp_path), pid=99, run_id='r9', name='t/t')]
    e = Env(tmp_path, alive={11, 12})
    e.tick([out], rows=rows)
    assert len(e.asks) == 1 and not e.resumes


def test_recovery_rearms_alarm(tmp_path):
    out = mk(tmp_path)
    e = Env(tmp_path)
    e.resume_ok = True
    e.tick([out])
    e.tick([out], now=NOW + 120)
    e.alive = {11, 12}
    e.tick([out], now=NOW + 240)             # healthy again
    e.alive = {12}
    e.tick([out], now=NOW + 360)
    e.tick([out], now=NOW + 480)
    assert len(e.resumes) == 2               # second crash handled (attempt 2 of 2)


def test_failed_post_is_retried(tmp_path):
    out = mk(tmp_path)
    e = Env(tmp_path, alive={11, 12})
    e.tick([out])
    (out / 'STOP').write_text('x')
    calls = []

    def bad(b):
        calls.append(b)
        raise RuntimeError('down')
    log = S.tick(now=NOW, targets=[out], rows_fn=lambda r: [], alive=lambda p: False, poster=bad, asker=lambda t, b: 'R',
               unit_fn=lambda u: 'active', mem_path=tmp_path / 'mem.json', services=(), journal=lambda m, now=None: [],
               beat_path=tmp_path / 'nb')
    assert any(l[0] == 'notify-error' for l in log)
    e.tick([out])
    assert len(e.sent) == 1


def test_service_restart_bounded(tmp_path):
    e = Env(tmp_path)
    e.units['qrl-dashboard.service'] = 'failed'
    for i in range(4):
        e.tick([], now=NOW + 60 * i, services=('qrl-dashboard.service',))
    assert len(e.restarts) == S.MAX_SERVICE_RESTARTS and len(e.asks) == 1


def test_service_activating_and_unobservable_untouched(tmp_path):
    e = Env(tmp_path)
    e.units['u1'] = 'activating'
    e.tick([], services=('u1',))
    e.units['u2'] = 'unobservable'
    e.tick([], services=('u2',))
    assert not e.restarts and len(e.sent) == 1


def test_dry_run_acts_on_nothing(tmp_path):
    out = mk(tmp_path)
    e = Env(tmp_path)
    (tmp_path / 'mem.json').write_text(json.dumps(dict(targets={'run': {'suspect_since': NOW}})))
    log = e.tick([out], now=NOW + 120, dry=True)
    assert not e.resumes and not e.sent and any(l[0] == 'would-resume' for l in log)


def test_classify_matrix(tmp_path):
    base = dict(alive=dict(drive=True, watch=True), stop_file=False, state_age=5, n_active=0, last_output_age=None,
                dead_runs=[], state=dict(state='RUNNING'), resumes=0)
    assert S.classify(base)[0] == 'healthy'
    assert S.classify(dict(base, alive=dict(drive=False, watch=True)))[0] == 'role_dead'
    assert S.classify(dict(base, alive=dict(drive=False, watch=False), state=dict(state='DONE')))[0] == 'finished'
    assert S.classify(dict(base, state_age=999))[0] == 'stalled'


# ---- driver.resume guards (no process is started unless the guards pass)
def _driver(tmp, monkeypatch):
    spec = importlib.util.spec_from_file_location('c345_driver_sup', ROOT / 'tools/c345/driver.py')
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    monkeypatch.setattr(d, 'OUT', tmp)
    monkeypatch.setattr(d, 'validate', lambda s: s)
    monkeypatch.setattr(d, 'Backend', lambda rid, spec: type('B', (), {'approval': lambda self: None})())
    return d


def _prep(tmp, d, **over):
    (tmp / 'parent-spec.json').write_text('{}')
    r = dict(request='R-1', session='s', phase='GO', pids=dict(drive=2 ** 22 + 5, watch=2 ** 22 + 6), resumes=0,
             spec_hash=d.canonical_hash({}))
    r.update(over)
    (tmp / 'receipt.json').write_text(json.dumps(r))
    (tmp / 'state.json').write_text(json.dumps(dict(state='RUNNING', ts=datetime.now(timezone.utc).isoformat())))


@pytest.mark.parametrize('over,msg', [(dict(resumes=2), 'budget'), (dict(phase='ABORT'), 'binding'),
                                      (dict(spec_hash='bad'), 'binding')])
def test_driver_resume_refusals(tmp_path, monkeypatch, over, msg):
    d = _driver(tmp_path, monkeypatch)
    _prep(tmp_path, d, **over)
    with pytest.raises(d.LabError, match=msg):
        d.resume('R-1')


def test_driver_resume_refuses_stop_and_terminal_and_alive(tmp_path, monkeypatch):
    d = _driver(tmp_path, monkeypatch)
    _prep(tmp_path, d)
    (tmp_path / 'STOP').write_text('x')
    with pytest.raises(d.LabError, match='STOP'):
        d.resume('R-1')
    (tmp_path / 'STOP').unlink()
    (tmp_path / 'state.json').write_text(json.dumps(dict(state='STOPPED', ts=datetime.now(timezone.utc).isoformat())))
    with pytest.raises(d.LabError, match='state'):
        d.resume('R-1')
    (tmp_path / 'state.json').write_text(json.dumps(dict(state='RUNNING', ts=datetime.now(timezone.utc).isoformat())))
    r = json.loads((tmp_path / 'receipt.json').read_text())
    r['pids'] = dict(drive=os.getpid(), watch=os.getpid())
    (tmp_path / 'receipt.json').write_text(json.dumps(r))
    with pytest.raises(d.LabError, match='alive'):
        d.resume('R-1')


def test_driver_resume_respawns_only_dead_role(tmp_path, monkeypatch):
    d = _driver(tmp_path, monkeypatch)
    _prep(tmp_path, d)
    r = json.loads((tmp_path / 'receipt.json').read_text())
    r['pids']['watch'] = os.getpid()                      # watch alive, drive dead
    (tmp_path / 'receipt.json').write_text(json.dumps(r))
    spawned = []

    class P:
        pid = 777777

        def __init__(self, cmd, **kw):
            spawned.append(cmd)
            (tmp_path / 'drive-ready.json').write_text(json.dumps(dict(session='s', pid=self.pid)))

        def poll(self):
            return None
    monkeypatch.setattr(d.subprocess, 'Popen', P)
    d.resume('R-1')
    assert len(spawned) == 1 and 'drive' in spawned[0] and 'resume' not in spawned[0]
    r = json.loads((tmp_path / 'receipt.json').read_text())
    assert r['resumes'] == 1 and r['phase'] == 'GO' and r['pids']['drive'] == 777777 and r['pids']['watch'] == os.getpid()


def test_historic_terminal_or_abandoned_targets_are_baselined(tmp_path):
    old_stopped = mk(tmp_path, name='a', state='STOPPED')
    abandoned = mk(tmp_path, name='b', age=10 * 3600)
    e = Env(tmp_path)
    e.tick([old_stopped, abandoned])
    e.tick([old_stopped, abandoned], now=NOW + 120)
    e.tick([old_stopped, abandoned], now=NOW + 240)
    assert not e.sent and not e.asks and not e.resumes


def test_resume_keeps_phase_go_and_restores_on_failure(tmp_path, monkeypatch):
    d = _driver(tmp_path, monkeypatch)
    _prep(tmp_path, d)
    seen = []

    class P:
        pid = 888888

        def __init__(self, cmd, **kw):
            seen.append(json.loads((tmp_path / 'receipt.json').read_text())['phase'])

        def poll(self):
            return 1                                       # child dies at once -> handshake fails
    monkeypatch.setattr(d.subprocess, 'Popen', P)
    with pytest.raises(d.LabError, match='handshake'):
        d.resume('R-1')
    r = json.loads((tmp_path / 'receipt.json').read_text())
    assert seen and set(seen) == {'GO'} and r['phase'] == 'GO' and r['pids']['drive'] == 2 ** 22 + 5


def test_service_bound_survives_failed_post(tmp_path):
    e = Env(tmp_path)
    e.units['u'] = 'failed'
    def bad(b): raise RuntimeError('x')
    for i in range(4):
        S.tick(now=NOW + 60 * i, targets=[], rows_fn=lambda r: [], alive=lambda p: False, poster=bad, asker=lambda t, b: 'R',
               unit_fn=lambda u: e.units.get(u, 'active'), restarter=lambda u: e.restarts.append(u) or True,
               mem_path=tmp_path / 'mem.json', services=('u',), journal=lambda m, now=None: [], beat_path=tmp_path / 'nb')
    assert len(e.restarts) == S.MAX_SERVICE_RESTARTS


def test_resumer_exception_counts_as_failure(tmp_path):
    out = mk(tmp_path)
    e = Env(tmp_path)
    def boom(o, r): raise TimeoutError('t')
    kw = dict(rows_fn=lambda r: [], alive=lambda p: False, poster=lambda b: e.sent.append(b) or 'M', asker=lambda t, b: e.asks.append(t),
              resumer=boom, unit_fn=lambda u: 'active', mem_path=tmp_path / 'mem.json', services=(), journal=lambda m, now=None: [],
              beat_path=tmp_path / 'nb')
    S.tick(now=NOW, targets=[out], **kw)
    S.tick(now=NOW + 120, targets=[out], **kw)
    S.tick(now=NOW + 240, targets=[out], **kw)
    assert len(e.asks) == 1 and 'ΑΠΕΤΥΧΕ' in e.sent[1]
    mem = json.loads((tmp_path / 'mem.json').read_text())
    assert mem['targets']['run']['resume_failed'] and mem['targets']['run']['resume_attempts'] == 1


def test_ask_rearms_after_recovery(tmp_path):
    out = mk(tmp_path)
    e = Env(tmp_path, alive={11, 12})
    log = tmp_path / 'output.log'
    rows = [dict(status='running', run_dir=str(tmp_path), pid=11, run_id='r', name='t/t')]
    log.write_text('x')
    os.utime(log, (NOW - 7200, NOW - 7200))
    e.tick([out], rows=rows)                       # stalled -> ask #1
    os.utime(log, (NOW + 100, NOW + 100))
    e.tick([out], now=NOW + 120, rows=rows)        # healthy -> rearm
    os.utime(log, (NOW - 7200 + 300, NOW - 7200 + 300))
    e.tick([out], now=NOW + 7500, rows=rows)       # stalled again
    assert len(e.asks) == 2


def test_driver_resume_refuses_old_heartbeat(tmp_path, monkeypatch):
    d = _driver(tmp_path, monkeypatch)
    _prep(tmp_path, d)
    (tmp_path / 'state.json').write_text(json.dumps(dict(state='RUNNING', ts='2020-01-01T00:00:00+00:00')))
    with pytest.raises(d.LabError, match='abandoned'):
        d.resume('R-1')
