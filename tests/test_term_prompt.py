import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import term_prompt as tp

PANE = """ some output
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for this command
   3. No
 Esc to cancel
"""
PANE_BAD = PANE.replace("1. Yes", "1. Yes, and don't ask again")
PANE_OTHER = PANE.replace("proceed", "delete everything")


def setup(monkeypatch, tmp_path, pane):
    sent = []
    monkeypatch.setenv("QRL_LAB_DIR", str(tmp_path))
    (tmp_path / ".lab").mkdir()
    monkeypatch.setattr(tp, "capture", lambda: pane)
    monkeypatch.setattr(tp, "send", lambda k: sent.append(k) or True)
    return sent


def log(tmp_path):
    return [json.loads(l) for l in (tmp_path / ".lab" / "events.jsonl").read_text().splitlines()]


def test_same_prompt_sends(monkeypatch, tmp_path):
    sent = setup(monkeypatch, tmp_path, PANE)
    _, h = tp.current()
    assert h
    assert tp.answer("approve", h, "t", True)[0] and sent == ["1"]
    assert tp.answer("deny", h, "t", True)[0] and sent == ["1", "Escape"]
    assert log(tmp_path)[0]["result"] == "sent"


def test_changed_prompt_refuses(monkeypatch, tmp_path):
    sent = setup(monkeypatch, tmp_path, PANE)
    _, h = tp.current()
    monkeypatch.setattr(tp, "capture", lambda: PANE_OTHER)
    assert not tp.answer("approve", h, "x", True)[0] and not sent
    monkeypatch.setattr(tp, "capture", lambda: "nothing here")
    assert not tp.answer("deny", h, "x", True)[0] and not sent


def test_option1_always_refuses_approve_only(monkeypatch, tmp_path):
    sent = setup(monkeypatch, tmp_path, PANE_BAD)
    _, h = tp.current()
    assert not tp.answer("approve", h, "x", True)[0] and not sent
    assert tp.answer("deny", h, "x", True)[0] and sent == ["Escape"]


def test_locked_refuses(monkeypatch, tmp_path):
    sent = setup(monkeypatch, tmp_path, PANE)
    _, h = tp.current()
    assert not tp.answer("approve", h)[0] and not tp.answer("deny", h, "x", False)[0] and not sent
