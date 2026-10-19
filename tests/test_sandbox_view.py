"""Tests for tools/sandbox_view.py. Run: .venv/bin/python tests/test_sandbox_view.py"""
import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import sandbox_view as sv  # noqa: E402


def test_summarize():
    ev = [{"event": "start", "run_id": "a", "name": "b0", "cores": [3], "ts": "2026-10-19T10:00:00+00:00"},
          {"event": "start", "run_id": "b", "name": "b0", "cores": [4], "ts": "2026-10-19T10:00:00+00:00"},
          {"event": "done", "run_id": "b", "wall_s": 5.0, "cpu_seconds": 4.5, "ts": "2026-10-19T10:00:05+00:00"}]
    now = dt.datetime(2026, 10, 19, 10, 1, tzinfo=dt.timezone.utc)
    v = sv.summarize(ev, {"a": {"name": "b0/e0"}, "b": {"name": "b0/e1", "status": "done"}}, now)
    assert v["running"][0]["run_id"] == "a" and v["running"][0]["elapsed_s"] == 60 and v["running"][0]["name"] == "b0/e0"
    assert v["finished"] == [{"run_id": "b", "name": "b0/e1", "wall_s": 5.0, "cpu_seconds": 4.5, "status": "done",
                              "ts": "2026-10-19T10:00:05+00:00"}]
    assert len(sv.summarize(ev * 1, {}, now, last=0)["finished"]) == 0


def test_read_ledger_skips_garbage():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "R-1.ledger.jsonl")
        open(p, "w").write('{"event":"start","run_id":"x"}\nnot json\n')
        assert len(sv.read_ledger(p)) == 1 and sv.ledger_paths(d) == [p]
        assert sv.read_ledger(os.path.join(d, "none")) == []


if __name__ == "__main__":
    test_summarize(); test_read_ledger_skips_garbage(); print("ok")
