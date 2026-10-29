import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import cycle2_daily as cd  # noqa: E402

LIST = """\
20261029-131731-R-20261029-006-s0-a1  running  exit=None  sim  cycle2-claude-smoke-w1/j53-smoke-lstm-c0-s15000
20261029-131731-R-20261029-006-s2-a1  done     exit=0  sim  cycle2-claude-smoke-w1/j53-smoke-dinos-c0-s15000
20261029-131731-R-20261029-006-s6-a1  done     exit=1  sim  cycle2-codex-smoke-w1/j51-smoke-dinos-c0-s15000
20261030-100000-R-20261029-006-s0-a1  done     exit=0  sim  cycle2-codex-tuning-w1/j51-tune-v2-c1-s13000
20261022-200212-R-20261022-003-s8-a1  done     exit=0  sim  c20n5-5/c20n5s-spike300_d5-dinos_a1h-t20000-grid-dqn5-s55
"""
STATUS = ("R-20261029-006 (dinos-poisson,dinos-poisson-astra): 3.114 / 160.0 CPU-h used, 156.886 left; "
          "6/8 running; expires 2026-11-05T05:10:39+00:00 (159.83 h left)")


def test_parse_and_report(tmp_path):
    runs = cd.parse_list(LIST)
    assert len(runs) == 4                      # other requests ignored
    st = cd.parse_status(STATUS)
    assert st == {"used": 3.114, "budget": 160.0, "running": 6}
    d = tmp_path / "20261029-131731-R-20261029-006-s6-a1"
    d.mkdir()
    (d / "spec_entry.json").write_text(json.dumps({"sandbox": {"repo": "code-poisson-astra"}}))
    body = cd.build_report(runs, st, tmp_path, 20, dt.date(2026, 10, 29))
    assert len(body.splitlines()) <= 17
    assert "3.1 / 160" in body and "άνω όριο" in body
    assert "claude: smoke 1✓/1▶/0✗ · tuning — · final —" in body
    assert "codex: smoke 0✓/0▶/1✗ · tuning 1✓/0▶/0✗ · final —" in body
    assert "Αποτυχίες: 1" in body and "s6-a1" in body
    assert "docs/EXPERIMENTS.md:20" in body


def test_missing_inputs_say_unknown(tmp_path):
    body = cd.build_report([], cd.parse_status(""), tmp_path, None, dt.date(2026, 11, 2))
    assert "CPU-h: unknown" in body and "Μητρώο: unknown" in body and "0 μέρες" in body


def test_gate_skips_outside_hour(monkeypatch):
    calls = []
    monkeypatch.setattr(cd, "run_cli", lambda *a: calls.append(a) or "")

    class FakeDT(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 10, 30, 10, 0, tzinfo=tz)
    monkeypatch.setattr(cd.dt, "datetime", FakeDT)
    assert cd.main([]) == 0 and calls == []    # 10:00 Athens: nothing read, nothing posted


def test_past_deadline_posts_nothing(monkeypatch):
    removed = []
    monkeypatch.setattr(cd, "remove_cron_line", lambda: removed.append(1) or True)
    monkeypatch.setattr(cd, "run_cli", lambda *a: (_ for _ in ()).throw(AssertionError("must not run")))

    class FakeDT(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 11, 3, 18, 0, tzinfo=tz)
    monkeypatch.setattr(cd.dt, "datetime", FakeDT)
    assert cd.main([]) == 0 and removed == [1]
