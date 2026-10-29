"""Report «Μεγάλος κύκλος εκπαίδευσης και testing σε ημιτονοειδή είσοδο 1» (M-20261028-011).

Everything shown comes from existing files (parsed tables or verbatim markdown sections); no number is computed here
except (a) per-seed means of the 20 test traces for the optional figures and (b) plain re-formatting. Figures are
generated only on request (make_figures) from the run JSONs under code-tuning/tuning/results/<tag>/ and cached under
.lab/figs/cycle1/.
"""
import glob
import json
import os
import re

CYC = ".lab/tuning/cycles"
SOURCES = {
    "freeze24": f"{CYC}/c24_freeze.md", "freeze21": f"{CYC}/c21_freeze.md", "res10": f"{CYC}/c21_test10_result.md",
    "res11": f"{CYC}/c24_test11_result.md", "c3": f"{CYC}/c3_synthesis.md", "c19": f"{CYC}/c19_screen.md",
    "c23": f"{CYC}/c23_screen.md", "tuning": "docs/tuning_experiments.md", "paper": "docs/paper_notes.md",
    "models": ".lab/tuning/model_definitions.md", "protocols": ".lab/tuning/protocols.md",
}
DISPLAY = {"transfer_a1h_dqn3": "Dinos+Transfer V.2", "dinos_a1h_dqn3": "Dinos", "lstm_scratch_dqn3": "LSTM",
           "transfer_orig_orig_d0_dqn3": "LSTM+transfer", "mlp_hist10_dqn3": "MLP", "mlp_a1h_dqn3": "mlp_a1h",
           "transfer_mlp_a1h_dqn3": "transfer_mlp_a1h", "derp_hist10": "enhanced DERP", "derp": "DERP"}
SPLITS = {"test10": ("c18c", "c18c_summary.json"), "test11": ("c24c", "c24c_summary.json")}


def read(root, key_or_path):
    p = os.path.join(root, SOURCES.get(key_or_path, key_or_path))
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def section(text, heading):
    """Verbatim markdown from the line starting with `heading`. A '#' heading runs to the next heading of the same or higher
    level; a bullet heading ('- Arms') runs to the next bullet, heading, or a 'Command:'/'Generated'/'Lab file' line."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(heading):
            lvl = len(ln) - len(ln.lstrip("#"))
            j = i + 1
            while j < len(lines):
                n = lines[j]
                if lvl:
                    if n.startswith("#") and len(n) - len(n.lstrip("#")) <= lvl:
                        break
                elif n.startswith(("- ", "#", "Command:", "Generated", "Lab file")):
                    break
                j += 1
            return "\n".join(lines[i:j]).strip()
    return ""


def md_tables(text):
    """[(header_cells, [row_cells...])] for every pipe table in text."""
    out, cur = [], []
    for ln in text.splitlines() + [""]:
        if ln.strip().startswith("|"):
            cur.append([c.strip() for c in ln.strip().strip("|").split("|")])
        elif cur:
            if len(cur) >= 2:
                out.append((cur[0], [r for r in cur[2:]]))
            cur = []
    return out


def clean(s):
    return s.replace("**", "").strip()


def test10_main_table(text):
    """Header + rows of the arm table of c21_test10_result.md."""
    for hdr, rows in md_tables(text):
        if "test10" in hdr:
            return hdr, rows
    return [], []


def test10_baselines(text):
    """[(name, value)] from the line 'Baselines test10: oracle_Dstep 88620, causal_be 71184, ...' (verbatim values)."""
    m = re.search(r"^Baselines test10:\s*(.+?)\.?$", text, re.M)
    return [(a.strip(), b.replace("−", "-")) for a, b in re.findall(r"([^,]+?)\s+(−?-?\d+)(?:,|$)", m.group(1))] if m else []


def test10_hypotheses(text):
    """[(H, contrast, diff, ci, outcome)] from c21_test10_result.md (H1-H3 lines + the H4-H6 descriptive line)."""
    rows = []
    for m in re.finditer(r"^- H(\d) (.+?): ([+−-]\d+) \[([^\]]+)\] → (.+)$", text, re.M):
        rows.append(("H" + m.group(1), m.group(2), m.group(3), "[" + m.group(4) + "]",
                     m.group(5).split("(")[0].strip()))
    line = re.search(r"^- H4 .*$", text, re.M)
    if line:
        for m in re.finditer(r"H(\d) (.+?) ([+−-]\d+) \[([^\]]+)\]", line.group(0)):
            rows.append(("H" + m.group(1), m.group(2), m.group(3), "[" + m.group(4) + "]", "descriptive"))
    return rows


def test11_means(text):
    """[(name, value, note)] from the 'Means on test11 ...' paragraph of c24_test11_result.md."""
    m = re.search(r"^Means on test11[^:]*:\s*(.+?)\n\n", text + "\n\n", re.M | re.S)
    if not m:
        return []
    out = []
    for part in m.group(1).replace("\n", " ").split(" · "):
        mm = re.match(r"(.+?)\s+(-?\d+)\s*(\(.*\))?\.?\s*$", part.strip())
        if mm:
            out.append((mm.group(1), mm.group(2), mm.group(3) or ""))
    return out


def test11_hypotheses(text):
    for hdr, rows in md_tables(text):
        if hdr and hdr[0] == "H":
            return hdr, rows
    return [], []


def iqm_lines(root):
    """[(arm_key, iqm, mean)] from .lab/tuning/c24c_iqm.txt."""
    out = []
    for ln in read(root, ".lab/tuning/c24c_iqm.txt").splitlines():
        m = re.match(r"(\S+)\s+files \d+ eps \d+ IQM\s+(\d+) mean\s+(\d+)", ln)
        if m:
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def cycle_syntheses(root):
    """Sorted [(name, relative path)] of cycles/c*_synthesis.md."""
    ps = glob.glob(os.path.join(root, CYC, "c*_synthesis.md"))
    key = lambda p: int(re.search(r"c(\d+)_", os.path.basename(p)).group(1))
    return [(os.path.basename(p), os.path.relpath(p, root)) for p in sorted(ps, key=key)]


# ----------------------------------------------------------------------------- figures
def summary(root, split):
    tag, fn = SPLITS[split]
    with open(os.path.join(root, ".lab", "tuning", fn), encoding="utf-8") as f:
        return json.load(f)["spike300_d5"]


def arm_stats(root, split):
    """{arm_key: {mean, sd, ck, val_by_checkpoint}} straight from the summary JSON (strings cast to float)."""
    s = summary(root, split)
    return {k: {"mean": float(a["mean"]), "sd": float(a["sd_over_seeds"]), "ck": int(a["checkpoint"]),
                "val": {int(c): float(v) for c, v in a["val_by_checkpoint"].items()}}
            for k, a in s["arms"].items() if a.get("status") == "complete"}


def baseline_means(root, split):
    b = summary(root, split)["baselines"][split]
    return {k: float(v["mean_ret"]) for k, v in b.items() if isinstance(v, dict) and "mean_ret" in v}


def _arm_key(run_arm, keys):
    for k in (run_arm, run_arm + "_dqn3"):
        if k in keys:
            return k
    return None


def extract_per_seed(root, split):
    """{arm_key: {seed: {'test': mean-of-20-traces at locked ck, 'val_curve': {ck: mean-of-val-episodes}}}} from the run JSONs.
    Averages are plain arithmetic means of the recorded episode returns."""
    tag, _ = SPLITS[split]
    st = arm_stats(root, split)
    out = {}
    for f in sorted(glob.glob(os.path.join(root, "code-tuning", "tuning", "results", tag, "spike300_d5-*.json"))):
        if re.search(r"\.ck\d+\.json$", f) or os.path.basename(f).startswith("baselines"):
            continue
        with open(f, encoding="utf-8") as fh:
            r = json.load(fh)
        k = _arm_key(r.get("arm", ""), st)
        if k is None or "checkpoint_results" not in r:
            continue
        cr = r["checkpoint_results"]
        ck = str(st[k]["ck"])
        if ck not in cr:
            continue
        mean = lambda eps: sum(e["ret"] for e in eps) / len(eps)
        out.setdefault(k, {})[int(r["seed"])] = {
            "test": mean(cr[ck][split]["episodes"]),
            "val_curve": {int(c): mean(v["val"]["episodes"]) for c, v in cr.items() if "val" in v}}
    return out


def make_figures(root, outdir):
    """Write PNGs + data cache to outdir; returns list of figure paths. Only called from the dashboard button."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(outdir, exist_ok=True)
    figs = []
    for split in SPLITS:
        st = arm_stats(root, split)
        ps = extract_per_seed(root, split)
        with open(os.path.join(outdir, f"per_seed_{split}.json"), "w", encoding="utf-8") as f:
            json.dump(ps, f, indent=1)
        keys = sorted(st, key=lambda k: -st[k]["mean"])
        base = baseline_means(root, split)
        # bar chart: summary mean +- sd over seeds (the summaries hold no CI for an arm mean), per-seed dots
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.bar(range(len(keys)), [st[k]["mean"] for k in keys], yerr=[st[k]["sd"] for k in keys], capsize=3, color="#4c78a8")
        for i, k in enumerate(keys):
            vals = list(ps.get(k, {}).values())
            ax.scatter([i] * len(vals), [v["test"] for v in vals], color="k", s=10, zorder=3)
        for name in ("hpa_demand", "hpa_rule", "fixed_best", "oracle_Dstep"):
            if name in base:
                ax.axhline(base[name], ls="--", lw=0.8, color="gray")
                ax.text(len(keys) - 0.5, base[name], name, fontsize=7, ha="right", va="bottom")
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels([DISPLAY.get(k, k) for k in keys], rotation=30, ha="right", fontsize=8)
        ax.set_ylabel(f"return on {split}")
        ax.set_title(f"{split}: mean over seeds ± sd over seeds (error bars), dots = per-seed means")
        fig.tight_layout()
        p = os.path.join(outdir, f"bar_{split}.png")
        fig.savefig(p, dpi=130)
        plt.close(fig)
        figs.append(p)
        # validation curves vs checkpoint (summary val_by_checkpoint = mean over seeds)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for k in keys:
            xs = sorted(st[k]["val"])
            ax.plot(xs, [st[k]["val"][x] for x in xs], marker="o", ms=3, label=DISPLAY.get(k, k))
        ax.set_xscale("log")
        ax.set_xlabel("training ticks (checkpoint)")
        ax.set_ylabel("validation return (mean over seeds)")
        ax.set_title(f"{split} run: validation return by checkpoint")
        ax.legend(fontsize=7)
        fig.tight_layout()
        p = os.path.join(outdir, f"valcurve_{split}.png")
        fig.savefig(p, dpi=130)
        plt.close(fig)
        figs.append(p)
    return figs
