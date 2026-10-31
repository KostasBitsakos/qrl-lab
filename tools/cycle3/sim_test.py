"""Offline simulation of the driver (fake DB/launcher/results in a temp dir). Starts nothing real."""
import json, os, sqlite3, sys, tempfile, hashlib, subprocess
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, 'tools/cycle3'); sys.path.insert(0, 'tools')
import cycle3 as C, sandbox_guard as G
real = Path(C.ROOT)
tmp = Path(tempfile.mkdtemp())
for d in ('code-poisson/tuning/results', 'code-poisson-astra/tuning/results', '.lab'):
    (tmp / d).parent.mkdir(parents=True, exist_ok=True)
os.makedirs(tmp / 'code-poisson/tuning/results'); os.makedirs(tmp / 'code-poisson-astra/tuning/results')
os.symlink(real / 'code-poisson/tuning/results/cycle2-j119', tmp / 'code-poisson/tuning/results/cycle2-j119')
os.symlink(real / 'code-poisson-astra/tuning/results/cycle2-j120', tmp / 'code-poisson-astra/tuning/results/cycle2-j120')
os.makedirs(tmp / '.lab'); os.symlink(real / '.lab/specs', tmp / '.lab/specs')
(tmp / 'out').mkdir()
C.ROOT, C.OUT = tmp, tmp / 'out'
tpl = json.loads((real / 'code-poisson/tuning/results/cycle2-j119/j119-screen-dinos-c0-s15010.json').read_text())
conn = sqlite3.connect(':memory:'); conn.row_factory = sqlite3.Row
conn.execute('create table runs(request_id, name, status, exit_code)')
C.db = lambda: SimpleNamespace(conn=conn)
C.approval_ok = lambda: True
pend=[]
def fsleep(s):
    if s < 30: return
    for name,out,x,ok in pend:
        if ok: out.write_text(json.dumps(x))
        conn.execute('update runs set status=?,exit_code=? where name=?',('done' if ok else 'failed',0 if ok else 1,'c3/'+name))
    pend.clear()
C.time.sleep = fsleep
posts = []; C.post = lambda b, status='x': posts.append(b)
G.used_cpu_hours = lambda d, r, strict=False: 12.0
n = {'k': 0, 'fail': os.environ.get('FAIL')}
def fake_run(cmd, **kw):
    spec = json.loads(Path(cmd[cmd.index('--spec') + 1]).read_text())
    e = spec['entries'][0]; name = e['name']
    out = tmp / spec['cwd'] / e['cmd'][e['cmd'].index('--out') + 1]
    os.makedirs(out.parent, exist_ok=True)
    x = json.loads(json.dumps(tpl)); h = int(hashlib.md5(name.split('-s')[0].encode()).hexdigest()[:6], 16) % 1000
    cm = e['cmd']
    if '--pretrain-ticks' in cm:
        g = lambda f: int(cm[cm.index(f) + 1])
        assert g('--total-ticks') == g('--pretrain-ticks') + g('--finetune-ticks'), ('total != pretrain+finetune', name)
    tk = int(e['cmd'][e['cmd'].index('--total-ticks') + 1]); x['seed'] = e['seed']; x['total_ticks'] = tk
    x['checkpoint_results'] = {str(tk): list(x['checkpoint_results'].values())[-1]}
    for ck in x['checkpoint_results'].values():
        for ep in ck['val']['episodes']: ep['ret'] = 1000.0 * h; 
    ok = not (n['fail'] and n['fail'] in name)
    pend.append((name,out,x,ok))
    conn.execute('insert into runs values(?,?,?,?)', (C.PARENT, 'c3/' + name, 'running', None))
    n['k'] += 1
    return SimpleNamespace(returncode=0, stdout='ok', stderr='')
_orig = subprocess.run
C.subprocess.run = fake_run
try:
    C.drive()
except SystemExit as e:
    print('EXIT', e.code)
print('submitted', n['k'], 'state', (C.OUT / 'state.json').read_text()[:400]); print('posts', posts[-1][:200] if posts else None)
