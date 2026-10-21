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
    assert len(pod) == 1 and pod[0]["label"] == "redis" and pod[0]["status"] == "stale" and pod[0]["parent"] == "ns:default" and any(n["id"] == "ns:default" for n in nodes)


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
    assert page.count("</script>") == 3 and "3d-force-graph@1.73.4" in page and "three.min.js" not in page and "force-graph@1.43.5" in page and "Το 3D δεν φόρτωσε" in page


def test_tailscale_parse():
    t = "https://h.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8501\n\nhttps://h.ts.net:8443 (tailnet only)\n|-- / proxy http://127.0.0.1:8502\n"
    assert tv.parse_tailscale(t) == ["443->http://127.0.0.1:8501", "8443->http://127.0.0.1:8502"]


def test_every_node_has_icon_and_shape():
    inv = tv.build_inventory({"claude_roles": tv.claude_roles(mkroot()), "k8s": None})
    for n in inv["nodes"]:
        assert n["icon"] and n["shape"], n["id"]
    by = {n["id"]: n for n in inv["nodes"]}
    assert by["engineer"]["shape"] == "hexagon" and by["codex-quick"]["shape"] == "diamond" and by["coordinator"]["icon"] == "♛"


IP_BRIEF = """lo               UNKNOWN        127.0.0.1/8 ::1/128
ens4             UP             10.0.1.28/16 fe80::1/64
tailscale0       UNKNOWN        100.98.24.6/32 fd7a::1/128
docker0          DOWN           172.17.0.1/16
calia951c370842@if3 UP             fe80::ecee:eeff:feee:eeee/64
tunl0@NONE       UNKNOWN        10.244.37.128/32
"""
IP_ROUTE = """default via 10.0.0.10 dev ens4 proto dhcp src 10.0.1.28 metric 100
10.0.0.0/16 dev ens4 proto kernel scope link src 10.0.1.28
blackhole 10.244.37.128/26 proto bird
10.244.37.168 dev calia951c370842 scope link
172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1 linkdown
"""
K8S = {"up": True, "context": "ctx", "data": {"items": [
    {"kind": "Node", "metadata": {"name": "n1"}, "status": {"conditions": [{"type": "Ready", "status": "True"}],
                                                          "addresses": [{"type": "InternalIP", "address": "100.98.24.6"}]}},
    {"kind": "Pod", "metadata": {"name": "grafana-6d8f9c7b5d-abcde", "namespace": "monitoring"},
     "status": {"phase": "Running", "podIP": "10.244.37.168"}, "spec": {"nodeName": "n1"}},
    {"kind": "Service", "metadata": {"name": "redis-cluster-service"}, "spec": {"clusterIP": "10.109.35.136"}},
    {"kind": "Service", "metadata": {"name": "kubernetes"}, "spec": {"clusterIP": "10.96.0.1"}},
    {"kind": "Service", "metadata": {"name": "headless"}, "spec": {"clusterIP": "None"}}]}}


def test_ip_parsers():
    f = tv.parse_ip_brief(IP_BRIEF)
    assert [x["name"] for x in f] == ["lo", "ens4", "tailscale0", "docker0", "calia951c370842", "tunl0"]
    r = tv.parse_ip_route(IP_ROUTE)
    assert r[0] == {"dst": "default", "type": "unicast", "dev": "ens4", "via": "10.0.0.10", "src": "10.0.1.28"}
    assert r[2]["type"] == "blackhole" and r[2]["dst"] == "10.244.37.128/26" and r[2]["dev"] is None
    assert tv.iface_of_ip(f, "10.0.1.28") == "ens4" and tv.iface_of_ip(f, "10.0.5.5") == "ens4"
    assert tv.iface_of_ip(f, "100.98.24.6") == "tailscale0" and tv.iface_of_ip(f, "8.8.8.8") is None


def test_network_nodes_and_links():
    f, r = tv.parse_ip_brief(IP_BRIEF), tv.parse_ip_route(IP_ROUTE)
    nodes, links = tv.network_nodes(f, r, K8S, ["443->http://127.0.0.1:8501"])
    ids = {n["id"] for n in nodes}
    assert ids == {"net:lo", "net:ens4", "net:tailscale0", "net:docker0", "net:calico", "net:k8s-svc"}
    by = {n["id"]: n for n in nodes}
    assert by["net:docker0"]["status"] == "down" and "10.244.37.128/26" in by["net:calico"]["runs_as"]
    assert "10.96.0.1 … 10.109.35.136" in by["net:k8s-svc"]["runs_as"]      # numeric, not string, order
    L = {(s, t): (why, how) for s, t, k, why, how in links}
    assert ("dashboard", "net:lo") in L and "127.0.0.1:8501" in L[("dashboard", "net:lo")][1]
    assert ("node:n1", "net:tailscale0") in L and ("grafana", "net:calico") in L
    assert ("redis", "net:calico") not in L            # no redis pod in the snapshot -> no guessed link
    assert ("redis", "net:k8s-svc") in L and "redis-cluster-service" in L[("redis", "net:k8s-svc")][1]
    assert ("openai", "net:ens4") in L and ("openai", "net:docker0") not in L
    assert tv.network_nodes([], [], None) == ([], [])


def test_every_edge_has_why_and_how():
    src = {"claude_roles": tv.claude_roles(mkroot()), "k8s": K8S, "ifaces": tv.parse_ip_brief(IP_BRIEF),
           "routes": tv.parse_ip_route(IP_ROUTE), "tailscale": ["443->http://127.0.0.1:8501"]}
    inv = tv.build_inventory(src)
    assert any(n["group"] == "networks" for n in inv["nodes"])
    for l in inv["links"]:
        assert l["why"] and l["how"], l
    by = {(l["source"], l["target"]): l for l in inv["links"]}
    assert "443 → proxy http://127.0.0.1:8501" in by[("tailscale", "dashboard")]["how"]
    assert by[("tailscale", "terminal")]["how"].endswith("(status: άγνωστο)")
    assert by[("simulator", "redis")]["how"] == "άγνωστο"
    assert "Unix socket" in by[("coordinator", "codex-reviewer")]["how"]
    assert "codex exec" in by[("coordinator", "codex-deputy")]["how"]
    page = tv.render(inv)
    assert "linkLabel(ltip)" in page and "classList.toggle('cmp'" in page


if __name__ == "__main__":  # noqa
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
    print("ok")
