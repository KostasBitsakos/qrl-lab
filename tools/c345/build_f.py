"""J380 / C345: DRAFT frozen spec for stage F (10 seeds x 39,936 total ticks, poisson_ms, val 13000-13019).
Inputs: W selection (.lab/j380/w_analysis.json, produced by the frozen rule in build_w.select_w) and measured W CPU.
Data only: never launches. J381: driver.py supports stage F (timing_mode f_from_w, recomputed in validate); the spec is
launch_ready only as a FROZEN CARD that still needs the researcher's approval (hash bound by the launcher).
Output: .lab/j381/F-spec-{A,B}.json (two parents: guard caps one sandbox at 160 CPU-h) + F-summary.json
"""
import hashlib, json, math, statistics as st, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools')); sys.path.insert(0, str(ROOT / 'tools/c345'))
import build_w as W  # noqa: E402
from labdb import canonical_hash  # noqa: E402
import sandbox_guard as G  # noqa: E402

OUT = ROOT / '.lab/j380'
RUNTIME = ['tools/c345/driver.py', 'tools/c345/build_w.py', 'tools/c345/build_f.py', 'tools/sandbox_guard.py',
           'tools/launch_run.py', '.lab/j380/w_analysis.json']
MARGIN = 2.0          # cap = 2x measured W CPU (same arm/config, 2x ticks assumed linear) -> rounded up
HALVES = {'A': W.F_SEEDS[:5], 'B': W.F_SEEDS[5:]}


def build(half):
    an = json.loads((OUT / 'w_analysis.json').read_text())
    sel, rows = an['selection'], an['rows']
    cfgs = W.configs(('opus', 'astra'))
    tasks = []
    for arm in W.ARMS:
        s = sel[arm]
        extra = cfgs[(s['lane'], arm)][int(s['config'][1:])]
        meas = [r['cpu_h'] for r in rows if r['arm'] == arm and r['lane'] == s['lane'] and r['cfg'] == s['config']]
        # W ran 19,968 ticks; F is 2x ticks -> expected 2x measured; cap = MARGIN x that, slowest W run
        nom = 2 * st.mean(meas)
        cap = math.ceil(MARGIN * 2 * max(meas) * 1e6) / 1e6
        for seed in HALVES[half]:
            name = f'c345-F-{arm}-s{seed}'
            out = f'tuning/results/c345/{name}.json'
            c, tgt = W.cmd_for(arm, seed, W.F_TOTAL, extra, out)
            # F uses endpoint weights saved; W flag set already has --save-weights on
            tasks.append(W.task('F', name, arm, seed, c, nom, out, s['lane'], s['config'], tgt, margin=cap / nom))
    res = sum(t['reserve_cpu_h'] for t in tasks)
    return dict(kind='sandbox', scope='sim', name=f'c345-F{half}', tasks=tasks, cwd=W.REPO,
                entries=[t['child']['entries'][0] for t in tasks], limits={'wall_clock_hours': max(t['reserve_cpu_h'] for t in tasks)},
                max_parallel=16, cpu_affinity='8-39',
                authority=['R-20261106-002', 'M-20261106-011', 'R-20261107-001 (J381: F frozen card; launch = approval of this card)'],
                sandbox=dict(worktrees=[dict(repo=W.REPO, branch=W.BRANCH)],
                             frozen_env_commit=G.C345_ENV_COMMIT, frozen_harness_commit=G.C345_HARNESS_COMMIT,
                             frozen_entry_sha256=G.C345_ENTRY_SHA256, cpu_affinity='8-39', max_parallel=16,
                             cpu_hours_budget=round(res + 1e-6, 6),
                             per_run_wall_clock_hours=max(t['reserve_cpu_h'] for t in tasks),
                             expires='2026-11-10T23:59:00+00:00',
                             seed_ranges_allowed=[[13000, 13019], [HALVES[half][0], HALVES[half][-1]]],
                             seed_ranges_forbidden=[W.TEST12, [14500, 14519], [16500, 16519], [18500, 18501]],
                             allowed_children=[canonical_hash(t['child']) for t in tasks]),
                policy=dict(stages=['F'], gate_stages=[], expected_tasks=len(tasks), variant=W.VARIANT, val_seeds=W.VAL,
                            failure_mode='abort', max_failures=3, retry=False, half=half, label=f'Στάδιο F-{half}',
                            arms=list(W.ARMS), seeds=HALVES[half], total_ticks=W.F_TOTAL, transfer_source_ticks=W.SRC,
                            selection=sel, selection_source='.lab/j380/w_analysis.json (W rule, val only, n=2, NO claim)',
                            eval='val 13000-13019 at endpoint (no best-on-val)', test12='forbidden (single-use, after F, reviewed unlock)',
                            later_stages='test12 and HPA test not authorized by this spec',
                            launch_ready=True, timing_mode='f_from_w', margin=MARGIN,
                            costs='reserve = 2 x 2 x slowest measured W run of the selected config (2x ticks, linear assumption); overrun stops all',
                            hpa='reference val already in W (c345-W-reference-hpa); test12 HPA after unlock',
                            interpretation='10 seeds, val only; paired comparison by seed; IQM+bootstrap CI in analysis; no speed-up/quantum claim'),
                nominal_cpu_h=round(sum(t['nominal_cpu_h'] for t in tasks), 4), reserved_cpu_h=round(res, 4),
                runtime_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in RUNTIME})


if __name__ == '__main__':
    (ROOT / '.lab/j381').mkdir(exist_ok=True)
    summ = {}
    for h in HALVES:
        s = build(h)
        (ROOT / '.lab/j381' / f'F-spec-{h}.json').write_text(json.dumps(s, indent=2) + '\n')
        summ[h] = dict(tasks=len(s['tasks']), nominal=s['nominal_cpu_h'], reserved=s['reserved_cpu_h'], hash=canonical_hash(s))
        print(h, summ[h])
    (ROOT / '.lab/j381/F-summary.json').write_text(json.dumps(summ, indent=1))
