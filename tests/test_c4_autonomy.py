"""Scoped authorization tests; fake lab only, no experiment processes."""
import datetime as dt
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import c4_autonomy as A
import launch_run as L
from labdb import LabDB, LabError, canonical_hash

AT = dt.datetime.fromisoformat('2026-11-11T01:00+02:00')


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv('QRL_LAB_DIR', str(tmp_path))
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/c4_auto_approve.json').write_text(json.dumps({'auto_approve': {
        'scope': 'c4-sim', 'paths': A.PATHS, 'until': A.UNTIL.isoformat()}}))
    (tmp_path / 'code-poisson-c4').mkdir()
    p = tmp_path / '.lab/c4/timing.json'
    p.parent.mkdir(parents=True)
    spec = {'name': 'c4-timing', 'scope': 'sim', 'cwd': 'code-poisson-c4',
            'entries': [{'cmd': [str(tmp_path / '.venv/bin/python'), '-m', 'tuning.c4_train',
                                 '--out', 'tuning/results/timing.json']}],
            'limits': {'wall_clock_hours': 2}}
    p.write_text(json.dumps(spec))
    return tmp_path, p, spec


def test_frozen_hash_and_expiry(lab):
    root, p, spec = lab
    auth, frozen = A.authorize(root, p, AT)
    assert auth['spec_hash'] == canonical_hash(spec)
    assert frozen == spec
    assert json.loads(Path(auth['spec_path']).read_text()) == spec
    assert A.authorize(root, p, AT)[0]['id'] == auth['id']
    with pytest.raises(LabError, match='expired'):
        A.authorize(root, p, A.UNTIL)
    with pytest.raises(LabError, match='expired'):
        A.authorize(root, p, A.UNTIL + dt.timedelta(seconds=1))
    f = Path(auth['spec_path'])
    f.chmod(0o644)
    f.write_text('{}')
    with pytest.raises(LabError, match='hash mismatch'):
        A.authorize(root, p, AT)


@pytest.mark.parametrize('change', ['real', 'qpu', 'cwd', 'shell', 'binary', 'test', 'out', 'init', 'kind', 'abbrev', 'equals', 'config', 'env'])
def test_reject_out_of_scope(lab, change):
    root, p, spec = lab
    cmd = spec['entries'][0]['cmd']
    if change in ('real', 'qpu'):
        spec['scope'] = change
        spec['real'] = dict(kube_context='no', namespace='no', rollback='no')
    elif change == 'cwd':
        spec['cwd'] = 'code-poisson-c345'
    elif change == 'shell':
        cmd[:] = ['bash', '-c', 'true']
    elif change == 'binary':
        cmd[:] = ['kubectl', 'get', 'pods']
    elif change == 'test':
        cmd += ['--split', 'test13']
    elif change == 'out':
        cmd[-1] = '../../outside.json'
    elif change == 'init':
        cmd += ['--set', 'init_from="../../other.pt"']
    elif change == 'abbrev':
        cmd[-2] = '--ou'
    elif change == 'equals':
        cmd[-2:] = ['--out=/outside.json']
    elif change == 'config':
        cmd += ['--config', '../../outside.json']
    elif change == 'env':
        spec['env_threads'] = {'PYTHONPATH': '../code-poisson-c345'}
    elif change == 'kind':
        spec['kind'] = 'sandbox'
    p.write_text(json.dumps(spec))
    with pytest.raises(LabError):
        A.authorize(root, p, AT)


def test_path_escape_and_symlink(lab):
    root, p, spec = lab
    outside = root / 'outside.json'
    outside.write_text(json.dumps(spec))
    with pytest.raises(LabError, match='path outside'):
        A.authorize(root, outside, AT)
    link = p.parent / 'link.json'
    link.symlink_to(outside)
    with pytest.raises(LabError, match='path outside'):
        A.authorize(root, link, AT)


def test_audit_attempt_hash_and_supervision_expiry(lab, monkeypatch):
    root, p, spec = lab
    auth = A.authorize(root, p, AT)
    db = LabDB()
    spawn = Mock()
    monkeypatch.setattr(L.subprocess, 'Popen', spawn)
    monkeypatch.setattr(L, 'git_sha', lambda _: 'fake-sha')
    rid = L.start_entry(db, auth[0]['id'], 0, auth)
    row = db.run(rid)
    assert row['spec_hash'] == canonical_hash(spec)
    meta = json.loads((Path(row['run_dir']) / 'spec_entry.json').read_text())
    assert dt.datetime.fromisoformat(meta['envelope_expires']) == A.UNTIL
    audit = db.conn.execute("SELECT * FROM audit WHERE action='auto-approve'").fetchone()
    assert json.loads(audit['detail'])['spec_hash'] == row['spec_hash']
    assert not db.requests()  # no card or researcher decision fabricated
    assert spawn.call_count == 1
    with pytest.raises(LabError, match='max_parallel'):
        L.start_entry(db, auth[0]['id'], 0, auth)


def test_ordinary_request_still_requires_approval(lab):
    db = LabDB()
    with pytest.raises(LabError, match='Unknown request'):
        L.load_approved_spec(db, 'no-request')


def test_changed_policy_cannot_extend_authorization(lab):
    root, p, spec = lab
    config = root / 'config/c4_auto_approve.json'
    c = json.loads(config.read_text())
    c['auto_approve']['until'] = '2026-11-14T00:00+02:00'
    config.write_text(json.dumps(c))
    with pytest.raises(LabError, match='Invalid'):
        A.authorize(root, p, AT)


def test_worktree_root_symlink_rejected(lab):
    root, p, spec = lab
    wt = root / 'code-poisson-c4'
    wt.rmdir()
    other = root / 'code-poisson-c345'
    other.mkdir()
    wt.symlink_to(other, target_is_directory=True)
    with pytest.raises(LabError, match='symlinks'):
        A.authorize(root, p, AT)


def test_existing_outputs_are_preserved(lab):
    root, p, spec = lab
    output = root / 'code-poisson-c4/tuning/results/timing.json'
    output.parent.mkdir(parents=True)
    output.write_text('preserve')
    with pytest.raises(LabError, match='overwrite'):
        A.authorize(root, p, AT, entry=0)
    assert output.read_text() == 'preserve'


def test_later_batch_entry_starts_after_prior_output(lab, monkeypatch):
    root, p, spec = lab
    import copy
    second = copy.deepcopy(spec['entries'][0])
    second['cmd'][-1] = 'tuning/results/second.json'
    spec['entries'].append(second)
    p.write_text(json.dumps(spec))
    auth = A.authorize(root, p, AT, entry=0)
    output = root / 'code-poisson-c4/tuning/results/timing.json'
    output.parent.mkdir(parents=True)
    output.write_text('prior completed result')
    auth2 = A.authorize(root, p, AT, entry=1)
    assert auth[0]['id'] == auth2[0]['id']
    db = LabDB()
    monkeypatch.setattr(L.subprocess, 'Popen', Mock())
    monkeypatch.setattr(L, 'git_sha', lambda _: 'fake-sha')
    run_id = L.start_entry(db, auth2[0]['id'], 1, auth2)
    assert db.run(run_id)['entry'] == 1
    assert output.read_text() == 'prior completed result'
    with pytest.raises(LabError, match='overwrite'):
        L.start_entry(db, auth[0]['id'], 0, auth)
