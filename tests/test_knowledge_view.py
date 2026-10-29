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


def test_theme_tree_counts_and_search():
    entries = ENTRIES + [{"path": "code-tuning/experiments/x.md", "title": "X", "description": "", "lines": 1},
                         {"path": ".lab/tuning/cycles/c1.md", "title": "c1", "description": "poisson", "lines": 1}]
    t = kv.tree_data(entries, "poisson")
    themes = {c["id"]: c for c in t["children"]}
    assert t["n"] == len(entries) == sum(c["n"] for c in t["children"])
    assert themes["cat:start"]["children"][0]["path"] == "docs/STATE.md"  # entry point lives under «Ξεκίνα εδώ»
    assert themes["cat:rules"]["children"][0]["name"] == "rules/"  # docs/ prefix stripped inside a theme
    assert themes["cat:exp"]["hit"] and not themes["cat:code"]["hit"] and t["hit"]
    assert kv.category("export/results/a.md") == "exp" and kv.category("export/docs/a.md") == "export"
    assert kv.category("weird.md") == "other"


def test_tree_html_is_self_contained_and_escaped():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import knowledge_tree as ktr
    page = ktr.render(kv.tree_data([{"path": "a.md", "title": "</script><b>", "description": "", "lines": 1}]), "/r/", "📁 Αρχεία")
    assert "</script><b>" not in page and "<\\/script>" in page
    assert "http://" not in page.replace("http://www.w3.org/2000/svg", "") and "https://" not in page  # no CDN
    real = ktr.render(kv.tree_data(kv.load(ROOT)), ROOT, "📁 Αρχεία")
    assert ',ROOT="/r",FILES_TAB="📁 Αρχεία";' in page  # absolute paths for the Files tab (?path=)
    assert "__DATA__" not in real and "pointerdown" in real
