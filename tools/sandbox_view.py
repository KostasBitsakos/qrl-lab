"""Read-only view model of sandbox ledgers (.lab/sandbox/<RID>.ledger.jsonl) for the dashboard Sandbox section.

Ledger events: start {ts, run_id, name, seeds, reserve_cpu_h, cpus, cores}; done {ts, run_id, wall_s, cpu_seconds}.
The entry name comes from the DB runs.name ("<child>/<entry>") when the run is known, else the ledger's child name.
Status of a finished run comes from the DB (the done event has none); "?" when the DB does not know it.
"""
import datetime as dt
import glob
import json
import os


def _ts(s):
    try:
        return dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def read_ledger(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    out.append(o)
    except OSError:
        pass
    return out


def ledger_paths(sandbox_dir):
    return sorted(glob.glob(os.path.join(sandbox_dir, "*.ledger.jsonl")))


def summarize(events, runs_by_id=None, now=None, last=20):
    """-> {"running": [...], "finished": [... newest first, at most `last`]}."""
    runs_by_id = runs_by_id or {}
    now = now or dt.datetime.now(dt.timezone.utc)
    starts, done = {}, {}
    for e in events:
        if e.get("event") == "start":
            starts[e.get("run_id")] = e
        elif e.get("event") == "done":
            done[e.get("run_id")] = e
    running, finished = [], []
    for rid, s in starts.items():
        r = runs_by_id.get(rid) or {}
        name = r.get("name") or s.get("name") or ""
        t0 = _ts(s.get("ts"))
        if rid in done:
            d = done[rid]
            finished.append({"run_id": rid, "name": name, "wall_s": d.get("wall_s"), "cpu_seconds": d.get("cpu_seconds"),
                             "status": r.get("status") or "?", "ts": d.get("ts")})
        else:
            running.append({"run_id": rid, "name": name, "batch": s.get("name") or "", "cores": s.get("cores") or [],
                            "started": s.get("ts"), "elapsed_s": (now - t0).total_seconds() if t0 else None})
    finished.sort(key=lambda x: x["ts"] or "", reverse=True)
    running.sort(key=lambda x: x["started"] or "")
    return {"running": running, "finished": finished[:last]}
