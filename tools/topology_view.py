#!/usr/bin/env python3
"""Tab «Αρχιτεκτονική»: inventory of the whole lab as a graph (nodes = agents/services/cluster/external APIs).

Pure core:  build_inventory(src) -> {"nodes": [...], "links": [...], "groups": {...}}   (no I/O, no clock)
I/O shell:  collect_sources(root, now) -> src dict (reads real files / read-only kubectl / cheap local checks)
Routing:    docs/agent_routing.json  {role: {model, effort, updated, by}}  written ONLY by apply_routing() (PIN gate).
            It never touches .claude/settings.json or permission files. Every change is appended to .lab/routing_log.jsonl.
HTML:       render(inventory, height) -> self-contained page (3d-force-graph + three.js from cdn.jsdelivr.net, pinned).

Nothing is invented: a component appears only if a file, a tmux window, a cron line, a k8s object or a documented
decision shows it. Where the source does not say (e.g. how the simulator is started) the field is "unknown".
Node status: alive | idle | stale | down | unknown. `hb` = heartbeat age in seconds (None = no heartbeat concept).
"""
import glob
import html
import ipaddress
import json
import os
import re
import socket
import subprocess
import time

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

CLAUDE_MODELS = ("haiku", "sonnet", "opus", "fable")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
CODEX_MODELS = ("gpt-6-luna", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra")
CODEX_EFFORTS = ("low", "medium", "high")

GROUPS = {  # key -> (label, neon colour)
    "agents": ("Πράκτορες Claude", "#00e5ff"),
    "codex": ("Codex (OpenAI)", "#ff2bd6"),
    "services": ("Υπηρεσίες lab", "#7CFF4F"),
    "cluster": ("Cluster / έρευνα", "#ffb300"),
    "external": ("Εξωτερικά API / δίκτυο", "#b388ff"),
    "networks": ("Δίκτυα συστήματος", "#4dd0e1"),
}
STATUS_COLOR = {"alive": "#39ff88", "idle": "#6c8cff", "stale": "#ffb020", "down": "#ff3b5c", "unknown": "#8a94a6"}

EDGE_CAT = {"task": "control", "request": "control", "restart": "control", "boot": "control", "start": "control", "status": "control",
            "spawn": "control", "run": "control", "scale": "control", "hosts": "control", "contains": "control",
            "r/w": "data", "labq": "data", "metrics": "data", "datasource": "data", "workload": "data",
            "API": "api", "https": "api", "watch": "heartbeat", "net": "api"}
EDGE_CAT_LABEL = {"control": ("έλεγχος / ανάθεση", "#7aa2ff"), "data": ("δεδομένα", "#39ff88"), "api": ("API / δίκτυο", "#ff2bd6"),
                  "heartbeat": ("heartbeat / επίβλεψη", "#ffb020")}
EDGE_MAIN = {"watch", "r/w", "labq", "request", "API", "https", "spawn", "run", "scale", "metrics", "workload"}

# One glyph per node. Plain BMP symbols (render with DejaVu/system fonts everywhere, unlike colour emoji).
ICONS = {"coordinator": "♛", "engineer": "⚒", "scholar": "§", "writer": "✎", "runner": "▶", "Explore": "⌕",
         "codex-quick": "⚡", "codex-reviewer": "✔", "codex-researcher": "⚗", "codex-architect": "✦", "codex-deputy": "★",
         "dashboard": "◔", "health_watch": "♥", "watchdog": "◉", "terminal": "❯", "labdb": "⛁", "launcher": "➚",
         "boot_recover": "↻", "tailscale": "⌬", "sandbox_runs": "◈", "k8s": "☸", "redis": "⛃", "prometheus": "♨",
         "grafana": "▤", "simulator": "⚛", "anthropic": "☁", "openai": "☁", "researcher": "☻"}
GROUP_SHAPE = {"agents": "hexagon", "codex": "diamond", "services": "rounded", "cluster": "square", "external": "circle",
               "networks": "circle"}
GROUP_BORDER = {"agents": "solid", "codex": "dashed", "services": "dotted", "cluster": "double", "external": "solid",
                "networks": "dashed"}
UNKNOWN_GR = "άγνωστο"

# Codex roles: models from docs/DECISIONS.md table (parsed when possible; these are the fallbacks)
CODEX_ROLES = {
    "codex-quick": ("gpt-6-luna", "low", "Γρήγορες απλές ερωτήσεις."),
    "codex-reviewer": ("gpt-6.1-sol", "medium", "Review κώδικα/αποτελεσμάτων (adversarial)."),
    "codex-researcher": ("gpt-6.1-sol", "medium", "Δεύτερη γνώμη βιβλιογραφίας/venues (read-only)."),
    "codex-architect": ("gpt-6-astra", "high", "Council: simulator, μοντέλα, claims της εργασίας (με καταγεγραμμένο λόγο)."),
    "codex-deputy": ("unknown", "unknown", "Αναπληρωτής συντονιστή όταν το Claude είναι σε όριο χρήσης (tools/deputy.py, codex exec)."),
}


# ------------------------------------------------------------------ small parsers
def parse_frontmatter(text):
    """Minimal YAML frontmatter (key: value lines between ---). Returns {} when absent."""
    m = re.match(r"^---\s*\n(.*?)\n---", text or "", re.S)
    out = {}
    if m:
        for ln in m.group(1).splitlines():
            k, sep, v = ln.partition(":")
            if sep and k.strip() and not ln.startswith(" "):
                out[k.strip()] = v.strip()
    return out


def parse_decision_roles(text):
    """Rows like '| codex-quick (...) | `gpt-6-luna` / low |' in docs/DECISIONS.md -> {role: (model, effort)}."""
    out = {}
    for m in re.finditer(r"\|\s*(codex-[a-z]+)[^|]*\|\s*`?([\w.\-]+)`?\s*/\s*(\w+)", text or ""):
        out[m.group(1)] = (m.group(2), m.group(3))
    return out


def load_routing(root=None):
    try:
        with open(os.path.join(root or ROOT, "docs", "agent_routing.json"), encoding="utf-8") as f:
            o = json.load(f)
        return o if isinstance(o, dict) else {}
    except (OSError, ValueError):
        return {}


def allowed(role_kind):
    return (CLAUDE_MODELS, CLAUDE_EFFORTS) if role_kind == "claude" else (CODEX_MODELS, CODEX_EFFORTS)


def validate_routing(role, model, effort, kind):
    """Returns '' when valid, else a message. kind is 'claude' or 'codex'."""
    models, efforts = allowed(kind)
    if kind not in ("claude", "codex"):
        return "άγνωστο είδος ρόλου"
    if not re.fullmatch(r"[A-Za-z][\w\-]{0,40}", role or ""):
        return "άκυρο όνομα ρόλου"
    if model not in models:
        return f"μοντέλο {model!r} εκτός επιτρεπτών {models}"
    if effort not in efforts:
        return f"effort {effort!r} εκτός επιτρεπτών {efforts}"
    return ""


def apply_routing(role, model, effort, kind, unlocked, root=None, actor="researcher", now=None):
    """PIN-gated write of docs/agent_routing.json (ONLY that file) + a line in .lab/routing_log.jsonl.
    `unlocked` must be the dashboard's PIN state. Returns (ok, message)."""
    if not unlocked:
        return False, "Απαιτείται PIN (κλειδωμένο)."
    err = validate_routing(role, model, effort, kind)
    if err:
        return False, err
    root = root or ROOT
    known = set(CODEX_ROLES) if kind == "codex" else {"coordinator"} | {r["id"] for r in claude_roles(root)}
    if role not in known:
        return False, f"άγνωστος ρόλος {role!r}"
    now = time.time() if now is None else now
    cur = load_routing(root)
    old = cur.get(role)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))
    cur[role] = {"model": model, "effort": effort, "updated": stamp, "by": "researcher"}
    path = os.path.join(root, "docs", "agent_routing.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    try:
        os.makedirs(os.path.join(root, ".lab"), exist_ok=True)
        with open(os.path.join(root, ".lab", "routing_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(now, 3), "actor": actor, "role": role, "old": old, "new": cur[role]},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass
    return True, f"{role}: {model} / {effort} (docs/agent_routing.json)"


def claude_roles(root=None):
    out = []
    for p in sorted(glob.glob(os.path.join(root or ROOT, ".claude", "agents", "*.md"))):
        try:
            with open(p, encoding="utf-8") as f:
                fm = parse_frontmatter(f.read())
        except OSError:
            continue
        name = fm.get("name") or os.path.splitext(os.path.basename(p))[0]
        out.append({"id": name, "model": fm.get("model") or "unknown", "effort": fm.get("effort") or "unknown",
                    "tools": fm.get("tools") or "unknown", "description": fm.get("description") or "unknown",
                    "file": os.path.relpath(p, root or ROOT)})
    return out


# ------------------------------------------------------------------ pure inventory
def _age_status(age, stale_after):
    if age is None:
        return "unknown"
    return "alive" if age <= stale_after else "stale"


def _node(nid, label, group, runs_as, desc, status="unknown", hb=None, model="", effort="", extra=None):
    n = {"id": nid, "label": label, "group": group, "runs_as": runs_as, "desc": desc, "status": status,
         "hb": None if hb is None else round(float(hb), 1), "model": model, "effort": effort}
    if extra:
        n["extra"] = extra
    return n


def _workload(pod_name):
    """Pod name minus the ReplicaSet/pod hash suffixes -> workload name."""
    parts = pod_name.split("-")
    if len(parts) >= 3 and re.fullmatch(r"[a-z0-9]{8,10}", parts[-2]) and re.fullmatch(r"[a-z0-9]{5}", parts[-1]):
        return "-".join(parts[:-2])
    if len(parts) >= 2 and re.fullmatch(r"[a-z0-9]{5}", parts[-1]) and not parts[-1].isdigit():
        return "-".join(parts[:-1])
    return pod_name


def k8s_nodes(snap):
    """snap = k8s_view.fetch() dict or None. Returns (nodes, links). Degrades to one 'unreachable' node."""
    if not snap or not snap.get("up") or not snap.get("data"):
        err = (snap or {}).get("error") or "χωρίς απάντηση"
        return [_node("k8s", "Kubernetes API", "cluster", "kubectl (read-only) → apiserver",
                      f"Δεν ανακτήθηκε το cluster: {err}", "down")], []
    items = snap["data"].get("items", [])
    nodes, links = [], []
    ctx = snap.get("context") or "unknown"
    nodes.append(_node("k8s", "Kubernetes", "cluster", f"cluster, context {ctx}", "Control plane + workers του πειράματος.", "alive"))
    for it in items:
        if it.get("kind") == "Node":
            st = {c.get("type"): c.get("status") for c in it.get("status", {}).get("conditions", [])}
            nm = it["metadata"]["name"]
            nodes.append(_node(f"node:{nm}", f"node {nm}", "cluster", "Kubernetes node (VM)",
                               f"Κόμβος {nm}, Ready={st.get('Ready')}, kubelet {it.get('status', {}).get('nodeInfo', {}).get('kubeletVersion', '?')}",
                               "alive" if st.get("Ready") == "True" else "down"))
            links.append(("k8s", f"node:{nm}", "hosts"))
    wl = {}
    for it in items:
        if it.get("kind") != "Pod":
            continue
        ns, nm = it["metadata"].get("namespace", ""), it["metadata"]["name"]
        key = (ns, _workload(nm))
        w = wl.setdefault(key, {"n": 0, "running": 0, "phases": set(), "node": it.get("spec", {}).get("nodeName"), "restarts": 0})
        w["n"] += 1
        ph = it.get("status", {}).get("phase", "?")
        w["running"] += ph == "Running"
        w["phases"].add(ph)
        w["restarts"] += sum(c.get("restartCount", 0) for c in it.get("status", {}).get("containerStatuses", []) or [])
    per_ns = {}
    for (ns, name), w in wl.items():
        a = per_ns.setdefault(ns, {"wl": 0, "n": 0, "running": 0})
        a["wl"] += 1
        a["n"] += w["n"]
        a["running"] += w["running"]
    for ns, a in sorted(per_ns.items()):
        st = "alive" if a["running"] == a["n"] else ("down" if a["running"] == 0 else "stale")
        nodes.append(_node(f"ns:{ns}", f"ns {ns}", "cluster", f"k8s namespace · {a['wl']} workloads · {a['n']} pods",
                           f"Namespace {ns}: {a['running']}/{a['n']} pods Running σε {a['wl']} workloads. Κλικ: άνοιγμα/κλείσιμο των pods.",
                           st, extra="κλικ = άνοιγμα pods"))
        links.append(("k8s", f"ns:{ns}", "contains"))
    for (ns, name), w in sorted(wl.items()):
        nid = f"pod:{ns}/{name}"
        st = "alive" if w["running"] == w["n"] else ("down" if w["running"] == 0 else "stale")
        nd = _node(nid, name, "cluster", f"k8s pod ×{w['n']} · ns {ns}",
                   f"Workload {name} στο namespace {ns}: {w['running']}/{w['n']} Running, restarts {w['restarts']}, φάσεις {sorted(w['phases'])}.",
                   st, extra="pods")
        nd["parent"] = f"ns:{ns}"
        nodes.append(nd)
        links.append((f"ns:{ns}", nid, "contains"))
    return nodes, links


# ------------------------------------------------------------------ edges: why / how (M-20261021-012)
CODEX_PLUGIN = "~/.claude/plugins/marketplaces/openai-codex/plugins/codex/scripts"


def _ts_target(src, local):
    """'443->http://127.0.0.1:8501' entries whose target contains `local` -> 'https :443 → http://127.0.0.1:8501'."""
    hits = [x for x in (src.get("tailscale") or []) if local in x]
    return "; ".join("tailnet https :" + h.replace("->", " → proxy ") for h in hits)


def edge_info(s, t, kind, src, groups):
    """(why, how) of one edge, from what the code/config shows; «άγνωστο» where it does not say. groups: id -> group."""
    gs, gt = groups.get(s), groups.get(t)
    if s == "coordinator" and gt == "agents":
        return ("Ο συντονιστής αναθέτει εργασία (υλοποίηση, έρευνα, runs, κείμενο) στον υπο-πράκτορα.",
                "Agent tool μέσα στη διεργασία του Claude Code CLI (tmux lab:coordinator)· ο υπο-πράκτορας καλεί το "
                "Anthropic API μέσω HTTPS.")
    if s == "coordinator" and gt == "codex":
        if t == "codex-deputy":
            return ("Αναπληρωτής όταν το Claude είναι σε όριο χρήσης.",
                    "tools/deputy.py → subprocess `codex exec --sandbox read-only` (tools/deputy.py:147).")
        return ("Δεύτερη γνώμη / review / council από το Codex.",
                "Agent tool (subagent codex:codex-rescue) → node codex-companion.mjs → broker μέσω Unix socket "
                f"(JSON-RPC, {CODEX_PLUGIN}/lib/app-server.mjs:288) → `codex app-server` με stdin/stdout JSON-RPC "
                "(app-server.mjs:190).")
    if gs == "codex" and t == "openai":
        return ("Το Codex CLI εκτελεί το μοντέλο στο backend της OpenAI (συνδρομή ChatGPT).",
                "HTTPS από το Codex CLI προς την OpenAI· ακριβές endpoint: άγνωστο.")
    table = {
        ("coordinator", "anthropic"): ("Το μοντέλο του συντονιστή τρέχει στο Anthropic.", "HTTPS από το Claude Code CLI."),
        ("health_watch", "coordinator"): ("Εντοπίζει permission prompts, όρια χρήσης και αδράνεια του συντονιστή.",
                                          "`tmux capture-pane -p` του παραθύρου lab:coordinator (tools/health_watch.py:107)· "
                                          "γράφει .lab/health.json και heartbeat στον δίσκο."),
        ("dashboard", "labdb"): ("Μηνύματα, αποφάσεις, εγκρίσεις, runs.", "SQLite αρχείο .lab/lab.db στον δίσκο (tools/labdb.py)."),
        ("coordinator", "labdb"): ("Ο συντονιστής διαβάζει/απαντά στα μηνύματα του ερευνητή.",
                                   "subprocess `python3 tools/labq.py` → SQLite .lab/lab.db."),
        ("watchdog", "dashboard"): ("Επανεκκίνηση αν το dashboard πέσει.",
                                    "cron κάθε λεπτό → tools/watchdog.sh → verify_services.py (έλεγχος HTTP) και "
                                    "`tmux new-window` (tools/watchdog.sh:34)."),
        ("watchdog", "health_watch"): ("Επανεκκίνηση αν λείπει ή είναι stale.", "`tmux new-window` (tools/watchdog.sh:31)."),
        ("boot_recover", "watchdog"): ("Μετά από reboot ξαναστήνει το lab.",
                                       "cron @reboot → tools/boot_recover.sh → tools/start-coordinator.sh (tmux session lab)."),
        ("tailscale", "dashboard"): ("Πρόσβαση του ερευνητή στο dashboard από browser/κινητό.",
                                     _ts_target(src, "127.0.0.1:8501") or "tailscale serve → 127.0.0.1:8501 (status: άγνωστο)"),
        ("tailscale", "terminal"): ("Web terminal από το tailnet.",
                                    _ts_target(src, "127.0.0.1:8502") or "tailscale serve → 127.0.0.1:8502 (status: άγνωστο)"),
        ("dashboard", "terminal"): ("Ο ερευνητής ανοίγει shell από το dashboard.",
                                    "`tmux new-window … tools/web_terminal.py` (tools/web_terminal.py:43)· HTTP/websocket "
                                    "στο 127.0.0.1:8502 με token."),
        ("coordinator", "launcher"): ("Εκκίνηση εγκεκριμένων πειραμάτων.",
                                      "subprocess `python3 tools/launch_run.py` · έλεγχος έγκρισης στο .lab/lab.db."),
        ("dashboard", "launcher"): ("Κατάσταση sandbox / runs στην καρτέλα Πειράματα.",
                                    "import launch_run μέσα στη διεργασία του dashboard (sandbox_status) · ανάγνωση .lab/lab.db."),
        ("launcher", "sandbox_runs"): ("Τα runs των πειραμάτων.",
                                       "subprocess.Popen με sched_setaffinity σε αποκλειστικούς πυρήνες (tools/launch_run.py, supervise)."),
        ("launcher", "simulator"): ("Τα πειράματα τρέχουν τον κώδικα προσομοίωσης.", "subprocess (η εντολή του εγκεκριμένου run spec)."),
        ("simulator", "redis"): ("Ο autoscaler αλλάζει τα pods του Redis.", UNKNOWN_GR),
        ("prometheus", "simulator"): ("Μετρήσεις προς τον agent.", UNKNOWN_GR),
        ("researcher", "tailscale"): ("Ο ερευνητής μπαίνει στο lab.", "HTTPS μέσα στο tailnet (WireGuard, διεπαφή tailscale0)."),
        ("prometheus", "grafana"): ("Το Grafana δείχνει μετρήσεις του Prometheus.",
                                    "άγνωστο (η ρύθμιση datasource του Grafana δεν βρίσκεται στο ~/qrl-lab)."),
    }
    if (s, t) in table:
        return table[(s, t)]
    if kind in ("hosts", "contains"):
        return ("Ιεραρχία αντικειμένων Kubernetes.", "Kubernetes API · `kubectl get` read-only (tools/k8s_view.py:64).")
    if kind in ("workload", "metrics"):
        return ("Το workload τρέχει σε αυτό το pod.", "Kubernetes pod (cluster network Calico).")
    return (kind, UNKNOWN_GR)


# ------------------------------------------------------------------ networks of this machine (read-only `ip`)
def parse_ip_brief(text):
    """`ip -brief addr` -> [{name, state, addrs}] (veth '@ifN' suffix removed)."""
    out = []
    for ln in (text or "").splitlines():
        p = ln.split()
        if len(p) >= 2:
            out.append({"name": p[0].split("@")[0], "state": p[1], "addrs": p[2:]})
    return out


def parse_ip_route(text):
    """`ip route` -> [{dst, dev, via, src, type}] (type 'blackhole'/'unicast')."""
    out = []
    for ln in (text or "").splitlines():
        p = ln.split()
        if not p:
            continue
        typ = "unicast"
        if p[0] in ("blackhole", "unreachable", "prohibit"):
            typ, p = p[0], p[1:]
        r = {"dst": p[0] if p else "", "type": typ, "dev": None, "via": None, "src": None}
        for k in ("dev", "via", "src"):
            if k in p and p.index(k) + 1 < len(p):
                r[k] = p[p.index(k) + 1]
        out.append(r)
    return out


def _v4(addrs):
    return [a for a in addrs if re.fullmatch(r"\d+\.\d+\.\d+\.\d+/\d+", a)]


def _in_net(ip, cidr):
    import ipaddress
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def iface_of_ip(ifaces, ip):
    """Name of the interface whose own IPv4 address (or subnet) holds ip, else None."""
    for f in ifaces:
        for a in _v4(f["addrs"]):
            if a.split("/")[0] == ip:
                return f["name"]
    for f in ifaces:
        for a in _v4(f["addrs"]):
            if _in_net(ip, a) and not a.endswith("/32"):
                return f["name"]
    return None


def address_scope(addrs):
    """Classify observed addresses, never equating a default route with a public IP."""
    scopes = set()
    for value in addrs:
        try:
            ip = ipaddress.ip_interface(value).ip
        except ValueError:
            continue
        if ip.is_loopback:
            scopes.add("εσωτερικό, μόνο στο μηχάνημα (loopback)")
        elif ip.version == 4 and any(ip in ipaddress.ip_network(c) for c in
                                     ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
            scopes.add("εσωτερικό, ιδιωτικό (RFC1918)")
        elif ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
            scopes.add("εσωτερικό, κοινόχρηστες διευθύνσεις (CGNAT 100.64.0.0/10)")
        elif ip.is_link_local:
            scopes.add("εσωτερικό, μόνο στην ίδια ζεύξη")
        elif ip.version == 6 and ip in ipaddress.ip_network("fc00::/7"):
            scopes.add("εσωτερικό, ιδιωτικό IPv6")
        elif ip.is_global and not ip.is_multicast:
            scopes.add("εξωτερικό, δημόσια IP")
        else:
            scopes.add(UNKNOWN_GR)
    return "; ".join(sorted(scopes)) or UNKNOWN_GR


def network_info(ifaces, routes, service_ips=None):
    """Pure, conservative explanation for one interface/group from observed names and routes.

    service_ips=None means an interface; a list means observed Kubernetes ClusterIPs.
    Addresses alone cannot prove firewall policy, a cloud provider or a human creator.
    """
    names = {f["name"] for f in ifaces}
    addrs = [a for f in ifaces for a in f["addrs"]]
    bound_scope = address_scope(addrs)
    default = any(r["dst"] == "default" and r["dev"] in names for r in routes)
    what = "Διεπαφή δικτύου της VM· ακριβής ρόλος: άγνωστο."
    creator = UNKNOWN_GR
    reach = "άγνωστο· οι διευθύνσεις και οι διαδρομές δεν δείχνουν τους κανόνες πρόσβασης."
    if service_ips is not None:
        addrs = service_ips
        what = "Εικονικές διευθύνσεις για σταθερή πρόσβαση σε υπηρεσίες Kubernetes. Το συνολικό service CIDR είναι άγνωστο."
        creator = "Kubernetes· ποιος ζήτησε τη δημιουργία των Services: άγνωστο."
        reach = "Συνήθως από pods και κόμβους του cluster· πρόσβαση εκτός cluster: άγνωστο."
    elif names == {"lo"}:
        what = "Τοπική επιστροφή (loopback): το μηχάνημα μιλά στον εαυτό του."
        creator = "Πιθανότατα το λειτουργικό σύστημα."
        reach = "Μόνο αυτό το μηχάνημα· άλλη συσκευή χρειάζεται ενδιάμεση υπηρεσία ή σήραγγα."
    elif "tailscale0" in names:
        what = "Ιδιωτικό εικονικό δίκτυο Tailscale· συνήθως χρησιμοποιεί το 100.64.0.0/10."
        creator = "Πιθανότατα το Tailscale· ποιος το εγκατέστησε: άγνωστο."
        reach = "Συσκευές του δικού σου tailnet, εφόσον το επιτρέπουν οι κανόνες του Tailscale."
    elif "docker0" in names or any(n.startswith("br-") for n in names):
        what = "Πιθανότατα γέφυρα Docker: συνδέει τοπικά containers."
        creator = "Πιθανότατα το Docker· ποιος το ζήτησε: άγνωστο."
        reach = "Συνήθως η VM και τα συνδεδεμένα containers· άλλες διαδρομές πρόσβασης: άγνωστο."
    elif any(n.startswith(("cali", "flannel")) or n in ("tunl0", "cni0") for n in names):
        cni = ("Calico" if any(n.startswith("cali") for n in names) else
               "flannel" if any(n.startswith("flannel") for n in names) else UNKNOWN_GR)
        what = f"Πιθανότατα δίκτυο pods του Kubernetes· πρόσθετο δικτύωσης (CNI): {cni}."
        creator = "Πιθανότατα Kubernetes / πρόσθετο δικτύωσης· ποιος το εγκατέστησε: άγνωστο."
        reach = "Πιθανότατα pods και κόμβοι του cluster, ανάλογα με τους κανόνες δικτύου."
        addrs += [r["dst"] for r in routes if r["dev"] in names and r["dst"] != "default"]
    elif default:
        what = "Κύρια έξοδος της VM: από εδώ ξεκινά η προεπιλεγμένη διαδρομή προς άλλα δίκτυα."
        creator = "Πιθανότατα λειτουργικό / πάροχος cloud· αν είναι OpenStack και ποιος το ρύθμισε: άγνωστο."
        reach = "Πιθανότατα συσκευές του ίδιου ιδιωτικού δικτύου / έργου cloud, αν επιτρέπεται· το συγκεκριμένο έργο OpenStack: άγνωστο."
    scope = address_scope(addrs)
    if names != {"lo"} and service_ips is None:
        if "εξωτερικό, δημόσια IP" in bound_scope:
            reach += " Υπάρχει δημόσια IP στη διεπαφή· πρόσβαση από το internet μόνο αν επιτρέπουν δρομολόγηση και κανόνες πρόσβασης."
        else:
            reach += " Δημόσια IP στη διεπαφή δεν παρατηρείται· εξωτερική προώθηση ή δημόσια IP του cloud: άγνωστο."
    return {"Τι είναι": what, "Εσωτερικό ή εξωτερικό": scope,
            "Ποιος το έφτιαξε": creator, "Μέχρι πού φαίνεται": reach}


def network_usage(nid, links):
    """List only components tied to this network by existing graph edges."""
    labels = {"dashboard": "dashboard", "terminal": "web terminal", "tailscale": "Tailscale serve",
              "researcher": "ερευνητής", "redis": "Redis pods / υπηρεσίες", "prometheus": "Prometheus",
              "grafana": "Grafana", "k8s": "Kubernetes / kube-apiserver",
              "openai": "OpenAI", "anthropic": "Anthropic"}
    peers = sorted({s if t == nid else t for s, t, *_ in links if nid in (s, t)})
    return ", ".join(labels.get(p, p) for p in peers) or UNKNOWN_GR


def network_nodes(ifaces, routes, k8s_snap=None, ts=None):
    """Nodes for the networks of this machine + (s, t, kind, why, how) edges to the components that use them.
    Calico veths (cali*) and tunl0 are one 'Calico' node; Kubernetes Service ClusterIPs (from the read-only snapshot,
    if any) one node. Nothing is guessed: a link exists only when an address/port in code, config or `ip` output ties
    the component to that interface."""
    if not ifaces:
        return [], []
    nodes, links = [], []
    by = {f["name"]: f for f in ifaces}
    defaults = sorted({r["dev"] for r in routes if r["dst"] == "default" and r["dev"]})
    cali = [f for f in ifaces if f["name"].startswith("cali")]
    blocks = [r["dst"] for r in routes if r["type"] == "blackhole" and r["dst"].startswith("10.")]
    for f in ifaces:
        n = f["name"]
        if n.startswith("cali") or n == "tunl0":
            continue
        v4 = _v4(f["addrs"])
        nodes.append(_node(f"net:{n}", n, "networks", f"{', '.join(v4) or 'χωρίς IPv4'} · {f['state']}", "",
                           "down" if f["state"] == "DOWN" else "alive"))
    if cali or "tunl0" in by:
        t4 = _v4(by.get("tunl0", {}).get("addrs", []))
        nodes.append(_node("net:calico", f"Calico ({len(cali)} veth)" if cali else "tunl0 (τύπος άγνωστος)", "networks",
                           "pod network · block " + (", ".join(blocks) or UNKNOWN_GR) + (f" · tunl0 {t4[0]}" if t4 else ""),
                           "",
                           "alive"))
    import ipaddress
    items = ((k8s_snap or {}).get("data") or {}).get("items", [])
    svc_ips, svc_names = [], []
    for it in items:
        if it.get("kind") == "Service":
            ip = (it.get("spec") or {}).get("clusterIP")
            if ip and ip != "None":
                svc_ips.append(ip)
                svc_names.append((it.get("metadata") or {}).get("name", ""))
    if svc_ips:
        srt = sorted(svc_ips, key=ipaddress.ip_address)
        nodes.append(_node("net:k8s-svc", f"k8s Services ({len(svc_ips)})", "networks",
                           f"ClusterIP {srt[0]} … {srt[-1]} (CIDR: άγνωστο)",
                           "",
                           "alive"))
    ids = {n["id"] for n in nodes}

    def L(s, t, why, how):
        if t in ids:
            links.append((s, t, "net", why, how))
    L("dashboard", "net:lo", "Το dashboard ακούει μόνο τοπικά.", "Streamlit 127.0.0.1:8501 (.streamlit/config.toml).")
    L("terminal", "net:lo", "Το web terminal ακούει μόνο τοπικά.", "HTTP/websocket 127.0.0.1:8502 (tools/web_terminal.py:18-19).")
    L("tailscale", "net:tailscale0", "Το tailnet περνά από τη διεπαφή tailscale0.",
      "tailscaled· serve: " + ("; ".join(ts or []) or UNKNOWN_GR))
    L("researcher", "net:tailscale0", "Ο ερευνητής φτάνει στη VM μέσω tailnet.", "WireGuard (Tailscale) → tailscale0.")
    pr = iface_of_ip(ifaces, "10.0.1.28")
    if pr:
        L("prometheus", f"net:{pr}", "Το dashboard και το tailscale serve διαβάζουν το Prometheus.",
          "NodePort http://10.0.1.28:30000 (tools/prom_view.py:17; tailscale serve :8445).")
        L("grafana", f"net:{pr}", "Το tailscale serve δημοσιεύει το Grafana.", "NodePort http://10.0.1.28:32000 (tailscale serve :8444).")
    L("grafana", "net:lo", "Το iframe του dashboard.", "http://localhost:32000 (QRL_GRAFANA_URL default, dashboard/app.py).")
    for it in ((k8s_snap or {}).get("data") or {}).get("items", []):
        if it.get("kind") == "Node":
            nm = it["metadata"]["name"]
            for a in (it.get("status") or {}).get("addresses", []):
                if a.get("type") == "InternalIP":
                    f = iface_of_ip(ifaces, a.get("address", ""))
                    if f:
                        L(f"node:{nm}", f"net:{f}", "Η InternalIP του Kubernetes node.",
                          f"InternalIP {a['address']} (διεπαφή {f}, `kubectl get nodes`).")
    pod_nets = blocks + [r["dst"] for r in routes if (r["dev"] or "").startswith("cali")]
    for nid in ("redis", "prometheus", "grafana"):
        ips = sorted({(it.get("status") or {}).get("podIP") for it in items if it.get("kind") == "Pod"
                      and nid in (it.get("metadata") or {}).get("name", "").lower()} - {None})
        onp = [ip for ip in ips if any(_in_net(ip, c) for c in pod_nets)]
        if onp:
            L(nid, "net:calico", "Τα pods του επικοινωνούν στο pod network.",
              f"Calico CNI · pod IP {', '.join(onp[:4])}{' …' if len(onp) > 4 else ''} (`kubectl get pods`, `ip route`).")
    rs = [n for n in svc_names if n.startswith("redis")]
    if rs:
        L("redis", "net:k8s-svc", "Οι clients βρίσκουν το Redis μέσω Service.", "ClusterIP Services " + ", ".join(rs) + ".")
    for component, prefix in (("prometheus", "prometheus"), ("grafana", "grafana"), ("k8s", "kubernetes")):
        matches = [name for name in svc_names if name == prefix or name.startswith(prefix + "-")]
        if matches:
            L(component, "net:k8s-svc", "Πρόσβαση μέσω διεύθυνσης Service του Kubernetes.",
              "ClusterIP Services " + ", ".join(matches) + ".")
    for d in defaults:
        L("anthropic", f"net:{d}", "Έξοδος προς το internet.", f"προεπιλεγμένη διαδρομή μέσω {d} (`ip route`).")
        L("openai", f"net:{d}", "Έξοδος προς το internet.", f"προεπιλεγμένη διαδρομή μέσω {d} (`ip route`).")
    for node in nodes:
        nid = node["id"]
        members = ([f for f in ifaces if f["name"].startswith("cali") or f["name"] == "tunl0"]
                   if nid == "net:calico" else [by[nid[4:]]] if nid[4:] in by else [])
        info = network_info(members, routes, svc_ips if nid == "net:k8s-svc" else None)
        info["Ποια μέρη μας το χρησιμοποιούν"] = network_usage(nid, links)
        node["network_info"] = info
        node["desc"] = "\n".join(f"{key}: {value}" for key, value in info.items())
    return nodes, links


def build_inventory(src):
    """src keys (all optional, missing = unknown): claude_roles, decisions_roles, routing, active (set of roles),
    coord_alive(bool|None), health{state,checked,codex}, hb_age, dashboard_ok, terminal_ok, cron_lines, tmux_windows,
    tailscale(list of 'port->target'), sandbox_runs [{run_id,name,state,cores}], k8s (snapshot), now."""
    routing = src.get("routing") or {}
    active = set(src.get("active") or ())
    nodes, links = [], []

    def route(role, model, effort):
        o = routing.get(role)
        if isinstance(o, dict) and o.get("model") and o.get("effort"):
            return o["model"], o["effort"], True
        return model, effort, False

    coord = src.get("coord_alive")
    cm, ce, co = route("coordinator", "opus", "unknown")
    n = _node("coordinator", "Πάρις (coordinator)", "agents", "Claude Code CLI · tmux lab:coordinator",
              "Ο συντονιστής: διαβάζει το dashboard, αναθέτει σε υπο-πράκτορες και Codex, κρατεί PLAN/DECISIONS.",
              "unknown" if coord is None else ("alive" if coord else "down"), model=cm, effort=ce)
    n["override"] = co
    nodes.append(n)
    for r in src.get("claude_roles") or []:
        m, e, o = route(r["id"], r["model"], r["effort"])
        nd = _node(r["id"], r["id"], "agents", "Claude Code subagent (διεργασία κατά την κλήση, μέσω Agent tool)",
                   r["description"], "alive" if r["id"] in active else "idle", model=m, effort=e,
                   extra=f"tools: {r['tools']} · {r['file']}")
        nd["override"] = o
        nodes.append(nd)
        links.append(("coordinator", r["id"], "task"))
    dec = src.get("decisions_roles") or {}
    health = src.get("health") or {}
    codex_h = health.get("codex") or {}
    codex_down = isinstance(codex_h, dict) and codex_h.get("state") == "limit"
    for role, (m0, e0, desc) in CODEX_ROLES.items():
        m, e = dec.get(role, (m0, e0))
        m, e, o = route(role, m, e)
        st = "down" if codex_down else ("alive" if role in active else "idle")
        nd = _node(role, role, "codex", "Codex CLI (ChatGPT συνδρομή) → απομακρυσμένο OpenAI backend", desc, st, model=m, effort=e,
                   extra="usage limit" if codex_down else None)
        nd["override"] = o
        nodes.append(nd)
        links.append(("coordinator", role, "task"))
        links.append((role, "openai", "API"))

    hb = src.get("hb_age")
    hs = health.get("state")
    nodes += [
        _node("health_watch", "health_watch", "services", "διεργασία Python · tmux lab:health",
              "Παρακολουθεί το terminal του συντονιστή (permission/limit/idle) και γράφει .lab/health.json + heartbeat.",
              _age_status(hb, 180), hb=hb, extra=f"state: {hs}" if hs else None),
        _node("dashboard", "dashboard", "services", "Streamlit · tmux lab:dashboard · 127.0.0.1:8501",
              "Αυτό το UI: συνομιλία, αποφάσεις, runs, sudo, αρχιτεκτονική.", "alive" if src.get("dashboard_ok", True) else "down"),
        _node("terminal", "web terminal", "services", "ttyd-like server (terminado) · 127.0.0.1:8502, on demand",
              "Shell στο browser, token + PIN, κλείνει μετά από 30 λεπτά αδράνειας.",
              "alive" if src.get("terminal_ok") else "idle"),
        _node("labdb", "lab.db / labq", "services", "αρχείο SQLite (.lab/lab.db) + CLI tools/labq.py",
              "Μηνύματα, αποφάσεις, αιτήματα έγκρισης και audit μεταξύ ερευνητή και πρακτόρων.", "alive" if src.get("labdb_ok") else "unknown"),
        _node("launcher", "launch_run + sandbox", "services", "CLI tools/launch_run.py + tools/sandbox_guard.py (πυρήνες 8-23)",
              "Μοναδική είσοδος για πειράματα· απαιτεί εγκεκριμένο frozen spec· sandbox με ledger ανά run.", "idle"),
        _node("tailscale", "Tailscale serve", "external", "tailscaled (σύστημα) · tailnet-only HTTPS",
              "Δημοσιεύει dashboard/terminal/Grafana/Prometheus μόνο στο tailnet: " + ("; ".join(src.get("tailscale") or []) or "unknown"),
              "alive" if src.get("tailscale") else "unknown"),
    ]
    cron = src.get("cron_lines") or []
    wd = any("watchdog" in c for c in cron)
    br = any("boot_recover" in c for c in cron)
    nodes += [
        _node("watchdog", "watchdog (cron)", "services", "cron κάθε λεπτό · tools/watchdog.sh → verify_services.py",
              "Ελέγχει dashboard/health/coordinator και τα ξαναστήνει μετά από 3 αποτυχίες· εκτός λειτουργίας αν σταματήσει το cron.",
              "alive" if wd else ("unknown" if not cron else "down")),
        _node("boot_recover", "boot_recover (@reboot)", "services", "cron @reboot · tools/boot_recover.sh",
              "Μετά από reboot στήνει tmux, συντονιστή και dashboard και ποστάρει αναφορά.",
              "idle" if br else ("unknown" if not cron else "down")),
    ]
    links += [("health_watch", "coordinator", "watch"), ("dashboard", "labdb", "r/w"), ("coordinator", "labdb", "labq"),
              ("watchdog", "dashboard", "restart"), ("watchdog", "health_watch", "restart"), ("boot_recover", "watchdog", "boot"),
              ("tailscale", "dashboard", "https"), ("tailscale", "terminal", "https"), ("dashboard", "terminal", "start"),
              ("coordinator", "launcher", "request"), ("dashboard", "launcher", "status")]
    sb = src.get("sandbox_runs") or []
    if sb:
        run_n = sum(r.get("state") == "running" for r in sb)
        cores = sorted({c for r in sb if r.get("state") == "running" for c in (r.get("cores") or [])})
        nodes.append(_node("sandbox_runs", f"sandbox runs ({run_n} τρέχουν)", "cluster",
                           "διεργασίες σε αποκλειστικούς πυρήνες" + (f" ({cores[0]}-{cores[-1]})" if cores else ""),
                           f"Ledger .lab/sandbox: {len(sb)} runs, {run_n} χωρίς done event (η ζωντάνια της διεργασίας δεν ελέγχεται).",
                           "alive" if run_n else "idle"))
        links.append(("launcher", "sandbox_runs", "spawn"))

    knodes, klinks = k8s_nodes(src.get("k8s"))
    nodes += knodes
    links += klinks
    names = {n["id"] for n in nodes}
    for nid, label, runs_as, desc in (
            ("redis", "Redis", "k8s pods (namespace default) — το σύστημα που κάνει autoscale", "Το Redis cluster που κλιμακώνει το DInos."),
            ("prometheus", "Prometheus", "k8s pod (monitoring) · 10.0.1.28:30000", "Συλλογή μετρήσεων (tailnet :8445)."),
            ("grafana", "Grafana", "k8s pod (monitoring) · 10.0.1.28:32000", "Dashboards μετρήσεων (tailnet :8444)."),
    ):
        pod = next((n for n in knodes if n["id"].startswith("pod:") and nid in n["label"].lower()), None)
        nodes.append(_node(nid, label, "cluster", runs_as, desc, pod["status"] if pod else "unknown"))
        links.append((pod["id"] if pod else "k8s", nid, "metrics" if nid != "redis" else "workload"))
    nodes.append(_node("simulator", "simulator / DInos agent", "cluster",
                       "unknown (κώδικας στο ~/simulations/redisk8s και code/ worktree· δεν φαίνεται πώς τρέχει σε παραγωγή)",
                       "Προσομοιωτής και DRL autoscaler. Τρόπος εκκίνησης: unknown.", "unknown"))
    links += [("simulator", "redis", "scale"), ("prometheus", "simulator", "metrics"), ("launcher", "simulator", "run")]
    nodes += [
        _node("anthropic", "Anthropic API", "external", "απομακρυσμένη υπηρεσία (claude.ai / Claude Code)", "Backend των Claude πρακτόρων.", "unknown"),
        _node("openai", "OpenAI / ChatGPT (Codex)", "external", "απομακρυσμένη υπηρεσία μέσω Codex CLI",
              "Backend των Codex ρόλων (συνδρομή ChatGPT, όχι API key).", "down" if codex_down else "unknown"),
        _node("researcher", "Κώστας (browser/κινητό)", "external", "άνθρωπος · μέσω Tailscale",
              "Ο ερευνητής: στέλνει μηνύματα, εγκρίνει, ορίζει routing.", "unknown"),
    ]
    links += [("coordinator", "anthropic", "API"), ("researcher", "tailscale", "https"), ("prometheus", "grafana", "datasource")]
    nnodes, nlinks = network_nodes(src.get("ifaces") or [], src.get("routes") or [], src.get("k8s"), src.get("tailscale"))
    nodes += nnodes
    links += nlinks
    for n in nodes:
        i = n["id"]
        n["icon"] = ICONS.get(i) or ("▦" if i.startswith("ns:") else "▢" if i.startswith("pod:") else "▣" if i.startswith("node:") else "●")
        n["shape"] = GROUP_SHAPE.get(n["group"], "circle")
    names = {n["id"] for n in nodes}
    groups = {n["id"]: n["group"] for n in nodes}
    out = []
    for ln in links:
        s, t, k = ln[:3]
        if s not in names or t not in names:
            continue
        why, how = ln[3:5] if len(ln) >= 5 else edge_info(s, t, k, src, groups)
        out.append({"source": s, "target": t, "kind": k, "cat": EDGE_CAT.get(k, "control"), "why": why, "how": how,
                    "main": k in EDGE_MAIN and not (k == "API" and s != "coordinator")})
    links = out
    return {"nodes": nodes, "links": links, "groups": {k: {"label": v[0], "color": v[1]} for k, v in GROUPS.items()},
            "borders": GROUP_BORDER, "status_colors": STATUS_COLOR, "edge_cats": {k: {"label": v[0], "color": v[1]} for k, v in EDGE_CAT_LABEL.items()}, "now": src.get("now")}


# ------------------------------------------------------------------ I/O shell
def _tail_events(path, nbytes=262144):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - nbytes))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for ln in data.splitlines()[1:]:
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out


def parse_tailscale(text):
    """'tailscale serve status' text -> ['443->http://127.0.0.1:8501', ...]."""
    out, port = [], None
    for ln in (text or "").splitlines():
        m = re.match(r"https://\S+?(?::(\d+))?\s", ln + " ")
        if m:
            port = m.group(1) or "443"
            continue
        m = re.search(r"proxy\s+(\S+)", ln)
        if m and port:
            out.append(f"{port}->{m.group(1)}")
    return out


def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


_CACHE = {}


def _cached(key, ttl, fn, now):
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    v = fn()
    _CACHE[key] = (now, v)
    return v


def collect_sources(root=None, now=None):
    root = root or ROOT
    now = time.time() if now is None else now
    lab = os.path.join(root, ".lab")
    src = {"now": now, "claude_roles": claude_roles(root), "routing": load_routing(root)}
    try:
        with open(os.path.join(root, "docs", "DECISIONS.md"), encoding="utf-8") as f:
            src["decisions_roles"] = parse_decision_roles(f.read())
    except OSError:
        src["decisions_roles"] = {}
    try:
        import brain_view
        st = brain_view.derive(_tail_events(os.path.join(lab, "events.jsonl")), [], now)
        src["active"] = {r for r, v in st["nodes"].items() if v.get("active")}
    except Exception:  # noqa: BLE001 — a broken events file must not break the page
        src["active"] = set()
    try:
        with open(os.path.join(lab, "health.json"), encoding="utf-8") as f:
            src["health"] = json.load(f)
    except (OSError, ValueError):
        src["health"] = {}
    try:
        src["hb_age"] = now - os.stat(os.path.join(lab, "health_watch.heartbeat")).st_mtime
    except OSError:
        src["hb_age"] = None
    src["terminal_ok"] = _port_open(8502)
    src["dashboard_ok"] = True  # this page is served by it
    src["labdb_ok"] = os.path.exists(os.path.join(lab, "lab.db"))

    def tmux_coord():
        rc, out = _run(["tmux", "list-panes", "-t", "lab:coordinator", "-F", "#{pane_pid}"])
        if rc != 0 or not out.strip():
            return False
        try:
            import verify_services
            return bool(verify_services._descendants_have_claude(out.split()[0]))  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return None
    src["coord_alive"] = _cached("coord", 15, tmux_coord, now)
    rc, out = _cached("cron", 60, lambda: _run(["crontab", "-l"]), now)
    src["cron_lines"] = [l for l in out.splitlines() if "qrl-lab" in l and not l.lstrip().startswith("#")] if rc == 0 else []

    def ts():
        rc2, o = _run(["tailscale", "serve", "status"])
        return parse_tailscale(o) if rc2 == 0 else []
    src["tailscale"] = _cached("ts", 60, ts, now)
    rc3, o3 = _cached("ipa", 60, lambda: _run(["ip", "-brief", "addr"]), now)
    src["ifaces"] = parse_ip_brief(o3) if rc3 == 0 else []
    rc4, o4 = _cached("ipr", 60, lambda: _run(["ip", "route"]), now)
    src["routes"] = parse_ip_route(o4) if rc4 == 0 else []
    runs = []
    for p in sorted(glob.glob(os.path.join(lab, "sandbox", "*.ledger.jsonl")))[-3:]:
        state = {}
        try:
            with open(p, encoding="utf-8") as f:
                for ln in f:
                    try:
                        o = json.loads(ln)
                    except ValueError:
                        continue
                    if o.get("event") == "start":
                        state[o["run_id"]] = {"run_id": o["run_id"], "name": o.get("name"), "cores": o.get("cores"), "state": "running"}
                    elif o.get("event") == "done" and o.get("run_id") in state:
                        state[o["run_id"]]["state"] = "done"
        except OSError:
            continue
        runs += list(state.values())
    running = [r for r in runs if r["state"] == "running"]
    src["sandbox_runs"] = runs  # NB: "running" = no done event in the ledger (process liveness not checked)

    def k8s():
        import k8s_view
        return k8s_view.fetch(now)
    try:
        src["k8s"] = _cached("k8s", 30, k8s, now)
    except Exception:  # noqa: BLE001
        src["k8s"] = None
    return src


def inventory(root=None, now=None):
    return build_inventory(collect_sources(root, now))


# ------------------------------------------------------------------ HTML
_PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{margin:0;height:100%;background:radial-gradient(ellipse at center,#0b1030 0%,#03040c 80%);font-family:system-ui,sans-serif;color:#cfe;overflow:hidden}
#g{position:absolute;inset:0}
#lab{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:1}
.scene-tooltip,.float-tooltip-kap,.graph-tooltip{z-index:20!important}
.gb{position:absolute;left:0;top:0;border:1px solid;border-radius:14px;pointer-events:none;will-change:transform}
.gi{position:absolute;left:0;top:0;pointer-events:none;font:700 15px 'DejaVu Sans',sans-serif;color:#03061a;margin:-9px 0 0 -8px;width:16px;text-align:center;will-change:transform}
.gt{position:absolute;left:10px;top:6px;font-size:15px;font-weight:700;letter-spacing:.5px;text-shadow:0 0 6px #000}
#bt{position:absolute;left:8px;top:8px;z-index:6;display:flex;gap:6px}
#bt button{background:#050818dd;color:#cfe;border:1px solid #3af;border-radius:8px;padding:5px 9px;font-size:12px}
.nl{position:absolute;left:0;top:0;white-space:nowrap;font-size:12px;line-height:1.15;padding:1px 5px;border-radius:5px;background:#03061aee;border:1px solid;text-shadow:0 0 4px #000;will-change:transform}
.nl small{display:block;font-size:9px;opacity:.7}
.nl.cmp small{display:none}
.nl i{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:4px;animation:hb var(--p,3s) ease-in-out infinite}
@keyframes hb{0%,100%{transform:scale(1);opacity:.6}50%{transform:scale(1.7);opacity:1}}
#leg{position:absolute;right:6px;top:6px;max-height:70vh;overflow:auto;background:#050818cc;border:1px solid #234;border-radius:8px;padding:5px 7px;font-size:10px;max-width:42vw;z-index:5}
#leg i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;box-shadow:0 0 6px currentColor}
#info{position:absolute;left:8px;right:8px;bottom:8px;background:#050818ee;border:1px solid #2a4;border-radius:10px;padding:8px 10px;font-size:12px;z-index:5;display:none}
#err{position:absolute;inset:0;display:none;align-items:center;justify-content:center;text-align:center;padding:20px;color:#ff8a9c;font-size:15px;z-index:9}
.tip{background:#050818f0;border:1px solid #3af;border-radius:8px;padding:6px 9px;font-size:12px;max-width:340px;line-height:1.35;white-space:normal}
.tip b{color:#fff}.k{color:#7ad}
</style></head><body><div id="g"></div><div id="gbx"></div><div id="lab"></div><div id="ico"></div><div id="bt"><button id="bl">Ετικέτες</button><button id="bi">Υπόμνημα</button></div><div id="leg"></div><div id="info"></div><div id="err"></div>
<script>
function fail(r){var e=document.getElementById('err');e.style.display='flex';e.innerHTML='<div>Το 3D δεν φόρτωσε: '+String(r).replace(/[<&]/g,' ')+'<br><small>Δες τον πίνακα κόμβων από κάτω.</small></div>';}
window.addEventListener('error',function(ev){var t=ev.target;if(t&&t.tagName==='SCRIPT')fail('αποτυχία φόρτωσης από CDN ('+t.src+')');else if(ev.message)fail(ev.message);},true);
window.addEventListener('unhandledrejection',function(ev){fail(ev.reason);});
</script>
<script src="https://cdn.jsdelivr.net/npm/3d-force-graph@1.73.4/dist/3d-force-graph.min.js"></script>
<script>
(function(){try{
const D=__DATA__;
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SC=D.status_colors, GC={}, GL={};for(const k in D.groups){GC[k]=D.groups[k].color;GL[k]=D.groups[k].label}
const EC=D.edge_cats||{control:{label:'έλεγχος',color:'#7aa2ff'},data:{label:'δεδομένα',color:'#39ff88'},api:{label:'API',color:'#ff2bd6'},heartbeat:{label:'heartbeat',color:'#ffb020'}};
let gl=false;try{const c=document.createElement('canvas');gl=!!(c.getContext('webgl2')||c.getContext('webgl'))}catch(e){}
const use3d=gl&&typeof ForceGraph3D!=='undefined';
if(gl&&!use3d){setTimeout(()=>{if(typeof ForceGraph3D==='undefined')fail('το ForceGraph3D δεν ορίστηκε (CDN μπλοκαρισμένο ή offline)')},4000);return;}
const leg=document.getElementById('leg');
leg.innerHTML='<b>Ομάδες</b><br>'+Object.values(D.groups).map(g=>`<i style="color:${g.color};background:${g.color}"></i>${esc(g.label)}`).join('<br>')
 +'<br><b>Κατάσταση</b> (χρώμα κόμβου)<br>'+Object.keys(SC).map(s=>`<i style="color:${SC[s]};background:${SC[s]}"></i>${s}`).join(' ')
 +'<br><b>Ακμές</b><br>'+Object.values(EC).map(e=>`<i style="color:${e.color};background:${e.color}"></i>${esc(e.label)}`).join('<br>')
 +'<br><b>Σχήματα</b>: εξάγωνο = Claude · ρόμβος = Codex · στρογγυλεμένο = υπηρεσίες · τετράγωνο = cluster · κύκλος = εξωτερικά<br><span style="opacity:.7">έντονη = κύρια ροή · αχνή = δευτερεύουσα · παλμός = heartbeat · κλικ στο «ns …» ανοίγει τα pods · δείκτης πάνω σε ακμή = γιατί/πώς επικοινωνούν</span>'
 +(use3d?'':'<br><b style="color:#ffb020">Λειτουργία 2D (χωρίς WebGL) — για 3D ενεργοποίησε το hardware acceleration στον browser</b>');
leg.style.display='none';
document.getElementById('bi').onclick=()=>{leg.style.display=leg.style.display==='none'?'block':'none'};
function tip(n){return `<div class="tip"><b>${esc(n.label)}</b><br>${esc(n.desc).replace(/\\n/g,'<br>')}<br><span class="k">τρέχει ως:</span> ${esc(n.runs_as)}`
 +(n.model?`<br><span class="k">μοντέλο:</span> ${esc(n.model)} / ${esc(n.effort)}${n.override?' <b style="color:#ffb020">(override)</b>':''}`:'')
 +`<br><span class="k">κατάσταση:</span> <span style="color:${SC[n.status]}">${esc(n.status)}</span>`
 +(n.hb!=null?`<br><span class="k">heartbeat:</span> ${n.hb}s`:'')+(n.extra?`<br>${esc(n.extra)}`:'')+'</div>';}
const nodes=D.nodes.map(n=>Object.assign({},n)), idx={};nodes.forEach(n=>idx[n.id]=n);
function ltip(l){const a=l.source.id||l.source,b=l.target.id||l.target,s=idx[a]||{},t=idx[b]||{};
 return `<div class="tip"><b>${esc(s.label||a)} → ${esc(t.label||b)}</b> <span class="k">(${esc(l.kind)})</span>`
 +`<br><span class="k">γιατί:</span> ${esc(l.why||'άγνωστο')}<br><span class="k">πώς:</span> ${esc(l.how||'άγνωστο')}</div>`}
const short=s=>{s=String(s).split(/ [·(—]/)[0];return s.length>28?s.slice(0,27)+'…':s};
const trunc=(s,m)=>s.length>m?s.slice(0,m-1)+'…':s;
const period=n=>n.hb==null?(n.status==='alive'?2.4:(n.status==='idle'?5:1.2)):Math.min(8,.8+n.hb/30);
const expanded={};
const keys=Object.keys(D.groups), boxes={};
const CW=200,CH=56;
const isVis=n=>!n.parent||expanded[n.parent];
function layout(){
 const vis=nodes.filter(isVis), byg={};
 keys.forEach(k=>byg[k]=[]);
 vis.filter(n=>!n.parent).forEach(n=>{byg[n.group].push(n);vis.filter(c=>c.parent===n.id).forEach(c=>byg[n.group].push(c))});
 const gs=keys.filter(k=>byg[k].length).map(k=>{const m=byg[k].length,cols=Math.min(6,Math.max(2,Math.ceil(Math.sqrt(m)))),rows=Math.ceil(m/cols);return{k,cols,rows,w:cols*CW+30,h:rows*CH+64}});
 const MAXW=1900,GAP=70;let x=0,y=0,rowH=0,W=0;
 gs.forEach(g=>{if(x>0&&x+g.w>MAXW){x=0;y+=rowH+GAP;rowH=0}g.x=x;g.y=y;x+=g.w+GAP;rowH=Math.max(rowH,g.h);W=Math.max(W,g.x+g.w)});
 const H=y+rowH;
 gs.forEach((g,i)=>{boxes[g.k]={x:g.x,y:g.y,w:g.w,h:g.h,z:(i%2?1:-1)*40};
  byg[g.k].forEach((n,j)=>{const c=j%g.cols,r=Math.floor(j/g.cols);n.fx=g.x+15+c*CW+16;n.fy=g.y+54+r*CH+CH/2;n.fz=boxes[g.k].z;if(use3d)n.fy=-n.fy;n.x=n.fx;n.y=n.fy;n.z=n.fz})});
 keys.forEach(k=>{if(!byg[k].length)delete boxes[k]});
 return{W,H,vis}}
let LAY=layout();
function visLinks(){const seen={},out=[];const v=id=>{let n=idx[id];if(!n)return null;if(!isVis(n))n=idx[n.parent];return n?n.id:null};
 D.links.forEach(l=>{const s=v(l.source),t=v(l.target);if(!s||!t||s===t)return;const key=s+'|'+t+'|'+l.kind;if(seen[key])return;seen[key]=1;out.push({source:s,target:t,kind:l.kind,cat:l.cat||'control',main:!!l.main,why:l.why,how:l.how})});return out}
let LINKS=visLinks();
let hover=null,sel=null;
const focus=()=>hover||sel;
function nb(){const f=focus();if(!f)return null;const s=new Set([f.id]);LINKS.forEach(l=>{const a=l.source.id||l.source,b=l.target.id||l.target;if(a===f.id)s.add(b);if(b===f.id)s.add(a)});return s}
let NB=null;const lit=n=>!NB||NB.has(n.id);
const lid=x=>x.id||x;
const litLink=l=>NB&&(lid(l.source)===focus().id||lid(l.target)===focus().id);
function mix(c,a){const h=c.replace('#','');const r=parseInt(h.slice(0,2),16),g=parseInt(h.slice(2,4),16),b=parseInt(h.slice(4,6),16);return `rgb(${Math.round(r*a+12*(1-a))},${Math.round(g*a+16*(1-a))},${Math.round(b*a+40*(1-a))})`}
const linkCol=l=>{const c=EC[l.cat].color,h=c.replace('#','');const rgb=[0,2,4].map(i=>parseInt(h.slice(i,i+2),16)).join(',');const a=NB?(litLink(l)?.95:.05):(l.main?.6:.16);return `rgba(${rgb},${a})`};
const infoEl=document.getElementById('info'),el=document.getElementById('g');
function select(n){sel=n;if(n&&n.id.startsWith('ns:')){expanded[n.id]=!expanded[n.id];relayout()}
 infoEl.style.display=n?'block':'none';if(n)infoEl.innerHTML=tip(n).replace('class="tip"','');NB=nb();restyle()}
function size(G){G.width(window.innerWidth).height(window.innerHeight)}
let G,relayout,restyle;
if(use3d){
 const labs=document.getElementById('lab'),icos=document.getElementById('ico'),gbx=document.getElementById('gbx');let showAll=false;
 nodes.forEach(n=>{const d=document.createElement('div');d.className='nl';d.style.borderColor=GC[n.group];
  d.innerHTML=`<i style="background:${SC[n.status]};box-shadow:0 0 6px ${SC[n.status]};--p:${period(n)}s"></i>${esc(trunc(n.label,26))}<small>${esc(short(n.runs_as))}</small>`;
  labs.appendChild(d);n._el=d;const q=document.createElement('div');q.className='gi';q.textContent=n.icon||'';icos.appendChild(q);n._ic=q;});
 const gdiv={};keys.forEach(k=>{const d=document.createElement('div');d.className='gb';d.style.borderColor=GC[k];d.style.borderStyle=(D.borders||{})[k]||'solid';if(d.style.borderStyle==='double')d.style.borderWidth='3px';d.style.background=GC[k]+'14';d.innerHTML=`<div class="gt" style="color:${GC[k]}">${esc(GL[k])}</div>`;gbx.appendChild(d);gdiv[k]=d});
 G=ForceGraph3D()(el).backgroundColor('rgba(0,0,0,0)').graphData({nodes:LAY.vis,links:LINKS})
  .nodeColor(n=>lit(n)?(SC[n.status]||SC.unknown):mix(SC[n.status]||SC.unknown,.2)).nodeVal(n=>n.id==='coordinator'?70:(n.id.startsWith('ns:')?50:30)).nodeRelSize(5).nodeOpacity(.95).nodeResolution(14)
  .nodeLabel(tip).warmupTicks(2).cooldownTicks(2)
  .linkColor(linkCol).linkWidth(l=>NB&&litLink(l)?1.6:.5).linkCurvature(.12).linkOpacity(1)
  .linkDirectionalParticles(l=>(NB?litLink(l):l.main)?(l.cat==='api'?3:2):0).linkDirectionalParticleWidth(2.2).linkDirectionalParticleSpeed(.006)
  .linkDirectionalParticleColor(l=>EC[l.cat].color).linkLabel(ltip).linkHoverPrecision(6)
  .onNodeHover(n=>{hover=n;NB=nb();restyle()}).onNodeClick(select).onBackgroundClick(()=>select(null));
 size(G);addEventListener('resize',()=>{size(G);fit()});
 G.controls().autoRotate=false;
 let dist=1000;
 function fit(){const asp=window.innerWidth/Math.max(1,window.innerHeight),W=LAY.W+80,H=LAY.H+80;
  dist=Math.max(W/2/(0.466*asp),H/2/0.466)*1.04;const cx=LAY.W/2,cy=-LAY.H/2;G.cameraPosition({x:cx,y:cy+dist*.10,z:dist},{x:cx,y:cy,z:0},0)}
 restyle=()=>{G.nodeColor(n=>lit(n)?(SC[n.status]||SC.unknown):mix(SC[n.status]||SC.unknown,.2)).linkColor(linkCol)
  .linkWidth(l=>NB&&litLink(l)?1.6:.5).linkDirectionalParticles(l=>(NB?litLink(l):l.main)?(l.cat==='api'?3:2):0)};
 relayout=()=>{LAY=layout();LINKS=visLinks();G.graphData({nodes:LAY.vis,links:LINKS});fit()};
 document.getElementById('bl').onclick=()=>{showAll=!showAll};
 [100,800,2500].forEach(t=>setTimeout(fit,t));
 (function tick(){requestAnimationFrame(tick);const w=window.innerWidth,h=window.innerHeight,cam=G.camera().position,tg=G.controls().target;
  const close=cam.distanceTo(tg)<dist*.62;
  const cand=[],placed=[],f=focus();
  nodes.forEach(n=>{if(!isVis(n)){n._el.style.display='none';n._ic.style.display='none';return}const c=G.graph2ScreenCoords(n.x,n.y,n.z);
   const vis=c&&c.x>-30&&c.x<w+30&&c.y>-30&&c.y<h+30;n._ic.style.display=vis?'block':'none';if(vis){n._ic.style.transform=`translate(${c.x}px,${c.y}px)`;n._ic.style.opacity=lit(n)?1:.2;placed.push({x:c.x-8,y:c.y-9,w:16,h:18,id:n.id})}
   const on=c&&c.x>-80&&c.x<w+80&&c.y>-30&&c.y<h+30&&(showAll||close||(NB&&NB.has(n.id)));
   if(on)cand.push({n,c});else n._el.style.display='none'});
  // labels never overlap (M-20261021-012): focus first, then highlighted, then the rest; each tries 6 positions around
  // its node and is hidden if all collide; while hovering, neighbours show only their name (role line hidden)
  const pri=n=>n===f?3:(NB&&NB.has(n.id)?2:1);cand.sort((a,b)=>pri(b.n)-pri(a.n));
  cand.forEach(({n,c})=>{const el=n._el,cmp=!!(f&&n!==f&&NB);if(el._cmp!==cmp||el._w==null){el.classList.toggle('cmp',cmp);el._cmp=cmp;el.style.display='block';el._w=el.offsetWidth;el._h=el.offsetHeight}
   const W=el._w,H=el._h,offs=[[8,-10],[8,9],[-W-8,-10],[-W/2,-H-11],[-W/2,11],[-W-8,9]];let ok=null;
   for(const pass of [0,1]){for(const o of offs){const r={x:c.x+o[0],y:c.y+o[1],w:W,h:H};
     if(!pass&&(r.x<2||r.x+W>w-2||r.y<2||r.y+H>h-2))continue;
     if(!placed.some(p=>p.id!==n.id&&r.x<p.x+p.w&&r.x+r.w>p.x&&r.y<p.y+p.h&&r.y+r.h>p.y)){ok=r;break}}if(ok)break}
   if(!ok&&n===f)ok={x:c.x+8,y:c.y-10,w:W,h:H};
   if(!ok){el.style.display='none';return}
   placed.push(ok);el.style.display='block';el.style.transform=`translate(${ok.x}px,${ok.y}px)`;el.style.opacity=lit(n)?1:.25;el.style.zIndex=n===f?3:(lit(n)?2:1)});
  keys.forEach(k=>{const b=boxes[k],d=gdiv[k];if(!b){d.style.display='none';return}
   const P=[[b.x,-b.y],[b.x+b.w,-b.y],[b.x,-(b.y+b.h)],[b.x+b.w,-(b.y+b.h)]].map(q=>G.graph2ScreenCoords(q[0],q[1],b.z));
   const x0=Math.min(...P.map(q=>q.x)),x1=Math.max(...P.map(q=>q.x)),y0=Math.min(...P.map(q=>q.y)),y1=Math.max(...P.map(q=>q.y));
   d.style.display='block';d.style.width=(x1-x0)+'px';d.style.height=(y1-y0)+'px';d.style.transform=`translate(${x0}px,${y0}px)`})})();
 setTimeout(()=>{if(!document.querySelector('#g canvas'))fail('δεν δημιουργήθηκε canvas')},5000);
}else{
 document.getElementById('bl').style.display='none';
 const sc=document.createElement('script');sc.src='https://cdn.jsdelivr.net/npm/force-graph@1.43.5/dist/force-graph.min.js';
 sc.onload=()=>{try{
  const poly=(ctx,x,y,r,m,rot)=>{ctx.beginPath();for(let i=0;i<m;i++){const a=rot+i*6.2832/m;ctx[i?'lineTo':'moveTo'](x+r*Math.cos(a),y+r*Math.sin(a))}ctx.closePath()};
  const shapePath=(ctx,n,r)=>{const sh=n.shape;if(sh==='hexagon')poly(ctx,n.x,n.y,r*1.1,6,0);else if(sh==='diamond')poly(ctx,n.x,n.y,r*1.3,4,0);
   else if(sh==='rounded'||sh==='square'){const q=r*(sh==='square'?.95:.9);ctx.beginPath();ctx.moveTo(n.x-q+(sh==='square'?1:5),n.y-q);ctx.arcTo(n.x+q,n.y-q,n.x+q,n.y+q,sh==='square'?1:5);ctx.arcTo(n.x+q,n.y+q,n.x-q,n.y+q,sh==='square'?1:5);ctx.arcTo(n.x-q,n.y+q,n.x-q,n.y-q,sh==='square'?1:5);ctx.arcTo(n.x-q,n.y-q,n.x+q,n.y-q,sh==='square'?1:5);ctx.closePath()}
   else{ctx.beginPath();ctx.arc(n.x,n.y,r,0,6.2832)}};
  const fit2d=()=>{const k=Math.min(window.innerWidth/(LAY.W+90),window.innerHeight/(LAY.H+90));G.zoom(k,0);G.centerAt(LAY.W/2,LAY.H/2,0)};
  const rr=(ctx,x,y,w,h,r)=>{ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath()};
  G=ForceGraph()(el).backgroundColor('rgba(0,0,0,0)').graphData({nodes:LAY.vis,links:LINKS}).nodeLabel(tip).cooldownTicks(0)
   .linkColor(linkCol).linkWidth(l=>NB&&litLink(l)?2.2:1).linkCurvature(.14).linkLineDash(l=>l.cat==='api'?[6,4]:(l.cat==='heartbeat'?[2,3]:null))
   .linkDirectionalParticles(l=>(NB?litLink(l):l.main)?(l.cat==='api'?3:2):0).linkDirectionalParticleWidth(3).linkDirectionalParticleSpeed(.006)
   .linkDirectionalParticleColor(l=>EC[l.cat].color).linkLabel(ltip).linkHoverPrecision(6)
   .onRenderFramePre((ctx,k)=>{keys.forEach(kk=>{const b=boxes[kk];if(!b)return;ctx.save();rr(ctx,b.x,b.y,b.w,b.h,18);ctx.fillStyle=GC[kk]+'12';ctx.fill();ctx.strokeStyle=GC[kk]+'99';ctx.lineWidth=1.5/k;const bs=(D.borders||{})[kk];ctx.setLineDash(bs==='dashed'?[10/k,6/k]:bs==='dotted'?[2/k,5/k]:[]);if(bs==='double')ctx.lineWidth=3/k;ctx.stroke();if(bs==='double'){ctx.setLineDash([]);rr(ctx,b.x+6,b.y+6,b.w-12,b.h-12,13);ctx.lineWidth=1/k;ctx.stroke()}
     ctx.font='bold '+Math.min(26,Math.max(15,15/k))+'px sans-serif';ctx.fillStyle=GC[kk];ctx.fillText(GL[kk],b.x+14,b.y+30);ctx.restore()})})
   .nodeCanvasObject((n,ctx,k)=>{const r=n.id==='coordinator'?13:(n.id.startsWith('ns:')?11:10),t=Date.now()/1000,p=period(n),f=(t%p)/p,col=SC[n.status]||SC.unknown,on=lit(n);
     ctx.save();ctx.globalAlpha=on?1:.22;shapePath(ctx,n,r+f*r*1.5);ctx.strokeStyle=col;ctx.globalAlpha=(on?.55:.1)*(1-f);ctx.lineWidth=1.5/k;ctx.stroke();
     ctx.globalAlpha=on?1:.22;ctx.shadowColor=col;ctx.shadowBlur=on?16:0;shapePath(ctx,n,r);ctx.fillStyle=col;ctx.fill();
     ctx.shadowBlur=0;ctx.lineWidth=2/k;ctx.strokeStyle=GC[n.group];ctx.stroke();ctx.font="700 "+(r*1.25)+"px 'DejaVu Sans',sans-serif";ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#03061a';ctx.fillText(n.icon||'',n.x,n.y+.5);ctx.textAlign='left';ctx.textBaseline='alphabetic';
     const fs=Math.min(14,Math.max(7,12/k)),t1=trunc(n.label,24)+(n.id.startsWith('ns:')?(expanded[n.id]?' ▾':' ▸'):''),t2=short(n.runs_as);
     ctx.font=fs+'px sans-serif';const w1=ctx.measureText(t1).width;ctx.font=(fs*.78)+'px sans-serif';const w2=ctx.measureText(t2).width,bw=Math.min(CW-36,Math.max(w1,w2)+8);
     ctx.fillStyle='rgba(3,6,26,.82)';rr(ctx,n.x+r+3,n.y-fs*.9,bw,fs*2.1,3);ctx.fill();
     ctx.font=fs+'px sans-serif';ctx.fillStyle='#e6f6ff';ctx.fillText(t1,n.x+r+6,n.y+fs*.1);
     ctx.font=(fs*.78)+'px sans-serif';ctx.fillStyle='#8fb0c8';ctx.fillText(t2,n.x+r+6,n.y+fs*.95);ctx.restore();})
   .nodePointerAreaPaint((n,c,ctx)=>{ctx.fillStyle=c;ctx.fillRect(n.x-14,n.y-16,CW-26,32)})
   .onNodeHover(n=>{hover=n;NB=nb();restyle()}).onNodeClick(select).onBackgroundClick(()=>select(null)).autoPauseRedraw(false);
  size(G);addEventListener('resize',()=>{size(G);fit2d()});
  restyle=()=>{G.linkColor(linkCol).linkWidth(l=>NB&&litLink(l)?2.2:1).linkDirectionalParticles(l=>(NB?litLink(l):l.main)?(l.cat==='api'?3:2):0)};
  relayout=()=>{LAY=layout();LINKS=visLinks();G.graphData({nodes:LAY.vis,links:LINKS});setTimeout(fit2d,200)};
  setTimeout(fit2d,300);setTimeout(fit2d,2000);
 }catch(e){fail(e&&e.message||e)}};
 document.head.appendChild(sc);
}
}catch(e){fail(e&&e.message||e)}})();
</script></body></html>"""


def render(inv):
    """Self-contained page; data is embedded as JSON with '<' escaped so no node text can close the script tag."""
    data = json.dumps(inv, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", " ").replace("\u2029", " ")
    return _PAGE.replace("__DATA__", data)


def node_table(inv):
    """Plain rows for a fallback table under the 3D view (also usable when WebGL/CDN is blocked)."""
    return [{"κόμβος": n["label"], "ομάδα": GROUPS[n["group"]][0], "κατάσταση": n["status"],
             "μοντέλο": (f"{n['model']} / {n['effort']}" + (" (override)" if n.get("override") else "")) if n.get("model") else "",
             "τρέχει ως": n["runs_as"], "πληροφορίες δικτύου": n["desc"] if n.get("network_info") else "", "heartbeat s": n["hb"]} for n in inv["nodes"]]


def routable(inv):
    """[(role, kind, model, effort)] for the selector."""
    out = []
    for n in inv["nodes"]:
        if n["group"] == "agents" and n.get("model"):
            out.append((n["id"], "claude", n["model"], n["effort"]))
        elif n["group"] == "codex":
            out.append((n["id"], "codex", n["model"], n["effort"]))
    return out
