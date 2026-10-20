"""Tests for tools/res_view.py and tools/token_savings.py. Run: .venv/bin/python tests/test_res_view.py"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import res_view as rv  # noqa: E402
import token_savings as ts  # noqa: E402


def test_redact():
    s = rv.redact(["python", "x.py", "--token", "abc", "--api-key=zzz", "GH_TOKEN=q", "A" * 40, "--seed", "0"])
    assert "abc" not in s and "zzz" not in s and "=q" not in s and "A" * 40 not in s
    assert "--seed 0" in s and "x.py" in s
    assert len(rv.redact(["a" * 500])) <= 120


def test_categorize_and_parse():
    assert rv.categorize("python", ["streamlit", "run"])[0] == "dashboard+agents"
    assert rv.categorize("claude", [])[0] == "dashboard+agents"
    assert rv.categorize("redis-server", [])[1] == "redis"
    assert rv.categorize("kubelet", [])[0] == "k8s"
    assert rv.categorize("bash", [])[0] == "other"
    assert rv.parse_cpu("3m") == 0.3 and rv.parse_cpu("2") == 200
    assert rv.parse_mem("9Mi") == 9 * 2**20 and rv.parse_mem("1Gi") == 2**30
    assert rv.batch_arm("c10a-39", "c10a-baselines-spike300_d10") == ("c10a", "baselines-spike300_d10")
    assert rv.batch_arm("c9b2-1", None)[0] == "c9b2"


def test_shares():
    it = [{"category": "k8s", "cpu": 5}, {"category": "k8s", "cpu": 3}, {"category": "other", "cpu": 2}]
    assert rv.shares(it, "cpu", 100) == {"k8s": 8, "other": 2, "free": 90}
    assert rv.shares(it, "cpu", 5)["free"] == 0


def test_token_savings():
    a = {k: dict(v) for k, v in ts.DEFAULTS.items()}
    r = ts.compute({"subagents": 2, "codex": 1, "skills": 0}, a)
    assert r["without"] == 2 * 6000 + 8000 and r["with"] == 2 * 600 + 800 and r["saved"] == r["without"] - r["with"]
    assert abs(r["pct"] - 100 * r["saved"] / r["without"]) < 1e-9
    assert ts.compute({}, a)["pct"] == 0.0


def test_count_events():
    with tempfile.TemporaryDirectory() as d:
        ev, lg = os.path.join(d, "e.jsonl"), os.path.join(d, "l.jsonl")
        rows = [{"hook_event_name": "SubagentStart", "agent_type": "engineer", "ts": 100},
                {"hook_event_name": "SubagentStart", "agent_type": "codex-reviewer", "ts": 100},
                {"hook_event_name": "SubagentStart", "agent_type": "codex:codex-rescue", "ts": 100},
                {"hook_event_name": "SubagentStart", "agent_type": "engineer", "ts": 1},
                {"hook_event_name": "PreToolUse", "tool_name": "Skill", "ts": 100},
                {"hook_event_name": "HealthState", "ts": 100}]
        open(ev, "w").write("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
        open(lg, "w").write(json.dumps({"event": "done", "ts": "1970-01-01T00:01:40+00:00"}) + "\n")
        n = ts.count_events(ev, [lg], 50, 200)
        assert n == {"subagents": 1, "codex": 1, "skills": 1, "sandbox_runs": 1, "health_events": 1}, n


def test_load_assumptions_missing():
    assert ts.load_assumptions("/nonexistent")["codex"]["without"] == 8000


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f()
    print("ok")
