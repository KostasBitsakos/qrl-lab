"""Tests for tools/topology_view.py. Run: taskset -c 0-7 .venv/bin/python -m pytest tests/test_topology_view.py (or plain python)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import topology_view as tv  # noqa: E402


def mkroot():
    r = tempfile.mkdtemp()
    os.makedirs(os.path.join(r, ".claude", "agents"))
    os.makedirs(os.path.join(r, "docs"))
    with open(os.path.join(r, ".claude", "agents", "engineer.md"), "w") as f:
        f.write("---\nname: engineer\ndescription: does code\ntools: Read, Edit\nmodel: sonnet\n---\nbody")
    return r


def test_frontmatter_and_roles():
    r = mkroot()
    roles = tv.claude_roles(r)
    assert roles[0]["id"] == "engineer" and roles[0]["model"] == "sonnet" and roles[0]["effort"] == "unknown"


def test_decisions_parse():
    t = "| codex-quick (simple) | `gpt-6-luna` / low |\n| codex-architect (council) | `gpt-6-astra` / high, why |"
    assert tv.parse_decision_roles(t) == {"codex-quick": ("gpt-6-luna", "low"), "codex-architect": ("gpt-6-astra", "high")}


def test_inventory_pure_and_unknown():
    src = {"claude_roles": tv.claude_roles(mkroot()), "active": {"engineer"}, "hb_age": 500, "coord_alive": True,
           "routing": {"engineer": {"model": "opus", "effort": "high"}}, "k8s": None}
    inv = tv.build_inventory(src)
    by = {n["id"]: n for n in inv["nodes"]}
    assert by["engineer"]["status"] == "alive" and by["engineer"]["model"] == "opus" and by["engineer"]["override"]
    assert by["health_watch"]["status"] == "stale"  # hb 500 s > 180
    assert by["simulator"]["status"] == "unknown" and "unknown" in by["simulator"]["runs_as"]
    assert by["k8s"]["status"] == "down"  # degrades
    ids = set(by)
    assert all(l["source"] in ids and l["target"] in ids for l in inv["links"])
    assert tv.build_inventory(src) == inv


def test_k8s_nodes_grouping():
    snap = {"up": True, "context": "c", "data": {"items": [
        {"kind": "Node", "metadata": {"name": "n1"}, "status": {"conditions": [{"type": "Ready", "status": "True"}], "nodeInfo": {}}},
        {"kind": "Pod", "metadata": {"name": "redis-abc12345-xy1z2", "namespace": "default"}, "spec": {"nodeName": "n1"},
         "status": {"phase": "Running", "containerStatuses": [{"restartCount": 2}]}},
        {"kind": "Pod", "metadata": {"name": "redis-abc12345-xy1z3", "namespace": "default"}, "spec": {"nodeName": "n1"},
         "status": {"phase": "Pending"}}]}}
    nodes, _ = tv.k8s_nodes(snap)
    pod = [n for n in nodes if n["id"].startswith("pod:")]
    assert len(pod) == 1 and pod[0]["label"] == "redis" and pod[0]["status"] == "stale"


def test_routing_validation_and_pin_gate():
    r = mkroot()
    assert tv.apply_routing("engineer", "opus", "high", "claude", False, root=r)[0] is False
    assert not os.path.exists(os.path.join(r, "docs", "agent_routing.json"))
    assert not tv.apply_routing("engineer", "gpt-6-sol", "high", "claude", True, root=r)[0]
    assert not tv.apply_routing("engineer", "opus", "ultra", "claude", True, root=r)[0]
    assert not tv.apply_routing("codex-quick", "opus", "low", "codex", True, root=r)[0]
    assert not tv.apply_routing("nobody", "opus", "low", "claude", True, root=r)[0]
    assert not tv.apply_routing("codex-quick", "gpt-6-sol", "max", "codex", True, root=r)[0]
    ok, _ = tv.apply_routing("codex-quick", "gpt-6-sol", "high", "codex", True, root=r, now=1.0)
    assert ok
    ok, _ = tv.apply_routing("coordinator", "fable", "max", "claude", True, root=r, now=2.0)
    assert ok
    o = json.load(open(os.path.join(r, "docs", "agent_routing.json")))
    assert o["codex-quick"]["model"] == "gpt-6-sol" and o["coordinator"]["by"] == "researcher"
    log = open(os.path.join(r, ".lab", "routing_log.jsonl")).read().splitlines()
    assert len(log) == 2 and json.loads(log[1])["role"] == "coordinator"
    assert not os.path.exists(os.path.join(r, ".claude", "settings.json"))


def test_render_escapes_script_end():
    inv = {"nodes": [{"id": "x", "label": "</script><b>", "group": "agents", "runs_as": "", "desc": "", "status": "idle", "hb": None}],
           "links": [], "groups": tv.build_inventory({})["groups"], "status_colors": tv.STATUS_COLOR}
    page = tv.render(inv)
    assert page.count("</script>") == 3 and "3d-force-graph@1.73.4" in page and "three@0.160.0" in page


def test_tailscale_parse():
    t = "https://h.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8501\n\nhttps://h.ts.net:8443 (tailnet only)\n|-- / proxy http://127.0.0.1:8502\n"
    assert tv.parse_tailscale(t) == ["443->http://127.0.0.1:8501", "8443->http://127.0.0.1:8502"]


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
    print("ok")
