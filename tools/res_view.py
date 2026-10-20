"""Resource breakdown for the dashboard Resources tab: who uses CPU / RAM / disk. Read-only (kubectl get/top only).

Pure helpers (redact, categorize, parse_cpu, parse_mem, shares, batch_arm) are unit-tested; collect() does the I/O.
"""
import json
import os
import re
import shutil
import subprocess
import time

CATS = ["experiments", "k8s", "dashboard+agents", "other", "free"]
SECRET = re.compile(r"(token|key|passw|secret|auth|credential)", re.I)


def redact(argv, maxlen=120):
    """Short command line with secret-looking arguments masked (--token X, --api-key=X, TOKEN=X, long hex/base64)."""
    out, hide_next = [], False
    for a in argv or []:
        a = str(a)
        if hide_next:
            out.append("***"); hide_next = False
        elif SECRET.search(a):
            if "=" in a:
                out.append(a.split("=", 1)[0] + "=***")
            elif a.startswith("-"):
                out.append(a); hide_next = True
            else:
                out.append("***")
        elif len(a) >= 32 and re.fullmatch(r"[A-Za-z0-9_\-+/=.]+", a) and not a.startswith("/"):
            out.append("***")
        else:
            out.append(a)
    s = " ".join(out)
    return s if len(s) <= maxlen else s[:maxlen - 1] + "…"


def categorize(name, cmdline):
    """Non-experiment process -> category by name/command (experiments are attributed by pid tree, not here)."""
    s = (str(name) + " " + " ".join(cmdline or [])).lower()
    if "streamlit" in s or "qrl-lab/dashboard" in s:
        return "dashboard+agents", "dashboard"
    if re.search(r"\b(claude|codex)\b", s) or "/.claude/" in s or "/.codex/" in s:
        return "dashboard+agents", "claude/codex"
    if "redis" in s:
        return "other", "redis"
    if "prometheus" in s or "grafana" in s:
        return "other", "prometheus/grafana"
    if re.search(r"kubelet|kube-|etcd|containerd|dockerd", s):
        return "k8s", "k8s daemon"
    return "other", str(name)


def parse_cpu(v):
    """kubectl top CPU ('3m', '1', '250000n') -> percent of one core."""
    v = str(v)
    if v.endswith("m"): return float(v[:-1]) / 10
    if v.endswith("n"): return float(v[:-1]) / 1e7
    return float(v) * 100


def parse_mem(v):
    """kubectl top memory ('9Mi', '1Gi', '512Ki') -> bytes."""
    m = re.fullmatch(r"([\d.]+)([KMGT]i?)?", str(v))
    if not m: return 0
    mult = {None: 1, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "Ki": 1024, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40}[m.group(2)]
    return int(float(m.group(1)) * mult)


def batch_arm(spec_name, entry_name):
    """('c10a-39', 'c10a-baselines-spike300_d10') -> ('c10a', 'baselines-spike300_d10')."""
    n = str(entry_name or spec_name or "")
    m = re.match(r"^(c\d+[a-z]?\d*)-(.*)$", n)
    if m: return m.group(1), m.group(2)
    m = re.match(r"^(c\d+[a-z]?\d*)", str(spec_name or ""))
    return (m.group(1) if m else str(spec_name or "?")), n


def shares(items, key, total=None):
    """Sum `key` per category -> {cat: value}; with `total` an extra 'free' entry is total - sum (>= 0)."""
    out = {}
    for it in items:
        out[it["category"]] = out.get(it["category"], 0) + (it.get(key) or 0)
    if total is not None:
        out["free"] = max(0, total - sum(out.values()))
    return out


def _du(path, cap_s=3.0):
    t0, tot = time.time(), 0
    for dp, _dn, fn in os.walk(path, onerror=lambda e: None):
        for f in fn:
            try: tot += os.lstat(os.path.join(dp, f)).st_size
            except OSError: pass
        if time.time() - t0 > cap_s: break
    return tot


def _kubectl(args):
    try:
        p = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=8)
        return p.stdout if p.returncode == 0 else None
    except Exception:  # noqa: BLE001 - optional source
        return None


def k8s_pods():
    """[{name, ns, cpu_pct, mem}] from read-only `kubectl get pods` + `kubectl top pods`; None for metrics if unavailable."""
    got = _kubectl(["get", "pods", "-A", "-o", "json"])
    if got is None: return None, None
    try: pods = [(p["metadata"]["namespace"], p["metadata"]["name"], p.get("status", {}).get("phase")) for p in json.loads(got)["items"]]
    except (ValueError, KeyError): return None, None
    top = _kubectl(["top", "pods", "-A", "--no-headers"])
    usage = None
    if top is not None:
        usage = {}
        for ln in top.splitlines():
            f = ln.split()
            if len(f) >= 4:
                try: usage[(f[0], f[1])] = (parse_cpu(f[2]), parse_mem(f[3]))
                except ValueError: pass
    return pods, usage


def collect(root, db_runs):
    """Snapshot -> {items: [...], totals: {...}, notes: [...]}. items: name, category, cpu, mem, disk (bytes)."""
    import psutil
    notes, items = [], []
    procs = {}
    for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try: p.cpu_percent(None); procs[p.pid] = p
        except psutil.Error: pass
    time.sleep(0.4)
    cpu, rss, info = {}, {}, {}
    for pid, p in procs.items():
        try:
            cpu[pid] = p.cpu_percent(None); rss[pid] = p.info["memory_info"].rss if p.info["memory_info"] else 0
            info[pid] = (p.info["name"], p.info["cmdline"] or [])
        except psutil.Error: pass
    claimed = set()
    for r in db_runs:
        if r.get("status") != "running" or not r.get("pid") or r["pid"] not in procs: continue
        tree = {r["pid"]} | {c.pid for c in procs[r["pid"]].children(recursive=True)}
        tree &= set(cpu)
        claimed |= tree
        try: se = json.load(open(os.path.join(r["run_dir"], "spec_entry.json")))
        except (OSError, ValueError): se = {}
        b, arm = batch_arm(se.get("spec_name"), (se.get("entry_spec") or {}).get("name") or r.get("name"))
        disk = _du(r["run_dir"])
        cmd = (se.get("entry_spec") or {}).get("cmd") or []
        if "--out" in cmd and cmd.index("--out") + 1 < len(cmd):
            out = os.path.join(se.get("cwd") or "", cmd[cmd.index("--out") + 1])
            try: disk += os.path.getsize(out)
            except OSError: pass
        items.append({"name": f"{b} · {arm}", "category": "experiments", "cpu": sum(cpu[i] for i in tree),
                      "mem": sum(rss[i] for i in tree), "disk": disk, "detail": redact(cmd)})
    groups = {}
    for pid in cpu:
        if pid in claimed: continue
        cat, label = categorize(*info[pid])
        if cat == "other" and label not in ("redis", "prometheus/grafana"):
            try:
                if "kubepods" in open(f"/proc/{pid}/cgroup").read(): continue   # counted via kubectl top
            except OSError: pass
            label = "σύστημα (υπόλοιπο)"
        g = groups.setdefault((cat, label), [0.0, 0])
        g[0] += cpu[pid]; g[1] += rss[pid]
    for (cat, label), (c, m) in groups.items():
        items.append({"name": label, "category": cat, "cpu": c, "mem": m, "disk": 0, "detail": ""})
    pods, usage = k8s_pods()
    if pods is None: notes.append("Kubernetes: μη διαθέσιμο")
    else:
        if usage is None: notes.append("kubectl top: μη διαθέσιμο (metrics-server)")
        for ns, nm, ph in pods:
            u = (usage or {}).get((ns, nm))
            items.append({"name": f"{ns}/{nm}", "category": "k8s", "cpu": u[0] if u else 0, "mem": u[1] if u else 0,
                          "disk": 0, "detail": ph or "", "unavailable": u is None})
    home = os.path.expanduser("~")
    for nm, paths in (("dashboard + .lab", [os.path.join(root, "dashboard"), os.path.join(root, ".lab")]),
                      ("Claude/Codex δεδομένα", [os.path.join(home, ".claude"), os.path.join(home, ".codex")])):
        d = sum(_du(p) for p in paths if os.path.isdir(p))
        for it in items:
            if it["category"] == "dashboard+agents" and ((nm.startswith("dash") and it["name"] == "dashboard") or (nm.startswith("Claude") and it["name"] == "claude/codex")):
                it["disk"] += d; break
        else:
            items.append({"name": nm, "category": "dashboard+agents", "cpu": 0, "mem": 0, "disk": d, "detail": ""})
    notes.append("Δίσκος k8s/system: δεν μετριέται (απαιτεί δικαιώματα)· η «άλλο» = χρησιμοποιούμενος − μετρημένα.")
    vm, du = psutil.virtual_memory(), shutil.disk_usage(root)
    return {"items": items, "notes": notes,
            "totals": {"cpu": psutil.cpu_count() * 100.0, "mem": vm.total, "disk": du.total, "disk_used": du.used}}
