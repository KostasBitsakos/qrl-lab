"""C345 / R-20261106-002: DRAFT frozen spec for stage W (screening) on the ORIGINAL poisson_ms workload.
Data only: never trains, never launches. Writes .lab/j350/W-spec-draft.json (+ F template) and prints hashes.

W  = per lane, 2 configs x 2 common seeds (18500-18501) x 19,968 TOTAL ticks incl. transfer source, 10 learning arms
     (9 J332 arms + derp_ddqn) + one HPA reference task (hpa_orig + hpa_demand 5 thresholds, val 13000-13019).
F  = template only (10 seeds 18600-18609 x 39,936 total; transfer 9,984 + 29,952); filled after the joint W freeze.
Rebuild with --pilot-timings FILE for measured reservations. Without it launch_ready=false.
Reservation = 2 x nominal (council envelope); nominal from the cycle-3 ledger rates (J299 build.py RATES, extrapolated,
NOT measured on poisson_ms) until pilots replace them. derp_ddqn is costed like derp_hist10 (council, codex_round2 d).
Usage: build_w.py [--lanes opus[,astra]] [--check]
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import sandbox_guard as G  # noqa: E402
from labdb import canonical_hash  # noqa: E402

OUT = ROOT / '.lab/j350'
REPO, BRANCH = 'code-poisson-c345', 'dinos-poisson-c345'
VARIANT = 'pms:poisson_ms'
VAL = list(range(13000, 13020))
W_SEEDS, F_SEEDS = [18500, 18501], list(range(18600, 18610))
TEST12 = [14000, 14019]
W_TOTAL, SRC = 19968, 9984
F_TOTAL = 39936
ENVELOPE, MARGIN = 350.0, 2.0
# (source s/tick, target s/tick, eval+startup s) from tools/spiky_stage1/build.py RATES (cycle-3 ledger)
RATES = {'lstm': (0, .1794253729961939, 189.29), 'lstm_transfer': (.1767853, .1631976, 161.10),
         'dinos': (0, .1004527, 135.93), 'v2': (.0996972, .0985360, 128.95),
         'derp': (0, .0329961, 73.16), 'derp_hist10': (0, .0336917, 68.21), 'derp_ddqn': (0, .0336917, 68.21),
         'rppo': (0, .0077787, 224.32), 'mlp_a1h': (0, .0336917, 68.21),
         'transfer_mlp_a1h': (.0336917, .0336917, 68.21)}
ARMS = tuple(RATES)
# Opus lane = exploration/optimizer (council C341). c0 = the cycle-3 frozen command unchanged. DRAFT values, reviewable.
OPUS_C1 = {'derp': [('--eps-schedule', 'original')], 'derp_hist10': [('--eps-schedule', 'original')],
           'derp_ddqn': [('--derp-target-sync', '100')], 'rppo': [('--gae-lambda', '0.95')]}
FIXED_C1 = [('--lr', '5e-05'), ('--grad-clip', '10')]   # lstm, lstm_transfer, dinos, v2, mlp_a1h, transfer_mlp_a1h
ASTRA_FILE = ROOT / '.lab/j350/configs_astra.json'       # Codex lane: {arm: [[c0 flags], [c1 flags]]}; absent -> pending
TRANSFER = {'lstm_transfer', 'v2', 'transfer_mlp_a1h'}


def flag(c, k, v=None):
    c = list(c)
    if k in c:
        c[c.index(k) + 1] = str(v)
    else:
        c += [k, str(v)]
    return c


def template(arm):
    base = {'derp_ddqn': 'derp_hist10'}.get(arm, arm)
    p = ROOT / f'.lab/j299/children/spiky1-A-{base}-off-s17000.json'
    c = json.loads(p.read_text())['entries'][0]['cmd']
    c = [str(ROOT / '.venv/bin/python')] + c[1:]
    if arm in {'derp_hist10', 'derp_ddqn'}:
        c = flag(c, '--derp-history', 10)
    if arm == 'derp_ddqn':
        c = flag(c, '--derp-double', 'on')
    if '--history-ablation' in c:            # default 'off'; the flag is not needed on poisson_ms
        i = c.index('--history-ablation'); assert c[i + 1] == 'off'; del c[i:i + 2]
    return c


def configs(lanes):
    out = {}
    for arm in ARMS:
        if 'opus' in lanes:
            c1 = OPUS_C1.get(arm, FIXED_C1)
            out[('opus', arm)] = [[], c1]
        if 'astra' in lanes:
            a = json.loads(ASTRA_FILE.read_text())[arm]
            out[('astra', arm)] = [[tuple(x) for x in cfg] for cfg in a]
    return out


def nominal(arm, total):
    s, t, v = RATES[arm]
    src = SRC if arm in TRANSFER else 0
    return (s * src + t * (total - src) + v) / 3600


def cmd_for(arm, seed, total, extra, out):
    c = template(arm)
    tgt = total - SRC if arm in TRANSFER else total
    var_flag = '--variant' if arm == 'rppo' else '--orig-variant'
    for k, v in [('--seed', seed), ('--total-ticks', total), ('--checkpoints', tgt), (var_flag, VARIANT),
                 ('--out', out)]:
        c = flag(c, k, v)
    if arm in TRANSFER:
        c = flag(flag(c, '--pretrain-ticks', SRC), '--finetune-ticks', tgt)
    for k, v in extra:
        c = flag(c, k, v)
    return c, tgt


def task(stage, name, arm, seed, c, nom, out, lane=None, cfg=None, tgt=None):
    reserve = round(MARGIN * nom, 6)
    child = dict(name=name, scope='sim', repo=REPO, cwd=REPO, max_parallel=1, cpu_affinity='8-39',
                 env_threads={k: '1' for k in G.ENV_ALLOWED},
                 entries=[dict(name=name, seed=seed, cpus=1, wall_clock_hours=reserve, cmd=c)])
    return dict(name=name, stage=stage, arm=arm, lane=lane, config=cfg, seed=seed, mode='off', out=out,
                target_ticks=tgt, nominal_cpu_h=round(nom, 6), reserve_cpu_h=reserve, child=child)


def select_w(spec, returns):
    """Choose ONE candidate per arm across lanes, using both endpoint seed returns."""
    groups = {}
    for t in spec['tasks']:
        if t['stage'] != 'W':
            continue
        value = returns[t['name']]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('nonfinite W return')
        key = (t['arm'], t['lane'], t['config'])
        groups.setdefault(key, []).append((t['seed'], value))
    winners = {}
    for (arm, lane, cfg), rows in groups.items():
        if sorted(s for s, _ in rows) != W_SEEDS:
            raise ValueError('selection requires both common seeds exactly once')
        score = sum(v for _, v in rows) / len(rows)
        rank = (-score, cfg != 'c0', lane != 'opus', f'{lane}-{arm}-{cfg}')
        if arm not in winners or rank < winners[arm][0]:
            winners[arm] = (rank, dict(arm=arm, lane=lane, config=cfg, mean_val_return=score))
    if set(winners) != set(ARMS):
        raise ValueError('selection requires every arm')
    return {arm: winners[arm][1] for arm in ARMS}


def timing_key(cmd):
    """Bind timing to the full workload/configuration, independent of seed and output path."""
    c = list(cmd)
    for k in ('--seed', '--out'):
        if k in c:
            c[c.index(k) + 1] = '<variable>'
    return canonical_hash(c)


def apply_pilots(tasks, pilots):
    """Full W-exposure launcher timings; no linear extrapolation from short pilots."""
    required = {timing_key(t['child']['entries'][0]['cmd']): t['arm'] for t in tasks}
    by_arm = {}
    covered = set()
    for r in pilots['measurements']:
        key = timing_key(r['cmd'])
        seconds = r['elapsed_seconds']
        if key not in required or isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or \
                not math.isfinite(seconds) or seconds <= 0 or r.get('includes_startup_and_eval') is not True or \
                not r.get('run_id') or not r.get('request_id') or not r.get('evidence_path'):
            raise ValueError('invalid or unbound full-exposure pilot measurement')
        arm = required[key]
        by_arm[arm] = max(by_arm.get(arm, 0), seconds)
        covered.add(key)
    if covered != set(required):
        raise ValueError('pilot coverage incomplete: every distinct W command including reference is required')
    for t in tasks:
        # Round upwards: the frozen reservation must never be less than twice the measurement.
        cap = math.ceil(MARGIN * by_arm[t['arm']] / 3600 * 1e6) / 1e6
        t['reserve_cpu_h'] = cap
        t['child']['entries'][0]['wall_clock_hours'] = cap


def build(lanes=('opus',), pilots=None):
    tasks = []
    ref_out = 'tuning/results/c345/c345-W-reference-hpa.json'
    tasks.append(task('P0', 'c345-W-reference-hpa', 'reference', VAL[0],
                      [str(ROOT / '.venv/bin/python'), 'tuning/cycle2_entry.py', 'reference', '--variant', VARIANT,
                       '--controllers', 'hpa_orig,hpa_demand,fixed,oracle', '--split', 'val', '--out', ref_out],
                      .25, ref_out))
    seen, aliases = {}, {}      # identical commands across lanes run ONCE (same candidate); aliases recorded
    for (lane, arm), cfgs in configs(lanes).items():
        for ci, extra in enumerate(cfgs):
            key = (arm, tuple(cmd_for(arm, 0, W_TOTAL, extra, '-')[0]))
            if key in seen:
                aliases[f'{lane}-{arm}-c{ci}'] = seen[key]
                continue
            cid = seen[key] = f'{lane}-{arm}-c{ci}'
            for seed in W_SEEDS:
                name = f'c345-W-{cid}-s{seed}'
                out = f'tuning/results/c345/{name}.json'
                c, tgt = cmd_for(arm, seed, W_TOTAL, extra, out)
                tasks.append(task('W', name, arm, seed, c, nominal(arm, W_TOTAL), out, lane, f'c{ci}', tgt))
    if pilots is not None:
        apply_pilots(tasks, pilots)
    nom = sum(t['nominal_cpu_h'] for t in tasks)
    res = sum(t['reserve_cpu_h'] for t in tasks)
    budget = round(res + 1e-6, 6)
    sb = dict(worktrees=[dict(repo=REPO, branch=BRANCH)],
              frozen_env_commit=G.C345_ENV_COMMIT, frozen_harness_commit=G.C345_HARNESS_COMMIT,
              frozen_entry_sha256=G.C345_ENTRY_SHA256, cpu_hours_budget=budget, cpu_affinity='8-39',
              max_parallel=16, per_run_wall_clock_hours=max(t['reserve_cpu_h'] for t in tasks),
              expires='2026-11-09T23:59:00+00:00',
              seed_ranges_allowed=[[13000, 13019], [18500, 18501]],
              seed_ranges_forbidden=[TEST12, [14500, 14519], [16500, 16519], [18600, 18609]],
              allowed_children=[canonical_hash(t['child']) for t in tasks])
    return dict(kind='sandbox', scope='sim', name='c345-W-DRAFT', sandbox=sb, tasks=tasks, cwd=REPO,
                entries=[t['child']['entries'][0] for t in tasks], limits={'wall_clock_hours': sb['per_run_wall_clock_hours']},
                max_parallel=16, cpu_affinity='8-39',
                authority=['R-20261106-002', 'M-20261106-011', 'DRAFT: needs its own frozen-card approval'],
                policy=dict(stages=['P0', 'W'], expected_tasks=len(tasks), variant=VARIANT, val_seeds=VAL,
                            lanes=list(lanes), transfer_source_ticks=SRC, total_ticks=W_TOTAL,
                            checkpoint='last target endpoint only', failed_stop=3, overrun='stop all immediately',
                            retry=False, test12='forbidden (locked; only after F, reviewed unlock)',
                            later_stages='F not authorized by this spec',
                            selection='ONE config per arm across both lanes (distinct candidates; identical commands '
                                      'are run once, see config_aliases): max mean val return at the endpoint over '
                                      'the 2 seeds; ties -> config c0 first, then lane opus before astra, then candidate id order; '
                                      'rule frozen before W ends; intermediate evals diagnostics only',
                            config_aliases=aliases,
                            arm_labels={'derp_hist10': 'Enhanced DERP, explicit --derp-history 10',
                                        'derp_ddqn': 'Enhanced DERP, history 10 + Double-DQN; sync 1 isolates '
                                                     'target substitution; sync 100 also changes cadence'},
                            pilot_gate='Separate approved pilot spec required before W; full W exposure, startup '
                                       'and endpoint val included, each distinct config and reference covered; '
                                       'rebuild with --pilot-timings FILE; cap = 2x slowest measured pilot per arm',
                            launch_ready=pilots is not None,
                            pilot_timings=pilots,
                            envelope_cpu_h=ENVELOPE, margin=MARGIN,
                            costs=('measured pilot reservations; nominal figures remain historical extrapolations' if pilots is not None
                                   else 'extrapolated cycle-3 ledger rates, NOT launch-ready; rebuild after pilots'),
                            interpretation='screening on reused val; no winner claim from W'),
                nominal_cpu_h=round(nom, 6), reserved_cpu_h=round(res, 6),
                runtime_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                ['tools/c345/driver.py', 'tools/c345/build_w.py', 'tools/sandbox_guard.py', 'tools/launch_run.py']})


def f_template():
    """F stage shape for the envelope check only (configs filled after the W freeze)."""
    rows = []
    for arm in ARMS:
        n = nominal(arm, F_TOTAL)
        rows.append(dict(arm=arm, seeds=F_SEEDS, total_ticks=F_TOTAL,
                         target_ticks=F_TOTAL - SRC if arm in TRANSFER else F_TOTAL,
                         nominal_cpu_h_per_run=round(n, 6), reserve_cpu_h_per_run=round(MARGIN * n, 6)))
    tot = sum(r['reserve_cpu_h_per_run'] * len(F_SEEDS) for r in rows) + 2 * MARGIN * .25
    return dict(stage='F', rows=rows, hpa='reference task (hpa_orig + hpa_demand) on val, then test12 once after unlock',
                reserved_cpu_h=round(tot, 6), note='guard caps one aggregate sandbox at 160 CPU-h: F needs 2 parents')


def seed_guard():
    """Fail if any W/F seed already appears in a launcher child spec or a results file name."""
    hits = []
    want = set(W_SEEDS + F_SEEDS)
    for p in list(ROOT.glob('.lab/**/children/*.json')) + list(ROOT.glob('.lab/**/*spec*.json')):
        try:
            j = json.loads(p.read_text())
        except Exception:
            continue
        for e in j.get('entries', []) or []:
            if not isinstance(e, dict):
                continue
            c = e.get('cmd') or []
            s = {e.get('seed')} | {int(c[i + 1]) for i, x in enumerate(c[:-1]) if x == '--seed' and str(c[i + 1]).isdigit()}
            if s & want and 'j350' not in str(p):
                hits.append(f'{p}: {sorted(s & want)}')
    for p in ROOT.glob('code*/tuning/results/**/*.json'):
        if any(f's{x}' in p.name for x in want):
            hits.append(str(p))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lanes', default='opus')
    ap.add_argument('--pilot-timings', type=Path)
    a = ap.parse_args()
    lanes = tuple(a.lanes.split(','))
    hits = seed_guard()
    if hits:
        raise SystemExit('seed guard: seeds already used:\n' + '\n'.join(hits[:20]))
    spec = build(lanes, json.loads(a.pilot_timings.read_text()) if a.pilot_timings else None)
    ft = f_template()
    OUT.mkdir(exist_ok=True)
    (OUT / 'W-spec-draft.json').write_text(json.dumps(spec, indent=2) + '\n')
    (OUT / 'F-template.json').write_text(json.dumps(ft, indent=2) + '\n')
    total = spec['reserved_cpu_h'] + ft['reserved_cpu_h'] * (1 if 'astra' in lanes else 1)
    print(f"W lanes={lanes} tasks={len(spec['tasks'])} nominal={spec['nominal_cpu_h']:.2f} "
          f"reserved={spec['reserved_cpu_h']:.2f} hash={canonical_hash(spec)}")
    print(f"F template reserved={ft['reserved_cpu_h']:.2f}; W+F={total:.2f} / envelope {ENVELOPE}")
    print('seed guard: 18500-18501, 18600-18609 unused; test12 14000-14019 forbidden in the W sandbox')


if __name__ == '__main__':
    main()
