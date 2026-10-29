import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import token_savings as ts  # noqa: E402


def test_measured():
    with tempfile.TemporaryDirectory() as r:
        os.makedirs(os.path.join(r, ".lab")); os.makedirs(os.path.join(r, ".claude"))
        open(os.path.join(r, "CLAUDE.md"), "w").write("x" * 100)
        open(os.path.join(r, ".lab", "CLAUDE.md.bak-20261028"), "w").write("x" * 500)
        json.dump({"enabledMcpjsonServers": ["a"], "disableClaudeAiConnectors": True, "enabledPlugins": {"p": False, "q": True}},
                  open(os.path.join(r, ".claude", "settings.local.json"), "w"))
        m = ts.measured(r)
        c, a = m["files"]
        assert (c["now"], c["before"], c["saved_bytes"], c["saved_tokens_approx"]) == (100, 500, 400, 100)
        assert a["now"] is None and a["saved_bytes"] is None  # missing files are never guessed
        assert [s["value"] for s in m["settings"]] == [1, "ναι", 1]

import pathlib
import token_metrics as tm


def test_comparison_denominator_and_missing():
    r = tm.comparison('x', 500, 100, 'source', 'window')
    assert r['% του baseline bytes'] == 80
    assert r['≈ tokens ανά ανάγνωση'] == 100
    for baseline in (None, 0, -1, True):
        r = tm.comparison('x', baseline, 100, 'source', 'window')
        assert r['% του baseline bytes'] is None
        assert r['≈ tokens ανά ανάγνωση'] is None
    assert tm.comparison('x', 100, 200, '', '')['% του baseline bytes'] == -100


def test_bounded_audit_and_malformed(tmp_path):
    p = tmp_path / '.lab/j137/audit-summary.json'
    p.parent.mkdir(parents=True)
    good = dict(status='issues_found', checked_at='2026-10-29', coverage=['local'], findings=['open'], limits=['partial'])
    p.write_text(json.dumps(good))
    assert tm.load_audit(tmp_path) == good
    for value in ('[]', '{', json.dumps({**good, 'coverage': 'bad'}), ' ' * (tm.MAX_JSON + 1)):
        p.write_text(value)
        assert tm.load_audit(tmp_path)['status'] == 'εκκρεμεί'
    p.unlink()
    p.symlink_to('/must/not/read')
    assert tm.load_audit(tmp_path)['status'] == 'εκκρεμεί'


def test_snapshot_search_bounded_no_home(tmp_path, monkeypatch):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/INDEX.md').write_text('token\n' * 100)
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return type('Result', (), {'returncode': 0, 'stdout': b'token\n' * 8})()
    monkeypatch.setattr(tm.subprocess, 'run', run)
    d = tm.snapshot(tmp_path)
    assert d['rows'][0]['≈ tokens ανά ανάγνωση'] is None
    assert d['rows'][2]['bytes μετά'] == 48
    assert calls[0][0][1:4] == ['-i', '-m', '8']
    assert calls[0][1]['timeout'] == 2
    assert 'άγνωστο' in tm.summary_text(d)


def test_oversize_index_and_symlinks_never_searched(tmp_path, monkeypatch):
    (tmp_path / 'docs').mkdir()
    index = tmp_path / 'docs/INDEX.md'
    index.write_bytes(b'x' * (tm.MAX_INDEX_BYTES + 1))
    def forbidden(*args, **kwargs):
        raise AssertionError('must not search oversized or linked index')
    monkeypatch.setattr(tm.subprocess, 'run', forbidden)
    assert tm.snapshot(tmp_path)['rows'][2]['bytes μετά'] is None
    index.unlink()
    index.symlink_to('/must/not/read')
    assert tm.snapshot(tmp_path)['rows'][2]['bytes πριν'] is None


def test_real_streamlit_render():
    from streamlit.testing.v1 import AppTest
    root = pathlib.Path(__file__).resolve().parents[1]
    script = f'''
import sys
sys.path.insert(0, {str(root / 'tools')!r})
import streamlit as st
import token_metrics
data = token_metrics.snapshot({str(root)!r})
with st.sidebar:
    token_metrics.render(st, data, compact=True)
token_metrics.render(st, data)
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert any('Εξοικονόμηση tokens' in x.value for x in app.sidebar.markdown)
    assert len(app.dataframe) == 1
    assert any('Συνολική πραγματική εξοικονόμηση' in x.value for x in app.caption)


class RenderRecorder:
    def __init__(self):
        self.text = []
    def __getattr__(self, name):
        def record(value, **kwargs):
            self.text.append(str(value))
        return record


def test_both_render_paths_real_files():
    root = pathlib.Path(__file__).resolve().parents[1]
    data = tm.snapshot(root)
    for compact in (True, False):
        recorder = RenderRecorder()
        tm.render(recorder, data, compact=compact)
        text = '\n'.join(recorder.text)
        assert 'Συνολική πραγματική εξοικονόμηση και %: άγνωστα' in text
        assert 'Έλεγχος σπατάλης' in text
    app = (root / 'dashboard/app.py').read_text()
    assert 'st.html(token_metrics.card_html(token_snapshot()))' in app
    # card sits after the logo and usage rings (researcher M-20261029-288)
    assert app.index('{LOGO_SVG}</a>') < app.index('usage_rings()\n') < app.index('token_metrics.card_html(')
    card = tm.card_html(data)
    assert 'Εξοικονόμηση tokens' in card and 'άγνωστη' in card and 'Επεκτάσεις' in card
    assert 'token_metrics.render(st, token_snapshot())' in app
    assert 'token_savings.count_events(' not in app
    assert '@st.cache_data(ttl=300, show_spinner=False)\ndef token_snapshot' in app
