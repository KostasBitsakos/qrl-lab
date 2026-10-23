"""Tests for tools/claude_statusline.py with synthetic stdin fixtures. Run: .venv/bin/python tests/test_claude_statusline.py"""
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import claude_statusline as cs  # noqa: E402

FULL = {"session_id": "s", "transcript_path": "/x/t.jsonl", "cwd": "/home/u", "model": {"id": "claude-opus", "display_name": "Opus"},
        "cost": {"total_cost_usd": 1.2}, "rate_limits": {"five_hour": {"used_percentage": 23.4, "resets_at": 1800000000},
                                                          "seven_day": {"used_percentage": 41, "resets_at": 1800400000}}}


def _run(stdin_text, path):
    out = io.StringIO()
    rc = cs.main(io.StringIO(stdin_text), out, path)
    return rc, out.getvalue()


def test_full_input_writes_only_whitelisted():
    p = os.path.join(tempfile.mkdtemp(), "usage", "claude.json")      # dir is created
    rc, out = _run(json.dumps(FULL), p)
    assert rc == 0 and out == "Opus · 5ω 23% · 7ημ 41%\n"
    d = json.load(open(p))
    assert set(d) == {"five_hour", "seven_day", "as_of", "model", "session_cost_usd", "session_id"} and d["model"] == "Opus"
    assert d["five_hour"] == {"used_percentage": 23.4, "resets_at": 1800000000.0}
    assert d["session_cost_usd"] == 1.2 and d["session_id"] == "s" and "transcript_path" not in json.dumps(d)
    st = json.load(open(os.path.join(os.path.dirname(p), "extra_credits_state.json"))) if os.path.exists(os.path.join(os.path.dirname(p), "extra_credits_state.json")) else {}
    assert st == {}  # no purchase config in this temp dir
    assert [f for f in os.listdir(os.path.dirname(p)) if f.endswith(".tmp")] == []


def test_partial_and_missing_windows():
    p = os.path.join(tempfile.mkdtemp(), "claude.json")
    rc, out = _run(json.dumps({"model": {"display_name": "Sonnet"}, "rate_limits": {"seven_day": {"used_percentage": 5}}}), p)
    assert out == "Sonnet · 7ημ 5%\n"
    d = json.load(open(p))
    assert "five_hour" not in d and d["seven_day"] == {"used_percentage": 5.0, "resets_at": None}
    # no rate_limits at all: prints the model, keeps the previous reading
    rc, out = _run(json.dumps({"model": {"display_name": "Sonnet"}}), p)
    assert rc == 0 and out == "Sonnet\n" and json.load(open(p))["seven_day"]["used_percentage"] == 5.0


def test_bad_input_never_fails():
    p = os.path.join(tempfile.mkdtemp(), "claude.json")
    for bad in ["", "{not json", "[1,2]", "null", json.dumps({"rate_limits": "x"}),
                json.dumps({"model": "str", "rate_limits": {"five_hour": {"used_percentage": True}}}),
                json.dumps({"rate_limits": {"five_hour": {"used_percentage": "50"}}})]:
        rc, out = _run(bad, p)
        assert rc == 0 and out == "Claude\n", (bad, out)
    assert not os.path.exists(p)
    # unwritable target: status line still printed with the values
    rc, out = _run(json.dumps(FULL), "/proc/qrl-nope/claude.json")
    assert rc == 0 and out.startswith("Opus · 5ω 23%")


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("  ok ", n)
