#!/usr/bin/env python3
"""Read-only Kubernetes view for the dashboard. Only `kubectl get`, `version` and `config current-context` may run.

Pure parsing functions (testable with fixture JSON) plus one guarded subprocess wrapper.
"""
import datetime as dt
import json
import subprocess
import time

ALLOWED_VERBS = ("get", "version")  # plus exactly ["config", "current-context"]
RESOURCES = "pods,deployments,services,nodes,horizontalpodautoscalers"
_CACHE = {}
CACHE_TTL = 10.0


class K8sRefused(Exception):
    """A kubectl verb outside the allowlist was requested."""


def check_allowed(args):
    args = list(args)
    if args[:2] == ["config", "current-context"] and len(args) == 2:
        return
    if not args or args[0] not in ALLOWED_VERBS:
        raise K8sRefused(f"kubectl {args[0] if args else ''!r} is not allowed (read-only: {', '.join(ALLOWED_VERBS)})")
    if any(a in ("--kubeconfig", "--token", "--context", "--raw") or a.startswith(("--token=", "--kubeconfig=", "--context="))
           for a in args):
        raise K8sRefused("credential/context flags are not allowed")


def run_kubectl(args, timeout=8):
    """Returns (returncode, stdout, stderr). Never raises for a missing binary or timeout."""
    check_allowed(args)
    cmd = ["kubectl", "--request-timeout=5s"] + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "kubectl δεν βρέθηκε"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def first_line(text):
    for ln in (text or "").splitlines():
        if ln.strip():
            return ln.strip()
    return "—"


def current_context():
    rc, out, err = run_kubectl(["config", "current-context"], timeout=5)
    return out.strip() if rc == 0 and out.strip() else None


def fetch(now=None):
    """Cached (10 s) snapshot: {'up': bool, 'context', 'error', 'data'}."""
    now = time.time() if now is None else now
    hit = _CACHE.get("snap")
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    ctx = current_context()
    rc, out, err = run_kubectl(["get", RESOURCES, "-A", "-o", "json"])
    snap = {"up": False, "context": ctx, "error": None, "data": None, "fetched": now}
    if rc != 0:
        snap["error"] = first_line(err)
    else:
        try:
            snap["data"] = json.loads(out)
            snap["up"] = True
        except ValueError:
            snap["error"] = "μη έγκυρη JSON απάντηση"
    _CACHE["snap"] = (now, snap)
    return snap


def clear_cache():
    _CACHE.clear()


# ------------------------------------------------------------------ pure parsing
def _ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def age_str(created, now=None):
    t = _ts(created)
    if not t:
        return "—"
    now = now or dt.datetime.now(dt.timezone.utc)
    s = max(0, int((now - t).total_seconds()))
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{s // n}{unit}"
    return f"{s}s"


BAD_WAITING = {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError",
               "CreateContainerError", "InvalidImageName", "RunContainerError"}


def parse_pod(p, now=None):
    md, st, spec = p.get("metadata", {}), p.get("status", {}), p.get("spec", {})
    phase = st.get("phase", "Unknown")
    cs = st.get("containerStatuses") or []
    ready_n = sum(1 for c in cs if c.get("ready"))
    total = len(cs) or len(spec.get("containers", []))
    restarts = sum(c.get("restartCount", 0) for c in cs)
    reasons = []
    for c in cs:
        w = (c.get("state") or {}).get("waiting") or {}
        if w.get("reason") in BAD_WAITING:
            reasons.append(f"{c.get('name')}: {w['reason']}")
        t = (c.get("lastState") or {}).get("terminated") or {}
        if t.get("reason") == "OOMKilled":
            reasons.append(f"{c.get('name')}: OOMKilled")
    if phase == "Pending":
        for cond in st.get("conditions") or []:
            if cond.get("type") == "PodScheduled" and cond.get("status") == "False":
                reasons.append(f"Pending: {cond.get('reason', '')} {cond.get('message', '')}".strip())
        if not reasons:
            for c in cs:
                w = (c.get("state") or {}).get("waiting") or {}
                if w.get("reason"):
                    reasons.append(f"{c.get('name')}: {w['reason']}")
            if not reasons:
                reasons.append("Pending")
    if phase == "Failed":
        reasons.append(f"Failed: {st.get('reason', '')}".strip())
    conds = {c.get("type"): c.get("status") for c in st.get("conditions") or []}
    is_ready = conds.get("Ready") == "True"
    if phase == "Succeeded":
        health = "ok"
    elif reasons or phase in ("Failed", "Unknown"):
        health = "failing"
    elif not is_ready or restarts >= 5:
        health = "degraded"
        if not is_ready:
            reasons.append("Ready=False")
        if restarts >= 5:
            reasons.append(f"{restarts} restarts")
    else:
        health = "ok"
    return {"name": md.get("name"), "namespace": md.get("namespace"), "phase": phase, "ready": f"{ready_n}/{total}",
            "restarts": restarts, "age": age_str(md.get("creationTimestamp"), now), "node": spec.get("nodeName") or "—",
            "health": health, "reasons": reasons}


def parse_deployment(d):
    md, st, spec = d.get("metadata", {}), d.get("status", {}), d.get("spec", {})
    desired = spec.get("replicas", 1)
    ready, avail = st.get("readyReplicas", 0), st.get("availableReplicas", 0)
    health = "ok" if avail == desired else ("failing" if avail == 0 and desired > 0 else "degraded")
    return {"name": md.get("name"), "namespace": md.get("namespace"), "ready": f"{ready}/{desired}",
            "up_to_date": st.get("updatedReplicas", 0), "available": avail, "desired": desired, "health": health,
            "reasons": [] if health == "ok" else [f"available {avail}/{desired}"]}


def parse_service(s):
    md, spec = s.get("metadata", {}), s.get("spec", {})
    ports = ", ".join(f"{p.get('port')}{'/' + p['protocol'] if p.get('protocol') else ''}"
                      + (f":{p['nodePort']}" if p.get("nodePort") else "") for p in spec.get("ports") or [])
    return {"name": md.get("name"), "namespace": md.get("namespace"), "type": spec.get("type", "ClusterIP"),
            "cluster_ip": spec.get("clusterIP", "—"), "ports": ports or "—"}


def parse_node(n):
    md, st = n.get("metadata", {}), n.get("status", {})
    conds = {c.get("type"): c for c in st.get("conditions") or []}
    ready = conds.get("Ready", {}).get("status") == "True"
    reasons = [] if ready else [f"NotReady: {conds.get('Ready', {}).get('reason', 'Unknown')}"]
    for k in ("MemoryPressure", "DiskPressure", "PIDPressure"):
        if conds.get(k, {}).get("status") == "True":
            reasons.append(k)
    cap = st.get("capacity", {})
    health = "failing" if not ready else ("degraded" if reasons else "ok")
    return {"name": md.get("name"), "ready": ready, "cpu": cap.get("cpu", "—"), "memory": cap.get("memory", "—"),
            "health": health, "reasons": reasons}


def parse_hpa(h):
    md, st, spec = h.get("metadata", {}), h.get("status", {}), h.get("spec", {})
    targets = []
    for m in spec.get("metrics") or []:
        r = m.get("resource") or {}
        tgt = r.get("target", {})
        val = tgt.get("averageUtilization", tgt.get("averageValue", "?"))
        cur = "?"
        for cm in st.get("currentMetrics") or []:
            cr = cm.get("resource") or {}
            if cr.get("name") == r.get("name"):
                cur = cr.get("current", {}).get("averageUtilization", cr.get("current", {}).get("averageValue", "?"))
        targets.append(f"{r.get('name', m.get('type'))}: {cur}/{val}")
    return {"name": md.get("name"), "namespace": md.get("namespace"), "current": st.get("currentReplicas", 0),
            "desired": st.get("desiredReplicas", 0), "min": spec.get("minReplicas"), "max": spec.get("maxReplicas"),
            "targets": ", ".join(targets) or "—"}


def parse_snapshot(data, namespace=None, now=None):
    """data = `kubectl get ... -o json` List. namespace None = all."""
    out = {"pods": [], "deployments": [], "services": [], "nodes": [], "hpas": []}
    for it in (data or {}).get("items", []):
        kind = it.get("kind")
        ns = it.get("metadata", {}).get("namespace")
        if kind != "Node" and namespace and ns != namespace:
            continue
        if kind == "Pod":
            out["pods"].append(parse_pod(it, now))
        elif kind == "Deployment":
            out["deployments"].append(parse_deployment(it))
        elif kind == "Service":
            out["services"].append(parse_service(it))
        elif kind == "Node":
            out["nodes"].append(parse_node(it))
        elif kind == "HorizontalPodAutoscaler":
            out["hpas"].append(parse_hpa(it))
    return out


def namespaces(data):
    return sorted({it["metadata"]["namespace"] for it in (data or {}).get("items", [])
                   if it.get("metadata", {}).get("namespace")})


def kpis(v):
    pods = v["pods"]
    return {"nodes_ready": sum(1 for n in v["nodes"] if n["ready"]), "nodes_total": len(v["nodes"]),
            "pods_running": sum(1 for p in pods if p["phase"] == "Running"),
            "pods_pending": sum(1 for p in pods if p["phase"] == "Pending"),
            "pods_failed": sum(1 for p in pods if p["phase"] == "Failed"),
            "deploys_ok": sum(1 for d in v["deployments"] if d["health"] == "ok"),
            "deploys_total": len(v["deployments"])}


def failing_items(v):
    """[(kind, name, health, reason)] for everything not ok."""
    rows = []
    for kind, key in (("Node", "nodes"), ("Deployment", "deployments"), ("Pod", "pods")):
        for x in v[key]:
            if x["health"] != "ok":
                nm = f"{x['namespace']}/{x['name']}" if x.get("namespace") else x["name"]
                rows.append((kind, nm, x["health"], "; ".join(x["reasons"]) or "—"))
    return rows


def pods_by_phase(v):
    """{namespace: {phase: count}}"""
    res = {}
    for p in v["pods"]:
        res.setdefault(p["namespace"], {}).setdefault(p["phase"], 0)
        res[p["namespace"]][p["phase"]] += 1
    return res
