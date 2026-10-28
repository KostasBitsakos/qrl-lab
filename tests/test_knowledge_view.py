import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import knowledge_view as kv  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def test_tree_and_entry_points():
    t = kv.build_tree(kv.load(ROOT))
    assert "docs" in t and "." in t
    assert t["docs"][0]["path"] in kv.ENTRY_POINTS
    assert "STATE.md" in kv.file_html(t["docs"][0]) or "DECISIONS" in kv.file_html(t["docs"][0])


def test_escape():
    h = kv.file_html({"path": "x/<b>.md", "description": "<script>", "lines": 1})
    assert "<script>" not in h
