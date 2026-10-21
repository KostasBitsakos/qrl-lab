"""Tests for tools/agent_models.py (model shown per agent task). Run: .venv/bin/python tests/test_agent_models.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import agent_models as am  # noqa: E402
import race_view  # noqa: E402


def _ev():
    return [
        {"hook_event_name": "SessionStart", "source": "startup", "model": "claude-opus-5-1", "ts": 1},
        {"hook_event_name": "SessionStart", "source": "compact", "model": "claude-opus-5-5", "ts": 2},
        # hook start without model + agent_log start of the same role 9 min later -> agent_log model
        {"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "engineer", "ts": 1000},
        {"hook_event_name": "SubagentStart", "agent_id": "log-1", "agent_type": "engineer", "model": "claude-opus-5-5",
         "effort": "high", "ts": 1540},
        # Agent call with model, then the hook start 2 s later -> hook model
        {"hook_event_name": "PreToolUse", "tool_name": "Agent", "summary": "scholar: find venues",
         "agent_model": "opus", "ts": 2000},
        {"hook_event_name": "SubagentStart", "agent_id": "s1", "agent_type": "scholar", "ts": 2002},
        # nothing known -> frontmatter default / unknown
        {"hook_event_name": "SubagentStart", "agent_id": "w1", "agent_type": "writer", "ts": 3000},
        {"hook_event_name": "SubagentStart", "agent_id": "x1", "agent_type": "mystery", "ts": 3001},
        # a second engineer far away in time does NOT reuse the agent_log entry
        {"hook_event_name": "SubagentStart", "agent_id": "a2", "agent_type": "engineer", "ts": 9000},
        {"hook_event_name": "SubagentStart", "agent_id": "log-c", "agent_type": "codex-reviewer", "model": "gpt-6.1-sol", "ts": 9100},
    ]


def test_resolve_order():
    r = am.resolve(_ev(), {"writer": "sonnet", "engineer": "sonnet"})
    assert r["a1"] == ("claude-opus-5-5", "agent_log")
    assert r["s1"] == ("opus", "hook")
    assert r["w1"] == ("sonnet", "default") and am.text(*r["w1"]) == "προεπιλογή: sonnet"
    assert r["x1"] == ("", "unknown") and am.text(*r["x1"]) == "άγνωστο"
    assert r["a2"] == ("sonnet", "default"), r["a2"]
    assert r["log-c"] == ("gpt-6.1-sol", "agent_log") and r["log-1"][0] == "claude-opus-5-5"
    assert am.coordinator_model(_ev()) == "claude-opus-5-5" and am.coordinator_model([]) == ""


def test_hook_call_must_match_type_and_precede():
    ev = [{"hook_event_name": "PreToolUse", "tool_name": "Agent", "summary": "runner: go", "agent_model": "haiku", "ts": 10},
          {"hook_event_name": "SubagentStart", "agent_id": "e", "agent_type": "engineer", "ts": 11},
          {"hook_event_name": "SubagentStart", "agent_id": "r", "agent_type": "runner", "ts": 100}]
    r = am.resolve(ev)
    assert r["e"] == ("", "unknown") and r["r"] == ("", "unknown")      # wrong type / too late


def test_defaults_from_frontmatter():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".claude", "agents"))
    with open(os.path.join(d, ".claude", "agents", "engineer.md"), "w") as f:
        f.write("---\nname: engineer\ndescription: x: y\nmodel: sonnet\n---\nbody\nmodel: opus\n")
    with open(os.path.join(d, ".claude", "agents", "plain.md"), "w") as f:
        f.write("no frontmatter")
    assert am.defaults_from_agents_dir(d) == {"engineer": "sonnet"}


def test_race_lane_shows_resolved_model():
    ev = _ev()
    m = {aid: am.text(*v) for aid, v in am.resolve(ev, {"writer": "sonnet"}).items()}
    ln = race_view.lanes(ev, now=3010, roles={"engineer": ("engineer", "#e87ba4")}, models=m,
                         coord_model=am.coordinator_model(ev))
    by = {r.get("role"): r for r in ln}
    assert by["coordinator"]["model"] == "claude-opus-5-5"
    h = race_view.render(ln, 3010)
    assert "engineer · claude-opus-5-5" in h and "προεπιλογή: sonnet" in h and "Sonnet" not in h


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("  ok ", n)
