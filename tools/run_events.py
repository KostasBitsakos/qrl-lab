#!/usr/bin/env python3
"""v0.5.1 B3: end-of-batch summary written by a script (no model call).

`summary(request_id, runs, lab_dir)` -> Greek text with one line per run and, when episode metrics exist, mean reward and
VMs per mode and model (summarize_runs.aggregate_by_seed). Every summary carries a marker `[run-summary <ref>]` so the
dispatcher can tell, after a crash or restart, that it was already posted (exactly once)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summarize_runs as S  # noqa: E402

OK_STATUSES = ("done",)


def marker(ref):
    return f"[run-summary {ref}]"


def all_ok(runs):
    return bool(runs) and all(r["status"] in OK_STATUSES and (r["exit_code"] in (0, None)) for r in runs)


def summary(rid, runs, ref, lab_dir=None):
    lines = [f"Κώστα, η παρτίδα τελείωσε: και τα {len(runs)} πειράματα ολοκληρώθηκαν χωρίς σφάλμα."]
    full = ["Technical list:"] + [f"- {r['run_id']} · entry {r['entry']} · attempt {r['attempt']} · {r['name'] or '-'}"
                                  f" · {r['status']} · {r['run_dir']}" for r in sorted(runs, key=lambda r: (r["entry"], r["attempt"]))]
    try:
        agg = S.aggregate_by_seed(S.collect(rid, lab_dir or S.LAB))
    except Exception:  # metrics are optional: the list above is still the summary
        agg = {}
    if agg:
        lines += ["", "Μέσο reward ανά μοντέλο και workload (σε παρένθεση η διακύμανση):", "",
                  "| workload | μοντέλο | seeds | μέσο reward (sd) | μέσα VMs |", "|---|---|---|---|---|"]
        for mode in sorted(agg):
            for model, a in sorted(agg[mode].items()):
                vms = "-" if a["vms_mean"] is None else f"{a['vms_mean']:.2f}"
                lines.append(f"| {mode} | {model} | {a['n_seeds']} | {a['reward_mean']:,.0f} ({a['reward_sd']:,.0f}) | {vms} |")
    else:
        lines += ["", "Δεν βρέθηκαν ακόμα αριθμητικά αποτελέσματα· θα τα δεις όταν γίνει η ανάλυση."]
    lines += ["", "Ζήτα μου ανάλυση αν τη θέλεις. Αρχεία: καρτέλα 📁 Αρχεία.", "", marker(ref)]
    return "\n".join(lines) + "\n\n" + "\n".join(full)
