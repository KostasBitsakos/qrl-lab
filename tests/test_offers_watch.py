"""Tests for tools/offers_watch.py on fixtures (no network). Run: taskset -c 4-7 .venv/bin/python tests/test_offers_watch.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import offers_watch as ow  # noqa: E402

TMP = tempfile.mkdtemp()
for n, f in (("STATE", "s.json"), ("CANDS", "c.json"), ("EVENTS", "e.jsonl"), ("HEARTBEAT", "hb")):
    setattr(ow, n, os.path.join(TMP, f))

RSS = b"""<rss><channel><item><title>Old post</title><link>https://openai.com/a</link><guid>a</guid></item>%s</channel></rss>"""
NEW = b"""<item><title>Free Codex credits for all</title><link>https://openai.com/b</link><guid>b</guid></item>
<item><title>Boring update</title><link>https://openai.com/c</link><guid>c</guid></item>
<item><title>Evil offer</title><link>https://evil.example/d</link><guid>d</guid></item>"""
HTML = b"""<html><body><a href="/news/x">Claude gets higher limits</a><a href="/other">free</a>
<h2 id="r1">Weekly limits reset</h2><p>All users get a bonus.</p><h2 id="r2">Fixes</h2><p>bugs</p></body></html>"""


def test_parse():
    assert [i["id"] for i in ow.parse_items("rss", "u", RSS % b"")] == ["a"]
    L = ow.parse_items("links:/news/", "https://www.anthropic.com/news", HTML)
    assert L[0]["url"] == "https://www.anthropic.com/news/x" and len(L) == 1
    S = ow.parse_items("sections", "https://s/x", HTML)
    assert [s["title"] for s in S] == ["Weekly limits reset", "Fixes"] and S[0]["url"].endswith("#r1")
    assert ow.matched_words("Free credits and a RESET") == ["credits", "free", "reset"]
    assert ow.matched_words("nothing here") == []


def test_detect_resets():
    now = 1000.0
    prev = {"codex:5h": (90.0, 900.0), "claude:7d": (50.0, 5000.0)}
    cur = {"codex:5h": (3.0, 19000.0), "claude:7d": (52.0, 5000.0), "claude:5h": (1.0, 9.0)}
    ev = ow.detect_resets(prev, cur, now)
    assert [(e["provider"], e["window"]) for e in ev] == [("codex", "5h")]
    assert ow.detect_resets(prev, prev, now) == []


def test_run_once():
    state = {"n": 0}

    def fetcher(url):
        if "rss" not in url:
            raise OSError("down")
        return RSS % (b"" if state["n"] == 0 else NEW)
    ow.SOURCES[:] = [s for s in ow.SOURCES if s[3] == "rss"] + [ow.SOURCES[0]]
    ev, err = ow.run_once(100.0, fetcher=fetcher, codex=[{"window": "5h", "used_percent": 90.0, "resets_at": 150.0}], claude=None)
    assert ev == [] and "Anthropic news" in err               # seeding: nothing, one source error isolated
    state["n"] = 1
    ev, _ = ow.run_once(200.0, fetcher=fetcher, codex=[{"window": "5h", "used_percent": 2.0, "resets_at": 18150.0}], claude=None)
    kinds = sorted(e["kind"] for e in ev)
    assert kinds == ["candidate", "limit_reset"], ev
    c = json.load(open(ow.CANDS))
    assert len(c) == 1 and c[0]["status"] == "unverified" and c[0]["title"].startswith("Free Codex")
    ev, _ = ow.run_once(300.0, fetcher=fetcher, codex=[], claude=None)
    assert ev == []                                            # no duplicates
    assert len(open(ow.EVENTS).read().splitlines()) == 2 and os.path.exists(ow.HEARTBEAT)


def test_refuse_unofficial():
    try:
        ow.fetch("https://evil.example/x")
    except ValueError:
        return
    raise AssertionError("unofficial URL fetched")


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
