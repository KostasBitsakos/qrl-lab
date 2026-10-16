#!/usr/bin/env python3
"""Summarize launcher runs of one request: mean reward and mean VMs per entry and per model.

Usage: python3 tools/summarize_runs.py R-20261016-012
Reads .lab/runs/*-<request>-e*/{spec_entry.json, metrics.jsonl, results/fine_tune_steps.jsonl}.
Episode lines are metrics.jsonl objects with "model", "reward" and (optionally) "mean_vms".
"""
import glob
import json
import os
import statistics as st
import sys

LAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".lab")


def load(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def collect(req, lab=LAB):
    """Rows (run_dir_name, entry, status, episodes, fine_tune_steps) for every launcher run of request `req`."""
    rows = []
    for d in sorted(glob.glob(os.path.join(lab, "runs", f"*-{req}-e*"))):
        se = json.load(open(os.path.join(d, "spec_entry.json")))
        entry = (se.get("entry_spec") or {}).get("name") or se.get("name") or os.path.basename(d)
        lj = os.path.join(d, "launcher.json")
        status = json.load(open(lj)).get("status") if os.path.exists(lj) else "running"
        eps = [m for m in load(os.path.join(d, "metrics.jsonl")) if "reward" in m and "model" in m]
        ft = {r["model"]: r["steps_run"] for r in load(os.path.join(d, "results", "fine_tune_steps.jsonl"))}
        rows.append((os.path.basename(d), entry, status, eps, ft))
    return rows


def mode_of(entry):
    return entry.split("-seed")[0]


def _sd(x):
    return st.stdev(x) if len(x) > 1 else 0.0


def aggregate_by_seed(rows):
    """{mode: {model: {"n_seeds", "reward_mean", "reward_sd", "vms_mean", "vms_sd"}}}.

    Per run (= one seed) the episodes of a model are averaged first; mean and sd are then taken over the runs of the
    mode, so the error bars are between-seed spread. With a single seed the sd is 0.
    """
    per_run = {}
    for run, entry, _, eps, _ in rows:
        for model in {e["model"] for e in eps}:
            es = [e for e in eps if e["model"] == model]
            r = st.mean(e["reward"] for e in es)
            v = [e["mean_vms"] for e in es if "mean_vms" in e]
            per_run.setdefault((mode_of(entry), model), []).append((r, st.mean(v) if v else None))
    out = {}
    for (mode, model), lst in per_run.items():
        rs = [x[0] for x in lst]
        vs = [x[1] for x in lst if x[1] is not None]
        out.setdefault(mode, {})[model] = {
            "n_seeds": len(lst), "reward_mean": st.mean(rs), "reward_sd": _sd(rs),
            "vms_mean": st.mean(vs) if vs else None, "vms_sd": _sd(vs) if vs else None}
    return out


def request_ids(lab=LAB):
    """Request ids that have launcher runs (from run directory names ...-R-YYYYMMDD-NNN-eK-aK)."""
    import re
    ids = set()
    for d in glob.glob(os.path.join(lab, "runs", "*")):
        m = re.search(r"-(R-\d{8}-\d+)-e\d+", os.path.basename(d))
        if m:
            ids.add(m.group(1))
    return sorted(ids)


def main():
    req = sys.argv[1]
    rows = collect(req)

    print(f"| run | entry | status | episodes | mean reward / episode | mean VMs | fine-tune steps run |")
    print("|---|---|---|---|---|---|---|")
    for run, entry, status, eps, ft in rows:
        r = [e["reward"] for e in eps]
        v = [e["mean_vms"] for e in eps if "mean_vms" in e]
        print(f"| {run[-6:]} | {entry} | {status} | {len(eps)} | "
              f"{st.mean(r):,.0f} | {st.mean(v):.2f} | {', '.join(str(x) for x in ft.values()) or '-'} |"
              if r else f"| {run[-6:]} | {entry} | {status} | 0 | - | - | - |")

    print("\nPer model (mean over seeds of the per-episode mean):")
    groups = {}
    for _, entry, _, eps, _ in rows:
        mode = mode_of(entry)
        for e in eps:
            groups.setdefault((mode, e["model"]), []).append(e)
    print("| mode | model | n episodes | mean reward | sd reward | mean VMs |")
    print("|---|---|---|---|---|---|")
    for (mode, model), es in sorted(groups.items(), key=lambda kv: (str(kv[0][1]), kv[0][0])):
        r = [e["reward"] for e in es]
        v = [e["mean_vms"] for e in es if "mean_vms" in e]
        sd = st.stdev(r) if len(r) > 1 else 0.0
        print(f"| {mode} | {model} | {len(r)} | {st.mean(r):,.0f} | {sd:,.0f} | {st.mean(v):.2f} |" if v else
              f"| {mode} | {model} | {len(r)} | {st.mean(r):,.0f} | {sd:,.0f} | - |")


if __name__ == "__main__":
    main()
