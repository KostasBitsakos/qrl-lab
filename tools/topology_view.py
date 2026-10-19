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
}
STATUS_COLOR = {"alive": "#39ff88", "idle": "#6c8cff", "stale": "#ffb020", "down": "#ff3b5c", "unknown": "#8a94a6"}

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
    for (ns, name), w in sorted(wl.items()):
        nid = f"pod:{ns}/{name}"
        st = "alive" if w["running"] == w["n"] else ("down" if w["running"] == 0 else "stale")
        nodes.append(_node(nid, name, "cluster", f"k8s pod ×{w['n']} · ns {ns}",
                           f"Workload {name} στο namespace {ns}: {w['running']}/{w['n']} Running, restarts {w['restarts']}, φάσεις {sorted(w['phases'])}.",
                           st, extra="pods"))
        links.append((f"node:{w['node']}" if w["node"] else "k8s", nid, "runs"))
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
    names = {n["id"] for n in nodes}
    links = [{"source": s, "target": t, "kind": k} for s, t, k in links if s in names and t in names]
    return {"nodes": nodes, "links": links, "groups": {k: {"label": v[0], "color": v[1]} for k, v in GROUPS.items()},
            "status_colors": STATUS_COLOR, "now": src.get("now")}


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
#leg{position:absolute;left:8px;top:8px;background:#050818cc;border:1px solid #234;border-radius:8px;padding:6px 8px;font-size:11px;max-width:46vw;z-index:5}
#leg i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;box-shadow:0 0 6px currentColor}
#info{position:absolute;left:8px;right:8px;bottom:8px;background:#050818ee;border:1px solid #2a4;border-radius:10px;padding:8px 10px;font-size:12px;z-index:5;display:none}
.tip{background:#050818f0;border:1px solid #3af;border-radius:8px;padding:6px 9px;font-size:12px;max-width:260px;line-height:1.35}
.tip b{color:#fff}.k{color:#7ad}
</style></head><body><div id="g"></div><div id="leg"></div><div id="info"></div>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/3d-force-graph@1.73.4/dist/3d-force-graph.min.js"></script>
<script>
const D=__DATA__;
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SC=D.status_colors, GC={};for(const k in D.groups)GC[k]=D.groups[k].color;
const leg=document.getElementById('leg');
leg.innerHTML='<b>Ομάδες</b><br>'+Object.values(D.groups).map(g=>`<i style="color:${g.color};background:${g.color}"></i>${esc(g.label)}`).join('<br>')
 +'<br><b>Κατάσταση</b> (χρώμα πυρήνα)<br>'+Object.keys(SC).map(s=>`<i style="color:${SC[s]};background:${SC[s]}"></i>${s}`).join(' ')
 +'<br><span style="opacity:.7">παλμός = ηλικία heartbeat · σωματίδια = ροή</span>';
function tip(n){return `<div class="tip"><b>${esc(n.label)}</b><br>${esc(n.desc)}<br><span class="k">τρέχει ως:</span> ${esc(n.runs_as)}`
 +(n.model?`<br><span class="k">μοντέλο:</span> ${esc(n.model)} / ${esc(n.effort)}${n.override?' <b style="color:#ffb020">(override)</b>':''}`:'')
 +`<br><span class="k">κατάσταση:</span> <span style="color:${SC[n.status]}">${esc(n.status)}</span>`
 +(n.hb!=null?`<br><span class="k">heartbeat:</span> ${n.hb}s`:'')+(n.extra?`<br>${esc(n.extra)}`:'')+'</div>';}
const nodes=D.nodes.map(n=>Object.assign({},n)), idx={};nodes.forEach(n=>idx[n.id]=n);
const links=D.links.map(l=>Object.assign({},l));
const gl=[];  // pulsing meshes
function mk(n){
  const grp=new THREE.Group(), r=n.id==='coordinator'?7:(n.group==='external'?5:4);
  const core=new THREE.Mesh(new THREE.SphereGeometry(r,16,16),new THREE.MeshBasicMaterial({color:SC[n.status]||SC.unknown}));
  const shell=new THREE.Mesh(new THREE.SphereGeometry(r*1.7,16,16),new THREE.MeshBasicMaterial({color:GC[n.group],transparent:true,opacity:.22,depthWrite:false}));
  grp.add(core);grp.add(shell);
  const period=n.hb==null?(n.status==='alive'?2.4:(n.status==='idle'?5:0)):Math.min(8,Math.max(.8,.8+n.hb/30));
  const st=n.status==='down'||n.status==='stale'?1.8:1;
  if(period>0)gl.push({shell,core,period:period/st,ph:Math.random()*6.28,amp:n.status==='alive'?.28:.12});
  return grp;}
const el=document.getElementById('g'), info=document.getElementById('info');
const G=ForceGraph3D()(el).backgroundColor('rgba(0,0,0,0)').graphData({nodes,links})
 .nodeThreeObject(mk).nodeLabel(tip).nodeThreeObjectExtend(false)
 .linkColor(l=>'rgba(120,200,255,.35)').linkWidth(.4).linkOpacity(.5)
 .linkDirectionalParticles(l=>l.kind==='API'?3:2).linkDirectionalParticleWidth(1.6).linkDirectionalParticleSpeed(.006)
 .linkDirectionalParticleColor(l=>GC[(idx[l.target.id||l.target]||{}).group]||'#fff')
 .onNodeClick(n=>{info.style.display='block';info.innerHTML=tip(n).replace('class="tip"','');
   const d=70;G.cameraPosition({x:n.x*(1+d/Math.hypot(n.x,n.y,n.z||1)),y:n.y*(1+d/Math.hypot(n.x,n.y,n.z||1)),z:(n.z||0)*(1+d/Math.hypot(n.x,n.y,n.z||1))},n,900);})
 .onBackgroundClick(()=>{info.style.display='none'});
// group clustering: weak pull toward a per-group anchor
const keys=Object.keys(D.groups), anc={};keys.forEach((k,i)=>{const a=i/keys.length*6.283;anc[k]={x:Math.cos(a)*90,y:(i%2?1:-1)*35,z:Math.sin(a)*90}});
G.d3Force('cluster',a=>{nodes.forEach(n=>{const c=anc[n.group];if(!c||n.x==null)return;n.vx+=(c.x-n.x)*.012*a;n.vy+=(c.y-n.y)*.012*a;n.vz+=(c.z-n.z)*.012*a})});
G.d3Force('link').distance(28);
function size(){G.width(window.innerWidth).height(window.innerHeight)}size();addEventListener('resize',size);
const ctl=G.controls();ctl.autoRotate=true;ctl.autoRotateSpeed=.5;
el.addEventListener('pointerdown',()=>{ctl.autoRotate=false});
(function tick(t){requestAnimationFrame(tick);t=t/1000;gl.forEach(o=>{const s=1+o.amp*Math.sin(t*6.283/o.period+o.ph);o.shell.scale.setScalar(s);o.core.scale.setScalar(1+(s-1)*.4)})})(0);
</script></body></html>"""


def render(inv):
    """Self-contained page; data is embedded as JSON with '<' escaped so no node text can close the script tag."""
    data = json.dumps(inv, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", " ").replace("\u2029", " ")
    return _PAGE.replace("__DATA__", data)


def node_table(inv):
    """Plain rows for a fallback table under the 3D view (also usable when WebGL/CDN is blocked)."""
    return [{"κόμβος": n["label"], "ομάδα": GROUPS[n["group"]][0], "κατάσταση": n["status"],
             "μοντέλο": (f"{n['model']} / {n['effort']}" + (" (override)" if n.get("override") else "")) if n.get("model") else "",
             "τρέχει ως": n["runs_as"], "heartbeat s": n["hb"]} for n in inv["nodes"]]


def routable(inv):
    """[(role, kind, model, effort)] for the selector."""
    out = []
    for n in inv["nodes"]:
        if n["group"] == "agents" and n.get("model"):
            out.append((n["id"], "claude", n["model"], n["effort"]))
        elif n["group"] == "codex":
            out.append((n["id"], "codex", n["model"], n["effort"]))
    return out
