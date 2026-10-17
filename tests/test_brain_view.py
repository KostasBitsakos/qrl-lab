"""Tests for tools/brain_view.py on synthetic events. Run: .venv/bin/python tests/test_brain_view.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import brain_view as bv  # noqa: E402

NOW = 1_000_000.0


def ev(name, ts, agent_type="", aid=None, **kw):
    d = {"hook_event_name": name, "ts": ts, "agent_type": agent_type}
    if aid:
        d["agent_id"] = aid
    d.update(kw)
    return d


def test_spawn_pulse_and_active():
    s = bv.derive([ev("SubagentStart", NOW - 2, "engineer", "a1")], [], NOW)
    assert s["nodes"]["engineer"]["active"] and not s["nodes"]["runner"]["active"]
    assert s["pulses"] == [{"src": "coordinator", "dst": "engineer", "age": 2.0, "kind": "spawn"}]


def test_stop_report_pulse_and_inactive():
    s = bv.derive([ev("SubagentStart", NOW - 20, "scholar", "a1"), ev("SubagentStop", NOW - 1, "", "a1")], [], NOW)
    assert not s["nodes"]["scholar"]["active"]
    assert [(p["src"], p["dst"], p["kind"]) for p in s["pulses"]] == [("scholar", "coordinator", "report")]


def test_old_pulse_expires_but_open_agent_stays_active():
    s = bv.derive([ev("SubagentStart", NOW - 600, "writer", "a1")], [], NOW)
    assert s["pulses"] == [] and s["nodes"]["writer"]["active"]


def test_lost_start_is_not_active_forever():
    s = bv.derive([ev("SubagentStart", NOW - 3 * 3600, "writer", "a1")], [], NOW)
    assert not s["nodes"]["writer"]["active"]


def test_agent_log_codex_roles():
    s = bv.derive([ev("SubagentStart", NOW - 1, "codex-reviewer", "log-1"),
                   ev("SubagentStart", NOW - 1, "codex:codex-rescue", "p1")], [], NOW)
    assert s["nodes"]["codex-reviewer"]["active"]
    assert len(s["pulses"]) == 1  # the bare plugin agent is ignored


def test_tool_events_activity():
    s = bv.derive([ev("PreToolUse", NOW - 5, "", None), ev("PostToolUse", NOW - 100, "Explore", "x")], [], NOW)
    assert s["nodes"]["coordinator"]["active"] and not s["nodes"]["Explore"]["active"]
    s = bv.derive([ev("PreToolUse", NOW - 5, "Explore", "x")], [], NOW)
    assert s["nodes"]["Explore"]["active"]


def test_future_events_ignored():
    assert bv.derive([ev("SubagentStart", NOW + 5, "engineer", "a")], [], NOW)["pulses"] == []


def test_messages_deputy_and_unknown_codex():
    import datetime as dt
    ts = dt.datetime.fromtimestamp(NOW - 1, dt.timezone.utc).isoformat()
    m = {"ts": ts, "author": "codex", "title": "Αναπληρωτής", "body": "x"}
    s = bv.derive([], [m], NOW)
    assert s["nodes"]["codex-deputy"]["active"]
    assert s["pulses"][0]["src"] == "codex-deputy" and s["pulses"][0]["dst"] == "coordinator"
    m2 = {"ts": ts, "author": "codex", "title": "t", "body": "b"}
    assert bv.derive([], [m2], NOW)["pulses"] == []  # role unknown: nothing invented
    m3 = {"ts": ts, "author": "codex", "title": "t", "body": "b"}
    s = bv.derive([ev("SubagentStart", NOW - 100, "codex-architect", "l")], [m3], NOW)
    assert s["pulses"][0]["src"] == "codex-architect"


def test_render_labels_and_stability():
    h = bv.render(bv.derive([], [], NOW))
    for r, (label, *_r) in bv.ROLES.items():
        assert f">{bv.LAYOUT[r][2]}</text>" in h and f"<title>{label} " in h  # short label, full name on hover
    full = bv.render(bv.derive([], [], NOW), full_names=True)
    assert ">codex-researcher</text>" in full and ">cdx-research</text>" in h
    assert h == bv.render(bv.derive([], [], NOW + 50))  # no wall clock in idle output
    assert len({v[1] for v in bv.ROLES.values()}) == len(bv.ROLES)  # distinct colours
    assert "class=\"fire\"" not in h and 'class="sp"' in h and "breathe" in h  # ambient only when idle
    h2 = bv.render(bv.derive([ev("SubagentStart", NOW - 2, "runner", "a")], [], NOW))
    assert h2.count('class="fire"') == 2 and "animation-delay:-2.0s" in h2
    assert 'class="ag on" data-role="runner"' in h2 and 'class="ag" data-role="engineer"' in h2


def test_mesh_geometry():
    edges = set(bv.mesh_edges())
    assert len(edges) > 60
    for r in bv.WORKERS:  # every agent reaches the coordinator along real mesh edges
        p = bv.mesh_path(r, bv.COORD)
        assert p[0] == bv._vertex(r) and p[-1] == bv._vertex(bv.COORD)
        assert all((min(a, b), max(a, b)) in edges for a, b in zip(p, p[1:]))
    assert all(bv.LAYOUT[r][0] in bv.PTS for r in bv.ROLES)
    # ambient sparks never use an edge that touches an agent vertex
    agent_v = {bv._vertex(r) for r in bv.LAYOUT}
    assert "sp" in bv.render(bv.derive([], [], NOW))
    z = bv._zigzag([bv.PTS[v] for v in bv.mesh_path("engineer", "codex-deputy")])
    assert z[0] == bv.PTS[bv._vertex("engineer")] and z[-1] == bv.PTS[bv._vertex("codex-deputy")] and len(z) > 6
    assert agent_v


if __name__ == "__main__":
    n = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            n += 1
    print(f"{n} brain_view tests passed")
