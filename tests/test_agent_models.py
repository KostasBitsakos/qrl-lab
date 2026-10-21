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


def test_deputy_identity_and_race_use_actual_model():
    events = [{"hook_event_name": "SessionStart", "ts": 1, "model": "claude-opus-5-5"},
              {"hook_event_name": "PreToolUse", "ts": 99, "tool_name": "Bash"},
              {"hook_event_name": "SubagentStart", "ts": 90, "agent_id": "log-d", "agent_type": "codex-deputy",
               "model": "gpt-6-astra", "effort": "high", "task": "Fix dashboard"}]
    health = {"claude": {"state": "limit"}, "codex": {"state": "ok"}}
    identity = am.coordinator_identity(events, health, 100)
    assert (identity["provider"], identity["role"], identity["model"], identity["active"]) == (
        "Codex", "codex-deputy", "gpt-6-astra", True)
    lanes = race_view.lanes(events, now=100, health=health, coord_model="claude-opus-5-5")
    assert lanes[0]["model"] == "gpt-6-astra" and lanes[0]["status"] == "running"
    assert len(lanes) == 1 and lanes[0]["reasons"] == []
    rendered = race_view.render(lanes, 100)
    assert "Codex" in rendered and "codex-deputy" in rendered and "gpt-6-astra" in rendered
    assert "claude-opus" not in rendered and "Πάρις" not in rendered
    stopped = events + [{"hook_event_name": "SubagentStop", "ts": 101, "agent_id": "log-d"}]
    assert not am.coordinator_identity(stopped, health, 102)["active"]
    assert race_view.lanes(stopped, now=102, health=health)[0]["status"] == "idle"
    resumed = stopped + [{"hook_event_name": "SessionStart", "ts": 103, "model": "claude-opus-5-5"}]
    assert am.coordinator_identity(resumed, {"state": "ok"}, 104)["provider"] == "Claude"


def test_limit_does_not_invent_deputy_or_reuse_old_claude_model():
    events = [{"hook_event_name": "SessionStart", "ts": 1, "model": "claude-opus-5-5"}]
    i = am.coordinator_identity(events, {"state": "limit"}, 100)
    assert i["provider"] == am.UNKNOWN and i["model"] == "" and not i["active"]
    assert am.coordinator_identity([], now=100)["model"] == ""
    # An unrelated Codex worker never becomes the coordinator.
    events.append({"hook_event_name": "SubagentStart", "ts": 99, "agent_type": "codex-engineer",
                   "agent_id": "e", "model": "gpt-6-sol"})
    assert am.coordinator_identity(events, {"state": "limit"}, 100)["model"] == ""


def test_latest_actor_and_card():
    ev = [{"hook_event_name": "SessionStart", "ts": 10, "model": "claude-opus-5-5"},
          {"hook_event_name": "PreToolUse", "ts": 20, "tool_name": "Bash"}]
    ok = {"claude": {"state": "ok"}}
    assert am.coordinator_identity(ev, ok, 30)["card"] == "🧭 Συντονιστής (Claude) · μοντέλο claude-opus-5-5"
    import datetime as dt
    msg = {"author": "codex", "id": "M-1", "model": "gpt-6.1-sol · low · αναπληρωτής",
           "ts": dt.datetime.fromtimestamp(40).isoformat()}
    i = am.coordinator_identity(ev, ok, 50, messages=[msg])
    assert i["card"] == "🧭 Συντονιστής (Codex αναπληρωτής) · μοντέλο gpt-6.1-sol" and not i["active"]
    ev.append({"hook_event_name": "PreToolUse", "ts": 45, "tool_name": "Bash"})  # Claude acted later again
    assert am.coordinator_identity(ev, ok, 50, messages=[msg])["provider"] == "Claude"


def test_selector_options():
    assert am.MODEL_CHOICES[None].startswith("Πάρις")
    for m in ("claude-opus-5-5", "claude-fable-5-1", "gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"):
        assert m in am.MODEL_CHOICES
    assert am.effort_choices("claude-haiku-5-5") == ("low", "medium", "high")
    assert "xhigh" in am.effort_choices("gpt-6.1-sol") and "ultra" not in am.effort_choices("gpt-6-luna")


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("  ok ", n)
