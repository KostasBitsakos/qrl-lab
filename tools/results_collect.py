#!/usr/bin/env python3
"""Rebuild the paper-results folder for a cycle (copy-only, idempotent).

Usage: python3 tools/results_collect.py [--root DIR] [--out DIR] [--check]
Cycle 2-3 (default out): "Αποτελέσματα 2ου Κύκλου Πειραμάτων Poisson".
Cycle-4 results go to the sibling folder "Αποτελέσματα 4ου Κύκλου Poisson" (register batches in a
MANIFEST list the same way). Only existing summaries/traces are copied; spent/gated test splits
are never re-read: test12 appears only through the already-written summary .lab/j414/t12_analysis.json.
Per-seed CSVs are flattened from those summaries, nothing is recomputed or invented.
"""
import argparse, csv, hashlib, json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_NAME = "Αποτελέσματα 2ου Κύκλου Πειραμάτων Poisson"

# (batch folder, label, source rel path, split, seeds, feeds)
J444 = "code-poisson-c345/tuning/results/cycle3/j444/"
MANIFEST = [
    ("1_W_screening", "W: σύνοψη επιλογής ρυθμίσεων", ".lab/j380/w_analysis.json", "val 13000-13019", "18500-18501", "Πίνακας επιλογής ρυθμίσεων (παράρτημα)"),
    ("1_W_screening", "W: σύνοψη F", ".lab/j380/F-summary.json", "val", "-", "Παράρτημα"),
    ("2_F_poisson_ms", "F: ανάλυση 10 seeds, 10 μοντέλα + αναφορές", ".lab/c401/f_analysis.json", "val 13000-13019", "18600-18609", "Κύριος πίνακας val (poisson_ms)· παραβιάσεις SLO, pods, churn"),
    ("2_F_poisson_ms", "F: κείμενο αποτελεσμάτων", ".lab/c401/RESULTS.md", "val", "18600-18609", "Περιγραφή του πίνακα"),
    ("3_test12_poisson_ms", "test12: τελική ανάλυση (ΜΙΑ χρήση, ήδη ξοδεμένο)", ".lab/j414/t12_analysis.json", "test12", "18600-18609 (checkpoints)", "Τελικός πίνακας test + ιεραρχία υποθέσεων"),
    ("3_test12_poisson_ms", "test12: έτοιμος πίνακας", ".lab/j414/t12_table.md", "test12", "18600-18609", "Τελικός πίνακας test (μορφή paper)"),
    ("4_spiky_P0_stageA", "Spiky P0 αναφορές + Στάδιο A (6 seeds)", ".lab/j299/stageA_summary.json", "val 16000-16019", "17000-17005", "Πρώιμος πίνακας spiky (παράρτημα)"),
    ("4_spiky_P0_stageA", "Spiky ablation / mlp", ".lab/j312/summary.json", "val 16000-16019", "17000-17005", "Παράρτημα"),
    ("5_S_spiky_10seeds", "S: 7 μοντέλα × 10 seeds", ".lab/j442/summary.json", "val 16000-16019", "19100-19109", "Κύριος πίνακας spiky· paired διαφορές"),
    ("5_S_spiky_10seeds", "S: έλεγχος εγκυρότητας (J446)", ".lab/j446/summary.json", "val", "19100-19109", "Έλεγχος αναπαραγωγής"),
    ("6_shift_ENV_cycle3", "Shift: αναφορές + 9 μοντέλα", ".lab/c426/shift_results.json", "val 13500-13509", "18600-18609", "Πίνακας shift (προσαρμογή σε αλλαγή καθεστώτος)"),
    ("6_shift_ENV_cycle3", "Shift: αναλυτικά (J431)", ".lab/j431/summary.json", "val 13500-13509", "-", "Αναφορές HPA/oracle/fixed στο shift"),
    ("6_shift_ENV_cycle3", "Shift: αναλυτικά (J438)", ".lab/j438/summary.json", "val", "18600-18609", "Αναλυτικά ανά run"),
    ("7_T_Dinos_vs_V2", "T: Dinos vs Dinos+Transfer V.2, 10 νέα seeds", ".lab/j450/T-summary.json", "val", "19200-19209", "Πίνακας T + διαφορά V.2−Dinos με CI"),
    ("8_J444_traces_figures", "Σχήμα: ίχνη φόρτου/pods, spiky", J444 + "base_spiky.json", "val 16000-16002", "-", "Σχήμα φόρτου, αναφορές"),
    ("8_J444_traces_figures", "Σχήμα: ίχνη φόρτου/pods, shift", J444 + "base_shift.json", "val", "-", "Σχήμα φόρτου, αναφορές"),
] + [("8_J444_traces_figures", f"Σχήμα: ίχνη μοντέλου {m}", f"{J444}c3S-{m}-s19100.traj.json", "val 16000-16002", "19100", "Σχήματα προσαρμογής (pods vs load, rewards)")
     for m in ("dinos", "derp", "derp_hist10", "lstm", "lstm_transfer", "v2")]

# per-seed CSVs flattened from existing summaries: (dest, source, extractor name)
def _s(path):  # J442 batch S: {arm: {seeds: {seed: ret}}}
    d = json.load(open(path))
    return [(arm, int(k), v) for arm, a in d.items() for k, v in a["seeds"].items()]

def _arms(path):  # F / test12 analysis: arms[arm].seed_means
    d = json.load(open(path))
    return [(arm, int(k), v) for arm, a in d["arms"].items() for k, v in a["seed_means"].items()]

def _t(path):  # T: groups[workload][arm].per_seed
    d = json.load(open(path))
    return [(f"{w}/{arm}", int(k), v) for w, g in d["groups"].items() for arm, a in g.items() if isinstance(a, dict) and "per_seed" in a for k, v in a["per_seed"].items()]

CSVS = [
    ("2_F_poisson_ms/F_per_seed_val.csv", ".lab/c401/f_analysis.json", _arms),
    ("3_test12_poisson_ms/test12_per_seed.csv", ".lab/j414/t12_analysis.json", _arms),
    ("5_S_spiky_10seeds/S_per_seed_val.csv", ".lab/j442/summary.json", _s),
    ("7_T_Dinos_vs_V2/T_per_seed_val.csv", ".lab/j450/T-summary.json", _t),
]

README_HEAD = """# Αποτελέσματα 2ου Κύκλου Πειραμάτων Poisson

Εδώ μαζεύονται **αντίγραφα** των αριθμών που τροφοδοτούν τους πίνακες και τις γραφικές του paper.
Δεν αλλάζει τίποτα στα αρχικά αρχεία. Αν ένα αρχείο λείπει, γράφεται «ΛΕΙΠΕΙ» και δεν φτιάχνεται αριθμός.
Ξαναφτιάχνεται με: `python3 tools/results_collect.py`

Κανόνας: κάθε νέα παρτίδα πειραμάτων αποθηκεύει εδώ τους αριθμούς πινάκων/γραφικών της.
Ο 4ος κύκλος θα έχει δικό του φάκελο: «Αποτελέσματα 4ου Κύκλου Poisson».

Σημείωση: val = σύνολο επικύρωσης (όχι τελικός έλεγχος). Το test12 έχει ήδη χρησιμοποιηθεί μία φορά και δεν ξαναδιαβάζεται·
εδώ υπάρχει μόνο η έτοιμη σύνοψή του. Τα αποτελέσματα val είναι περιγραφικά, όχι ισχυρισμοί.

| Φάκελος / αρχείο | Τι είναι | Πηγή | Σύνολο | Seeds | Τροφοδοτεί |
|---|---|---|---|---|---|
"""

def dest_name(src):
    """Unique copy name: .lab/j438/summary.json -> j438_summary.json (avoids collisions)."""
    p = Path(src)
    return f"{p.parent.name}_{p.name}" if src.startswith(".lab/") else p.name


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def build(root: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    rows, missing, files = [], [], {}
    for batch, label, src, split, seeds, feeds in MANIFEST:
        sp = root / src
        dest = out / batch / dest_name(src)
        if not sp.is_file():
            missing.append(src); rows.append((f"{batch}/{dest_name(src)}", label, src + " (ΛΕΙΠΕΙ)", split, seeds, feeds)); continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or sha(dest) != sha(sp):
            shutil.copy2(sp, dest)
        files[str(dest.relative_to(out))] = {"source": src, "sha256": sha(dest)}
        rows.append((f"{batch}/{dest.name}", label, src, split, seeds, feeds))
    for rel, src, fn in CSVS:
        sp = root / src
        if not sp.is_file():
            missing.append(src); continue
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = sorted(fn(sp))
        with open(dest, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["arm", "seed", "mean_return"]); w.writerows(data)
        files[rel] = {"source": src, "sha256": sha(dest)}
        rows.append((rel, "Ανά-seed βαθμολογίες (CSV από τη σύνοψη)", src, "όπως η σύνοψη", "-", "Πίνακες/boxplot ανά seed"))
    for p in out.rglob("*"):  # prune stale copies from older manifests (keeps the rebuild idempotent)
        if p.is_file() and p.name not in ("README.md", "MANIFEST.json") and str(p.relative_to(out)) not in files:
            p.unlink()
    (out / "README.md").write_text(README_HEAD + "".join(
        "| {} | {} | `{}` | {} | {} | {} |\n".format(*r) for r in rows)
        + ("\n**Λείπουν:** " + ", ".join(missing) + "\n" if missing else ""), encoding="utf-8")
    (out / "MANIFEST.json").write_text(json.dumps({"files": files, "missing": missing}, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return files, missing

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT)); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    root = Path(a.root)
    files, missing = build(root, Path(a.out) if a.out else root / OUT_NAME)
    print(f"copied/verified {len(files)} files; missing {len(missing)}: {missing}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
