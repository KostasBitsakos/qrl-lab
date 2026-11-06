"""C345 (J350): sandbox_guard profile for code-poisson-c345, generalised driver, W draft builder. No launches."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import importlib.util  # noqa: E402

import sandbox_guard as G  # noqa: E402


def _load(name):
    """Load tools/c345/<name>.py under a unique module name (tools/spiky_stage1 also has driver.py/build.py)."""
    key = f"c345_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, ROOT / "tools/c345" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
    return sys.modules[key]


def test_profiles_keep_old_pins():
    assert G.profile({"repo": "code-poisson-spiky"}) == (G.SPIKY_ENV_COMMIT, G.SPIKY_HARNESS_COMMIT, G.SPIKY_ENTRY_SHA256)
    assert G.profile({"repo": "code-poisson"}) == (G.CYCLE2_ENV_COMMIT, G.CYCLE2_HARNESS_COMMIT, G.CYCLE2_ENTRY_SHA256)
    assert G.profile({"repo": G.C345_REPO})[1] == G.C345_HARNESS_COMMIT
    assert G.SANDBOX_BRANCHES[G.C345_REPO] == "dinos-poisson-c345" and G.C345_REPO in G.MANIFEST_REPOS


@pytest.mark.skipif(not (ROOT / "code-poisson-c345").is_dir(), reason="c345 worktree absent")
def test_w_draft_builds_and_validates():
    B, D = _load("build_w"), _load("driver")
    spec = B.build(("opus",))
    assert len(spec["tasks"]) == 1 + 10 * 2 * 2
    assert {t["seed"] for t in spec["tasks"] if t["stage"] == "W"} == {18500, 18501}
    assert [14000, 14019] in spec["sandbox"]["seed_ranges_forbidden"]
    assert spec["reserved_cpu_h"] <= spec["sandbox"]["cpu_hours_budget"] <= 160
    for t in spec["tasks"]:
        c = t["child"]["entries"][0]["cmd"]
        if t["stage"] == "W":
            assert c[c.index("--total-ticks") + 1] == "19968"
            assert "pms:poisson_ms" in c and "pms:poisson_ms_spiky" not in c
            assert ("--derp-double" in c) == (t["arm"] == "derp_ddqn")
            if "--pretrain-ticks" in c:
                assert c[c.index("--pretrain-ticks") + 1] == c[c.index("--finetune-ticks") + 1] == "9984"
    D.validate(spec, protected=True)
    bad = dict(spec, tasks=spec["tasks"][:-1])
    with pytest.raises(Exception):
        D.validate(bad, protected=False)


SMOKE = ROOT / ".lab/j350/smoke_out"


def _artifact_case(tmp_path, name, mutate=None):
    import json
    D = _load("driver")
    from labdb import LabError  # noqa: F401
    x = json.loads((SMOKE / f"{name}.json").read_text())
    cmd = json.loads((SMOKE / f"{name}.cmd").read_text())
    if mutate:
        mutate(x)
    (tmp_path / "w").mkdir(exist_ok=True)
    (tmp_path / "w" / "a.json").write_text(json.dumps(x))
    arm = name.split("-")[3]
    tgt = int(cmd[cmd.index("--checkpoints") + 1])
    D.SPEC.clear()
    D.SPEC.update(variant="pms:poisson_ms", val_seeds=list(range(13000, 13020)))
    t = dict(stage="W", arm=arm, seed=18500, mode="off", out="a.json", target_ticks=tgt, child=dict(cwd="w", entries=[dict(cmd=cmd)]))
    D.artifact(t, root=tmp_path)


@pytest.mark.skipif(not SMOKE.is_dir(), reason="J350 smoke outputs absent")
@pytest.mark.parametrize("name,mutate", [
    ("c345-W-opus-derp_ddqn-c0-s18500", lambda x: x.update(double_dqn_target=None)),        # plain DERP artifact
    ("c345-W-opus-derp_ddqn-c0-s18500", lambda x: x.update(derp_history=1)),                # wrong history
    ("c345-W-opus-derp_ddqn-c1-s18500", lambda x: x.update(target_sync_replays=1)),         # wrong sync
    ("c345-W-astra-lstm_transfer-c1-s18500", lambda x: x.update(pretrain_variant="spike300_d5")),  # wrong source
    ("c345-W-astra-lstm_transfer-c1-s18500", lambda x: x.update(finetune_eps="restart")),
    ("c345-W-astra-lstm-c1-s18500", lambda x: x.update(target_sync_replays=250)),           # wrong optimiser cfg
])
def test_artifact_provenance_mutations(tmp_path, name, mutate):
    from labdb import LabError
    _artifact_case(tmp_path, name)                  # the genuine artifact is accepted
    with pytest.raises(LabError):
        _artifact_case(tmp_path, name, mutate)


def test_history_and_selection_across_lanes():
    B = _load('build_w')
    spec = B.build(('opus', 'astra'))
    for t in spec['tasks']:
        if t['arm'] in {'derp_hist10', 'derp_ddqn'}:
            cmd = t['child']['entries'][0]['cmd']
            assert cmd[cmd.index('--derp-history') + 1] == '10'
    values = {t['name']: 1.0 for t in spec['tasks'] if t['stage'] == 'W'}
    winners = B.select_w(spec, values)
    assert len(winners) == len(B.ARMS)
    assert all(w['config'] == 'c0' and w['lane'] == 'opus' for w in winners.values())
    for t in spec['tasks']:
        if t['arm'] == 'v2' and t['lane'] == 'astra' and t['config'] == 'c1':
            values[t['name']] = 2.0
    assert B.select_w(spec, values)['v2']['lane'] == 'astra'
    values.pop(next(iter(values)))
    with pytest.raises(KeyError):
        B.select_w(spec, values)


def _pilot_fixture(spec):
    """Synthetic metadata ONLY: no workload is executed and no timing is measured."""
    B = _load('build_w')
    return {'measurements': [dict(cmd=t['child']['entries'][0]['cmd'], elapsed_seconds=20 + i,
                                  run_id=f'fixture-{i}', request_id='fixture', evidence_path='fixture-only',
                                  includes_startup_and_eval=True) for i, t in enumerate(spec['tasks'])]}


def test_pilots_rebuild_caps_and_whitelist():
    import math
    from labdb import canonical_hash
    B, D = _load('build_w'), _load('driver')
    draft = B.build(('opus', 'astra'))
    assert not draft['policy']['launch_ready']
    with pytest.raises(Exception, match='pilot timing gate'):
        D.Backend('unapproved-fixture', draft).approval()
    fixture = _pilot_fixture(draft)
    measured = B.build(('opus', 'astra'), fixture)
    assert measured['policy']['launch_ready']
    for t in measured['tasks']:
        slowest = max(20 + i for i, old in enumerate(draft['tasks']) if old['arm'] == t['arm'])
        assert t['reserve_cpu_h'] == math.ceil(2 * slowest / 3600 * 1e6) / 1e6
        assert t['reserve_cpu_h'] == t['child']['entries'][0]['wall_clock_hours']
    assert measured['sandbox']['allowed_children'] == [canonical_hash(t['child']) for t in measured['tasks']]
    assert measured['reserved_cpu_h'] < measured['sandbox']['cpu_hours_budget']
    D.validate(measured, protected=True)
    with pytest.raises(ValueError, match='coverage incomplete'):
        B.build(('opus', 'astra'), {'measurements': fixture['measurements'][:1]})


@pytest.mark.parametrize('patch', [dict(elapsed_seconds=-1), dict(elapsed_seconds=float('nan')),
                                  dict(elapsed_seconds=True), dict(includes_startup_and_eval=False),
                                  dict(run_id=''), dict(request_id=''), dict(evidence_path='')])
def test_invalid_pilot_rejected(patch):
    B = _load('build_w')
    fixture = _pilot_fixture(B.build())
    fixture['measurements'][0].update(patch)
    with pytest.raises(ValueError):
        B.build(pilots=fixture)


@pytest.mark.parametrize('arm,lane,cfg,field,bad', [
    ('derp_ddqn', 'opus', 'c0', 'double_dqn_target', False),
    ('derp_ddqn', 'opus', 'c0', 'double_dqn_target', 1),
    ('derp_ddqn', 'opus', 'c0', 'derp_history', 3),
    ('derp_ddqn', 'opus', 'c1', 'target_sync_replays', 1),
    ('derp_hist10', 'opus', 'c0', 'derp_history', 3),
    ('lstm_transfer', 'astra', 'c0', 'pretrain_variant', 'spike300_d5'),
    ('lstm', 'astra', 'c1', 'target_sync_replays', 250),
    ('lstm', 'opus', 'c0', 'double_dqn_target', False),
    ('lstm', 'opus', 'c0', 'target_sync_replays', 100),
    ('lstm_transfer', 'astra', 'c0', 'pretrain_env_family', 'coupled'),
    ('dinos', 'opus', 'c0', 'double_dqn_target', False),
    ('v2', 'opus', 'c0', 'double_dqn_target', False),
    ('mlp_a1h', 'opus', 'c0', 'double_dqn_target', False),
    ('transfer_mlp_a1h', 'astra', 'c0', 'double_dqn_target', False),
])
def test_frozen_command_artifact_mutations(tmp_path, arm, lane, cfg, field, bad):
    import copy
    import json
    from labdb import LabError
    B, D = _load('build_w'), _load('driver')
    spec = B.build(('opus', 'astra'))
    t = copy.deepcopy(next(t for t in spec['tasks'] if (t['arm'], t['lane'], t['config']) == (arm, lane, cfg)))
    c = t['child']['entries'][0]['cmd']
    def opt(k, default=None):
        return c[c.index(k) + 1] if k in c else default
    c[c.index('--save-weights') + 1] = 'off'
    t['child']['cwd'] = 'fixture'
    t['out'] = 'artifact.json'
    x = dict(seed=t['seed'], total_ticks=19968, eval_splits=['val'], eval_seeds={'val': B.VAL},
             target_variant=B.VARIANT, history_ablation='off', agent=opt('--agent'),
             agent_variant=opt('--agent-variant', 'legacy'),
             double_dqn_target=arm == 'derp_ddqn' or (opt('--agent') != 'derp' and opt('--agent-variant', 'legacy') not in ('legacy', 'verbatim')),
             derp_history=int(opt('--derp-history', 1)),
             target_sync_replays=int(opt('--derp-target-sync', 1) if opt('--agent') == 'derp' else opt('--target-sync', 250)),
             pretrain_env_family=opt('--pretrain-env-family'),
             pretrain_variant=opt('--pretrain-variant'), finetune_eps=opt('--finetune-eps', 'restart'),
             eps_schedule=opt('--eps-schedule'), pretrain_ticks=int(opt('--pretrain-ticks', 0)),
             target_ticks=t['target_ticks'], arm=arm, optim_options={},
             checkpoint_results={str(t['target_ticks']): {'val': {'episodes': [dict(ret=1., slo_viol_rate=0.)]*20}}})
    p = tmp_path/'fixture'/'artifact.json'
    p.parent.mkdir()
    D.SPEC.clear(); D.SPEC.update(spec['policy'])
    p.write_text(json.dumps(x))
    D.artifact(t, root=tmp_path)
    x[field] = bad
    p.write_text(json.dumps(x))
    with pytest.raises(LabError):
        D.artifact(t, root=tmp_path)


def test_selection_ties_without_opus_c0():
    B = _load('build_w')
    spec = B.build(('opus', 'astra'))
    assert 'config c0 first, then lane opus before astra' in spec['policy']['selection']
    values = {t['name']: 0. for t in spec['tasks'] if t['stage'] == 'W'}
    for t in spec['tasks']:
        if t['arm'] == 'v2' and (t['config'] == 'c1' or t['lane'] == 'astra'):
            values[t['name']] = 1.
    winner = B.select_w(spec, values)['v2']
    assert (winner['lane'], winner['config']) == ('astra', 'c0')
    for t in spec['tasks']:
        if t['arm'] == 'v2' and t['config'] == 'c0':
            values[t['name']] = 0.
    winner = B.select_w(spec, values)['v2']
    assert (winner['lane'], winner['config']) == ('opus', 'c1')


def test_measured_reservations_and_dependency_are_frozen():
    B, D = _load('build_w'), _load('driver')
    draft = B.build()
    measured = B.build(pilots=_pilot_fixture(draft))
    assert 'tools/c345/build_w.py' in measured['runtime_sha256']
    measured['tasks'][0]['reserve_cpu_h'] += .01
    with pytest.raises(Exception, match='measured pilot caps'):
        D.validate(measured, protected=False)
    draft['policy']['launch_ready'] = True
    with pytest.raises(Exception, match='invalid pilot timing gate'):
        D.validate(draft, protected=False)
