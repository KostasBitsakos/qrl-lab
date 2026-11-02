"""Offline scheduler simulations. Fake launcher, fake accounting, no real training/evaluation."""
import copy
import inspect
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/spiky_stage1'))
import build
import driver as D
from labdb import LabError,canonical_hash


class Fake:
    def __init__(self,spec):
        self.spec=spec;self.r=[];self.stopped=False;self.ok=True;self.extra=0;self.bad_art=set();self.launch_error=False
    def approval(self):
        if not self.ok:raise LabError('not approved')
    def rows(self):return self.r
    def output_exists(self,t):return False
    def used(self):
        return self.extra+sum(next(t['reserve_cpu_h'] for t in self.spec['tasks'] if r['name'].split('/')[0]==t['name']) for r in self.r)
    def launch(self,t):
        if self.launch_error:raise LabError('ambiguous launch')
        self.r.append(dict(name=t['name']+'/'+t['name'],spec_hash=canonical_hash(t['child']),
                           status='running',exit_code=None,run_id=t['name']))
    def stop_all(self):
        self.stopped=True
        for r in self.r:
            if r['status'] in D.ACTIVE:r.update(status='stopped',exit_code=1)
    def verify_artifact(self,t):
        if t['name'] in self.bad_art:raise LabError('corrupt artifact')
    def finish(self,status='done'):
        for r in self.r:
            if r['status'] in D.ACTIVE:r.update(status=status,exit_code=0 if status=='done' else 1)


@pytest.fixture
def setup(tmp_path):
    spec=build.build();b=Fake(spec);return spec,b,D.Engine(spec,b,tmp_path)


def test_manifest_complete_budget_and_exposure():
    s=build.build();assert len(s['tasks'])==67
    from labdb import validate_spec
    assert validate_spec(s) is True
    assert 46.69<s['reserved_cpu_h']<=46.7
    for a in build.RATES:
        ts=[t for t in s['tasks'] if t['stage']=='A' and t['arm']==a]
        assert [t['seed'] for t in ts]==list(range(17000,17006))
    for t in s['tasks'][1:]:
        c=t['child']['entries'][0]['cmd'];v=lambda k:c[c.index(k)+1]
        assert v('--checkpoints')=='19968'
        assert int(v('--total-ticks'))==(29952 if '--pretrain-ticks' in c else 19968)


def test_complete_simulation_stage_barriers(setup):
    s,b,e=setup
    assert e.step()=='RUNNING' and len(b.r)==1
    assert e.step()=='RUNNING' and len(b.r)==1 # P0 barrier
    for _ in range(30):
        b.finish();state=e.step()
        assert sum(r['status'] in D.ACTIVE for r in b.r)<=8
        if state!='RUNNING':break
    assert state=='DONE' and len(b.r)==67 and len(e.state['checked'])==67


def test_three_failed_runs_stop_all(setup):
    s,b,e=setup;e.step();b.finish();e.step()
    for r in b.r[1:4]:r.update(status='failed',exit_code=1)
    assert e.step()=='STOPPED' and b.stopped and len(e.state['errors'])==3


def test_one_failure_is_retained_not_retried(setup):
    s,b,e=setup;e.step();b.finish();e.step();b.r[1].update(status='failed',exit_code=1)
    for _ in range(30):
        b.finish();state=e.step()
        if state!='RUNNING':break
    assert state=='INCOMPLETE' and len(b.r)==67 and len(e.state['errors'])==1


@pytest.mark.parametrize('scenario',['p0failure','timeout','budget','approval','ambiguous','stopfile','corrupt','duplicate'])
def test_fail_closed(setup,scenario):
    s,b,e=setup
    if scenario=='approval':b.ok=False
    if scenario=='budget':b.extra=1
    if scenario=='ambiguous':b.launch_error=True
    if scenario=='stopfile':(e.out/'STOP').write_text('stop')
    e.step()
    if scenario=='p0failure':b.finish('failed')
    if scenario=='timeout':b.finish('stopped')
    if scenario=='corrupt':b.bad_art.add(s['tasks'][0]['name']);b.finish()
    if scenario=='duplicate':b.r.append(dict(b.r[0]))
    assert e.step()=='STOPPED' and b.stopped
    before=len(b.r);e.step();assert len(b.r)==before


def test_intent_without_row_not_resubmitted(setup):
    s,b,e=setup;e.state['intents']=[s['tasks'][0]['name']];e.save()
    e=D.Engine(s,b,e.out)
    assert e.step()=='STOPPED' and not b.r


def test_resume_never_duplicates(setup):
    s,b,e=setup;e.step();b.finish();e.step()
    e2=D.Engine(s,b,e.out);e2.step()
    assert len(b.r)==9


def test_cli_parsing_and_validators_no_training(tmp_path,monkeypatch):
    # Real parser and production validators, intercepted at training boundary.
    sys.path.insert(0,str(ROOT/'code-poisson-spiky'))
    from tuning.legacy import c5_protocol as C5,run_legacy as RL
    from tuning import pms_adapter as PA,rppo as RP, pms_reference as REF
    original=C5.run_c5
    class Intercept(Exception):pass
    def intercept(*args,**kw):
        a=inspect.signature(original).bind(*args,**kw);a.apply_defaults();v=a.arguments
        otr,h=C5.validate_c9b(v['agent'],v['env_family'],v['source_variant'],v['pretrain_env_family'],v['pretrain_variant'],v['finetune_eps'],v['agent_variant'],v['derp_history'])
        C5.validate(v['agent'],'legacy' if otr else v['source_variant'],v['pretrain_ticks'],v['finetune_ticks'],v['total_ticks'],v['checkpoints'])
        C5.validate_c6(v['agent'],v['agent_variant'],v['target_sync'],v['diag'])
        C5.validate_c19(v['ddqn'],v['agent'],v['agent_variant'],v['diag'],v['source_variant'])
        C5.validate_history_ablation(v['history_ablation'],v['agent'],v['agent_variant'])
        PA.check_seeds(v['orig_variant'],v['seed'],['val'])
        raise Intercept
    monkeypatch.setattr(C5,'run_c5',intercept)
    def rp(*args,**kwargs):
        assert args[1]==19968 and args[2]==[19968] and args[3]=='pms:poisson_ms_spiky'
        PA.check_seeds(args[3],args[0],['val']);raise Intercept
    monkeypatch.setattr(RP,'run',rp)
    for t in build.build()['tasks'][1:]:
        c=t['child']['entries'][0]['cmd'];which=RP.main if t['arm']=='rppo' else RL.main
        with pytest.raises(Intercept):which(c[3:])
    # Reference parser resolves all grids, intercepted before first evaluate.
    def ref(*a,**k):raise Intercept
    monkeypatch.setattr(REF,'evaluate',ref)
    c=build.build()['tasks'][0]['child']['entries'][0]['cmd']
    with pytest.raises(Intercept):REF.main(c[3:])


def test_artifact_rejects_wrong_trace_and_checkpoint(tmp_path):
    t=build.build()['tasks'][1];p=tmp_path/t['child']['cwd']/t['out'];p.parent.mkdir(parents=True)
    x=dict(seed=t['seed'],total_ticks=19968,eval_splits=['val'],eval_seeds={'val':list(range(16000,16020))},
           target_variant='pms:poisson_ms_spiky',agent='lstm_scratch',agent_variant='fixed',pretrain_ticks=0,target_ticks=19968,
           checkpoint_results={'19968':{'val':{'episodes':[dict(ret=1.,slo_viol_rate=.1)]*20}}})
    x['saved_weights']=dict(selected_checkpoint=19968,selected_file=p.with_suffix('.selected.pt').name,checkpoints={'19968':p.with_suffix('.ck19968.pt').name})
    p.write_text(json.dumps(x));p.with_suffix('.ck19968.pt').write_bytes(b'fixture')
    import torch
    torch.save({'weight':torch.ones(2)},p.with_suffix('.ck19968.pt'))
    torch.save({'weight':torch.ones(2)},p.with_suffix('.selected.pt'))
    p.with_suffix('.ck19968.json').write_text(json.dumps(dict(seed=t['seed'],target_variant=x['target_variant'],checkpoint=x['checkpoint_results']['19968'])))
    D.artifact(t,tmp_path)
    x['eval_seeds']['val'][0]=16500;p.write_text(json.dumps(x))
    with pytest.raises(LabError,match='traces'):D.artifact(t,tmp_path)
    x['eval_seeds']['val'][0]=16000;x['checkpoint_results']={'9984':{}};p.write_text(json.dumps(x))
    with pytest.raises(LabError,match='checkpoint'):D.artifact(t,tmp_path)


def test_elapsed_overrun_stops_before_launcher_timeout(setup):
    from datetime import datetime,timezone,timedelta
    s,b,e=setup;e.step()
    b.r[0]['started']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    assert e.step()=='STOPPED' and 'overrun' in e.state['reason'] and b.stopped


def test_start_without_approval_never_spawns(tmp_path,monkeypatch):
    s=build.build();(tmp_path/'parent-spec.json').write_text(json.dumps(s))
    monkeypatch.setattr(D,'OUT',tmp_path)
    monkeypatch.setattr(D,'validate',lambda s:s)
    monkeypatch.setattr(D.Backend,'approval',lambda self: (_ for _ in ()).throw(LabError('not approved')))
    def spawn(*a,**k):pytest.fail('spawn before approval')
    monkeypatch.setattr(D.subprocess,'Popen',spawn)
    with pytest.raises(LabError,match='not approved'):D.start('R-fixture')
    assert not (tmp_path/'receipt.json').exists()


def test_runtime_hash_tamper_rejected():
    s=build.build();s['runtime_sha256']['tools/spiky_stage1/driver.py']='0'*64
    with pytest.raises(LabError,match='runtime source'):D.validate(s,protected=False)


def test_stopping_waits_until_all_payloads_terminal(setup):
    s,b,e=setup;e.step()
    b.stop_all=lambda: ['simulated stop API outage']
    assert e.stop('test')=='STOPPING'
    assert e.step()=='STOPPING' and len(b.r)==1
    b.finish('stopped')
    assert e.step()=='STOPPED' and len(b.r)==1


def test_stop_race_does_not_skip_other_runs(monkeypatch):
    b=D.Backend('R-test',{})
    rows=[dict(run_id='r1',status='running'),dict(run_id='r2',status='running')]
    monkeypatch.setattr(b,'rows',lambda:rows)
    called=[]
    class DB:
        def request_stop(self,r,actor):
            called.append(r)
            if r=='r1':raise LabError('terminal race')
        def close(self):pass
    monkeypatch.setattr(D,'LabDB',DB)
    assert len(b.stop_all())==1 and called==['r1','r2']


def test_watchdog_spawn_failure_aborts_driver(tmp_path,monkeypatch):
    s=build.build();(tmp_path/'parent-spec.json').write_text(json.dumps(s))
    monkeypatch.setattr(D,'OUT',tmp_path);monkeypatch.setattr(D,'validate',lambda s:s)
    monkeypatch.setattr(D.Backend,'approval',lambda self:None);monkeypatch.setattr(D.Backend,'rows',lambda self:[])
    class Child:
        pid=1234
        dead=False
        def poll(self):return 0 if self.dead else None
        def terminate(self):self.dead=True
        def wait(self,timeout):return 0
    child=Child();calls=[]
    def spawn(*args,**kwargs):
        calls.append(args)
        if len(calls)==2:raise OSError('watch spawn fails')
        return child
    monkeypatch.setattr(D.subprocess,'Popen',spawn)
    with pytest.raises(OSError):D.start('R-test')
    assert child.dead and D.load(tmp_path/'receipt.json')['phase']=='ABORT'
    assert not (tmp_path/'state.json').exists()


def test_live_startup_requires_bound_pid_and_healthy_watchdog(tmp_path,monkeypatch):
    import os
    s=build.build();(tmp_path/'parent-spec.json').write_text(json.dumps(s));monkeypatch.setattr(D,'OUT',tmp_path)
    r=dict(request='R-test',session='abc',spec_hash=canonical_hash(s),pids={'drive':os.getpid(),'watch':os.getpid()},phase='GO')
    D.atomic(tmp_path/'receipt.json',r)
    D.atomic(tmp_path/'watch-ready.json',dict(session='abc',pid=os.getpid(),ts=D.stamp()))
    D.live_startup('R-test','abc')
    r['phase']='PREPARED';D.atomic(tmp_path/'receipt.json',r)
    with pytest.raises(LabError,match='handshake'):D.live_startup('R-test','abc')
    r['phase']='GO';r['pids']['drive']=os.getpid()+999;D.atomic(tmp_path/'receipt.json',r)
    with pytest.raises(LabError,match='authorized'):D.live_startup('R-test','abc')


def test_incomplete_artifact_manifest_is_failure(tmp_path):
    t=build.build()['tasks'][1];p=tmp_path/t['child']['cwd']/t['out'];p.parent.mkdir(parents=True)
    x=dict(seed=t['seed'],total_ticks=19968,eval_splits=['val'],eval_seeds={'val':list(range(16000,16020))},
           target_variant='pms:poisson_ms_spiky',agent='lstm_scratch',agent_variant='fixed',pretrain_ticks=0,target_ticks=19968,
           checkpoint_results={'19968':{'val':{'episodes':[dict(ret=1.,slo_viol_rate=.1)]*20}}})
    p.write_text(json.dumps(x));p.with_suffix('.ck19968.pt').write_bytes(b'fixture')
    with pytest.raises(FileNotFoundError):D.artifact(t,tmp_path)


def test_watchdog_retries_stop_even_when_notification_fails(tmp_path,monkeypatch):
    s=build.build();(tmp_path/'parent-spec.json').write_text(json.dumps(s));monkeypatch.setattr(D,'OUT',tmp_path)
    D.atomic(tmp_path/'receipt.json',dict(pids={'drive':12345}))
    monkeypatch.setattr(D,'ready_role',lambda *a:None)
    monkeypatch.setattr(D.os,'kill',lambda *a:(_ for _ in ()).throw(ProcessLookupError('dead driver')))
    calls=[]
    class B:
        def __init__(self,*a):pass
        def stop_all(self):
            calls.append('stop')
            if len(calls)<3:raise LabError('temporary stop failure')
        def rows(self):return [dict(status='running')] if len(calls)<3 else []
    monkeypatch.setattr(D,'Backend',B)
    monkeypatch.setattr(D,'post',lambda *a:(_ for _ in ()).throw(LabError('notification fails')))
    sleeps=[]
    def sleep(s):
        sleeps.append(s)
        assert len(sleeps)<5,'watchdog failed to finish after payload terminal'
    monkeypatch.setattr(D.time,'sleep',sleep)
    D.watch('R-test','session')
    assert calls==['stop']*3 and len(sleeps)==2


def test_weight_artifacts_compare_tensors_not_zip_bytes(tmp_path):
    import torch
    a,b=tmp_path/'endpoint.pt',tmp_path/'selected.pt'
    torch.save({'weight':torch.ones(2)},a);torch.save({'weight':torch.ones(2)},b)
    D.verify_weights(a,b)
    torch.save({'weight':torch.zeros(2)},b)
    with pytest.raises(LabError,match='differ'):D.verify_weights(a,b)


def test_real_cycle3_artifact_schema_compatibility(tmp_path):
    """Existing artifacts are schema fixtures only; rewrite provenance in temp, NEVER publish them as new results."""
    import shutil
    sys.path.insert(0,str(ROOT/'code-poisson-spiky'))
    from tuning.legacy import c5_protocol as C5
    olddir=ROOT/'code-poisson/tuning/results/cycle3-opus'
    for t in build.build()['tasks'][1:]:
        if t['seed']!=17000 or t['stage']!='A' or t['arm'] in ('mlp_a1h','transfer_mlp_a1h'):continue
        old=next(olddir.glob(f"c3-opus-F-{t['arm']}-*-s15100.json"))
        x=json.loads(old.read_text());x['seed']=t['seed'];x['eval_seeds']={'val':list(range(16000,16020))}
        key='variant' if t['arm']=='rppo' else 'target_variant';x[key]='pms:poisson_ms_spiky'
        out=tmp_path/t['child']['cwd']/t['out'];out.parent.mkdir(parents=True,exist_ok=True)
        if t['arm']=='rppo':
            shutil.copyfile(str(old)+'.ck19968.pt',str(out)+'.ck19968.pt')
        else:
            # Derive names from the ACTUAL frozen producer, independently of driver helpers.
            for tag in ('ck19968','selected'):
                shutil.copyfile(C5.pt_path(str(old),tag),C5.pt_path(str(out),tag))
            ck=json.loads(Path(C5.ck_path(str(old),19968)).read_text())
            ck.update(seed=t['seed'],target_variant=x['target_variant'])
            Path(C5.ck_path(str(out),19968)).write_text(json.dumps(ck))
            x['saved_weights']['selected_file']=Path(C5.pt_path(str(out),'selected')).name
            x['saved_weights']['checkpoints']={'19968':Path(C5.pt_path(str(out),'ck19968')).name}
        out.write_text(json.dumps(x))
        D.artifact(t,tmp_path)
