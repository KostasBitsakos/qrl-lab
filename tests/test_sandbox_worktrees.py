"""Second tuning worktree in tools/sandbox_guard.py (C-20261021-03): WORKTREES 'code' -> code-tuning and
'code-astra' -> code-tuning-astra, each with the sandbox-branch check, and commands confined to the sandbox's own
worktree. Builds throw-away git repos in a temp dir; never touches the real worktrees.
Run: .venv/bin/python -m pytest tests/test_sandbox_worktrees.py"""
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import sandbox_guard as G  # noqa: E402
from labdb import LabError  # noqa: E402


def _repo(path, branch):
    os.makedirs(path)
    subprocess.run(["git", "-C", path, "init", "-q", "-b", branch], check=True)
    open(os.path.join(path, "toy.py"), "w").write("print(1)\n")
    subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"],
                   check=True)


@pytest.fixture
def root():
    with tempfile.TemporaryDirectory() as d:
        _repo(os.path.join(d, "code-tuning"), "dinos-tuning")
        _repo(os.path.join(d, "code-tuning-astra"), "dinos-tuning-astra")
        yield d


def test_worktree_map():
    assert G.WORKTREES == {"code": "code-tuning", "code-astra": "code-tuning-astra",
                           "code-poisson": "code-poisson", "code-poisson-astra": "code-poisson-astra",
                           "code-poisson-spiky": "code-poisson-spiky"}


def test_paths_and_branch_check(root):
    sb1 = {"repo": "code", "branch": "dinos-tuning"}
    sb2 = {"repo": "code-astra", "branch": "dinos-tuning-astra"}
    assert G.worktree_path(sb2, root) == os.path.realpath(os.path.join(root, "code-tuning-astra"))
    assert G.resolve_cwd("code-astra", sb2, root) == os.path.realpath(os.path.join(root, "code-tuning-astra"))
    assert G.resolve_cwd("code", sb1, root) == os.path.realpath(os.path.join(root, "code-tuning"))
    with pytest.raises(LabError, match="not on branch"):          # astra worktree, wrong sandbox branch
        G.resolve_cwd("code-astra", dict(sb2, branch="dinos-tuning"), root)
    with pytest.raises(LabError, match="not on branch"):
        G.resolve_cwd("code", dict(sb1, branch="dinos-tuning-astra"), root)
    with pytest.raises(LabError, match="no tuning worktree"):
        G.worktree_path({"repo": "code-x", "branch": "b"}, root)


def test_commands_confined_to_own_worktree(root):
    a = os.path.join(root, "code-tuning-astra")
    c = os.path.join(root, "code-tuning")
    py = os.path.join(root, ".venv", "bin", "python")
    assert G.check_cmd([py, "toy.py"], a, root, a) == os.path.realpath(os.path.join(a, "toy.py"))
    with pytest.raises(LabError, match="not a file inside"):     # astra sandbox may not run code-tuning scripts
        G.check_cmd([py, "../code-tuning/toy.py"], a, root, a)
    with pytest.raises(LabError, match="not a file inside"):
        G.check_cmd([py, "../code-tuning-astra/toy.py"], c, root, c)
    assert G.check_cmd([py, "toy.py"], c, root) == os.path.realpath(os.path.join(c, "toy.py"))   # default = code


def test_missing_worktree_refused():
    with tempfile.TemporaryDirectory() as d:
        _repo(os.path.join(d, "code-tuning"), "dinos-tuning")
        with pytest.raises(LabError, match="does not exist"):
            G.resolve_cwd("code-astra", {"repo": "code-astra", "branch": "dinos-tuning-astra"}, d)
