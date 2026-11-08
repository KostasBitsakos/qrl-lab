#!/usr/bin/env python3
"""J402: F-stage analysis (val only, NO claim). per seed -> mean over 20 val episodes at the final checkpoint
(no best-on-val). Across seeds: mean, IQM, bootstrap 95% CI (10000 resamples). Paired vs HPA references on the same
20 val traces (per-episode difference, then seed level). Writes .lab/c401/f_analysis.json. Read-only on results."""
import glob, json, re, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / 'code-poisson-c345/tuning/results/c345'
rng = np.random.default_rng(0)

def iqm(x):
    x = np.sort(np.asarray(x, float)); n = len(x); lo, hi = int(np.floor(n*.25)), int(np.ceil(n*.75))
    return float(x[lo:hi].mean())

def boot(x, f, B=10000):
    x = np.asarray(x, float)
    v = [f(x[rng.integers(0, len(x), len(x))]) for _ in range(B)]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]

hpa = json.load(open(RES / 'c345-W-reference-hpa.json'))
refs = {'hpa_orig': hpa['grids']['hpa_orig']['50']['episodes'], 'hpa_demand': hpa['grids']['hpa_demand']['0.9']['episodes'] if '0.9' in hpa['grids']['hpa_demand'] else None,
        'fixed': hpa['grids']['fixed']['10']['episodes']}
def agg(eps, k): return float(np.mean([e[k] for e in eps]))
out = {'refs': {}, 'arms': {}}
for r, eps in refs.items():
    if eps: out['refs'][r] = {'ret': agg(eps, 'ret'), 'slo': agg(eps, 'slo_viol_rate'), 'pods': agg(eps, 'mean_pods'), 'churn': agg(eps, 'pods_changes')}
arms = {}
for f in sorted(glob.glob(str(RES / 'c345-F-*-s186*.json'))):
    if re.search(r'\.ck\d+\.json$', f): continue
    d = json.load(open(f)); cr = d['checkpoint_results']; k = str(max(int(x) for x in cr))
    eps = cr[k]['val']['episodes']
    arms.setdefault(re.match(r'c345-F-(.+)-s\d+\.json', Path(f).name).group(1), {})[d['seed']] = (k, eps)
for arm, seeds in arms.items():
    ks = {v[0] for v in seeds.values()}
    sc = {s: agg(e, 'ret') for s, (_, e) in seeds.items()}
    x = list(sc.values())
    row = {'n_seeds': len(x), 'ckpt': sorted(ks), 'seed_means': sc, 'mean': float(np.mean(x)), 'iqm': iqm(x), 'ci_mean': boot(x, np.mean),
           'sd': float(np.std(x, ddof=1)) if len(x) > 1 else None,
           'slo': float(np.mean([agg(e, 'slo_viol_rate') for _, e in seeds.values()])), 'pods': float(np.mean([agg(e, 'mean_pods') for _, e in seeds.values()])),
           'churn': float(np.mean([agg(e, 'pods_changes') for _, e in seeds.values()])), 'p95': float(np.mean([agg(e, 'p95_latency') for _, e in seeds.values()]))}
    for r, reps in refs.items():
        if not reps: continue
        diffs = [np.mean([a['ret'] - b['ret'] for a, b in zip(e, reps)]) for _, e in seeds.values()]
        row['vs_' + r] = {'mean_diff': float(np.mean(diffs)), 'ci': boot(diffs, np.mean), 'frac_seeds_better': float(np.mean(np.array(diffs) > 0))}
    out['arms'][arm] = row
Path(ROOT / '.lab/c401/f_analysis.json').write_text(json.dumps(out, indent=1))
print(json.dumps({'refs': out['refs']}, indent=1))
for a, r in sorted(out['arms'].items(), key=lambda t: -t[1]['mean']):
    print(f"{a:18s} n={r['n_seeds']} ck={r['ckpt']} mean={r['mean']:9.0f} iqm={r['iqm']:9.0f} CI={r['ci_mean'][0]:.0f}..{r['ci_mean'][1]:.0f} sd={r['sd']:.0f} slo={r['slo']:.3f} pods={r['pods']:.1f} churn={r['churn']:.0f} "
          f"vsHPAorig={r['vs_hpa_orig']['mean_diff']:+.0f}[{r['vs_hpa_orig']['ci'][0]:+.0f},{r['vs_hpa_orig']['ci'][1]:+.0f}] vsDemand={r.get('vs_hpa_demand',{}).get('mean_diff',float('nan')):+.0f}")
