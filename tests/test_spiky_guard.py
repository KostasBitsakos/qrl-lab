"""Engineering checks only: guard admission, no payload execution."""
import copy
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'tools/spiky_stage1'))
import sandbox_guard as G
import build
from labdb import LabError, canonical_hash


def test_frozen_spiky_content():
    p=build.build(); c=p['tasks'][0]['child']
    G.check_child(c,p)
    G.verify_sandbox_protected(G.select_worktree(p['sandbox'],c),ROOT)


@pytest.mark.parametrize('field,value',[('frozen_env_commit',G.CYCLE2_ENV_COMMIT),
    ('frozen_harness_commit',G.CYCLE2_HARNESS_COMMIT),('frozen_entry_sha256','0'*64)])
def test_old_profile_rejected(field,value):
    p=build.build(); p['sandbox'][field]=value
    with pytest.raises(LabError): G.check_child(p['tasks'][0]['child'],p)


def test_exact_child_not_arbitrary_code():
    p=build.build(); c=copy.deepcopy(p['tasks'][1]['child'])
    c['entries'][0]['cmd'] += ['--n-step','1']
    with pytest.raises(LabError,match='frozen Stage1'): G.check_child(c,p)


def test_forbidden_even_if_whitelisted():
    p=build.build(); c=copy.deepcopy(p['tasks'][1]['child']); c['entries'][0]['seed']=16500
    i=c['entries'][0]['cmd'].index('--seed'); c['entries'][0]['cmd'][i+1]='16500'
    p['sandbox']['allowed_children'].append(canonical_hash(c))
    with pytest.raises(LabError,match='seed'): G.check_child(c,p)


def test_legacy_profile_unchanged():
    p=build.build()['sandbox']; p['worktrees']=[dict(repo='code-poisson',branch='dinos-poisson')]
    p.update(frozen_env_commit=G.CYCLE2_ENV_COMMIT,frozen_harness_commit=G.CYCLE2_HARNESS_COMMIT,
             frozen_entry_sha256=G.CYCLE2_ENTRY_SHA256)
    s=G.select_worktree(p,dict(repo='code-poisson'))
    assert G.profile(s)==(G.CYCLE2_ENV_COMMIT,G.CYCLE2_HARNESS_COMMIT,G.CYCLE2_ENTRY_SHA256)


def test_changed_tuning_import_rejected(tmp_path):
    # Fake git data, actual working copies: both matching positive control and corrupt negative.
    import subprocess
    wt=tmp_path/'code-poisson-spiky'; wt.mkdir()
    def git(*a): return subprocess.check_output(['git','-C',str(wt),*a],text=True).strip()
    git('init','-q','-b','dinos-poisson-spiky')
    for rel in set(G.PROTECTED_FILES+G.CYCLE2_HARNESS_FILES+(G.CYCLE2_ENTRY_FILE,'tuning/poisson_ms.py','tuning/legacy/agent_lstm_v2.py')):
        p=wt/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# frozen\n')
    git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
    sha=git('rev-parse','HEAD')
    from unittest.mock import patch
    sb=dict(repo=G.SPIKY_REPO,branch='dinos-poisson-spiky')
    with patch.object(G,'SPIKY_ENV_COMMIT',sha),patch.object(G,'SPIKY_HARNESS_COMMIT',sha),patch.object(G,'SPIKY_ENTRY_SHA256',G._sha(b'# frozen\n')):
        G.verify_sandbox_protected(sb,tmp_path)
        (wt/'tuning/legacy/agent_lstm_v2.py').write_text('# changed\n')
        with pytest.raises(LabError,match='Protected file'):G.verify_sandbox_protected(sb,tmp_path)
        (wt/'tuning/legacy/agent_lstm_v2.py').write_text('# frozen\n')
        (wt/'tuning/unreviewed.py').write_text('# extra\n')
        with pytest.raises(LabError,match='Unreviewed spiky'):G.verify_sandbox_protected(sb,tmp_path)
