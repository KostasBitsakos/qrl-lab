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


ENTRIES = [{"path": "docs/STATE.md", "title": "STATE", "description": "handoff", "lines": 5},
           {"path": "docs/rules/a.md", "title": "Rule A", "description": "cores <x>", "lines": 2},
           {"path": "README.md", "title": "R", "description": "", "lines": 1}]


def test_icicle_whole_tree_consistent():
    d = kv.icicle_data(ENTRIES)
    ids = d["ids"]
    assert set(ids) == {kv.ROOT_ID, "docs", "docs/rules", "docs/STATE.md", "docs/rules/a.md", "README.md"}
    assert all(p == "" or p in ids for p in d["parents"])  # every parent exists
    val = dict(zip(ids, d["values"]))
    assert val[kv.ROOT_ID] == 3 and val["docs"] == 2 and val["docs/rules"] == 1  # branchvalues="total" holds
    col = dict(zip(ids, d["colors"]))
    assert col["docs/STATE.md"] == kv.ROLE_COLOR["index"]
    assert "<x>" not in d["hover"][ids.index("docs/rules/a.md")]


def test_search_highlights_file_and_ancestors():
    d = kv.icicle_data(ENTRIES, "CORES")
    col = dict(zip(d["ids"], d["colors"]))
    assert d["hits"] == ["docs/rules/a.md"]
    assert col["docs/rules/a.md"] == col["docs/rules"] == col["docs"] == kv.ROLE_COLOR["match"]
    assert col["README.md"] != kv.ROLE_COLOR["match"] and col[kv.ROOT_ID] == kv.ROLE_COLOR["root"]


def test_figure_real_index_and_zoom():
    entries = kv.load(ROOT)
    fig = kv.figure(entries, level="docs/rules")
    tr = fig.data[0]
    assert tr.type == "icicle" and tr.level == "docs/rules" and tr.pathbar.visible
    assert len(tr.ids) > len(entries)  # all files plus their folders
    assert kv.figure(entries, level="nope").data[0].level == kv.ROOT_ID
    assert "docs/rules" in kv.folders(entries)
