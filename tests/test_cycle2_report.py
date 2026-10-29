import json
from pathlib import Path
import sqlite3
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cycle2_report as c


def fixture(tmp_path):
    (tmp_path / '.lab/specs').mkdir(parents=True)
    name = 'j119-screen-rppo-c0-s15010'
    cmd = ['python', '--out', 'result.json']
    entry = dict(name=name,cmd=cmd)
    spec = {'review': {'screen_waves': {'code-poisson': [{'entries': [entry, dict(entry, name='j119-screen-rppo-c0-s15011')]}]}}}
    (tmp_path / c.AMENDMENT).write_text(json.dumps(spec))
    lane = tmp_path / 'code-poisson';lane.mkdir()
    ep = dict(ret=10, mean_pods=3,slo_viol_rate=.2,p95_latency=4,pods_changes=2)
    x = dict(seed=15010, eval_splits=['val'], total_ticks=4992, checkpoint_results={'4992': {'val': {'episodes': [ep]*20}, 'target_tick':4992}})
    (lane / 'result.json').write_text(json.dumps(x))
    db = sqlite3.connect(':memory:')
    with db:
        db.execute('CREATE TABLE runs (request_id,run_id,name,cmd,cwd,status,exit_code,created)')
        db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)', (c.PARENT,'run1','wave03/'+name,json.dumps(cmd),str(lane),'done',0,'1'))
    return x, lane, db


def test_manifest_launcher_names_and_pending_are_not_double_counted(tmp_path):
    _, _, db = fixture(tmp_path)
    s=c.snapshot(tmp_path, _connect=lambda *args, **kwargs: db)
    assert not s['issues']
    assert s['stages'][2] == dict(stage='screen',planned=2,valid=1,statuses={'done':1,'pending':1})
    r=next(x for x in c.grouped(s,'screen') if x['Μοντέλο'].startswith('DRe') and x['Κλάδος']=='code-poisson')
    assert r['Val return']==10 and r['Training seeds']=='15010'
    assert r['Έγκυρα / προβλεπόμενα']=='1 / 2'
    assert any(x['Μοντέλο']=='Dinos+Transfer V.2' and x['Val return'] is None for x in c.grouped(s,'screen'))


@pytest.mark.parametrize('bad', ['test', 'nan', 'partial', 'invalid'])
def test_rejects_invalid_or_non_val_outputs(tmp_path,bad):
    x,lane,db=fixture(tmp_path)
    if bad=='test':x['eval_splits']=['test12']
    if bad=='nan':x['checkpoint_results']['4992']['val']['episodes'][0]['ret']=float('nan')
    if bad=='partial':x['checkpoint_results']['4992']['val']['episodes'].pop()
    (lane/'result.json').write_text('{' if bad=='invalid' else json.dumps(x))
    s=c.snapshot(tmp_path, _connect=lambda *args, **kwargs: db)
    assert s['stages'][2]['valid']==0 and s['issues']
    assert all(x['Val return'] is None for x in c.grouped(s,'screen'))


def test_latest_attempt_only_and_failed_output_not_used(tmp_path):
    _, _, db = fixture(tmp_path)
    with db:
        db.execute("INSERT INTO runs SELECT request_id,'run2',name,cmd,cwd,'failed',1,'2' FROM runs")
    s=c.snapshot(tmp_path, _connect=lambda *args, **kwargs: db)
    assert len(s['rows'])==2 and s['stages'][2]['valid']==0


def test_stage_lane_candidate_separation(tmp_path):
    _, _, db = fixture(tmp_path)
    s=c.snapshot(tmp_path, _connect=lambda *args, **kwargs: db)
    assert all(x['Val return'] is None for x in c.grouped(s,'calib'))
    assert all(x['Val return'] is None for x in c.grouped(s,'screen') if x['Κλάδος']=='code-poisson-astra')


def test_missing_db_and_manifest_show_unknown(tmp_path):
    s=c.snapshot(tmp_path)
    assert s['issues'] and not s['rows']
    assert all(x['Val return'] is None for x in c.grouped(s,'screen'))
