"""Dry validation of the C345 W draft spec: driver.validate (protected tree, whitelist, reservation equality with the
launcher's check_child, runtime hashes) + seed-range checks. Never launches."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools')); sys.path.insert(0, str(ROOT / 'tools/c345'))
import driver as D
import sandbox_guard as G
spec = D.load(sys.argv[1] if len(sys.argv) > 1 else ROOT / '.lab/j350/W-spec-draft.json')
D.validate(spec, protected=True)
sb = spec['sandbox']
for t in spec['tasks']:
    for lo, hi in G.entry_seeds(t['child']['entries'][0]):
        assert not (lo <= 14019 and hi >= 14000), 'test12 seed in a task'
cmds = [' '.join(t['child']['entries'][0]['cmd']) for t in spec['tasks']]
assert not any('test12' in c or '--eval-split test' in c for c in cmds)
print(f"VALID: {len(spec['tasks'])} tasks, reserved {spec['reserved_cpu_h']:.3f} <= budget {sb['cpu_hours_budget']}, "
      f"whitelist {len(sb['allowed_children'])}, harness {sb['frozen_harness_commit'][:7]}, test12 untouched")
