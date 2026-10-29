"""Cycle2 guard and aggregate reservations; temporary repos/DB, no experiments or supervisor."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import sandbox_guard as G
import launch_run as L
from labdb import LabDB, LabError


def git(wt, *args):
    return subprocess.check_output(['git', '-C', str(wt), '-c', 'user.name=test',
                                    '-c', 'user.email=test@example.invalid', *args], text=True).strip()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    # Two branches share one committed frozen environment. Never touch real code repos.
    wt = tmp_path / 'code-poisson'
    wt.mkdir()
    git(wt, 'init', '-q', '-b', 'dinos-poisson')
    for rel in G.PROTECTED_FILES + G.CYCLE2_HARNESS_FILES + (G.CYCLE2_ENTRY_FILE, 'tuning/poisson_ms.py', 'sim_v2/policies.py', 'toy.py'):
        p = wt / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('# fixture\n')
    git(wt, 'add', '.')
    git(wt, 'commit', '-qm', 'frozen fixture')
    sha = git(wt, 'rev-parse', 'HEAD')
    git(wt, 'tag', '-a', 'cycle2-env-v1', '-m', 'fixture')
    git(wt, 'worktree', 'add', '-qb', 'dinos-poisson-astra', str(tmp_path / 'code-poisson-astra'))
    monkeypatch.setattr(G, 'CYCLE2_ENV_COMMIT', sha)
    monkeypatch.setattr(G, 'CYCLE2_HARNESS_COMMIT', sha)
    monkeypatch.setattr(G, 'CYCLE2_ENTRY_SHA256', G._sha(b'# fixture\n'))
    monkeypatch.setenv('QRL_LAB_DIR', str(tmp_path))
    monkeypatch.setattr(L, 'subprocess', SimpleNamespace(**(vars(subprocess) | {'Popen': lambda *a, **kw: None})))
    monkeypatch.setattr(L.os, 'sched_getaffinity', lambda pid: set(range(8, 40)))
    sb = dict(worktrees=[dict(repo=r, branch=b) for r, b in G.CYCLE2_BRANCHES.items()],
              frozen_env_commit=sha, frozen_harness_commit=sha, frozen_entry_sha256=G.CYCLE2_ENTRY_SHA256,
              cpu_hours_budget=1.0, max_parallel=4,
              seed_ranges_allowed=[[100, 119]], seed_ranges_forbidden=[], cpu_affinity='8-39',
              per_run_wall_clock_hours=1.0,
              expires=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat())
    parent = dict(name='aggregate', kind='sandbox', scope='sim', cwd='code-poisson', sandbox=sb,
                  entries=[dict(cmd=['true'])], limits=dict(wall_clock_hours=1))
    db = LabDB()
    rid = db.ask('approval', 'aggregate fixture', 'fixture', scope='sim', spec=parent)
    # Test-only approval in isolated temp database.
    db.decide(rid, 'approve')
    yield tmp_path, parent, db, rid
    db.close()


def child(repo='code-poisson', hours=0.6):
    return dict(name='fixture', scope='sim', repo=repo, cwd=repo,
                entries=[dict(seed=100, cpus=1, wall_clock_hours=hours, cmd=['python3', 'toy.py'])])


@pytest.mark.parametrize('repo', list(G.CYCLE2_BRANCHES))
def test_both_branches_and_frozen_content(setup, repo):
    root, parent, db, rid = setup
    c = child(repo)
    cwd, plan = G.check_child(c, parent, root=str(root))
    assert cwd == str(root / repo)
    sb = G.select_worktree(parent['sandbox'], c)
    G.verify_sandbox_protected(sb, str(root))
    assert plan[0]['reserve_cpu_h'] == .6
    p = root / repo / 'tuning/poisson_ms.py'
    p.write_text('# dirty\n')
    with pytest.raises(LabError, match='Protected file'):
        L.start_sandbox(db, rid, c)
    p.unlink()
    with pytest.raises(LabError, match='Protected file'):
        L.start_sandbox(db, rid, c)
    assert db.runs() == []


def test_wrong_branch_reference_and_escape(setup, monkeypatch):
    root, parent, db, rid = setup
    p = copy.deepcopy(parent)
    p['sandbox']['worktrees'][0]['branch'] = 'dinos-tuning'
    with pytest.raises(LabError, match='branch binding'):
        G.check_child(child(), p)
    git(root / 'code-poisson', 'checkout', '-qb', 'wrong')
    with pytest.raises(LabError, match='not on branch'):
        G.check_child(child(), parent)
    git(root / 'code-poisson', 'checkout', '-q', 'dinos-poisson')
    p = copy.deepcopy(parent)
    del p['sandbox']['frozen_env_commit']
    with pytest.raises(LabError, match='frozen_env_commit'):
        G.check_child(child(), p)
    c = child(); c['entries'][0]['cmd'][1] = '../code-poisson-astra/toy.py'
    with pytest.raises(LabError, match='not a file inside'):
        G.check_child(c, parent)
    c = child(); del c['repo']
    with pytest.raises(LabError, match='select one'):
        G.check_child(c, parent)
    # Valid working bytes but reviewed git blob is absent.
    selected = G.select_worktree(parent['sandbox'], child())
    monkeypatch.setattr(G, 'CYCLE2_ENV_COMMIT', '0' * 40)
    with pytest.raises(LabError, match='Protected file'):
        G.verify_sandbox_protected(selected, str(root))


def test_combined_budget_and_metadata(setup):
    root, parent, db, rid = setup
    a = L.start_sandbox(db, rid, child())[0]
    with pytest.raises(LabError, match='Budget'):
        L.start_sandbox(db, rid, child('code-poisson-astra'))
    b = L.start_sandbox(db, rid, child('code-poisson-astra', .4))[0]
    assert G.used_cpu_hours(db, rid, strict=True) == 1
    assert L.sandbox_status(db, rid)['cpu_hours_left'] == 0
    metas = [json.loads((Path(db.run(r)['run_dir']) / 'spec_entry.json').read_text()) for r in (a, b)]
    assert {m['sandbox']['branch'] for m in metas} == set(G.CYCLE2_BRANCHES.values())
    assert not set(metas[0]['sandbox']['cores']) & set(metas[1]['sandbox']['cores'])
    (Path(db.run(a)['run_dir']) / 'spec_entry.json').unlink()
    with pytest.raises(LabError, match='accounting'):
        L.start_sandbox(db, rid, child(hours=.01))


def test_concurrent_reservations(setup):
    root, parent, db, rid = setup
    barrier = Barrier(2)
    def reserve(repo):
        conn = LabDB(db.path)
        barrier.wait(timeout=10)
        try:
            return L.start_sandbox(conn, rid, child(repo))
        except LabError as e:
            return str(e)
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, G.CYCLE2_BRANCHES))
    assert sum(isinstance(x, list) for x in results) == 1, results
    assert sum(isinstance(x, str) and 'Budget' in x for x in results) == 1, results
    assert len(db.runs()) == 1
    assert G.used_cpu_hours(db, rid, strict=True) == .6


def test_expiry_legacy_and_no_direct_start(setup):
    root, parent, db, rid = setup
    with pytest.raises(LabError, match='sandbox-start'):
        L.start_entry(db, rid, 0)
    p = copy.deepcopy(parent)
    p['sandbox']['expires'] = '2000-01-01T00:00:00+00:00'
    with pytest.raises(LabError, match='expired'):
        G.check_child(child(), p)
    p = copy.deepcopy(parent)
    p['sandbox']['cpu_hours_budget'] = float('inf')
    with pytest.raises(LabError, match='Non-finite'):
        G.check_child(child(), p)
    for value in (0, 161, True):
        p['sandbox']['cpu_hours_budget'] = value
        with pytest.raises(LabError, match='cpu_hours_budget'):
            G.check_child(child(), p)
    # Existing single-worktree parents retain exactly their old branch selection.
    legacy = dict(repo='code', branch='dinos-tuning')
    assert G.select_worktree(legacy, {}) == legacy
    with pytest.raises(LabError, match='aggregate'):
        G.select_worktree(dict(repo='code-poisson', branch='dinos-poisson'), child())


def test_finished_cost_unknown_failure_and_shared_parallel_cap(setup):
    root, parent, db, rid = setup
    run = L.start_sandbox(db, rid, child())[0]
    # Charge measured elapsed wall * reserved cores, the existing conservative metric.
    db.conn.execute("UPDATE runs SET status='done', started=?, ended=? WHERE run_id=?",
                    ('2026-01-01T00:00:00+00:00', '2026-01-01T00:30:00+00:00', run))
    assert G.used_cpu_hours(db, rid, strict=True) == .5
    with pytest.raises(LabError, match='Budget'):
        L.start_sandbox(db, rid, child('code-poisson-astra'))
    db.conn.execute("UPDATE runs SET status='failed', started=NULL, ended=NULL WHERE run_id=?", (run,))
    assert G.used_cpu_hours(db, rid, strict=True) == .6
    # A second parent with max_parallel=1 shares its cap across the branches.
    p = copy.deepcopy(parent)
    p['sandbox']['max_parallel'] = 1
    rid2 = db.ask('approval', 'parallel fixture', 'fixture', scope='sim', spec=p)
    db.decide(rid2, 'approve')
    L.start_sandbox(db, rid2, child(hours=.1))
    with pytest.raises(LabError, match='max_parallel'):
        L.start_sandbox(db, rid2, child('code-poisson-astra', .1))


def test_extra_module_dirty_common_module_and_spawn_recheck(setup, monkeypatch):
    root, parent, db, rid = setup
    wt = root / 'code-poisson'
    module = wt / 'sim_v2/policies.py'
    original = module.read_text()
    module.write_text('# changed policies\n')
    with pytest.raises(LabError, match='Protected file'):
        L.start_sandbox(db, rid, child())
    module.write_text(original)
    extra = wt / 'sim_v2/numpy.py'
    extra.write_text('# unreviewed\n')
    with pytest.raises(LabError, match='Unreviewed protected'):
        L.start_sandbox(db, rid, child())
    extra.unlink()
    run = L.start_sandbox(db, rid, child())[0]
    module.write_text('# changed after reservation\n')
    # Supervisor must fail before calling Popen. Fixture already mocks supervisor spawns.
    monkeypatch.setattr(L, 'LabDB', lambda: db)
    def forbidden_spawn(*args, **kwargs):
        raise AssertionError('must refuse before Popen')
    monkeypatch.setattr(L.subprocess, 'Popen', forbidden_spawn)
    L.supervise(run)
    assert db.run(run)['status'] == 'failed'
    assert 'Protected file' in (Path(db.run(run)['run_dir']) / 'output.log').read_text()


@pytest.mark.parametrize('rel', G.CYCLE2_HARNESS_FILES)
def test_harness_files_pinned(setup, monkeypatch, rel):
    root, parent, db, rid = setup
    p = root / 'code-poisson-astra' / rel
    original = p.read_text()
    p.write_text('# branch-local harness edit\n')
    with pytest.raises(LabError, match='Protected file'):
        L.start_sandbox(db, rid, child('code-poisson-astra'))
    p.write_text(original)
    monkeypatch.setattr(G, 'CYCLE2_HARNESS_COMMIT', '0' * 40)
    with pytest.raises(LabError, match='frozen_harness_commit'):
        L.start_sandbox(db, rid, child('code-poisson-astra'))


@pytest.mark.parametrize('repo', list(G.CYCLE2_BRANCHES))
@pytest.mark.parametrize('mutation', ['changed', 'missing'])
def test_entry_wrapper_pinned(setup, repo, mutation):
    root, parent, db, rid = setup
    sb = G.select_worktree(parent['sandbox'], child(repo))
    G.verify_sandbox_protected(sb, str(root))
    wrapper = root / repo / G.CYCLE2_ENTRY_FILE
    if mutation == 'changed':
        wrapper.write_text('# unreviewed dispatch\n')
    else:
        wrapper.unlink()
    with pytest.raises(LabError, match='Protected wrapper'):
        L.start_sandbox(db, rid, child(repo))
    assert not db.runs(), 'wrapper refusal must precede reservation'


@pytest.mark.parametrize('value', [None, '0' * 64])
def test_entry_parent_pin_required(setup, value):
    root, parent, db, rid = setup
    if value is None:
        del parent['sandbox']['frozen_entry_sha256']
    else:
        parent['sandbox']['frozen_entry_sha256'] = value
    with pytest.raises(LabError, match='frozen_entry_sha256'):
        G.check_child(child(), parent, str(root))


def test_entry_wrapper_supervisor_recheck(setup, monkeypatch):
    root, parent, db, rid = setup
    run = L.start_sandbox(db, rid, child())[0]
    (root / 'code-poisson' / G.CYCLE2_ENTRY_FILE).write_text('# post-reservation edit\n')
    monkeypatch.setattr(L, 'LabDB', lambda: db)
    def forbidden_spawn(*args, **kwargs):
        raise AssertionError('must refuse changed wrapper before Popen')
    monkeypatch.setattr(L.subprocess, 'Popen', forbidden_spawn)
    L.supervise(run)
    assert db.run(run)['status'] == 'failed'
    assert 'Protected wrapper' in (Path(db.run(run)['run_dir']) / 'output.log').read_text()
