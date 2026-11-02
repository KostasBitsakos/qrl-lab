"""Build data-only Stage1 manifest from cycle3's frozen winning commands. Never trains."""
import hashlib
import json
import math
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import sandbox_guard as G
from labdb import canonical_hash
OUT = ROOT / '.lab/j299'
RATES = {'lstm': (0,.1794253729961939,189.29), 'lstm_transfer': (.1767853,.1631976,161.10),
         'dinos': (0,.1004527,135.93), 'v2': (.0996972,.0985360,128.95),
         'derp': (0,.0329961,73.16), 'derp_hist10': (0,.0336917,68.21),
         'rppo': (0,.0077787,224.32), 'mlp_a1h': (0,.0336917,68.21),
         'transfer_mlp_a1h': (.0336917,.0336917,68.21)}


def flag(c, k, v):
    c = list(c)
    if k in c:
        c[c.index(k)+1] = str(v)
    else:
        c += [k, str(v)]
    return c


def templates():
    """Commands submitted for cycle3 F, common winning config used in BOTH lanes.
    MLP controls inherit their sequence partner's optimization configuration, replacing topology only.
    """
    ts = {}
    for a in RATES:
        base = {'mlp_a1h': 'dinos', 'transfer_mlp_a1h': 'v2'}.get(a, a)
        files = sorted((ROOT / '.lab/j269/children').glob(f'c3-opus-F-{base}-*-s15100.json'))
        if len(files) != 1:
            raise ValueError(f'expected one F template for {a}: {files}')
        c = json.loads(files[0].read_text())['entries'][0]['cmd']
        if a in ('mlp_a1h', 'transfer_mlp_a1h'):
            c = flag(c, '--agent-variant', 'mlp_a1h')
        ts[a] = c
    return ts


def build():
    tasks = []
    def add(stage, arm, seed, c, nominal, mode='off'):
        name = f'spiky1-{stage}-{arm}-{mode}-s{seed}'
        out = f'tuning/results/spiky-stage1/{name}.json'
        c = flag(c, '--out', out)
        reserve = round(1.25 * nominal, 6)
        child = dict(name=name, scope='sim', repo=G.SPIKY_REPO, cwd=G.SPIKY_REPO,
                     max_parallel=1, cpu_affinity='8-39', env_threads={'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
                     'OPENBLAS_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'},
                     entries=[dict(name=name, seed=seed, cpus=1, wall_clock_hours=reserve, cmd=c)])
        tasks.append(dict(name=name, stage=stage, arm=arm, seed=seed, mode=mode, out=out,
                          nominal_cpu_h=nominal, reserve_cpu_h=reserve, child=child))
    add('P0', 'reference', 16000, [str(ROOT / '.venv/bin/python'), 'tuning/cycle2_entry.py', 'reference',
        '--variant','pms:poisson_ms_spiky','--controllers','hpa_orig,hpa_demand,fixed,oracle','--split','val'], .5)
    ts = templates()
    for stage, arm, mode in [('A',a,'off') for a in RATES] + [('ablation','dinos',m) for m in ('shuffle','newest')]:
        s,t,v = RATES[arm]
        nominal = (s*9984+t*19968+v)/3600
        for seed in range(17000,17006):
            c = list(ts[arm]); c[0] = str(ROOT / '.venv/bin/python')
            for k,value in [('--seed',seed),('--total-ticks',29952 if s else 19968),
                            ('--checkpoints',19968),('--orig-variant','pms:poisson_ms_spiky')]:
                # RPPO names its workload --variant, not --orig-variant.
                if arm == 'rppo' and k == '--orig-variant': k='--variant'
                c=flag(c,k,value)
            if s:
                c=flag(flag(c,'--pretrain-ticks',9984),'--finetune-ticks',19968)
            if arm != 'rppo':
                c=flag(c,'--history-ablation',mode)
            add(stage,arm,seed,c,nominal,mode)
    # The proposal rounded 46.76055 to 46.7. Keep the stated HARD ceiling: distribute
    # 46.7 proportionally (effective margin ~1.24838), never silently raise budget.
    margin = 46.7 / sum(t['nominal_cpu_h'] for t in tasks)
    for t in tasks:
        reserve = math.floor(t['nominal_cpu_h'] * margin * 1e6) / 1e6
        t['reserve_cpu_h'] = reserve
        t['child']['entries'][0]['wall_clock_hours'] = reserve
    sb = dict(worktrees=[dict(repo=G.SPIKY_REPO,branch='dinos-poisson-spiky')],
              frozen_env_commit=G.SPIKY_ENV_COMMIT, frozen_harness_commit=G.SPIKY_HARNESS_COMMIT,
              frozen_entry_sha256=G.SPIKY_ENTRY_SHA256, cpu_hours_budget=46.7, cpu_affinity='8-39',
              max_parallel=8, per_run_wall_clock_hours=2.5, expires='2026-11-05T23:59:00+00:00',
              seed_ranges_allowed=[[16000,16019],[17000,17005]],
              seed_ranges_forbidden=[[14000,14019],[14500,14519],[16500,16519]],
              allowed_children=[canonical_hash(t['child']) for t in tasks])
    return dict(kind='sandbox',scope='sim',name='spiky-stage1-j299',sandbox=sb,tasks=tasks,
                cwd=G.SPIKY_REPO, entries=[t['child']['entries'][0] for t in tasks],
                limits={'wall_clock_hours':2.5}, max_parallel=8, cpu_affinity='8-39',
                authority=['R-20261101-004','M-20261101-030','M-20261101-035'],
                policy=dict(stages=['P0','A','ablation'],target_ticks=19968,transfer_source_ticks=9984,
                            checkpoint='last target endpoint only',failed_stop=3,overrun='stop all immediately',
                            retry=False,test13='forbidden',later_stages='not authorized',
                            budget='NEW separate 46.7 CPU-h; no charge or transfer from R-006',
                            costs='RATES: .lab/j291/plan.py (cycle3 ledger); MLP rates assumed, references unknown',
                            mlp_config='matched topology controls inherit selected Dinos/V.2 optimizer flags; no tuning',
                            interpretation='exploratory val-only; no winner or architecture claim from Stage1'),
                planning_margin=margin,
                nominal_cpu_h=sum(t['nominal_cpu_h'] for t in tasks),
                reserved_cpu_h=sum(t['reserve_cpu_h'] for t in tasks),
                runtime_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                                ['tools/spiky_stage1/driver.py','tools/sandbox_guard.py','tools/launch_run.py']})


if __name__ == '__main__':
    spec=build()
    assert spec['reserved_cpu_h'] <= 46.7
    OUT.mkdir(exist_ok=True)
    (OUT/'parent-spec.json').write_text(json.dumps(spec,indent=2)+'\n')
    print(f"tasks={len(spec['tasks'])} nominal={spec['nominal_cpu_h']:.6f} reserved={spec['reserved_cpu_h']:.6f} hash={canonical_hash(spec)}")
