import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import tutorials_view as tv


def library(tmp_path):
    folder = tmp_path / 'docs' / 'tutorials'
    folder.mkdir(parents=True)
    return folder


def test_catalog_and_safe_fallback(tmp_path):
    folder = library(tmp_path)
    (folder / 'registered.pdf').write_bytes(b'%PDF-test')
    (folder / 'new_guide.pdf').write_bytes(b'%PDF-new')
    (folder / 'catalog.json').write_text(json.dumps({
        'registered.pdf': {'title': 'Ελληνικός οδηγός', 'date': '2026-10-29', 'description': 'Περιγραφή'},
        '../outside.pdf': {'title': 'Escape'},
    }))
    items = {x.path.name: x for x in tv.discover(tmp_path)}
    assert set(items) == {'registered.pdf', 'new_guide.pdf'}
    assert items['registered.pdf'].title == 'Ελληνικός οδηγός'
    assert items['registered.pdf'].description == 'Περιγραφή'
    assert items['new_guide.pdf'].title == 'new guide'


def test_non_pdf_and_symlink_never_exposed(tmp_path):
    folder = library(tmp_path)
    secret = tmp_path / 'outside.pdf'
    secret.write_bytes(b'%PDF-outside')
    (folder / 'linked.pdf').symlink_to(secret)
    (folder / 'invalid.pdf').write_text('not a PDF')
    (folder / 'sub').mkdir()
    (folder / 'sub' / 'nested.pdf').write_bytes(b'%PDF-nested')
    assert tv.discover(tmp_path) == []


def test_missing_or_broken_catalog(tmp_path):
    assert tv.discover(tmp_path) == []
    folder = library(tmp_path)
    (folder / 'guide.pdf').write_bytes(b'%PDF-test')
    for data in ('broken json', '[]', '{"guide.pdf": []}', '{"guide.pdf": {"date": null}}'):
        (folder / 'catalog.json').write_text(data)
        items = tv.discover(tmp_path)
        assert len(items) == 1
        assert items[0].title == 'guide'
        assert len(items[0].date) == 10


def test_streamlit_download_bytes_and_mobile_layout(tmp_path):
    from streamlit.testing.v1 import AppTest
    folder = library(tmp_path)
    payload = b'%PDF-test exact payload'
    (folder / 'guide.pdf').write_bytes(payload)
    (folder / 'catalog.json').write_text(json.dumps({'guide.pdf': {
        'title': 'Ο οδηγός μου', 'date': '2026-10-29', 'description': 'Κατανοητό PDF'}}))
    # Exercise real Streamlit rendering, including the download widget.
    script = f"import sys; sys.path.insert(0, {str(Path(tv.__file__).parent)!r})\nimport tutorials_view\ntutorials_view.render({str(tmp_path)!r})"
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert app.subheader[0].value == 'Ο οδηγός μου'
    buttons = app.get('download_button')
    assert len(buttons) == 1
    assert buttons[0].proto.label == '⬇ Λήψη PDF'
    assert buttons[0].proto.url
    assert len(app.get('column')) == 0  # single-column cards inherit existing phone CSS


def test_dashboard_wires_both_tab_modes():
    import ast
    root = Path(tv.__file__).resolve().parents[1]
    source = (root / 'dashboard' / 'app.py').read_text()
    tree = ast.parse(source)
    reload_names = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == '_LOCAL_MODS' for t in n.targets))
    assert {'mobile_view', 'tutorials_view'} <= set(reload_names)
    targets = []
    tab_labels = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == 'TAB_NAMES' for t in node.targets):
                tab_labels = node.value.elts
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                if node.value.func.attr == 'tabs' and node.value.args and isinstance(node.value.args[0], ast.Name):
                    if node.value.args[0].id == 'TAB_NAMES':
                        targets.append(node.targets[0].elts)
    assert tab_labels is not None and len(targets) == 2
    assert any(isinstance(e, ast.Constant) and e.value == '📚 Tutorials' for e in tab_labels)
    for target in targets:
        assert len(target) == len(tab_labels)
        assert target[-1].id == 'tab_tutorials'
