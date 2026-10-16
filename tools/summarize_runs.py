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


def main():
    req = sys.argv[1]
    rows = []
    for d in sorted(glob.glob(os.path.join(LAB, "runs", f"*-{req}-e*"))):
        entry = json.load(open(os.path.join(d, "spec_entry.json"))).get("name", os.path.basename(d))
        status = json.load(open(os.path.join(d, "launcher.json"))).get("status") if os.path.exists(
            os.path.join(d, "launcher.json")) else "running"
        eps = [m for m in load(os.path.join(d, "metrics.jsonl")) if "reward" in m and "model" in m]
        ft = {r["model"]: r["steps_run"] for r in load(os.path.join(d, "results", "fine_tune_steps.jsonl"))}
        rows.append((os.path.basename(d), entry, status, eps, ft))

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
        mode = entry.split("-seed")[0]
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
