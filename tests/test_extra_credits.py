import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import extra_credits as ec  # noqa: E402
import health_watch as hw  # noqa: E402

P = 1792756800.0  # 2026-10-23T11:40:00Z


def _dir():
    d = tempfile.mkdtemp()
    json.dump({"claude": {"purchased_usd": 20, "purchased_at": "2026-10-23T11:40:00Z", "cost_baseline_usd": None}},
              open(os.path.join(d, "extra_credits.json"), "w"))
    return d


def test_purchased_ts():
    assert ec.purchased_ts({"purchased_at": "2026-10-23T11:40:00Z"}) == 1792755600.0
    assert ec.purchased_ts({"purchased_at": "bad"}) is None


def test_spend_estimate_per_session_baseline():
    d = _dir()
    t = ec.purchased_ts(ec.load_config(d)["claude"])
    ec.observe("a", 5.0, t - 10, d)          # before purchase: ignored
    ec.observe("a", 6.0, t + 1, d)           # baseline 6
    ec.observe("a", 8.5, t + 2, d)
    ec.observe("b", 1.0, t + 3, d)           # baseline 1
    ec.observe("b", 1.5, t + 4, d)
    ec.observe("c", True, t + 5, d)          # bad input
    s = ec.status("claude", d)
    assert abs(s["spent_usd"] - 3.0) < 1e-9 and s["active"] and abs(s["remaining_usd"] - 17.0) < 1e-9
    ec.observe("a", 30.0, t + 6, d)
    assert not ec.status("claude", d)["active"] and ec.status("claude", d)["remaining_usd"] == 0


def test_no_config_inactive():
    assert not ec.status("claude", tempfile.mkdtemp())["active"]


LINE = "You've hit your weekly limit · resets Oct 24, 9am (Europe/Athens)"


def test_classifier_extra_vs_limit():
    assert hw.detect(LINE)["state"] == "limit"
    assert hw.detect(LINE, extra_active=True)["state"] == "extra"
    r = hw.detect("You're out of extra usage · resets Oct 24, 9am (Europe/Athens)", extra_active=True)
    assert r["state"] == "limit"
    assert hw.detect("hello", extra_active=True)["state"] == "ok"


def test_awake_info_and_html():
    a = ec.awake_info("claude", {"state": "limit", "detail": "9am", "resets_at": 1792994400}, P)
    import re
    assert not a["awake"] and re.fullmatch(r"\d\d/\d\d \d\d:\d\d", a["reset"])
    assert ec.awake_info("claude", {"state": "extra"}, P)["badge"] == "💳"
    h = ec.awake_html([a, ec.awake_info("codex", {}, P)])
    assert "😴" in h and "Codex" in h and "Πάρις" in h
    b = ec.awake_info("codex", {}, P)
    b["windows"] = [{"label": "5ω", "pct": 42.0, "resets_at": 1792994400}, {"label": "7ημ", "pct": None, "resets_at": None}]
    h2 = ec.awake_html([b])
    assert "Ξύπνιος" in h2 and "42%" in h2 and "άγνωστο" in h2 and "width:42%" in h2
    assert "Εκτός" in ec.awake_html([ec.awake_info("codex", {"state": "down"}, P)])
    assert ec.show_credits(100, "ok", {"active": True}) and ec.show_credits(10, "extra", {"active": True})
    assert not ec.show_credits(100, "ok", {"active": False}) and not ec.show_credits(50, "ok", {"active": True})
