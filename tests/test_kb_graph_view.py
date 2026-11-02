import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import kb_graph_view as kg


def test_file_graph_aggregates_cross_file_edges_only():
    g = {"nodes": [{"id": "a1", "source_file": "qrl/a.py"}, {"id": "a2", "source_file": "qrl/a.py"},
                   {"id": "b1", "source_file": "tuning/b.py"}, {"id": "c1", "source_file": "qrl/c.py"}],
         "edges": [{"source": "a1", "target": "b1", "relation": "calls"}, {"source": "a2", "target": "b1", "relation": "calls"},
                   {"source": "a1", "target": "a2", "relation": "calls"}, {"source": "a1", "target": "c1", "relation": "contains"}]}
    d = kg.file_graph(g)
    assert d["edges"] == [["qrl/a.py", "tuning/b.py", 2, "calls"]]
    assert {n["id"] for n in d["nodes"]} == {"qrl/a.py", "tuning/b.py"}
    assert d["total_files"] == 3 and d["total_symbols"] == 4
    html = kg.render(d)
    assert "qrl/a.py" in html and "</script>" in html


def test_load_missing(tmp_path):
    data, err = kg.load(tmp_path)
    assert data is None and err
    assert kg.index_stats(tmp_path) == {}


def test_real_graph_if_present():
    root = Path(__file__).resolve().parents[1]
    data, err = kg.load(root)
    if data is not None:
        assert data["nodes"] and data["edges"] and len(data["nodes"]) <= 400
