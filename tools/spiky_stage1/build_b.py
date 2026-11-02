"""Stage 1b (J307): the 24 Stage-1 runs that did not finish (mlp_a1h, transfer_mlp_a1h, Dinos shuffle/newest ablation).
Same commands as build.py (so results are directly comparable with Stage 1 A); only reservations, gates and failure
policy differ. Per-run cap = 1.6 x the WORST measured (or measured-derived) wall time, not a guessed rate. Never trains."""
import json
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B
G, ROOT, canonical_hash = B.G, B.ROOT, B.canonical_hash
OUT = ROOT / '.lab/j307'
MARGIN = 1.6
# Measured basis (hours, wall of one run on one pinned core, 8 parallel). Pointers in `basis` below.
MEASURED_H = {
    # dinos A runs s17000-5 finished in 0.574-0.601 h (.lab/j299/state.json + DB); shuffle/newest add a per-call
    # permutation/zeroing of the window: unmeasured, covered by the 1.6x margin.
    'dinos': 0.601,
    # mlp_a1h s17000 reached training tick 15000 after 925 s (progress.json of run s43) = 61.7 s/1k ticks;
    # train 19968 ticks = 1232 s, eval of 20 traces <= dinos' 110 s (2124.2 s total - 100.9 s/1k x 19.968k).
    'mlp_a1h': (61.7*19.968 + 110)/3600,
    # transfer_mlp s17000 was at 10984 steps after 681 s (62 s/1k): 29 952 train ticks + eval.
    'transfer_mlp_a1h': (62.0*29.952 + 110)/3600,
}
FORCED = {('mlp_a1h', 'off'), ('transfer_mlp_a1h', 'off'), ('dinos', 'shuffle'), ('dinos', 'newest')}
BUDGET = 21.0


def build():
    full = B.build()
    tasks = []
    for t in full['tasks']:
        if (t['arm'], t['mode']) not in FORCED or t['stage'] == 'P0':
            continue
        cap = round(MARGIN * MEASURED_H[t['arm']], 6)
        t['nominal_cpu_h'] = round(MEASURED_H[t['arm']], 6)
        t['reserve_cpu_h'] = cap
        t['child']['entries'][0]['wall_clock_hours'] = cap
        t['stage'] = 'C' if t['seed'] == 17000 else 'B'      # canary: one run per distinct config first
        tasks.append(t)
    assert len(tasks) == 24, len(tasks)
    sb = dict(full['sandbox'])
    sb.update(cpu_hours_budget=BUDGET, allowed_children=[canonical_hash(t['child']) for t in tasks])  # seed ranges (incl. val 16000-16019 evaluation ids) inherited
    spec = dict(full)
    spec.update(name='spiky-stage1b-j307', sandbox=sb, tasks=tasks, entries=[t['child']['entries'][0] for t in tasks],
                authority=['R-20261101-004', 'M-20261102-006'],
                nominal_cpu_h=sum(t['nominal_cpu_h'] for t in tasks),
                reserved_cpu_h=sum(t['reserve_cpu_h'] for t in tasks))
    pol = dict(spec['policy'])
    pol.update(stages=['C', 'B'], gate_stages=['C'], expected_tasks=24, failure_mode='isolate', max_failures=6,
               overrun='per-run cap = 1.6x worst measured wall; a run that hits its cap is ONE recorded failure, others continue',
               stop_all_on='hash/DB/intent mismatch, budget breach, STOP file, canary failure, >=6 failures, launcher not enforcing cap',
               budget='NEW separate 21 CPU-h (caps sum 20.4); no charge or transfer from R-005/R-006',
               costs='measured: see tools/spiky_stage1/build_b.py MEASURED_H', reply_to='M-20261029-006',
               signature='— Πάρις (Opus)', label='Στάδιο 1b', stages_note='C = 4 canaries (seed 17000 of each config), then B = 20 runs',
               later_stages='not authorized', interpretation=pol['interpretation'])
    spec['policy'] = pol
    spec['runtime_sha256'] = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                              ['tools/spiky_stage1/driver.py', 'tools/sandbox_guard.py', 'tools/launch_run.py']}
    return spec


if __name__ == '__main__':
    spec = build()
    assert spec['reserved_cpu_h'] <= BUDGET
    OUT.mkdir(exist_ok=True)
    (OUT/'parent-spec.json').write_text(json.dumps(spec, indent=2)+'\n')
    print(f"tasks={len(spec['tasks'])} nominal={spec['nominal_cpu_h']:.4f} caps={spec['reserved_cpu_h']:.4f} hash={canonical_hash(spec)}")
