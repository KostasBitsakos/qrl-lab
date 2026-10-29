import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import publish_release as pr  # noqa: E402


def test_tag_names():
    assert pr.TAG_RE.match("cycle2-claude-v1.0")
    assert pr.TAG_RE.match("cycle12-final-v2.3")
    for bad in ("main", "cycle2-claude", "v1.0", "cycle2-gpt-v1.0", "cycle2-claude-v1"):
        assert not pr.TAG_RE.match(bad)


def test_secret_patterns():
    for p in (".env", "a/.env.local", "id_rsa", "x/server.pem", "auth.json", "k/.kube/config"):
        assert pr.SECRET_RE.search(p), p
    for p in ("tuning/env.py", "docs/keys.md", "README.md", "environment.yml"):
        assert not pr.SECRET_RE.search(p), p


def test_review_needs_sha_and_both(tmp_path):
    sha = "a" * 40
    f = tmp_path / "r.md"
    f.write_text(f"commit {sha}\nclaude: APPROVE\n")
    with pytest.raises(SystemExit):
        pr.check_review(str(f), sha)
    f.write_text(f"commit {sha}\nclaude: APPROVE\ncodex: APPROVE r2\n")
    pr.check_review(str(f), sha)
    with pytest.raises(SystemExit):
        pr.check_review(str(f), "b" * 40)
    f.write_text(f"commit {sha}\nclaude: APPROVE\ncodex: CHANGE\n")
    with pytest.raises(SystemExit):
        pr.check_review(str(f), sha)


def test_remote_tag_never_moved(tmp_path, monkeypatch):
    sha = pr.resolve("HEAD")
    f = tmp_path / "r.md"
    f.write_text(f"{sha}\nclaude: APPROVE\ncodex: APPROVE\n")
    monkeypatch.setattr(pr, "check_secrets", lambda s: None)
    pushed = []
    monkeypatch.setattr(pr, "push", lambda spec, dry: pushed.append(spec))
    with pytest.raises(SystemExit):
        pr.publish_tag("cycle9-final-v1.0", sha, str(f), None, True, {"refs/tags/cycle9-final-v1.0": "0" * 40})
    pr.publish_tag("cycle9-final-v1.0", sha, str(f), None, True, {"refs/tags/cycle9-final-v1.0": sha})
    assert pushed == []
    pr.publish_tag("cycle9-final-v1.0", sha, str(f), None, True, {})
    assert pushed == ["refs/tags/cycle9-final-v1.0:refs/tags/cycle9-final-v1.0"]
