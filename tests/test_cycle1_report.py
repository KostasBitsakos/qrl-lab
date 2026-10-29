import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import cycle1_report as c

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R10 = c.read(ROOT, "res10")
R11 = c.read(ROOT, "res11")


def test_section_and_tables():
    t = "# A\nx\n## B\n| a | b |\n|---|---|\n| 1 | 2 |\n## C\ny\n"
    assert c.section(t, "## B").startswith("## B") and "y" not in c.section(t, "## B")
    assert c.md_tables(t) == [(["a", "b"], [["1", "2"]])]


def test_test10_parse():
    hdr, rows = c.test10_main_table(R10)
    assert "test10" in hdr and len(rows) == 9
    assert any("PRIMARY" in r[0] and r[3] == "87781" for r in rows)
    h = c.test10_hypotheses(R10)
    assert [x[0] for x in h] == ["H1", "H2", "H3", "H4", "H5", "H6"]
    assert h[0][2:] == ("+24784", "[+17854, +31755]", "CONFIRMED")
    assert h[2][4].startswith("NOT confirmed") and h[3][4] == "descriptive"
    assert ("HPA-demand", "47530") in c.test10_baselines(R10)


def test_test11_parse():
    m = dict((a, b) for a, b, _ in c.test11_means(R11))
    assert m["his HPA"] == "249" and m["V.2"] == "83983" and m["oracle_Dstep"] == "88822"
    hdr, rows = c.test11_hypotheses(R11)
    assert len(rows) == 6 and rows[0][4] == "CONFIRMED" and rows[2][3] == "[-2478, +3709]"
    i = {a: (b, d) for a, b, d in c.iqm_lines(ROOT)}
    assert i["transfer_a1h_dqn3"][0] == "84082"


def test_sources_and_syntheses():
    assert "c3_synthesis.md" in [n for n, _ in c.cycle_syntheses(ROOT)]
    assert c.section(c.read(ROOT, "paper"), "## 6.").startswith("## 6. Reminders")
    st = c.arm_stats(ROOT, "test11")
    assert round(st["transfer_a1h_dqn3"]["mean"]) == 83983 and st["transfer_a1h_dqn3"]["ck"] == 10000


def test_make_figures_synthetic(tmp_path):
    root = tmp_path
    (root / ".lab" / "tuning").mkdir(parents=True)
    arms = {"derp": {"status": "complete", "checkpoint": "20000", "mean": "100", "sd_over_seeds": "5",
                     "val_by_checkpoint": {"1000": 1.0, "20000": 90.0}}}
    s = {"spike300_d5": {"arms": arms, "baselines": {sp: {"hpa_rule": {"mean_ret": 1.0}} for sp in ("test10", "test11")}}}
    for fn in ("c18c_summary.json", "c24c_summary.json"):
        (root / ".lab" / "tuning" / fn).write_text(json.dumps(s))
    for tag, sp in (("c18c", "test10"), ("c24c", "test11")):
        d = root / "code-tuning" / "tuning" / "results" / tag
        d.mkdir(parents=True)
        run = {"arm": "derp", "seed": 1, "checkpoint_results": {"20000": {"val": {"episodes": [{"ret": 90.0}]},
                                                                        sp: {"episodes": [{"ret": 98.0}, {"ret": 102.0}]}}}}
        (d / "spike300_d5-derp-s1.json").write_text(json.dumps(run))
    figs = c.make_figures(str(root), str(root / "out"))
    assert len(figs) == 4 and all(os.path.getsize(p) > 1000 for p in figs)
    assert json.load(open(root / "out" / "per_seed_test10.json"))["derp"]["1"]["test"] == 100.0


def test_bullet_section():
    s = c.section(c.read(ROOT, "freeze24"), "- Explicit recipe")
    assert s.startswith("- Explicit recipe") and "Command:" not in s and "linear10k" in s
    a = c.section(c.read(ROOT, "freeze21"), "- Arms")
    assert a.startswith("- Arms") and "Checkpoint:" not in a


def test_overview_keeps_controls_and_display_names():
    rows = c.overview_rows(R11)
    means = {r['Μοντέλο']: r['Μέση επίδοση'] for r in rows}
    assert means['Dinos+Transfer V.2'] == 83983
    assert means['HPA'] == 249
    assert means['MLP (a1h)'] > means['LSTM+transfer']
    main = ('LSTM', 'LSTM+transfer', 'Dinos', 'Dinos+Transfer V.2', 'DERP', 'enhanced DERP', 'HPA')
    assert max(main, key=means.get) == 'LSTM+transfer'
    h4 = c.test11_hypotheses(R11)[1][3]
    assert h4[0] == 'H4' and h4[2].startswith('-')
    assert all(float(n.strip()) < 0 for n in h4[3].strip('[]').split(','))
    assert h4[4].startswith('descriptive')
    assert {'LSTM', 'LSTM+transfer', 'Dinos', 'DERP', 'enhanced DERP'} <= means.keys()
    assert 'oracle_Dstep' not in means
    assert c.overview_rows('') == []


def test_experiments_report_renders_inside_tab_and_figures_are_on_demand(tmp_path, monkeypatch):
    """Run the real dashboard in an isolated lab, with no runs or production state writes."""
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    root = Path(ROOT)
    for name in ('tools', 'dashboard', 'docs', 'paper', '.streamlit'):
        (tmp_path / name).symlink_to(root / name, target_is_directory=True)
    for rel in (c.SOURCES['res11'], c.SOURCES['res10'], c.SOURCES['freeze24']):
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text((root / rel).read_text())
    monkeypatch.setenv('QRL_LAB_DIR', str(tmp_path))
    monkeypatch.setenv('QRL_EAGER_TABS', '0')
    monkeypatch.setenv('QRL_PROM_URL', 'http://127.0.0.1:9')
    calls = []
    monkeypatch.setattr(c, 'make_figures', lambda *args: calls.append(args) or [])
    at = AppTest.from_file(str(tmp_path / 'dashboard/app.py'), default_timeout=60)
    at.query_params['tab'] = '📈 Πειράματα'
    at.run()
    assert not at.exception
    report_tab = next(t for t in at.tabs if 'Πειράματα' in t.label)
    assert any(x.value == 'Κύκλος 1 · Ολοκληρώθηκε' for x in report_tab.subheader)
    assert not any('Κύκλος 1 · Ολοκληρώθηκε' in x.value for t in at.tabs if t != report_tab for x in t.subheader)
    table = report_tab.dataframe[0]
    assert list(table.value.columns) == ['Μοντέλο', 'Μέση επίδοση', 'Ρόλος']
    config = json.loads(table.proto.columns)
    assert all(config[col].get('help') for col in table.value.columns)
    assert report_tab.expander[0].label.startswith('Κύκλος 1 · Πρωτόκολλο')
    raw = next(e for e in report_tab.expander if e.label.startswith('Εκτελέσεις, ζωντανή'))
    assert not raw.proto.expanded
    assert sum(x.value == 'Κύκλος 1 · Ολοκληρώθηκε' for x in at.subheader) == 1
    assert not calls
    at.button(key='c1_show_figures').click().run()
    assert not at.exception
    assert len(calls) == 1
