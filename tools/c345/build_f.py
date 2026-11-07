"""J380 / C345: DRAFT frozen spec for stage F (10 seeds x 39,936 total ticks, poisson_ms, val 13000-13019).
Inputs: W selection (.lab/j380/w_analysis.json, produced by the frozen rule in build_w.select_w) and measured W CPU.
Data only: never launches. NOT launch-ready: driver.py has no stage-F support yet (needs reviewed extension).
Output: .lab/j380/F-spec-draft-{A,B}.json (two parents: guard caps one sandbox at 160 CPU-h) + F-summary.json
"""
import json, math, statistics as st, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools')); sys.path.insert(0, str(ROOT / 'tools/c345'))
import build_w as W  # noqa: E402
from labdb import canonical_hash  # noqa: E402

OUT = ROOT / '.lab/j380'
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
    return dict(kind='sandbox', scope='sim', name=f'c345-F{half}-DRAFT', tasks=tasks, cwd=W.REPO,
                sandbox=dict(worktrees=[dict(repo=W.REPO, branch=W.BRANCH)], cpu_affinity='8-39', max_parallel=16,
                             cpu_hours_budget=round(sum(t['reserve_cpu_h'] for t in tasks) + 1e-6, 6),
                             seed_ranges_allowed=[[13000, 13019], [HALVES[half][0], HALVES[half][-1]]],
                             seed_ranges_forbidden=[W.TEST12, [14500, 14519], [16500, 16519], [18500, 18501]],
                             allowed_children=[canonical_hash(t['child']) for t in tasks]),
                policy=dict(stage='F', arms=list(W.ARMS), seeds=HALVES[half], total_ticks=W.F_TOTAL, transfer_source_ticks=W.SRC,
                            selection=sel, eval='val 13000-13019 at endpoint (no best-on-val)', test12='forbidden here',
                            launch_ready=False, why_not='driver.py lacks stage F; selection needs Claude+Codex joint freeze',
                            hpa='reference val already in W (c345-W-reference-hpa); test12 HPA after unlock'),
                nominal_cpu_h=round(sum(t['nominal_cpu_h'] for t in tasks), 4),
                reserved_cpu_h=round(sum(t['reserve_cpu_h'] for t in tasks), 4))


if __name__ == '__main__':
    summ = {}
    for h in HALVES:
        s = build(h)
        (OUT / f'F-spec-draft-{h}.json').write_text(json.dumps(s, indent=2) + '\n')
        summ[h] = dict(tasks=len(s['tasks']), nominal=s['nominal_cpu_h'], reserved=s['reserved_cpu_h'], hash=canonical_hash(s))
        print(h, summ[h])
    (OUT / 'F-summary.json').write_text(json.dumps(summ, indent=1))
