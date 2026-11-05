import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import convo_context as cc  # noqa: E402
import md_dedupe as md  # noqa: E402


def _root():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "docs"))
    with open(os.path.join(d, "docs", "index.json"), "w", encoding="utf-8") as f:
        json.dump([{"path": "docs/MOBILE.md", "title": "Mobile access", "description": "tailscale serve dashboard terminal"}], f)
    with open(os.path.join(d, "docs", "DECISIONS.md"), "w", encoding="utf-8") as f:
        f.write("- 2026-10-16 — R-20261016-007 ανανέωση πιστοποιητικών K8s με grant, εγκρίθηκε\n- unrelated line about quantum circuits\n")
    return d


def test_relevant_finds_accent_insensitive_and_bounded():
    r = cc.relevant("ανανεωση πιστοποιητικων του K8s", _root(), max_chars=300)
    assert "DECISIONS.md:1" in r and "quantum" not in r and len(r) <= 300


def test_relevant_empty_when_nothing_matches():
    assert cc.relevant("zzzz qqqq", _root()) == ""


def test_tree_entry_matches():
    assert "docs/MOBILE.md" in cc.relevant("tailscale terminal dashboard access", _root())


def test_dedupe_detects_same_id_and_overlap():
    lines = ["- R-20261016-007 ανανέωση πιστοποιητικών K8s εγκρίθηκε", "- other thing entirely different here"]
    assert md.similar(lines, "R-20261016-007 ανανέωση πιστοποιητικών K8s ξανά")[0][0] == 1
    assert md.similar(lines, "completely new topic about plotting figures")== []


def test_append_and_replace():
    d = _root()
    p = os.path.join(d, "docs", "DECISIONS.md")
    assert md.main(["append", p, "- brand new words about dashboard flicker async refresh"]) == 0
    assert md.main(["append", p, "- brand new words about dashboard flicker async refresh"]) == 1
    n = len(open(p, encoding="utf-8").read().splitlines())
    assert md.main(["append", p, "- brand new words about dashboard flicker async refresh v2", "--replace", str(n)]) == 0
    assert open(p, encoding="utf-8").read().count("flicker") == 1


def test_exclude_ids_removes_current_and_pack_messages():
    from labdb import LabDB
    root = _root()
    os.makedirs(os.path.join(root, ".lab"))
    db = LabDB(os.path.join(root, ".lab", "lab.db"))
    text = "ανανεωση πιστοποιητικων του K8s με grant"
    cur, other = db.researcher_send(text), db.researcher_send(text + " ξανά")
    r = cc.relevant(text, root)
    assert f"labq.py show {cur}" in r and f"labq.py show {other}" in r  # sanity: both match without a filter
    r = cc.relevant(text, root, exclude_ids={cur})
    assert f"labq.py show {cur}" not in r and f"labq.py show {other}" in r
    assert f"labq.py show {other}" not in cc.relevant(text, root, exclude_ids={cur, other})
