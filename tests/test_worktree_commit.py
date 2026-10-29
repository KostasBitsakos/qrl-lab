"""Real Git integration checks for claim-scoped commits (no research runs)."""
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from work import LabError, git_commit, commit_scope, Work
import sqlite3


def git(repo, *args):
    return subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'lab'
    root.mkdir()
    (root / '.lab').mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 'test@example.invalid')
    for name in ('mine', 'other'):
        (root / name).write_text('base\n')
    git(root, 'add', 'mine', 'other')
    git(root, 'commit', '-qm', 'initial')
    git(root, 'worktree', 'add', '-qb', 'worker', str(root / 'wt'))
    return root


@pytest.mark.parametrize('worktree', [None, 'wt'])
def test_scoped_commit_preserves_unrelated_index(repo, worktree):
    target = repo / worktree if worktree else repo
    (target / 'mine').write_text('owned\n')
    (target / 'other').write_text('staged other\n')
    git(target, 'add', 'other')
    before = git(target, 'ls-files', '--stage', 'other')
    (target / 'other').write_text('unstaged other\n')
    claim = 'wt/mine' if worktree else 'mine'
    result = git_commit(str(repo), [claim, '.lab/no-file'], 'scoped', worktree)
    assert result.returncode == 0, result.stderr
    assert git(target, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').strip() == 'mine'
    assert git(target, 'ls-files', '--stage', 'other') == before
    assert (target / 'other').read_text() == 'unstaged other\n'
    assert (repo / '.lab/git.lock').exists()
    assert not (target / '.lab/git.lock').exists() if worktree else True


def test_directory_literal_names_and_deletion(repo):
    wt = repo / 'wt'
    (wt / 'mine').unlink()
    (wt / 'dir').mkdir()
    (wt / 'dir/a[1]').write_text('literal')
    result = git_commit(str(repo), ['wt/mine', 'wt/dir'], 'delete and add', 'wt')
    assert result.returncode == 0, result.stderr
    assert set(git(wt, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()) == {'mine', 'dir/a[1]'}


@pytest.mark.parametrize('selection', ['..', 'alias', 'wt/subdir'])
def test_reject_bad_worktree(repo, selection):
    (repo / 'alias').symlink_to(repo.parent, target_is_directory=True)
    (repo / 'wt/subdir').mkdir()
    with pytest.raises(LabError):
        commit_scope(str(repo), ['wt/mine'], selection)


def test_no_claims_beneath_worktree(repo):
    with pytest.raises(LabError, match='no claims beneath'):
        git_commit(str(repo), ['mine', '.'], 'no', 'wt')


def test_reject_claim_and_file_symlink_escape(repo):
    (repo / 'wt/escape').symlink_to(repo.parent / 'outside')
    with pytest.raises(LabError, match='outside'):
        commit_scope(str(repo), ['../outside'], 'wt')
    with pytest.raises(LabError, match='outside'):
        commit_scope(str(repo), ['wt'], 'wt')


def test_root_never_stages_worktree_gitlink(repo):
    with pytest.raises(LabError, match='nested'):
        git_commit(str(repo), ['wt'], 'must fail')
    assert git(repo, 'ls-files', '--stage', 'wt') == ''


def test_staging_error_is_reported(repo):
    (repo / 'mine').write_text('change')
    actual = subprocess.run
    def failing(args, **kw):
        if args[:2] == ['git', 'add']:
            return subprocess.CompletedProcess(args, 128, '', 'index permission denied')
        return actual(args, **kw)
    with patch('work.subprocess.run', side_effect=failing):
        result = git_commit(str(repo), ['mine'], 'fails')
    assert result.returncode == 128
    assert result.stderr == 'index permission denied'
    assert 'nothing to commit' not in result.stdout


def test_overlapping_claims_are_rejected(repo):
    conn = sqlite3.connect(':memory:', isolation_level=None)
    conn.row_factory = sqlite3.Row
    board = Work(conn, str(repo))
    conn.execute("INSERT INTO jobs(id,status) VALUES ('J1','running'),('J2','running')")
    assert board.claim('J1', ['wt/dir']) == []
    assert board.claim('J2', ['wt/dir/file'])
    assert board.claim('J2', ['wt/mine']) == []


def test_unchanged_or_never_created_claim(repo):
    result = git_commit(str(repo), ['mine', 'never-created'], 'empty')
    assert result.returncode == 0
    assert 'nothing to commit' in result.stdout


def test_cli_maps_only_callers_claims(repo):
    script = str(Path(__file__).resolve().parents[1] / 'tools/work.py')
    env = dict(os.environ, QRL_JOB='Jtest', QRL_LAB_DIR=str(repo),
               QRL_DISPATCH_DB=str(repo / '.lab/dispatch.db'))
    def cli(*args):
        return subprocess.run([sys.executable, script, *args], env=env, cwd=repo,
                              capture_output=True, text=True)
    assert cli('claim', 'wt/mine', 'mine').returncode == 0
    (repo / 'wt/mine').write_text('worker change')
    (repo / 'mine').write_text('root change')
    (repo / 'wt/other').write_text('another job')
    git(repo / 'wt', 'add', 'other')
    result = cli('commit', '--worktree', 'wt', '-m', 'CLI scoped')
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(repo / 'wt', 'show', '--format=', '--name-only', 'HEAD').strip() == 'mine'
    assert git(repo / 'wt', 'diff', '--cached', '--name-only').strip() == 'other'
    assert git(repo, 'diff', '--name-only').strip() == 'mine'
