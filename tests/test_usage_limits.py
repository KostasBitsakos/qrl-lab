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
    h = ul.ring_html("Codex", None, None, 'a "q" <b>', "#10a37f")
    assert "—" in h and "&quot;q&quot;" in h and "<b>" not in h
    assert "30%" in ul.ring_html("Codex", 30.0, "7d", "t", "#10a37f")


def test_offers_file():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "o.json")
    assert ul.load_offers(p) == []
    with open(p, "w") as f:
        json.dump([{"provider": "x", "title": "t", "url": "https://e", "as_of": "2027-01-01"}, {"no": "title"}, 3], f)
    assert ul.load_offers(p) == [{"provider": "x", "title": "t", "url": "https://e", "as_of": "2027-01-01", "note": ""}]
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "free_offers.json")) as f:
        assert json.load(f) == []                        # shipped empty: no invented offers


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("  ok ", n)
