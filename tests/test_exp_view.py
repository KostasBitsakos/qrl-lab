"""Tests for tools/exp_view.py (experiments tab helpers, M-20261021-008). Run: .venv/bin/python tests/test_exp_view.py"""
import datetime as dt
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import exp_view as ev  # noqa: E402


class _C:
    """Stand-in for code-tuning/tuning/closeness.py with the same formulas (paper targets)."""
    import math
    DERP_T, DINOS_T = 2.2e5, 3.8e6

    @classmethod
    def part(cls, x, t):
        return 0.0 if x is None or x <= 0 else max(0.0, 1.0 - abs(cls.math.log10(x / t)))

    @classmethod
    def score(cls, di, de):
        rt = cls.DINOS_T / cls.DERP_T
        r = max(0.0, 1.0 - abs(cls.math.log10((di / de) / rt)) / max(abs(cls.math.log10(rt)), 1.0))
        p = {"derp": cls.part(de, cls.DERP_T), "dinos": cls.part(di, cls.DINOS_T), "ratio": r}
        p["total"] = sum(p.values()) / 3
        return p


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)


def _res(arm, agent, seed, val, test, variant="spike300_d5", **kw):
    cr = {str(c): {"val": {"mean_ret": v}, "test9": {"mean_ret": t, "mean_pods": 2.0, "episodes": []}}
          for c, v, t in zip((10000, 20000), val, test)}
    return dict(protocol="c5", arm=arm, agent=agent, seed=seed, orig_variant=variant, env_family="orig",
                eval_splits=["val", "test9"], checkpoint_results=cr, **kw)


def test_live_reader_and_candidates():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "c99", "live", "a.json")
    _write(p, {"cols": ["t", "phase", "load", "pods"], "rows": [[1, "train", 50.0, 6], [2, "eval", 51.0, 7], [3, "bad"]],
               "arm": "derp"})
    old = os.path.join(d, "c98", "live", "b.json")
    _write(old, {"cols": ["t"], "rows": []})
    os.utime(old, (time.time() - 1000, time.time() - 1000))
    _write(os.path.join(d, "c99", "x.json"), {"not": "live"})
    c = ev.live_candidates(d, time.time())
    assert [x[0] for x in c] == [p], c
    r = ev.read_live(p)
    assert r["columns"]["t"] == [1, 2] and r["columns"]["phase"] == ["train", "eval"] and r["arm"] == "derp"
    with open(p, "w") as f:
        f.write("{half")
    assert ev.read_live(p) is None


def test_result_listing_and_paths():
    assert ev.is_main_result("/r/c13a/a-s1.json") and not ev.is_main_result("/r/c13a/a-s1.ck10000.json")
    assert not ev.is_main_result("/r/c13a/baselines-x.json") and not ev.is_main_result("/r/c13a/live/a.json")
    assert ev.out_path_of(json.dumps(["py", "x.py", "--out", "tuning/r/a.json"]), "/w") == "/w/tuning/r/a.json"
    assert ev.out_path_of(["py"], "/w") is None
    assert ev.driver_files([["python3", ".lab/tuning/drive_chunks.py", ".lab/tuning/c15_entries.json", "c15"],
                            ["bash"]]) == {"c15_entries.json"}


def test_select_ck_and_closeness():
    r = _res("derp", "derp", 1, (100.0, 90.0), (40000.0, 50000.0))
    assert ev.select_ck(r) == 10000 and ev.test_split(r) == "test9"
    c = ev.run_closeness(_C, r)
    assert c["x"] == 200000.0 and c["kind"] == "derp" and abs(c["part"] - _C.part(2e5, 2.2e5)) < 1e-12
    assert ev.run_closeness(_C, _res("lstm_scratch", "lstm_scratch", 1, (1, 2), (3, 4))).get("part") is None
    rs = [_res("derp", "derp", s, (1.0, 2.0), (50000.0 + s, 58000.0 + s)) for s in (1, 2)] + \
         [_res("transfer_orig_orig_d0", "dinos_t", s, (2.0, 1.0), (88000.0, 70000.0)) for s in (1, 2)]
    am = ev.folder_arm_means(rs)
    assert am[("spike300_d5", "derp")]["ck"] == 20000 and am[("spike300_d5", "derp")]["mean"] == 58001.5
    assert am[("spike300_d5", "transfer_orig_orig_d0")]["ck"] == 10000
    fs = ev.folder_scores(_C, am)["spike300_d5"]
    ref = _C.score(5 * 88000.0, 5 * 58001.5)
    assert abs(fs["total"] - ref["total"]) < 1e-12 and abs(fs["ratio_part"] - ref["ratio"]) < 1e-12
    assert abs(fs["ratio"] - 88000.0 / 58001.5) < 1e-12


def test_param_rows_unknown_and_intro():
    r = _res("derp", "derp", 3, (1, 2), (3, 4), learning_rate=1e-4, epsilon_start=1.0, n_params=17923)
    rows = ev.param_rows(r, None, "/x/a.json")
    by = {x["παράμετρος"]: x for x in rows}
    assert by["learning rate"]["τιμή"] == "0.0001" and "learning_rate" in by["learning rate"]["πηγή"]
    assert by["gamma"]["τιμή"] == ev.UNKNOWN and "agent_introspect" in by["gamma"]["πηγή"]
    assert by["layers"]["τιμή"] == ev.UNKNOWN
    intro = {"hyper": {"gamma": {"value": 0.95, "source": "tuning/legacy/ddqnagent.py:20"}},
             "layers": [{"name": "fc1", "type": "Linear", "in": 7, "units": 128, "activation": "ReLU",
                         "connection": "fully connected (dense)"}], "network_source": "n.py:8",
             "reward_lines": {"orig": [{"line": "reward = min(c, l) - 3 * vms", "source": "env_orig.py:91"}]}}
    by = {x["παράμετρος"]: x for x in ev.param_rows(r, intro)}
    assert by["gamma"]["τιμή"] == "0.95" and by["gamma"]["πηγή"].endswith(":20")
    assert "units 128" in by["1. fc1"]["τιμή"] and "ReLU" in by["1. fc1"]["τιμή"]
    assert by["τύπος (env)"]["πηγή"] == "env_orig.py:91"
    assert ev.intro_key(r) == ("derp", "verbatim", 6, 1, False)
    assert ev.intro_args(("dinos_t", "fixed", 7, 1, True))[-1] == "--transfer"


def test_forecast_and_history():
    f = ev.forecast([31, 37, 36, 36], steps=1)
    assert abs(f["slope"] - 1.4) < 1e-9 and abs(f["pred"] - 38.5) < 1e-9 and f["lo"] < f["pred"] < f["hi"]
    assert ev.forecast([50]) is None
    g = ev.forecast([90, 95, 99, 100])
    assert g["hi"] == 100.0 and g["pred"] <= 100.0
    h = ev.forecast([10, 10])
    assert h["band"] == 2.0 and h["pred"] == 10.0
    s = ev.primary_series(ev.SEED_HISTORY)
    assert [e["cycle"] for e in s] == ["c8", "c9b", "c10b", "c12a", "c13a"] and s[2]["variant"] == "orig_d10"
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t", "h.json")
    assert ev.ensure_history(p) == ev.SEED_HISTORY and ev.load_history(p) == ev.SEED_HISTORY


def test_remaining_runs():
    d = tempfile.mkdtemp()
    tdir, code = os.path.join(d, "tuning"), os.path.join(d, "code")

    def ent(n, out=None):
        return {"name": n, "cmd": ["py", "--out", out or f"r/{n}.json"]}
    _write(os.path.join(tdir, "a_entries.json"), [ent(f"a{i}") for i in range(10)])
    with open(os.path.join(tdir, "a_entries.json.launched"), "w") as f:
        f.write("6")
    _write(os.path.join(tdir, "b_entries.json"), [ent("a7"), ent("b1"), ent("b2")])     # a7 re-queued
    with open(os.path.join(tdir, "b_entries.json.launched"), "w") as f:
        f.write("1")
    # no counter: a8 is counted elsewhere; o1 orphan (no result); o2 has a result
    _write(os.path.join(tdir, "o_entries.json"), [ent("a8"), ent("o1"), ent("o2")])
    _write(os.path.join(code, "r", "o2.json"), {})
    r = ev.remaining_runs(tdir, code, running=5, drivers={"b_entries.json"})
    # pending: a6, a8, a9 (a7 launched via b), b1, b2 -> 5
    assert r["queued"] == 5 and r["orphan"] == 1 and r["running"] == 5 and r["total"] == 10, r
    files = {x["file"]: x for x in r["files"]}
    assert files["a_entries.json"]["remaining"] == 3 and files["b_entries.json"]["driver"]
    now = dt.datetime(2026, 10, 21, 11, 59, tzinfo=dt.timezone.utc)
    assert abs(ev.hours_left(now) - 12.0) < 1e-9


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("  ok ", n)


def test_variant_info_and_fit():
    import math
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    i = ev.variant_info(root, "orig_d5")
    assert i and i["noise_sd"] == 0.2 and i["spike_len"] == 100 and i["spike_pos"] == 1500 and not i["multi"]
    assert ev.variant_info(root, "noise15")["noise_sd"] == 15.0
    assert ev.variant_info(root, "multispike")["n_spikes"] == 4
    assert ev.variant_info(root, "bogus") is None
    t = list(range(3000, 3300))
    load = [50 + 50 * math.sin(i["omega"] * x + 0.7) for x in t]
    for k in range(100, 130):
        load[k] += 100
    fit, mask = ev.fit_sinusoid(t, load, i)
    assert max(abs(a - b) for a, b in zip(fit, [50 + 50 * math.sin(i["omega"] * x + 0.7) for x in t])) < 1
    assert all(mask[100:130:5]) and not any(mask[:90])


def test_branch_of():
    assert ev.branch_of("R-20261021-007") == "astra"
    assert ev.branch_of("R-20261021-005") == "opus"
    assert ev.branch_of(None, "/h/qrl-lab/code-tuning-astra/tuning") == "astra"
    assert ev.branch_of(None, "/h/qrl-lab/code-astra") == "astra"
    assert ev.branch_of(None, None, "/h/qrl-lab/code-tuning-astra/tuning/results/c1/x.json") == "astra"
    assert ev.branch_of("R-20261019-001", "/h/qrl-lab/code-tuning") == "opus"
    assert ev.branch_of() == "opus"
