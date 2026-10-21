"""Tests for tools/usage_limits.py on synthetic fixtures. Run: .venv/bin/python tests/test_usage_limits.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import usage_limits as ul  # noqa: E402

NOW = 1_800_000_000.0


def _codex_rec(ts_iso, p5, r5, p7, r7):
    return {"timestamp": ts_iso, "type": "event_msg", "payload": {"type": "token_count", "info": {"x": 1}, "rate_limits": {
        "limit_id": "codex", "primary": {"used_percent": p5, "window_minutes": 300, "resets_at": r5},
        "secondary": {"used_percent": p7, "window_minutes": 10080, "resets_at": r7}, "plan_type": "plus"}}}


def _claude_rej(ts_iso, resets, typ="five_hour"):
    return {"type": "assistant", "timestamp": ts_iso, "apiError": "usage_limit_reached",
            "apiErrorParams": {"rate_limit_info": {"status": "rejected", "resetsAt": resets, "rateLimitType": typ}}}


def _write(path, recs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in recs:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    os.utime(path, (NOW - 60, NOW - 60))


def test_parse_codex_and_latest():
    e = ul.parse_codex(_codex_rec("2027-01-15T08:00:00Z", 12.0, NOW + 3600, 40.0, NOW + 86400), "f")
    assert [x["window"] for x in e] == ["5h", "7d"] and e[0]["used_percent"] == 12.0 and e[1]["slot"] == "secondary"
    assert ul.parse_codex({"payload": {"type": "agent_message"}}) == [] and ul.parse_codex("x") == []
    d = tempfile.mkdtemp()
    _write(os.path.join(d, "2027", "a", "rollout-1.jsonl"),
           [_codex_rec("2027-01-15T07:00:00Z", 5.0, NOW + 100, 30.0, NOW + 9000), "{broken",
            _codex_rec("2027-01-15T07:30:00Z", 7.0, NOW + 100, 31.0, NOW + 9000), {"payload": {"type": "other"}}])
    got = ul.latest_codex(NOW, os.path.join(d, "**", "rollout-*.jsonl"))
    assert got[0]["used_percent"] == 7.0 and got[1]["used_percent"] == 31.0


def test_claude_scanner_incremental():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "proj", "s.jsonl")
    _write(p, [{"type": "user", "timestamp": "2027-01-15T07:00:00Z"}, _claude_rej("2027-01-15T07:10:00Z", NOW - 500)])
    sc = ul.ClaudeScanner(os.path.join(d, "**", "*.jsonl"))
    e = sc.scan(NOW)
    assert e["provider"] == "claude" and e["used_percent"] == 100.0 and e["resets_at"] == NOW - 500
    off = sc.off[p]
    with open(p, "a") as f:
        f.write(json.dumps(_claude_rej("2027-01-15T07:20:00Z", NOW + 1800)) + "\n")
    os.utime(p, (NOW - 10, NOW - 10))
    e = sc.scan(NOW)
    assert e["resets_at"] == NOW + 1800 and sc.off[p] > off and len(sc.found) == 2
    assert ul.parse_claude({"apiError": "usage_limit_reached", "apiErrorParams": {"rate_limit_info": {"status": "allowed"}}}) == []


def test_rings_never_invent():
    pct, win, tip = ul.provider_ring("claude", [None], NOW)
    assert pct is None and win is None and tip.startswith(ul.NO_SOURCE)
    old = ul.parse_claude(_claude_rej("2027-01-15T07:10:00Z", NOW - 5))[0]
    assert ul.provider_ring("claude", [old], NOW)[0] is None
    act = ul.parse_claude(_claude_rej("2027-01-15T07:10:00Z", NOW + 7200))[0]
    pct, win, tip = ul.provider_ring("claude", [act], NOW)
    assert pct == 100.0 and win == "5h" and "2 ώ 0 λ" in tip
    cx = ul.parse_codex(_codex_rec("2027-01-15T07:00:00Z", 5.0, NOW - 1, 30.0, NOW + 3600))
    pct, win, tip = ul.provider_ring("codex", cx, NOW)
    assert pct == 30.0 and win == "7d" and "ανανεώθηκε" in tip              # 5h window passed: not shown as 0 %
    assert ul.provider_ring("codex", [], NOW) == (None, None, ul.NO_SOURCE)
    h = ul.ring_html("Codex", [], "#10a37f", NOW, empty_tip='a "q" <i>')
    assert "—" in h and "&quot;q&quot;" in h and "<i>" not in h


def test_windows_and_ring_html():
    st = {"five_hour": {"used_percentage": 23.4, "resets_at": NOW + 2 * 3600 + 14 * 60 + 5},
          "seven_day": {"used_percentage": 41, "resets_at": NOW + 5 * 86400}, "as_of": NOW - 30}
    w = ul.claude_windows(st, None, NOW)
    assert [x["label"] for x in w] == ["5ω", "7ημ"] and w[0]["pct"] == 23.4
    assert ul.win_line(w[0], NOW) == "23% χρησιμοποιημένο · reset σε 2ω 14λ"
    assert ul.win_line(w[1], NOW) == "41% χρησιμοποιημένο · reset σε 120ω 0λ"
    assert ul.headline(w) == 41
    h = ul.ring_html("Claude", w, "#d97757", NOW)
    assert "<details" in h and "<summary" in h and "stroke-dasharray" in h and "#d97757" in h
    assert "23% χρησιμοποιημένο · reset σε 2ω 14λ" in h and "7ημ" in h and "<script" not in h
    c = 2 * 3.141592653589793 * 11
    assert f"{c * 0.41:.2f} {c:.2f}" in h                                  # arc length proportional to %
    # 5h window already reset -> «—» with the reset hint; headline falls back to the valid window
    st["five_hour"]["resets_at"] = NOW - 1
    w = ul.claude_windows(st, None, NOW)
    assert w[0]["pct"] is None and ul.win_line(w[0], NOW) == "— · " + ul.RESET_TIP and ul.headline(w) == 41
    st["seven_day"]["resets_at"] = NOW - 1
    w = ul.claude_windows(st, None, NOW)
    h = ul.ring_html("Claude", w, "#d97757", NOW)
    assert ul.headline(w) is None and ">—</text>" in h and ul.RESET_TIP in h
    # colours: amber >= 75, red >= 90
    assert ul.ring_color(74.9, "#x") == "#x" and ul.ring_color(75, "#x") == ul.AMBER and ul.ring_color(90, "#x") == ul.RED
    assert ul.RED in ul.ring_html("C", [ul._win("5ω", 95.0, NOW + 60, NOW)], "#x", NOW)
    # fallback: no statusline file -> active log rejection (100 %), else nothing
    rej = ul.parse_claude(_claude_rej("2027-01-15T07:10:00Z", NOW + 600))[0]
    assert ul.claude_windows(None, rej, NOW)[0]["pct"] == 100.0 and ul.claude_windows({}, None, NOW) == []
    assert ul.claude_windows({"five_hour": {"used_percentage": "x"}}, None, NOW) == []
    # codex reset window -> «—»
    cx = ul.codex_windows(ul.parse_codex(_codex_rec("2027-01-15T07:00:00Z", 5.0, NOW - 1, 30.0, NOW + 3600)), NOW)
    assert cx[0]["pct"] is None and cx[1]["pct"] == 30.0 and [x["label"] for x in cx] == ["5ω", "7ημ"]


def test_load_claude_status():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "claude.json")
    assert ul.load_claude_status(p) is None
    with open(p, "w") as f:
        f.write("{bad")
    assert ul.load_claude_status(p) is None
    with open(p, "w") as f:
        json.dump({"five_hour": {"used_percentage": 1, "resets_at": 2}}, f)
    assert ul.load_claude_status(p)["five_hour"]["used_percentage"] == 1


def test_offers_file():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "o.json")
    assert ul.load_offers(p) == []
    with open(p, "w") as f:
        json.dump([{"provider": "x", "title": "t", "url": "https://e", "as_of": "2027-01-01"}, {"no": "title"}, 3], f)
    assert ul.load_offers(p) == [{"provider": "x", "title": "t", "url": "https://e", "as_of": "2027-01-01", "note": "",
                                  "source": "", "added_at": ""}]
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "free_offers.json")) as f:
        assert json.load(f) == []                        # shipped empty: no invented offers
    o = {"added_at": "2027-01-15T08:00:00Z", "as_of": "2027-01-10"}
    t = ul._ts("2027-01-15T08:00:00Z")
    assert ul.offer_is_new(o, t - 1) and not ul.offer_is_new(o, t + 1) and not ul.offer_is_new({"as_of": "x"}, 0)
    assert ul.offer_is_new({"as_of": "2027-01-10"}, 0)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("  ok ", n)
