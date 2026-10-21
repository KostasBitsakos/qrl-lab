"""Tests for tools/offers_check.py. Run: .venv/bin/python tests/test_offers_check.py"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
sys.path.insert(0, TOOLS)
import offers_check as oc  # noqa: E402

NOW = dt.datetime(2027, 1, 15, 8, 0, tzinfo=dt.timezone.utc)


def _c(url, **kw):
    e = {"provider": "Anthropic", "title": "t", "url": url, "as_of": "2027-01-14", "note": "", "source": ""}
    e.update(kw)
    return e


def test_domain_allowlist():
    ok = ["https://www.anthropic.com/news/x", "https://claude.ai/x", "https://claude.com", "https://support.anthropic.com/a",
          "https://openai.com/index/x", "https://help.openai.com/en/x", "https://chatgpt.com/x", "https://docs.claude.com:443/x"]
    bad = ["http://anthropic.com/x", "https://evilanthropic.com/x", "https://anthropic.com.evil.io/x",
           "https://user@anthropic.com/x", "https://anthropic.com:8443/x", "ftp://openai.com", "https://", "javascript:alert(1)",
           "https://x.com/?u=https://openai.com", "https://anthropic.com:bad/x"]
    assert all(oc.official_https(u) for u in ok), [u for u in ok if not oc.official_https(u)]
    assert not any(oc.official_https(u) for u in bad), [u for u in bad if oc.official_https(u)]


def test_validate():
    assert oc.validate(_c("https://openai.com/a"))[1] is None
    assert oc.validate(_c("https://openai.com/a", title=""))[1] == "missing title"
    assert oc.validate(_c("https://openai.com/a", as_of="soon"))[1].startswith("as_of")
    assert oc.validate(_c("https://openai.com/a", source="https://reddit.com/r/x"))[1].startswith("source")
    assert oc.validate(_c("https://openai.com/a", note=5))[1] == "note is not a string"
    assert oc.validate("x")[1] == "not an object"


def test_merge_dedupe_and_new():
    p = os.path.join(tempfile.mkdtemp(), "o.json")
    r = oc.merge([_c("https://openai.com/a/"), _c("https://OpenAI.com/a#frag"), _c("http://openai.com/b"),
                  _c("https://claude.ai/c", source="https://support.anthropic.com/s")], p, now=NOW)
    assert [e["url"] for e in r["added"]] == ["https://openai.com/a/", "https://claude.ai/c"]
    assert len(r["duplicates"]) == 1 and r["rejected"][0]["reason"].startswith("url")
    d = json.load(open(p))
    assert len(d) == 2 and d[0]["added_at"] == "2027-01-15T08:00:00Z"
    r = oc.merge(_c("https://openai.com/a"), p, now=NOW)                    # single object, already present
    assert r["added"] == [] and len(r["duplicates"]) == 1 and len(json.load(open(p))) == 2
    r = oc.merge([_c("https://chatgpt.com/z")], p, dry_run=True)
    assert len(r["added"]) == 1 and len(json.load(open(p))) == 2
    with open(p, "w") as f:
        f.write("{}")
    try:
        oc.merge([_c("https://chatgpt.com/z")], p)
        raise AssertionError("non-list file must not be overwritten")
    except ValueError:
        pass


def test_cli():
    d = tempfile.mkdtemp()
    p, c = os.path.join(d, "o.json"), os.path.join(d, "c.json")
    json.dump([_c("https://anthropic.com/n")], open(c, "w"))
    out = subprocess.run([sys.executable, os.path.join(TOOLS, "offers_check.py"), c, "--file", p],
                         capture_output=True, text=True, check=True).stdout
    assert len(json.loads(out)["added"]) == 1 and len(json.load(open(p))) == 1


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("  ok ", n)
