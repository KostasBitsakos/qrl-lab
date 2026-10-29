#!/usr/bin/env python3
"""Publish a jointly reviewed version to GitHub as an annotated tag (R-20261029-008).

Versions are tags (cycle<N>-claude-vX.Y, cycle<N>-codex-vX.Y, cycle<N>-final-vX.Y); only `main` is a branch and it
only moves fast-forward. Tags never create "Compare & pull" banners. Guards (R-20261029-002): remote `github` only,
never force, a review file with both `claude: APPROVE` and `codex: APPROVE` for the exact commit, no secret-looking
files in the tree, an existing remote tag is never moved.

Usage:
  publish_release.py tag  --tag cycle2-claude-v1.0 --commit <sha> --review <file> [-m msg] [--dry-run]
  publish_release.py main --commit <sha> --review <file> [--dry-run]
  publish_release.py retire-branch --branch cycle1-claude --tag cycle1-claude-v1.0 --review <file> [--dry-run]
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE = "github"
REPO_URLS = {"git@github.com:KostasBitsakos/dinos_sofia_k8s_redis_scaling.git",
             "https://github.com/KostasBitsakos/dinos_sofia_k8s_redis_scaling.git"}  # only target (M-20261029-147)
TAG_RE = re.compile(r"^cycle\d+-(claude|codex|final)-v\d+\.\d+$")
SECRET_RE = re.compile(r"(^|/)(\.env(\..*)?|id_rsa.*|id_ed25519.*|.*\.pem|.*\.key|auth\.json|credentials.*|"
                       r"\.kube/config|qiskit-ibm\.json)$", re.I)
LOG = os.path.join(ROOT, ".lab", "publish", "log.jsonl")


def git(*args, check=True):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def resolve(commit):
    return git("rev-parse", "--verify", f"{commit}^{{commit}}")


def check_review(path, sha):
    """Review file must name the full commit and carry both approvals."""
    if not path or not os.path.isfile(path):
        sys.exit(f"review file missing: {path}")
    text = open(path, encoding="utf-8").read()
    if sha not in text:
        sys.exit(f"review file does not name commit {sha}")
    for who in ("claude", "codex"):
        if not re.search(rf"^\s*{who}\s*:\s*APPROVE\b", text, re.I | re.M):
            sys.exit(f"review file lacks '{who}: APPROVE'")


def check_secrets(sha):
    bad = [p for p in git("ls-tree", "-r", "--name-only", sha).splitlines() if SECRET_RE.search(p)]
    if bad:
        sys.exit("secret-looking files in tree: " + ", ".join(bad[:10]))


def check_remote():
    """Refuse unless remote `github` points exactly at the researcher's repo, for fetch and push."""
    for args in (("remote", "get-url", REMOTE), ("remote", "get-url", "--push", "--all", REMOTE)):
        urls = git(*args, check=False).splitlines()
        if not urls or any(u.strip() not in REPO_URLS for u in urls):
            sys.exit(f"remote {REMOTE} must be exactly {sorted(REPO_URLS)[0]}; got {urls}")


def remote_refs():
    out = git("ls-remote", REMOTE)
    return {ref: sha for sha, ref in (l.split("\t") for l in out.splitlines() if "\t" in l)}


def push(refspec, dry):
    check_remote()
    cmd = ["git", "-C", ROOT, "push", REMOTE, refspec]
    print(("DRY-RUN: " if dry else "") + " ".join(cmd))
    if not dry:
        r = subprocess.run(cmd)
        if r.returncode:
            sys.exit("push failed")


def log(entry, dry):
    if dry:
        return
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    entry["ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def publish_tag(tag, sha, review, msg, dry, refs):
    if not TAG_RE.match(tag):
        sys.exit(f"tag name must match {TAG_RE.pattern}: {tag}")
    check_review(review, sha)
    check_secrets(sha)
    peeled = refs.get(f"refs/tags/{tag}^{{}}") or refs.get(f"refs/tags/{tag}")
    if peeled:
        if peeled == sha:
            print(f"{tag} already on {REMOTE} at {sha[:7]}; nothing to do")
            return
        sys.exit(f"{tag} already on {REMOTE} at {peeled[:7]}; tags are never moved, bump the version")
    local = git("rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}", check=False)
    if local and local != sha:
        sys.exit(f"local tag {tag} points to {local[:7]}, not {sha[:7]}")
    if not local and not dry:
        git("tag", "-a", tag, sha, "-m", msg or f"{tag} (jointly reviewed: {os.path.relpath(review, ROOT)})")
    push(f"refs/tags/{tag}:refs/tags/{tag}", dry)
    log({"action": "tag", "tag": tag, "commit": sha, "review": review}, dry)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tag")
    t.add_argument("--tag", required=True)
    t.add_argument("--commit", required=True)
    t.add_argument("-m", "--message")
    m = sub.add_parser("main")
    m.add_argument("--commit", required=True)
    r = sub.add_parser("retire-branch")
    r.add_argument("--branch", required=True)
    r.add_argument("--tag", required=True)
    for p in (t, m, r):
        p.add_argument("--review", required=True)
        p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    review = os.path.abspath(a.review)
    check_remote()
    refs = remote_refs()

    if a.cmd == "tag":
        publish_tag(a.tag, resolve(a.commit), review, a.message, a.dry_run, refs)
    elif a.cmd == "main":
        sha = resolve(a.commit)
        check_review(review, sha)
        check_secrets(sha)
        cur = refs.get("refs/heads/main")
        if cur == sha:
            print("main already there")
            return
        if cur and subprocess.run(["git", "-C", ROOT, "merge-base", "--is-ancestor", cur, sha]).returncode:
            sys.exit(f"remote main {cur[:7]} is not an ancestor of {sha[:7]}; fast-forward only")
        push(f"{sha}:refs/heads/main", a.dry_run)
        log({"action": "main", "commit": sha, "review": review}, a.dry_run)
    else:
        if a.branch == "main":
            sys.exit("main is never retired")
        sha = refs.get(f"refs/heads/{a.branch}")
        if not sha:
            sys.exit(f"branch {a.branch} not on {REMOTE}")
        git("cat-file", "-e", f"{sha}^{{commit}}")
        publish_tag(a.tag, sha, review, None, a.dry_run, refs)
        if not a.dry_run:
            after = remote_refs()
            if (after.get(f"refs/tags/{a.tag}^{{}}") or after.get(f"refs/tags/{a.tag}")) != sha:
                sys.exit(f"tag {a.tag} not verified on {REMOTE}; branch kept")
        push(f":refs/heads/{a.branch}", a.dry_run)
        log({"action": "retire-branch", "branch": a.branch, "tag": a.tag, "commit": sha, "review": review},
            a.dry_run)


if __name__ == "__main__":
    main()
