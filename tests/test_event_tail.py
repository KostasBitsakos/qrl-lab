"""Tests for tools/event_tail.py (incremental JSONL tail). Run: .venv/bin/python -m pytest tests/test_event_tail.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import event_tail  # noqa: E402


def _w(path, recs, mode="a", partial=""):
    with open(path, mode) as f:
        f.write("".join(json.dumps(r) + "\n" for r in recs) + partial)


def test_incremental_append_partial_and_rotation():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "events.jsonl")
    t = event_tail.EventTail(p, keep=5)
    assert t.refresh() == (0, [])                                   # missing file: empty, no error
    _w(p, [{"i": i} for i in range(3)], "w")
    v1, r = t.refresh()
    assert [e["i"] for e in r] == [0, 1, 2]
    assert t.refresh()[0] == v1                                     # unchanged file: same version, nothing re-parsed
    _w(p, [{"i": 3}], partial='{"i": 4')                            # writer mid-line: the cut line waits
    v2, r = t.refresh()
    assert v2 > v1 and [e["i"] for e in r] == [0, 1, 2, 3]
    with open(p, "a") as f:
        f.write('}\nnot json\n[1]\n')                                # completes line 4; junk and non-dicts skipped
    _w(p, [{"i": 5}, {"i": 6}])
    assert [e["i"] for e in t.refresh()[1]] == [2, 3, 4, 5, 6]      # keep=5 most recent
    _w(p, [{"i": 9}], "w")                                          # truncated/rewritten: full re-read
    assert [e["i"] for e in t.refresh()[1]] == [9]
    _w(p, [{"i": 7, "pad": "y" * 80}, {"i": 8}], "w")               # rewritten in place, LONGER than before
    assert [e["i"] for e in t.refresh()[1]] == [7, 8]
    os.replace(p, p + ".old")
    _w(p, [{"i": 10}], "w")                                          # rotated (new inode)
    assert [e["i"] for e in t.refresh()[1]] == [10]
    os.remove(p)
    assert t.refresh()[1] == []


def test_mid_file_tail_skips_cut_first_line():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "events.jsonl")
    _w(p, [{"i": i, "pad": "x" * 50} for i in range(100)], "w")
    t = event_tail.EventTail(p, keep=1000, tail_bytes=1000)
    r = t.refresh()[1]
    assert r and r[-1]["i"] == 99 and all(set(e) == {"i", "pad"} for e in r)
    assert [e["i"] for e in r] == list(range(r[0]["i"], 100))       # contiguous, nothing half-parsed


if __name__ == "__main__":
    test_incremental_append_partial_and_rotation()
    test_mid_file_tail_skips_cut_first_line()
    print("ok")
