#!/usr/bin/env python3
"""Read-only Prometheus view for the dashboard.

Only HTTP GET to /api/v1/query, /api/v1/query_range and /api/v1/label/__name__/values is allowed.
PromQL lives in CATALOGUE; parsing and query building are pure functions (tested with mocked responses).

NOTE: this cluster has no node-exporter (no node_* metrics). The "Node" entries therefore use the cAdvisor
root cgroup (id="/") and machine_* metrics; node_load1 has no equivalent and is not offered as a default.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("QRL_PROM_URL", "http://10.0.1.28:30000")
ALLOWED_PATHS = ("/api/v1/query", "/api/v1/query_range", "/api/v1/label/__name__/values")
RANGES = {"15 m": 15, "1 h": 60, "6 h": 360, "24 h": 1440}  # label -> minutes
TIMEOUT = 8

# Redis pods live in the default namespace; qrl-calib is included when it exists (the regex simply matches nothing otherwise).
REDIS = 'namespace=~"default|qrl-calib",pod=~"redis.*",container!="",container!="POD"'
REDIS_NOCT = 'namespace=~"default|qrl-calib",pod=~"redis.*"'

# key -> (category, title, expr, unit, default, note)
_E = [
    ("node_cpu", "Node", "CPU utilisation % (cAdvisor root cgroup / cores)",
     'sum(rate(container_cpu_usage_seconds_total{id="/"}[5m])) / sum(machine_cpu_cores) * 100', "%", True, ""),
    ("node_mem", "Node", "Memory used % (working set / machine memory)",
     'sum(container_memory_working_set_bytes{id="/"}) / sum(machine_memory_bytes) * 100', "%", True, ""),
    ("node_net_rx", "Node", "Network rx (B/s, root cgroup)",
     'sum(rate(container_network_receive_bytes_total{id="/"}[5m]))', "B/s", False, ""),
    ("node_net_tx", "Node", "Network tx (B/s, root cgroup)",
     'sum(rate(container_network_transmit_bytes_total{id="/"}[5m]))', "B/s", False, ""),
    ("node_disk_read", "Node", "Disk read (B/s, root cgroup)",
     'sum(rate(container_fs_reads_bytes_total{id="/"}[5m]))', "B/s", False, ""),
    ("node_disk_write", "Node", "Disk write (B/s, root cgroup)",
     'sum(rate(container_fs_writes_bytes_total{id="/"}[5m]))', "B/s", False, ""),
    ("node_load1", "Node", "load1 (node-exporter)", "node_load1", "", False, "needs node-exporter"),
    ("node_cpu_ne", "Node", "CPU utilisation % (node-exporter)",
     '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100', "%", False, "needs node-exporter"),
    ("node_mem_ne", "Node", "Memory used % (node-exporter)",
     '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100', "%", False, "needs node-exporter"),
    ("node_disk_io_ne", "Node", "Disk IO time (node-exporter)",
     'rate(node_disk_io_time_seconds_total[5m])', "s/s", False, "needs node-exporter"),
    ("redis_cpu", "Redis pods", "CPU per pod (cores)",
     f'sum by (namespace,pod) (rate(container_cpu_usage_seconds_total{{{REDIS}}}[5m]))', "cores", True, ""),
    ("redis_mem", "Redis pods", "Memory working set per pod (MiB)",
     f'sum by (namespace,pod) (container_memory_working_set_bytes{{{REDIS}}}) / 1048576', "MiB", True, ""),
    ("redis_mem_pct", "Redis pods", "Memory working set vs container limit (% of 16Mi)",
     f'container_memory_working_set_bytes{{{REDIS}}} / on(namespace,pod,container) '
     f'(container_spec_memory_limit_bytes{{{REDIS}}} > 0) * 100', "%", True, ""),
    ("redis_throttle", "Redis pods", "CPU throttling ratio (throttled / total periods)",
     f'sum by (namespace,pod) (rate(container_cpu_cfs_throttled_periods_total{{{REDIS}}}[5m])) / '
     f'sum by (namespace,pod) (rate(container_cpu_cfs_periods_total{{{REDIS}}}[5m]))', "ratio", True, ""),
    ("redis_pods", "Redis pods", "Pod count (Running)",
     'count(kube_pod_status_phase{namespace=~"default|qrl-calib",pod=~"redis.*",phase="Running"} == 1)', "pods", True, ""),
    ("redis_restarts", "Redis pods", "Container restarts",
     'sum by (namespace,pod) (kube_pod_container_status_restarts_total{namespace=~"default|qrl-calib",pod=~"redis.*"})',
     "restarts", False, ""),
    ("k8s_phase", "Kubernetes", "Pods by phase",
     'sum by (phase) (kube_pod_status_phase == 1)', "pods", True, ""),
    ("k8s_dep_desired", "Kubernetes", "Deployment replicas desired",
     'kube_deployment_spec_replicas{namespace=~"default|qrl-calib"}', "replicas", False, ""),
    ("k8s_dep_avail", "Kubernetes", "Deployment replicas available",
     'kube_deployment_status_replicas_available{namespace=~"default|qrl-calib"}', "replicas", True, ""),
    ("prom_up", "Prometheus", "Up targets",
     'sum(up)', "targets", True, ""),
    ("prom_up_by_job", "Prometheus", "Up by job",
     'sum by (job) (up)', "targets", False, ""),
]
CATALOGUE = {k: {"key": k, "category": c, "title": t, "expr": e, "unit": u, "default": d, "note": n}
             for k, c, t, e, u, d, n in _E}
CATEGORIES = list(dict.fromkeys(v["category"] for v in CATALOGUE.values()))


class PromRefused(Exception):
    """A request outside the read-only allowlist was attempted."""


def check_path(path):
    if path not in ALLOWED_PATHS:
        raise PromRefused(f"Prometheus path {path!r} is not allowed (read-only GET: {', '.join(ALLOWED_PATHS)})")


def http_get(path, params=None, base=None, timeout=TIMEOUT):
    """GET base+path; returns parsed JSON. Raises PromError on any failure. Only allowlisted paths."""
    check_path(path)
    url = (base or BASE_URL).rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise PromError(str(e)) from e


class PromError(Exception):
    pass


def step_for(minutes):
    """Step in seconds giving at most ~240 points, at least 15 s."""
    return max(15, int(minutes * 60 / 240))


def build_range_params(expr, minutes, now=None):
    now = int(now if now is not None else time.time())
    return {"query": expr, "start": now - minutes * 60, "end": now, "step": step_for(minutes)}


def default_expr_for_metric(name, is_counter=None):
    """Free-form metric: rate() for counters (by naming convention), the raw selector otherwise."""
    if is_counter is None:
        is_counter = name.endswith(("_total", "_count", "_sum", "_bucket"))
    return f"rate({name}[5m])" if is_counter else name


def series_label(metric, fallback="series"):
    for k in ("pod", "deployment", "phase", "job", "instance", "namespace"):
        if metric.get(k):
            ns = metric.get("namespace")
            return f"{ns}/{metric[k]}" if k == "pod" and ns else metric[k]
    rest = {k: v for k, v in metric.items() if k != "__name__"}
    return ",".join(f"{k}={v}" for k, v in sorted(rest.items())) or metric.get("__name__", fallback)


def parse_matrix(resp):
    """-> list of (label, [(ts, float), ...]); NaN/Inf samples dropped. Raises PromError on status != success."""
    if not isinstance(resp, dict) or resp.get("status") != "success":
        raise PromError((resp or {}).get("error", "bad response") if isinstance(resp, dict) else "bad response")
    out = []
    for s in resp["data"].get("result", []):
        pts = []
        for ts, v in s.get("values", []):
            try:
                f = float(v)
            except ValueError:
                continue
            if f == f and f not in (float("inf"), float("-inf")):
                pts.append((float(ts), f))
        if pts:
            out.append((series_label(s.get("metric", {})), pts))
    return out


def parse_vector(resp):
    if not isinstance(resp, dict) or resp.get("status") != "success":
        raise PromError("bad response")
    out = []
    for s in resp["data"].get("result", []):
        try:
            out.append((series_label(s.get("metric", {})), float(s["value"][1])))
        except (KeyError, ValueError, IndexError):
            continue
    return out


def parse_names(resp):
    if not isinstance(resp, dict) or resp.get("status") != "success":
        raise PromError("bad response")
    return sorted(resp.get("data", []))


def query_range(expr, minutes, base=None, now=None):
    return parse_matrix(http_get("/api/v1/query_range", build_range_params(expr, minutes, now), base))


def metric_names(base=None):
    return parse_names(http_get("/api/v1/label/__name__/values", None, base))


def has_data(expr, base=None):
    try:
        return bool(parse_vector(http_get("/api/v1/query", {"query": expr}, base)))
    except PromError:
        return False


def availability(base=None):
    return {k: has_data(v["expr"], base) for k, v in CATALOGUE.items()}


if __name__ == "__main__":  # quick check against the live server (GET only)
    for k, ok in availability().items():
        print(("DATA   " if ok else "EMPTY  ") + k + ("  [default]" if CATALOGUE[k]["default"] else ""))
