"""No live posts, no experiment launches: fixtures exercise the independent monitors."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import pytest

DIR = Path(__file__).resolve().parents[1] / 'tools/c345'
sys.path.insert(0, str(DIR))
import monitor_common as C
import watch_alert as A
import progress_report as P
import install_monitors as I


def observation():
    return dict(now=2000, state=dict(state='RUNNING', checked={}, errors={}),
                spec=dict(tasks=[dict(name='a'), dict(name='b')]), rows=[],
                identities=dict(drive=True, watch=True), heartbeats=dict(drive=0, watch=0),
                counts=dict(done=0, running=1, queued=1, failed=0), launcher=[], dead_runs=[])


@pytest.mark.parametrize('kind,key', [('dead','process_dead'), ('stale','heartbeat_stale'),
                                      ('terminal','stopped'), ('worker','run_dead'),
                                      ('namespace','observation_error'), ('done','done')])
def test_alarm_cases(kind, key):
    s = observation()
    if kind == 'dead': s['identities']['drive'] = False
    if kind == 'stale': s['heartbeats']['watch'] = 181
    if kind == 'terminal': s['state']['state'] = 'STOPPED'
    if kind == 'worker': s['dead_runs'] = ['x']
    if kind == 'namespace': s['host_namespace'] = False
    if kind == 'done':
        s['state']['state'] = 'DONE'; s['counts'].update(done=2, running=0, queued=0)
    assert A.evaluate(s, {})[0] == key


def test_idle_stall_and_long_active_run():
    s = observation()
    previous = dict(fingerprint='[]', last_change=0)
    assert A.evaluate(s, previous)[0] == 'healthy'
    s['counts']['running'] = 0
    assert A.evaluate(s, previous)[0] == 'stalled'
    # New task/state transitions reset the idle clock.
    assert A.evaluate(s, dict(previous, fingerprint='changed'))[0] == 'healthy'


def test_completion_must_match_runs():
    s = observation(); s['state']['state'] = 'DONE'
    assert A.evaluate(s, {})[0] == 'inconsistent_done'


def test_launcher_mismatch_and_task_failure():
    s = observation()
    s['rows'] = [dict(run_id='x', status='failed', ended='ts')]
    assert A.evaluate(s, {})[0] == 'launcher_mismatch'
    s['launcher'] = ['x failed']; s['counts']['failed'] = 1
    assert A.evaluate(s, {})[0] == 'task_failed_1'


def test_delivery_dedup_retry_and_recovery():
    calls = []
    send = lambda body: calls.append(body) or 'M-fixture'
    prev = {}
    record = dict(checked_at='now')
    record = A.deliver('process_dead', 'dead', record, prev, send)
    assert record['delivered'] == 'process_dead'
    A.deliver('process_dead', 'dead', dict(record), record, send)
    assert len(calls) == 1
    record = A.deliver('healthy', '', dict(record), record, send)
    assert len(calls) == 2 and 'ξανά' in calls[-1]
    def fail(body): raise RuntimeError('delivery failed')
    prev = dict(record)
    with pytest.raises(RuntimeError):
        A.deliver('stopped', 'stopped', dict(record), prev, fail)
    assert prev['delivered'] == 'healthy'
    A.deliver('stopped', 'stopped', dict(record), prev, send)
    assert len(calls) == 3


def test_pid_reuse_and_zombie(tmp_path):
    p = tmp_path / '42'; p.mkdir()
    (p / 'stat').write_text('42 (python) S 1')
    (p / 'cmdline').write_bytes(b'python\0tools/c345/driver.py\0drive\0--session\0abc\0')
    assert C.identity(42, 'drive', 'abc', tmp_path)
    assert not C.identity(42, 'watch', 'abc', tmp_path)
    assert not C.identity(42, 'drive', 'other', tmp_path)
    (p / 'cmdline').write_bytes(b'kworker\0')
    assert not C.identity(42, 'drive', 'abc', tmp_path)
    (p / 'stat').write_text('42 (python) Z 1')
    assert not C.identity(42, proc=tmp_path)


def metric_fixture(tmp_path):
    s = observation()
    tasks = []
    for config, seed, ret in [('c0',18500,10), ('c0',18501,30), ('c1',18500,100)]:
        name = f'{config}-{seed}'
        task = dict(name=name, stage='W', arm='lstm', lane='opus', config=config, seed=seed,
                    target_ticks=20, out=name+'.json', child=dict(cwd='.'))
        artifact = dict(seed=seed, eval_splits=['val'], eval_seeds={'val': [1,2]},
                        target_variant='pms:poisson_ms', checkpoint_results={'20': {'val': {'episodes': [
                            dict(ret=ret,slo_viol_rate=.1),dict(ret=ret+2,slo_viol_rate=.3)]}}})
        (tmp_path / task['out']).write_text(json.dumps(artifact))
        tasks.append(task)
        s['state']['checked'][name] = 'ok'
    s['spec'] = dict(tasks=tasks, policy=dict(val_seeds=[1,2], variant='pms:poisson_ms'))
    s['task_rows'] = {t['name']:dict(status='done',exit_code=0) for t in tasks}
    return s


def test_seed_metrics_separate_configs(tmp_path):
    s = metric_fixture(tmp_path)
    lines, errors = P.metrics(s, tmp_path)
    assert not errors and len(lines) == 2
    assert '21.000' in lines[0] and 'n=2' in lines[0] and '0.200000' in lines[0]
    assert '101.000' in lines[1] and 'n=1' in lines[1]


def test_reject_unchecked_wrong_provenance_nonfinite(tmp_path):
    s = metric_fixture(tmp_path)
    s['state']['checked']['c0-18500'] = 'failed'
    path = tmp_path / 'c0-18501.json'; x = C.read(path); x['eval_splits'] = ['test']; path.write_text(json.dumps(x))
    path = tmp_path / 'c1-18500.json'; x = C.read(path); x['checkpoint_results']['20']['val']['episodes'][0]['ret'] = float('nan'); path.write_text(json.dumps(x))
    lines, errors = P.metrics(s, tmp_path)
    assert lines == [] and sorted(errors) == ['c0-18501','c1-18500']


def test_schedule_anchored_to_start():
    started = '2026-11-06T20:18:27+00:00'; start = C.epoch(started)
    assert P.due_slot(started, start+21599) == 0
    assert P.due_slot(started, start+21600) == 1
    assert P.due_slot(started, start+43200) == 2
    cmds = I.commands(started)
    assert '--on-unit-active=2min' in cmds[0]
    assert '--on-calendar=*-*-* 02,08,14,20:18:27 UTC' in cmds[1]
    assert all('--property=KillMode=process' in c for c in cmds)
    assert all('--property=CPUAffinity=4-7' in c for c in cmds)


def test_eta_unknown_before_learning_finishes():
    s = observation(); s['task_rows'] = {}; s['spec']['tasks'] = []
    assert P.eta(s).startswith('άγνωστο')


def test_snapshot_count_and_charge_independent_of_reservation(tmp_path, monkeypatch):
    import sqlite3
    out = tmp_path / 'out'; out.mkdir()
    lab = tmp_path / '.lab'; lab.mkdir()
    run = tmp_path / 'run'; run.mkdir()
    start = '2026-11-06T20:18:27+00:00'; now = C.epoch(start) + 1800
    spec = dict(tasks=[dict(name='a'),dict(name='b'),dict(name='c')])
    state = dict(state='RUNNING', ts=C.stamp(now), checked={'a':'ok'}, used_cpu_h=8)
    receipt = dict(request='R-fixture',pids={'drive':1,'watch':2}, session='test', started=start)
    for name, data in [('parent-spec.json',spec),('state.json',state),('receipt.json',receipt),
                       ('watch-ready.json',dict(ts=C.stamp(now)))]:
        (out / name).write_text(json.dumps(data))
    (run / 'spec_entry.json').write_text(json.dumps(dict(sandbox=dict(cpus=2,reserve_cpu_h=8))))
    with sqlite3.connect(lab / 'lab.db') as db:
        db.execute('CREATE TABLE runs (run_id,request_id,name,status,pid,exit_code,started,ended,run_dir,cmd)')
        db.executemany('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)', [
            ('id-a','R-fixture','a/a','done',11,0,start,C.stamp(now),str(run),'[]'),
            ('id-b','R-fixture','b/b','running',12,None,start,None,str(run),'[]')])
    monkeypatch.setattr(C,'command',lambda *a,**k:'id-a done\nid-b running')
    monkeypatch.setattr(C,'identity',lambda *a,**k:True)
    s = C.snapshot(now, out, tmp_path)
    assert s['counts'] == dict(done=1,running=1,queued=1,failed=0,verifying=0)
    assert s['charged_cpu_h'] == 2 # each run 0.5h x 2 cores; not 8h reservation
    assert s['state']['used_cpu_h'] == 8


def test_missing_metrics_render_unknown(tmp_path):
    s = observation()
    s.update(charged_cpu_h=None,task_rows={})
    s['state'].update(stage='P0',used_cpu_h=.75)
    s['counts']['verifying'] = 0
    s['spec'] = dict(tasks=[],policy=dict(val_seeds=[1,2]),sandbox=dict(cpu_hours_budget=80.561861))
    body = P.render(s,'fixture',tmp_path)
    assert 'Δεν υπάρχουν ακόμη' in body and 'άγνωστη CPU-h' in body
    assert 'val/screening' in body and 'χωρίς ισχυρισμό' in body


def test_post_failure_does_not_mark_schedule_delivered(tmp_path,monkeypatch):
    from contextlib import nullcontext
    start = '2026-11-06T20:18:27+00:00'
    (tmp_path / 'receipt.json').write_text(json.dumps(dict(started=start)))
    monkeypatch.setattr(C,'OUT',tmp_path); monkeypatch.setattr(C,'MONITOR',tmp_path)
    monkeypatch.setattr(C,'locked',lambda name:nullcontext())
    monkeypatch.setattr(P.time,'time',lambda:C.epoch(start)+21600)
    monkeypatch.setattr(C,'snapshot',lambda now:observation())
    monkeypatch.setattr(P,'changes',lambda *a,**k:('changes',{}))
    monkeypatch.setattr(P,'render',lambda *a,**k:'body')
    def fail(body): raise RuntimeError('post failed')
    monkeypatch.setattr(C,'post',fail); monkeypatch.setattr(sys,'argv',['progress','--due'])
    with pytest.raises(RuntimeError): P.main()
    assert not (tmp_path / 'progress-state.json').exists()
    monkeypatch.setattr(C,'post',lambda body:'M-fixture')
    P.main()
    assert C.read(tmp_path / 'progress-state.json')['slot'] == 1


def test_reference_metrics(tmp_path):
    s = observation()
    t = dict(name='ref',stage='P0',child=dict(cwd='.'),out='ref.json')
    s['spec'] = dict(tasks=[t],policy=dict(val_seeds=[1,2],variant='pms:poisson_ms'))
    s['state']['checked'] = {'ref':'ok'}
    s['task_rows'] = {'ref':dict(status='done',exit_code=0)}
    x = dict(split='val',seeds=[1,2],variant='pms:poisson_ms',grids={'hpa_orig':{'50':{
        'episodes':[dict(ret=4,slo_viol_rate=.2),dict(ret=6,slo_viol_rate=.4)]}}})
    (tmp_path / 'ref.json').write_text(json.dumps(x))
    lines, errors = P.metrics(s,tmp_path)
    assert not errors and len(lines) == 1
    assert '5.000' in lines[0] and 'χωρίς training seeds' in lines[0]


def test_failed_task_does_not_emit_false_recovery():
    s = observation(); s['counts']['failed'] = 1
    calls = []; previous = {}
    for _ in range(3):
        key,text,record = A.evaluate(s,previous)
        previous = A.deliver(key,text,record,previous,lambda body:calls.append(body) or 'M-test')
    assert len(calls) == 1 and 'ξανά' not in calls[0]


def test_fractional_and_non_utc_schedule():
    commands = I.commands('2026-11-06T22:18:27.398702+02:00')
    assert '--on-calendar=*-*-* 02,08,14,20:18:28 UTC' in commands[1]
    now = C.epoch('2026-11-07T02:18:28+00:00')
    assert P.due_slot('2026-11-06T22:18:27.398702+02:00',now) == 1


def test_payload_pid_binding(tmp_path):
    p = tmp_path / '42'; p.mkdir()
    (p / 'stat').write_text('42 (python) S 1')
    (p / 'cmdline').write_bytes(b'python\0tuning/cycle2_entry.py\0--out\0a.json\0')
    expected = ['python','tuning/cycle2_entry.py','--out','a.json']
    assert C.identity(42,proc=tmp_path,expected=expected)
    assert not C.identity(42,proc=tmp_path,expected=expected[:-1]+['other.json'])
    assert not C.identity(None,proc=tmp_path)
