"""Edit hold (no reply/dispatch while the researcher edits) and selector routing; temporary lab dir, no providers."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dispatcher  # noqa: E402
from labdb import LabDB, LabError  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("QRL_LAB_DIR", str(tmp_path))
    (tmp_path / ".lab").mkdir()
    return LabDB()


def test_agent_cannot_reply_while_editing(db):
    mid = db.researcher_send("hello")
    db.begin_edit(mid)
    with pytest.raises(LabError, match="being edited"):
        db.post("coordinator", "answer", mid)
    db.cancel_edit(mid)
    assert db.post("coordinator", "answer", mid)


def test_save_edit_requeues(db):
    mid = db.researcher_send("hello")
    db.begin_edit(mid)
    assert db.message(mid)["status"] == "editing"
    db.save_edit(mid, "hello 2")
    assert db.message(mid)["status"] == "new"


@pytest.mark.parametrize("model,effort,expect", [
    (None, None, (None, None, None)),
    ("opus", "high", ("claude", "opus", "high")),
    ("claude-sonnet-5-5", "med", ("claude", "claude-sonnet-5-5", "medium")),
    ("codex", "low", ("codex", None, "low")),
    ("gpt-6-sol", "ultra", ("codex", "gpt-6-sol", "ultra")),
    ("coordinator:gpt-6-astra", "high", ("codex", "gpt-6-astra", "high")),
    ("coordinator:claude-opus-5-5", None, ("claude", "claude-opus-5-5", None)),
])
def test_route_request(model, effort, expect):
    assert dispatcher.route_request(model, effort) == expect


def test_kb_savings_estimate(tmp_path):
    import json, time
    import token_metrics as tm
    assert tm.kb_savings(tmp_path) is None
    d = tmp_path / ".lab" / "kb"
    d.mkdir(parents=True)
    now = int(time.time())
    rows = [{"ts": now, "cmd": "query", "out_bytes": 1200}, {"ts": now, "cmd": "callers", "out_bytes": 400},
            {"ts": now - 90 * 86400, "cmd": "query", "out_bytes": 1200}]
    (d / "queries.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    r = tm.kb_savings(tmp_path)
    assert r["n"] == 1 and r["out_tok"] == 300
    assert r["saved_tok"] == round(tm.KB_GREP_TOK_PER_Q - 300)
    html = tm.card_html({"rows": [], "audit": {"status": "x"}, "used24": [], "kb": r})
    assert "ΕΚΤΙΜΗΣΗ" in html and "1 queries" in html
    assert "άγνωστο" in tm.card_html({"rows": [], "audit": {"status": "x"}, "used24": [], "kb": None})


def test_unknown_window_shows_future_reset_only():
    import time
    import extra_credits
    now = time.time()
    html = extra_credits.awake_html([dict(name="Claude", awake=True, badge="", windows=[
        {"label": "5ω", "pct": None, "resets_at": now + 3600}, {"label": "7ημ", "pct": None, "resets_at": now - 3600}])])
    assert "5ω: άγνωστο · επόμενο reset" in html and "7ημ: άγνωστο</div>" in html
