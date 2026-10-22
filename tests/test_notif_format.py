import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import notif_format as nf  # noqa: E402

NOW = 1_792_700_000.0
EV = {"ts": NOW - 7300, "kind": "limit_reset", "provider": "codex", "window": "5h",
      "title": "codex 5h: νέο παράθυρο (49% → 1%)", "url": "", "status": "local"}


def test_reset_message():
    f = nf.format_event(EV, NOW)
    assert f["text"] == "Codex: ανανεώθηκε το 5ωρο όριο — διαθέσιμο ξανά (ήταν 49% χρησιμοποιημένο)"
    assert f["icon"] == "✅" and f["severity"] == "ok" and f["brand"] == "#10a37f"
    assert f["when"] == "πριν 2 ώρες"


def test_warn_with_reset_time():
    e = {"ts": NOW, "kind": "limit_warn", "provider": "claude", "window": "7d", "used_percent": 90,
         "resets_at": NOW + 3 * 86400}
    f = nf.format_event(e, NOW)
    assert "90% του εβδομαδιαίου ορίου" in f["text"] and "ώρα Ελλάδας" in f["text"] and f["severity"] == "warn"


def test_candidate_and_unknown():
    c = nf.format_event({"ts": NOW, "kind": "candidate", "provider": "claude", "title": "X", "url": "https://a"}, NOW)
    assert c["url"] == "https://a" and "ανεπιβεβαίωτη" in c["text"]
    assert nf.format_event({"ts": NOW, "kind": "zzz", "provider": "p"}, NOW)["severity"] == "info"


def test_rel_time():
    assert nf.rel_time(NOW - 10, NOW) == "μόλις τώρα"
    assert nf.rel_time(NOW - 300, NOW) == "πριν 5 λεπτά"
    assert nf.rel_time(NOW - 3600, NOW) == "πριν 1 ώρα"
    assert nf.rel_time(NOW + 7200, NOW) == "σε 2 ώρες"


def test_athens_time():
    # 2026-10-22 12:00 UTC = 15:00 EEST
    t = 1792670400.0
    assert nf.athens_time(t).endswith("15:00")


def test_filter_and_dismiss(tmp_path):
    old = dict(EV, ts=NOW - 90000)
    p = str(tmp_path / "d.json")
    assert [e["ts"] for e in nf.visible([EV, old], set(), NOW)] == [EV["ts"]]
    nf.dismiss(p, [nf.event_id(EV)])
    assert nf.visible([EV], nf.load_dismissed(p), NOW) == []
    assert nf.load_dismissed(str(tmp_path / "none.json")) == set()
    g = nf.group_by_provider([nf.format_event(EV, NOW)])
    assert list(g) == ["codex"]
