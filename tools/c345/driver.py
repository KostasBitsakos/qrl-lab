"""C345 (R-20261106-002) poisson_ms stage scheduler: generalised copy of tools/spiky_stage1/driver.py (J299).
Workload, val traces and stages come from the frozen spec policy; per-task target ticks from the task.
Stage1 data-only scheduler. Commands come exclusively from the frozen sandbox task list.
Usage: driver.py validate | start --request R-id | drive --request R-id | watch --request R-id
No experiment at import, validate, or build time. All payloads use launch_run.py sandbox-start.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import sandbox_guard as G
from labdb import LabDB, LabError, canonical_hash
OUT = Path(os.environ.get('QRL_C345_OUT') or ROOT / '.lab/c345run').resolve()
SPEC = {}  # policy of the validated spec (set by validate)
ACTIVE = ('starting', 'running')
STAGES = ('P0', 'W', 'F')


def pol(spec, key, default):
    return spec.get('policy', {}).get(key, default)


def load(path):
    return G.loads_strict(Path(path).read_text())


def stamp():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def validate(spec, protected=True):
    tasks = spec['tasks']; sb = spec['sandbox']
    if spec['kind'] != 'sandbox' or spec['scope'] != 'sim' or sb['cpu_hours_budget'] > 160 \
            or pol(spec, 'variant', None) != 'pms:poisson_ms':
        raise LabError('invalid Stage1 sandbox')
    if len(tasks) != pol(spec, 'expected_tasks', 67) or len({t['name'] for t in tasks}) != len(tasks):
        raise LabError(f"Stage requires exactly {pol(spec, 'expected_tasks', 67)} tasks with unique names")
    if {t['stage'] for t in tasks} - set(pol(spec, 'stages', STAGES)):
        raise LabError('task in a stage outside policy.stages')
    if sb['allowed_children'] != [canonical_hash(t['child']) for t in tasks]:
        raise LabError('child whitelist mismatch')
    if sum(t['reserve_cpu_h'] for t in tasks) > sb['cpu_hours_budget']:
        raise LabError('mandatory reservations exceed budget')
    for t in tasks:
        _, plan = G.check_child(t['child'], spec)
        if len(plan) != 1 or abs(plan[0]['reserve_cpu_h']-t['reserve_cpu_h']) > 1e-9:
            raise LabError('reservation differs from launcher')
    for p, digest in spec['runtime_sha256'].items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != digest:
            raise LabError(f'runtime source changed: {p}')
    SPEC.clear(); SPEC.update(spec.get('policy', {}))
    if protected:
        G.verify_sandbox_protected(G.select_worktree(sb, tasks[0]['child']), ROOT)
    return spec


def artifact(t, root=ROOT):
    p = root / t['child']['cwd'] / t['out']
    x = load(p)
    if t['stage'] == 'P0':
        if x.get('variant') != SPEC['variant'] or x.get('split') != 'val' or x.get('seeds') != SPEC['val_seeds']:
            raise LabError('reference provenance mismatch')
        grids = {'hpa_orig': ['50'], 'fixed': [str(i) for i in range(1,21)],
                 'hpa_demand': ['0.5','0.6','0.7','0.8','0.9'], 'oracle': ['1.0','1.1','1.2','1.3','1.5']}
        if set(x['grids']) != set(grids):
            raise LabError('reference controllers missing')
        for kind, values in grids.items():
            if set(x['grids'][kind]) != set(values):
                raise LabError('reference grid incomplete')
            for v in values:
                eps = x['grids'][kind][v]['episodes']
                check_episodes(eps)
        return
    c=t['child']['entries'][0]['cmd']
    val=lambda k: c[c.index(k)+1]
    if x.get('seed') != t['seed'] or x.get('total_ticks') != int(val('--total-ticks')) or x.get('eval_splits') != ['val']:
        raise LabError('learning provenance mismatch')
    if x.get('eval_seeds') != {'val': SPEC['val_seeds']}:
        raise LabError('wrong validation traces')
    if (x.get('variant') if t['arm']=='rppo' else x.get('target_variant')) != SPEC['variant']:
        raise LabError('wrong workload')
    if x.get('history_ablation', 'off') != t['mode']:
        raise LabError('wrong ablation')
    if t['arm'] != 'rppo':
        if x.get('agent') != val('--agent') or x.get('agent_variant', 'legacy') != (val('--agent-variant') if '--agent-variant' in c else 'legacy'):
            raise LabError('wrong learning agent')
        opt = lambda k, d: val(k) if k in c else d  # noqa: E731
        if val('--agent') == 'derp':    # C345: plain DERP vs derp_ddqn vs history must match the frozen command
            dd = opt('--derp-double', 'off') == 'on'
            if bool(x.get('double_dqn_target', False)) != dd or x.get('derp_history') != int(opt('--derp-history', 1)):
                raise LabError('wrong DERP target/history')
            if dd and (x.get('arm') != 'derp_ddqn' or x.get('target_sync_replays') != int(opt('--derp-target-sync', 1))):
                raise LabError('wrong derp_ddqn sync')
        if x.get('pretrain_variant') != opt('--pretrain-variant', None) or \
                x.get('finetune_eps', 'restart') != opt('--finetune-eps', 'restart'):
            raise LabError('wrong transfer source')
        oo = x.get('optim_options') or {}
        if ('--lr' in c and oo.get('lr') != float(val('--lr'))) or \
                ('--grad-clip' in c and oo.get('grad_clip') != float(val('--grad-clip'))) or \
                x.get('eps_schedule') != opt('--eps-schedule', x.get('eps_schedule')) or \
                ('--target-sync' in c and x.get('target_sync_replays') != int(val('--target-sync'))):
            raise LabError('wrong optimiser/exploration config')
        if x.get('pretrain_ticks') != int(opt('--pretrain-ticks', 0)) or x.get('target_ticks') != t['target_ticks']:
            raise LabError('wrong training exposure')
    K = str(t['target_ticks'])
    if list(x['checkpoint_results']) != [K]:
        raise LabError('wrong checkpoint set')
    check_episodes(x['checkpoint_results'][K]['val']['episodes'])
    if val('--save-weights') == 'on':
        # Legacy pt_path strips .json; RPPO appends to the entire output name.
        wp = Path(str(p)+f'.ck{K}.pt') if t['arm']=='rppo' else p.with_suffix(f'.ck{K}.pt')
        if not wp.is_file() or not wp.stat().st_size:
            raise LabError('missing endpoint weights')
        if t['arm'] != 'rppo':
            ck = load(p.with_suffix(f'.ck{K}.json'))
            if ck.get('seed') != t['seed'] or ck.get('target_variant') != x['target_variant'] or ck.get('checkpoint') != x['checkpoint_results'][K]:
                raise LabError('checkpoint JSON provenance mismatch')
            selected = x.get('saved_weights', {})
            sp = p.with_suffix('.selected.pt')
            if selected.get('selected_checkpoint') != int(K) or selected.get('selected_file') != sp.name or selected.get('checkpoints') != {K:wp.name}:
                raise LabError('saved-weights manifest mismatch')
            verify_weights(wp, sp)
        else:
            read_weights(wp)


def verify_weights(endpoint, selected):
    if not selected.is_file() or not selected.stat().st_size:
        raise LabError('missing selected weights')
    import torch
    a = read_weights(endpoint)
    b = read_weights(selected)
    if set(a) != set(b) or not all(torch.equal(a[k], b[k]) for k in a):
        raise LabError('selected weights differ from sole endpoint')


def read_weights(path):
    import torch
    weights = torch.load(path, map_location='cpu', weights_only=True)
    if not isinstance(weights, dict) or not weights or not all(isinstance(v, torch.Tensor) and torch.isfinite(v).all() for v in weights.values()):
        raise LabError('invalid/nonfinite state dictionary')
    return weights


def check_episodes(eps):
    if len(eps) != 20 or not all(isinstance(e,dict) and all(isinstance(e.get(k),(int,float)) and
        math.isfinite(e[k]) for k in ('ret','slo_viol_rate')) for e in eps):
        raise LabError('incomplete or nonfinite validation metrics')


class Backend:
    def __init__(self, rid, spec, session=None):
        self.rid, self.spec, self.session = rid, spec, session
    @contextmanager
    def connection(self):
        c=sqlite3.connect(f'file:{ROOT}/.lab/lab.db?mode=ro',uri=True,timeout=30)
        c.row_factory=sqlite3.Row
        try:
            yield c
        finally:
            c.close()
    def approval(self):
        with self.connection() as c:
            r=c.execute('SELECT * FROM requests WHERE id=?',(self.rid,)).fetchone()
        if not r or r['kind'] != 'approval' or r['scope'] != 'sim' or r['state'] != 'approved' or r['spec_hash'] != canonical_hash(self.spec):
            raise LabError('sandbox not approved or frozen hash mismatch')
        if canonical_hash(load(r['spec_path'])) != r['spec_hash']:
            raise LabError('approved spec file mismatch')
        validate(self.spec)
        if self.session is not None:
            live_startup(self.rid, self.session)
    def rows(self):
        with self.connection() as c:
            return [dict(r) for r in c.execute('SELECT * FROM runs WHERE request_id=?',(self.rid,))]
    def used(self):
        with self.connection() as c:
            return G.used_cpu_hours(SimpleNamespace(conn=c), self.rid, strict=True)
    def launch(self,t):
        path=OUT/'children'/f"{t['name']}.json"
        path.parent.mkdir(exist_ok=True)
        atomic(path,t['child'])
        (ROOT/t['child']['cwd']/t['out']).parent.mkdir(parents=True,exist_ok=True)
        p=subprocess.run([sys.executable,str(ROOT/'tools/launch_run.py'),'sandbox-start','--request',self.rid,'--spec',str(path)],
                         cwd=ROOT,capture_output=True,text=True,timeout=120)
        if p.returncode:
            raise LabError(f'launcher failed (no retry): {p.stdout[-500:]} {p.stderr[-500:]}')
    def stop_all(self):
        db=LabDB()
        errors = []
        try:
            for r in self.rows():
                if r['status'] in ACTIVE:
                    try:
                        db.request_stop(r['run_id'],actor='c345-driver')
                    except Exception as ex:
                        # A terminal race on one row must never skip any other active row.
                        errors.append(f"{r['run_id']}: {ex}")
        finally:
            db.close()
        return errors
    def output_exists(self,t):
        return (ROOT/t['child']['cwd']/t['out']).exists()
    def verify_artifact(self,t):
        artifact(t)


class Engine:
    """One polling step is testable with an in-memory backend; durable intent precedes every launcher call."""
    def __init__(self,spec,backend,out=OUT):
        self.spec,self.b,self.out=spec,backend,out
        self.path=out/'state.json'
        self.state=load(self.path) if self.path.exists() else dict(state='READY',intents=[],checked={},errors={})
    def save(self):
        self.state.update(ts=stamp(),pid=os.getpid())
        atomic(self.path,self.state)
    def stop(self,reason):
        self.state.update(state='STOPPING',reason=reason)
        self.save()
        try:
            self.state['stop_errors'] = self.b.stop_all() or []
            if not any(r['status'] in ACTIVE for r in self.b.rows()):
                self.state['state'] = 'STOPPED'
        except Exception as ex:
            self.state['stop_errors'] = [str(ex)]
        self.save()
        return self.state['state']
    def step(self):
        if self.state['state'] in ('DONE','INCOMPLETE','STOPPED'):
            return self.state['state']
        if self.state['state']=='STOPPING':
            return self.stop(self.state['reason'])
        try:
            return self._step()
        except Exception as e:
            return self.stop(f'{type(e).__name__}: {e}')
    def _step(self):
        self.b.approval()
        if (self.out/'STOP').exists():
            return self.stop('STOP file')
        tasks={t['name']:t for t in self.spec['tasks']}
        isolate = pol(self.spec, 'failure_mode', 'abort') == 'isolate'
        gates = pol(self.spec, 'gate_stages', ['P0']); maxfail = pol(self.spec, 'max_failures', 3)
        stages = pol(self.spec, 'stages', STAGES)
        rows=self.b.rows(); by={}
        for r in rows:
            n=r['name'].split('/')[0]
            if n not in tasks or n in by or r['name'] != n+'/'+n or r['spec_hash'] != canonical_hash(tasks[n]['child']):
                return self.stop('unknown/duplicate/mismatched launcher row')
            by[n]=r
        intents=self.state['intents']
        if any(n not in by for n in intents) or any(n not in intents for n in by):
            return self.stop('intent/DB mismatch; reconcile manually, never retry')
        used=self.b.used()
        if not math.isfinite(used) or used < 0 or used > self.spec['sandbox']['cpu_hours_budget']:
            return self.stop('budget accounting invalid/over cap')
        for n,r in by.items():
            if r.get('started'):
                end = datetime.fromisoformat(r['ended']) if r.get('ended') else datetime.now(timezone.utc)
                elapsed = (end-datetime.fromisoformat(r['started'])).total_seconds()/3600
                # isolate mode: the launcher enforces the per-run cap itself (that run is then a recorded failure);
                # the driver only aborts when the launcher demonstrably failed to enforce it.
                slack = 5/3600 if not isolate else 0.15*tasks[n]['reserve_cpu_h'] + 120/3600
                if elapsed > tasks[n]['reserve_cpu_h'] + slack:
                    return self.stop('reservation overrun: '+n)
            if n in self.state['checked'] or r['status'] in ACTIVE:
                continue
            if r['status']=='stopped' and not isolate:
                return self.stop('payload stopped/overran reservation: '+n)
            try:
                if r['status']!='done' or r['exit_code']!=0:
                    raise LabError(f"run {r['status']}, exit {r['exit_code']}")
                self.b.verify_artifact(tasks[n])
                self.state['checked'][n]='ok'
            except Exception as e:
                self.state['checked'][n]='failed'; self.state['errors'][n]=str(e)
                if tasks[n]['stage'] in gates or len(self.state['errors'])>=maxfail:
                    return self.stop(f'gate stage failed or >={maxfail} failures: '+n)
        active=sum(r['status'] in ACTIVE for r in rows)
        for stage in stages:
            todo=[t for t in tasks.values() if t['stage']==stage]
            if all(t['name'] in self.state['checked'] for t in todo):
                continue
            # No later stage until every earlier stage is terminal and checked.
            for t in todo:
                if active>=self.spec['sandbox']['max_parallel']:
                    break
                if t['name'] in intents:
                    continue
                remaining=sum(v['reserve_cpu_h'] for v in tasks.values() if v['name'] not in intents)
                if used+remaining > self.spec['sandbox']['cpu_hours_budget']+1e-8:
                    return self.stop('used + remaining mandatory reservations exceeds budget')
                if self.b.output_exists(t):
                    return self.stop('output collision before launch: '+t['name'])
                intents.append(t['name']); self.save()
                self.b.launch(t)
                # Re-read actual DB reservation before another submission.
                by_now={r['name'].split('/')[0]:r for r in self.b.rows()}
                if t['name'] not in by_now:
                    return self.stop('launcher returned without DB row')
                used=self.b.used(); active+=1
                self.save()
            self.state.update(state='RUNNING',stage=stage,used_cpu_h=used)
            self.save()
            return 'RUNNING'
        self.state.update(state='INCOMPLETE' if self.state['errors'] else 'DONE', used_cpu_h=used)
        self.save()
        return self.state['state']


def post(body, spec=None):
    spec = spec or {}
    subprocess.run([sys.executable,str(ROOT/'tools/labq.py'),'post','--reply-to',pol(spec,'reply_to','M-20261101-035'),
                    '--author','coordinator','--kind','status','--body',body+'\n'+pol(spec,'signature','— Πάρις (Codex)')],cwd=ROOT,check=True)


def receipt_for(rid, session, role):
    r=load(OUT/'receipt.json')
    if not session or r['request']!=rid or r['session']!=session or r['spec_hash']!=canonical_hash(load(OUT/'parent-spec.json')):
        raise LabError('startup receipt binding mismatch')
    if r['pids'].get(role)!=os.getpid() or r['phase'] not in ('PREPARED','GO'):
        raise LabError('process is not an authorized startup child')
    return r


def ready_role(rid,session,role):
    deadline=time.monotonic()+20
    while True:
        try:
            r=receipt_for(rid,session,role)
            atomic(OUT/f'{role}-ready.json',dict(session=session,pid=os.getpid(),ts=stamp()))
            if r['phase']=='GO':
                return
        except LabError:
            # Parent may still be recording child pids; ABORT always fails immediately.
            r=load(OUT/'receipt.json')
            if r.get('phase')=='ABORT':raise
        if time.monotonic()>deadline:raise LabError('startup handshake timeout')
        time.sleep(.1)


def live_startup(rid,session):
    r=receipt_for(rid,session,'drive')
    w=load(OUT/'watch-ready.json')
    if r['phase']!='GO' or w['session']!=session or w['pid']!=r['pids']['watch']:
        raise LabError('watchdog handshake mismatch')
    os.kill(w['pid'],0)
    if (datetime.now(timezone.utc)-datetime.fromisoformat(w['ts'])).total_seconds()>90:
        raise LabError('watchdog heartbeat expired')


def drive(rid,session):
    ready_role(rid,session,'drive')
    spec=load(OUT/'parent-spec.json'); b=Backend(rid,spec,session)
    with (OUT/'driver.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        e=Engine(spec,b)
        while e.step() in ('RUNNING','STOPPING'):
            time.sleep(30)
        post(f"Κώστα, το {pol(spec,'label','Στάδιο 1')}: {e.state['state']}. {e.state.get('reason','')} "
             f"Αποτυχίες: {len(e.state['errors'])}. Στοιχεία: {OUT.relative_to(ROOT)}/state.json", spec)


def watch(rid,session):
    """Confirm whole-parent stop, including terminal races; never restart any process or payload."""
    ready_role(rid,session,'watch')
    wspec=load(OUT/'parent-spec.json'); b=Backend(rid,wspec)
    alarm=False
    first=time.monotonic()
    while True:
        try:
            atomic(OUT/'watch-ready.json',dict(session=session,pid=os.getpid(),ts=stamp()))
            r=load(OUT/'receipt.json')
            os.kill(r['pids']['drive'],0)
            if not (OUT/'state.json').exists() and time.monotonic()-first<60:
                time.sleep(1);continue
            s=load(OUT/'state.json')
            active=any(x['status'] in ACTIVE for x in b.rows())
            if s['state'] in ('DONE','INCOMPLETE','STOPPED') and not active:
                return
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(s['ts'])).total_seconds()
            if age>300:raise LabError('driver heartbeat older than 5 minutes')
            if s['state']=='STOPPED' and active:raise LabError('terminal state with active runs')
        except Exception as ex:
            try:
                (OUT/'STOP').write_text('watchdog: '+str(ex))
            except OSError as write_error:
                print(f'Cannot persist STOP: {write_error}',file=sys.stderr,flush=True)
            try:
                b.stop_all()
                no_active=not any(x['status'] in ACTIVE for x in b.rows())
            except Exception:
                no_active=False
            if not alarm:
                alarm=True
                try:
                    post('Κώστα, συναγερμός '+pol(wspec,'label','Σταδίου 1')+': '+str(ex)+'. Ζητήθηκε διακοπή· χωρίς retry.', wspec)
                except Exception as notify_error:
                    print(f'Watchdog notification failed: {notify_error}; continuing stop confirmation',file=sys.stderr,flush=True)
            if no_active:return
        time.sleep(30)


def start(rid):
    spec=validate(load(OUT/'parent-spec.json')); b=Backend(rid,spec); b.approval()
    with (OUT/'start.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if any((OUT/p).exists() for p in ('receipt.json','state.json','STOP')) or b.rows():
            raise LabError('one-shot start blocked: prior state/receipt/STOP/runs exist')
        receipt=dict(request=rid,spec_hash=canonical_hash(spec),started=stamp(),pids={},session=uuid.uuid4().hex,phase='PREPARED')
        atomic(OUT/'receipt.json',receipt)
        children=[]
        try:
            for role in ('drive','watch'):
                with (OUT/f'{role}.log').open('a') as f:
                    p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-u',str(Path(__file__).resolve()),role,'--request',rid,
                                        '--session',receipt['session']],cwd=ROOT,stdin=subprocess.DEVNULL,
                                        stdout=f,stderr=f,start_new_session=True)
                    children.append(p);receipt['pids'][role]=p.pid
                    atomic(OUT/'receipt.json',receipt)
            deadline=time.monotonic()+15
            while True:
                ok=[]
                for role in ('drive','watch'):
                    p=OUT/f'{role}-ready.json'
                    v=load(p) if p.exists() else {}
                    ok.append(v.get('session')==receipt['session'] and v.get('pid')==receipt['pids'][role])
                if all(ok) and all(p.poll() is None for p in children):break
                if time.monotonic()>deadline or any(p.poll() is not None for p in children):
                    raise LabError('startup handshake failed')
                time.sleep(.1)
            receipt['phase']='GO';atomic(OUT/'receipt.json',receipt)
        except Exception:
            receipt['phase']='ABORT';atomic(OUT/'receipt.json',receipt)
            for p in children:
                if p.poll() is None:
                    p.terminate();p.wait(timeout=10)
            raise
        print(json.dumps(receipt))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['validate','start','drive','watch'])
    ap.add_argument('--request')
    ap.add_argument('--session')
    a=ap.parse_args()
    if a.action=='validate':
        s=validate(load(OUT/'parent-spec.json'))
        print(f"VALID: {len(s['tasks'])} tasks, {s['reserved_cpu_h']:.6f} CPU-h reservations")
    else:
        if not a.request: ap.error('--request required')
        if a.action=='start':start(a.request)
        else:
            if not a.session:ap.error('--session is required for startup children')
            {'drive':drive,'watch':watch}[a.action](a.request,a.session)
