"""Frozen amendments: temporary DB/repos, fake supervisors; no experiment processes."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from test_cycle2_sandbox import setup, child
import sandbox_guard as G
import launch_run as L
from labdb import LabDB, LabError, validate_spec


def proposal(db, rid, budget=.9):
    return dict(kind='sandbox-amendment', name='test amendment', scope='sim',
                parent_request=rid, parent_spec_hash=db.request(rid)['spec_hash'],
                changes=dict(per_run_wall_clock_hours=2.5, cpu_hours_budget=budget),
                review=dict(source='isolated test'))


def approve(db, spec):
    aid = db.ask('approval', 'amendment fixture', 'fixture', scope='sim', spec=spec)
    db.decide(aid, 'approve')
    return aid


def test_no_approval_or_specless_authority(setup):
    root, parent, db, rid = setup
    aid = db.ask('approval', 'pending', 'fixture', scope='sim', spec=proposal(db, rid))
    with pytest.raises(LabError, match='not approved'):
        L.activate_sandbox_amendment(db, rid, aid)
    choice = db.ask('question', 'policy only', 'fixture', scope='sim')
    with pytest.raises(LabError, match='not an approval'):
        L.activate_sandbox_amendment(db, rid, choice)
    no_spec = db.ask('approval', 'no spec', 'fixture', scope='sim')
    db.decide(no_spec, 'approve')
    with pytest.raises(LabError, match='no run spec'):
        L.activate_sandbox_amendment(db, rid, no_spec)
    assert db.runs() == []


@pytest.mark.parametrize('mutation', ['parent', 'parent_hash', 'budget', 'expiry', 'pins', 'seeds', 'parallel', 'cap', 'bool', 'nan'])
def test_unapproved_relaxations(setup, mutation):
    root, parent, db, rid = setup
    spec = proposal(db, rid)
    if mutation == 'parent': spec['parent_request'] = 'R-other'
    elif mutation == 'parent_hash': spec['parent_spec_hash'] = '0' * 64
    elif mutation == 'budget': spec['changes']['cpu_hours_budget'] = 2
    elif mutation == 'cap': spec['changes']['per_run_wall_clock_hours'] = 2.51
    elif mutation == 'bool': spec['changes']['cpu_hours_budget'] = True
    elif mutation == 'nan': spec['changes']['cpu_hours_budget'] = float('nan')
    else: spec['changes'][mutation] = 'unauthorized'
    with pytest.raises(LabError):
        aid = approve(db, spec)
        L.activate_sandbox_amendment(db, rid, aid)
    assert db.conn.execute("SELECT count(*) FROM audit WHERE action='sandbox-amendment'").fetchone()[0] == 0


def test_immutable_parent_provenance_and_no_direct_execution(setup):
    root, parent, db, rid = setup
    before = dict(db.request(rid))
    parent_bytes = Path(before['spec_path']).read_bytes()
    aid = approve(db, proposal(db, rid))
    with pytest.raises(LabError, match='sandbox-start'):
        L.start_entry(db, aid, 0)
    with pytest.raises(LabError, match='not a sandbox'):
        L.start_sandbox(db, aid, child())
    L.activate_sandbox_amendment(db, rid, aid)
    assert dict(db.request(rid)) == before
    assert Path(before['spec_path']).read_bytes() == parent_bytes
    _, effective = L.load_sandbox(db, rid)
    expected = copy.deepcopy(parent)
    expected['sandbox'].update(proposal(db, rid)['changes'])
    assert effective == expected
    assert parent['sandbox']['per_run_wall_clock_hours'] == 1
    with pytest.raises(LabError, match='already has'):
        L.activate_sandbox_amendment(db, rid, aid)
    assert L.sandbox_status(db, rid)['budget'] == .9


def test_amendment_hash_tamper_rejected_before_and_after_activation(setup):
    root, parent, db, rid = setup
    aid = approve(db, proposal(db, rid))
    p = Path(db.request(aid)['spec_path'])
    old = p.read_text()
    # Temp fixture only: simulate filesystem tampering of frozen bytes.
    p.chmod(0o600)
    p.write_text(old.replace('test amendment', 'changed name'))
    with pytest.raises(LabError, match='changed after approval'):
        L.activate_sandbox_amendment(db, rid, aid)
    p.write_text(old)
    L.activate_sandbox_amendment(db, rid, aid)
    p.write_text(old.replace('test amendment', 'changed name'))
    with pytest.raises(LabError, match='changed after approval'):
        L.start_sandbox(db, rid, child())
    assert db.runs() == []


@pytest.mark.parametrize('status', ['starting', 'running'])
def test_activation_refuses_active_and_preserves_reservation(setup, status):
    root, parent, db, rid = setup
    run = L.start_sandbox(db, rid, child())[0]
    db.conn.execute('UPDATE runs SET status=? WHERE run_id=?', (status, run))
    before = Path(db.run(run)['run_dir'], 'spec_entry.json').read_bytes()
    aid = approve(db, proposal(db, rid))
    with pytest.raises(LabError, match='starting/running'):
        L.activate_sandbox_amendment(db, rid, aid)
    assert G.used_cpu_hours(db, rid, strict=True) == .6
    assert Path(db.run(run)['run_dir'], 'spec_entry.json').read_bytes() == before


def test_consumed_unknown_cost_and_reservations_stay_on_parent(setup):
    root, parent, db, rid = setup
    a = L.start_sandbox(db, rid, child(hours=.2))[0]
    db.conn.execute("UPDATE runs SET status='done', started=?,ended=? WHERE run_id=?",
                    ('2026-01-01T00:00:00+00:00', '2026-01-01T00:12:00+00:00', a))
    b = L.start_sandbox(db, rid, child(hours=.1))[0]
    db.conn.execute("UPDATE runs SET status='failed' WHERE run_id=?", (b,))
    aid = approve(db, proposal(db, rid, .8))
    L.activate_sandbox_amendment(db, rid, aid)
    assert G.used_cpu_hours(db, rid, strict=True) == pytest.approx(.3)
    L.start_sandbox(db, rid, child(hours=.4))
    assert G.used_cpu_hours(db, rid, strict=True) == pytest.approx(.7)
    with pytest.raises(LabError, match='Budget'):
        L.start_sandbox(db, rid, child(hours=.2))
    assert {r['request_id'] for r in db.runs()} == {rid}
    assert not [r for r in db.runs() if r['request_id'] == aid]
    assert L.sandbox_status(db, rid)['cpu_hours_used'] == .7


def test_higher_wall_cap_requires_activation_and_keeps_provenance(setup):
    root, parent, db, rid = setup
    p = copy.deepcopy(parent)
    p['sandbox']['cpu_hours_budget'] = 4
    rid = approve(db, p)
    with pytest.raises(LabError, match='wall_clock_hours'):
        L.start_sandbox(db, rid, child(hours=2.5))
    aid = approve(db, proposal(db, rid, 3))
    L.activate_sandbox_amendment(db, rid, aid)
    run = L.start_sandbox(db, rid, child(hours=2.5))[0]
    meta = json.loads(Path(db.run(run)['run_dir'], 'spec_entry.json').read_text())
    assert meta['limits']['wall_clock_hours'] == 2.5
    assert meta['sandbox']['reserve_cpu_h'] == 2.5
    assert meta['sandbox']['parent_spec_hash'] == db.request(rid)['spec_hash']
    assert meta['sandbox']['effective_sandbox_hash'] == L.canonical_hash(L.load_sandbox(db, rid)[1]['sandbox'])


def test_concurrent_activation_and_legacy_reservation_serialized(setup):
    root, parent, db, rid = setup
    aid = approve(db, proposal(db, rid, .5))
    barrier = Barrier(2)
    def operation(activate):
        conn = LabDB(db.path)
        barrier.wait(timeout=10)
        try:
            if activate:
                L.activate_sandbox_amendment(conn, rid, aid)
                return 'activated'
            L.start_sandbox(conn, rid, child(hours=.6))
            return 'reserved'
        except LabError as e:
            return str(e)
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation, (True, False)))
    assert ('activated' in results) != ('reserved' in results), results
    if 'activated' in results:
        assert any('Budget' in s for s in results)
        assert db.runs() == []
    else:
        assert any('starting/running' in s for s in results)
        assert len(db.runs()) == 1


def test_concurrent_amended_reservations_share_budget(setup):
    root, parent, db, rid = setup
    aid = approve(db, proposal(db, rid, .9))
    L.activate_sandbox_amendment(db, rid, aid)
    barrier = Barrier(2)
    def reserve(repo):
        conn = LabDB(db.path)
        barrier.wait(timeout=10)
        try:
            return L.start_sandbox(conn, rid, child(repo, .6))
        except LabError as e:
            return str(e)
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, G.CYCLE2_BRANCHES))
    assert sum(isinstance(r, list) for r in results) == 1
    assert sum(isinstance(r, str) and 'Budget' in r for r in results) == 1
    assert G.used_cpu_hours(db, rid, strict=True) == .6


def test_concurrent_double_activation_is_append_only(setup):
    root, parent, db, rid = setup
    aid = approve(db, proposal(db, rid))
    barrier = Barrier(2)
    def activate(_):
        conn = LabDB(db.path)
        barrier.wait(timeout=10)
        try:
            L.activate_sandbox_amendment(conn, rid, aid)
            return 'activated'
        except LabError as e:
            return str(e)
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate, (0, 1)))
    assert results.count('activated') == 1
    assert sum('already has' in r for r in results) == 1
    assert db.conn.execute("SELECT count(*) FROM audit WHERE action='sandbox-amendment'").fetchone()[0] == 1


@pytest.mark.parametrize('corruption', ['bad-json', 'wrong-parent', 'unknown-approval', 'wrong-hash', 'duplicate'])
def test_corrupt_activation_fails_closed(setup, corruption):
    root, parent, db, rid = setup
    aid = approve(db, proposal(db, rid))
    L.activate_sandbox_amendment(db, rid, aid)
    row = db.conn.execute("SELECT * FROM audit WHERE action='sandbox-amendment'").fetchone()
    binding = json.loads(row['detail'])
    if corruption == 'wrong-parent': binding['parent_spec_hash'] = '0' * 64
    elif corruption == 'unknown-approval': binding['request_id'] = 'R-unknown'
    elif corruption == 'wrong-hash': binding['spec_hash'] = '0' * 64
    if corruption == 'duplicate':
        db.conn.execute("INSERT INTO audit(ts,actor,action,target,detail) VALUES (?,?,?,?,?)",
                        (row['ts'], row['actor'], row['action'], rid, row['detail']))
    else:
        detail = 'invalid{' if corruption == 'bad-json' else json.dumps(binding)
        db.conn.execute('UPDATE audit SET detail=? WHERE id=?', (detail, row['id']))
    with pytest.raises(LabError): L.start_sandbox(db, rid, child())
    with pytest.raises(LabError): L.sandbox_status(db, rid)
    assert db.runs() == []


@pytest.mark.parametrize('failure', ['below-consumed', 'expired', 'protected', 'parent-hash', 'ceiling'])
def test_activation_failure_has_no_partial_record(setup, failure):
    root, parent, db, rid = setup
    if failure == 'below-consumed':
        run = L.start_sandbox(db, rid, child(hours=.6))[0]
        db.conn.execute("UPDATE runs SET status='failed' WHERE run_id=?", (run,))
    if failure == 'expired':
        parent = copy.deepcopy(parent)
        parent['sandbox']['expires'] = '2000-01-01T00:00:00+00:00'
        rid = approve(db, parent)
    spec = proposal(db, rid, .5)
    if failure == 'ceiling':
        spec['changes']['cpu_hours_budget'] = 137
        with pytest.raises(LabError, match='136'):
            validate_spec(spec)
        return
    aid = approve(db, spec)
    if failure == 'protected': (root / 'code-poisson/tuning/poisson_ms.py').write_text('# dirty\n')
    if failure == 'parent-hash':
        p = Path(db.request(rid)['spec_path'])
        p.chmod(0o600)
        p.write_text(p.read_text().replace('aggregate', 'changed'))
    with pytest.raises(LabError): L.activate_sandbox_amendment(db, rid, aid)
    assert db.conn.execute("SELECT count(*) FROM audit WHERE action='sandbox-amendment'").fetchone()[0] == 0


@pytest.mark.parametrize('scope', ['real', 'qpu'])
def test_non_sim_parent_refused(setup, scope):
    root, parent, db, rid = setup
    other = copy.deepcopy(parent)
    other['scope'] = scope
    with pytest.raises(LabError, match='sim sandbox'):
        G.apply_amendment(other, rid, db.request(rid)['spec_hash'], proposal(db, rid))


def test_amended_supervisor_refuses_tamper_before_process_spawn(setup, monkeypatch):
    root, parent, db, rid = setup
    aid = approve(db, proposal(db, rid))
    L.activate_sandbox_amendment(db, rid, aid)
    run = L.start_sandbox(db, rid, child(hours=.2))[0]
    meta = json.loads(Path(db.run(run)['run_dir'], 'spec_entry.json').read_text())
    assert meta['sandbox']['amendment_request_id'] == aid
    assert meta['sandbox']['amendment_spec_hash'] == db.request(aid)['spec_hash']
    p = Path(db.request(aid)['spec_path'])
    p.chmod(0o600)
    p.write_text(p.read_text().replace('test amendment', 'changed name'))
    monkeypatch.setattr(L, 'LabDB', lambda: db)
    def forbidden_spawn(*args, **kwargs):
        raise AssertionError('must refuse before Popen')
    monkeypatch.setattr(L.subprocess, 'Popen', forbidden_spawn)
    L.supervise(run)
    assert db.run(run)['status'] == 'failed'
    assert 'changed after approval' in Path(db.run(run)['run_dir'], 'output.log').read_text()
    assert G.used_cpu_hours(db, rid, strict=True) == .2
