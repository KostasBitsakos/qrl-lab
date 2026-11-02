"""Offline simulation of the whole Stage 1b plan (24 runs): no gate may false-trigger on a slow-but-legal run."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/spiky_stage1')); sys.path.insert(0, str(ROOT/'tests'))
import build_b
import driver as D
from test_spiky_stage1 import Fake


@pytest.fixture
def setup(tmp_path):
    spec = build_b.build(); b = Fake(spec); return spec, b, D.Engine(spec, b, tmp_path)


def run_to_end(e, b, per_step=lambda b: b.finish(), limit=40):
    state = e.step()
    for _ in range(limit):
        per_step(b); state = e.step()
        assert sum(r['status'] in D.ACTIVE for r in b.r) <= 8
        if state not in ('RUNNING',):
            break
    return state


def test_manifest_measured_caps_and_budget():
    s = build_b.build(); T = s['tasks']
    assert len(T) == 24 and s['reserved_cpu_h'] <= s['sandbox']['cpu_hours_budget'] == 21.0
    for t in T:
        assert t['reserve_cpu_h'] >= 1.5 * build_b.MEASURED_H[t['arm']]          # margin >= 1.5x measured
        assert t['child']['entries'][0]['wall_clock_hours'] == t['reserve_cpu_h'] <= 2.5
        c = t['child']['entries'][0]['cmd']; v = lambda k: c[c.index(k)+1]
        assert 17000 <= t['seed'] <= 17005 and '16500' not in ' '.join(c) and v('--checkpoints') == '19968'
        assert t['mode'] == v('--history-ablation') and t['out'].startswith('tuning/results/spiky-stage1/')
    assert {t['stage'] for t in T if t['seed'] == 17000} == {'C'} and sum(t['stage'] == 'C' for t in T) == 4
    # mlp_a1h cap exceeds what killed the first attempt (0.257 h) by > 2x
    assert min(t['reserve_cpu_h'] for t in T if t['arm'] == 'mlp_a1h') > 2*0.257
    # same commands as Stage 1, apart from the output path inside the reservation
    full = {t['name']: t for t in build_b.B.build()['tasks']}
    for t in T:
        assert t['child']['entries'][0]['cmd'] == full[t['name']]['child']['entries'][0]['cmd']


def test_full_plan_completes_without_any_gate_firing(setup):
    s, b, e = setup
    assert run_to_end(e, b) == 'DONE'
    assert len(b.r) == 24 and len(e.state['checked']) == 24 and not e.state['errors']
    assert b.used() <= s['sandbox']['cpu_hours_budget'] and not b.stopped


def test_canaries_run_before_the_rest(setup):
    s, b, e = setup
    e.step(); assert len(b.r) == 4 and e.step() == 'RUNNING' and len(b.r) == 4


def test_slow_but_legal_run_is_not_killed(setup):
    s, b, e = setup; e.step()
    for r in b.r:   # started 99% of cap ago: still inside its cap
        cap = next(t['reserve_cpu_h'] for t in s['tasks'] if t['name'] == r['name'].split('/')[0])
        r['started'] = (datetime.now(timezone.utc)-timedelta(hours=0.99*cap)).isoformat()
    assert e.step() == 'RUNNING' and not b.stopped


def test_run_that_hits_its_cap_is_one_failure_others_continue(setup):
    s, b, e = setup; e.step(); b.finish()
    b.r[0].update(status='done'); b.r[1].update(status='done')
    e.step()                                  # canaries checked, stage B launched
    victim = [r for r in b.r if r['status'] in D.ACTIVE][0]; victim.update(status='stopped', exit_code=-15)
    state = run_to_end(e, b)
    assert state == 'INCOMPLETE' and len(e.state['errors']) == 1 and len(b.r) == 24 and not b.stopped


def test_canary_failure_stops_before_stage_b(setup):
    s, b, e = setup; e.step(); b.r[0].update(status='stopped', exit_code=-15); b.finish()
    assert e.step() == 'STOPPED' and len(b.r) == 4 and b.stopped


def test_six_failures_stop_all(setup):
    s, b, e = setup; e.step(); b.finish(); e.step()
    for r in [r for r in b.r if r['status'] in D.ACTIVE][:6]:
        r.update(status='failed', exit_code=1)
    assert e.step() == 'STOPPED' and b.stopped and len(e.state['errors']) == 6


def test_five_failures_do_not_stop(setup):
    s, b, e = setup; e.step(); b.finish(); e.step()
    for r in [r for r in b.r if r['status'] in D.ACTIVE][:5]:
        r.update(status='failed', exit_code=1)
    assert run_to_end(e, b) == 'INCOMPLETE' and len(e.state['errors']) == 5 and not b.stopped


def test_launcher_failing_to_enforce_cap_still_aborts(setup):
    s, b, e = setup; e.step()
    b.r[0]['started'] = (datetime.now(timezone.utc)-timedelta(hours=5)).isoformat()
    assert e.step() == 'STOPPED' and 'overrun' in e.state['reason']


@pytest.mark.parametrize('scenario', ['stopfile', 'approval', 'duplicate', 'budget'])
def test_safety_gates_still_fail_closed(setup, scenario):
    s, b, e = setup; e.step()
    if scenario == 'stopfile': (e.out/'STOP').write_text('x')
    if scenario == 'approval': b.ok = False
    if scenario == 'duplicate': b.r.append(dict(b.r[0]))
    if scenario == 'budget': b.extra = 30
    assert e.step() == 'STOPPED' and b.stopped


def test_seed_authorization_covers_every_evaluation_trace():
    """Codex J307 r1: evaluation trace ids 16000-16019 pass the sandbox seed guard in the payload; test13 stays forbidden."""
    s = build_b.build()['sandbox']
    allowed = [tuple(x) for x in s['seed_ranges_allowed']]
    ok = lambda v: any(lo <= v <= hi for lo, hi in allowed)
    assert all(ok(v) for v in list(range(16000, 16020)) + list(range(17000, 17006)))
    assert not any(ok(v) for v in range(16500, 16520))
    assert [list(x) for x in s['seed_ranges_forbidden']] == [[14000, 14019], [14500, 14519], [16500, 16519]]
    assert allowed == [tuple(x) for x in build_b.B.build()['sandbox']['seed_ranges_allowed']]
