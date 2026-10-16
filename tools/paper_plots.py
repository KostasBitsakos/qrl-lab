"""Plots for the dashboard 'Πειράματα' tab: run result images and paper-style bar charts from metrics.jsonl data.

Styling follows ~/simulations/redisk8s/timeseries/Pytorch/all_metrics_plotted_final.py (bar panels, 'trained for Nk
steps' labels, rotation 45, y label 'Total Accumulated Reward'); no numbers are taken from that file.
"""
import glob
import os

COLORS = ["red", "green", "blue", "purple", "orange", "teal"]
IMG_EXT = (".jpg", ".jpeg", ".png")


def find_result_images(run_dir):
    """[(group, caption, abspath)] for images under <run_dir>/results/**, grouped by the folder relative to results/."""
    base = os.path.join(run_dir, "results")
    out = []
    for p in sorted(glob.glob(os.path.join(base, "**", "*"), recursive=True)):
        if os.path.isfile(p) and p.lower().endswith(IMG_EXT):
            rel = os.path.relpath(p, base)
            group = os.path.dirname(rel) or "(results)"
            out.append((group, rel, p))
    out.sort(key=lambda t: (t[0] != "(results)", _natkey(t[0]), t[1]))
    return out


def _natkey(s):
    import re
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def bar_label(mode, model):
    return f"{mode} trained for {model}k steps"


def comparison_figure(agg, metric="reward"):
    """One bar panel per mode; bars = models sorted numerically; error bars = sd over seeds.

    agg is the output of summarize_runs.aggregate_by_seed. metric: 'reward' or 'vms'. Returns a matplotlib Figure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    modes = sorted(agg)
    n = max(1, len(modes))
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 4 * rows), squeeze=False)
    ylabel = "Total Accumulated Reward" if metric == "reward" else "Mean VMs"
    for i, mode in enumerate(modes):
        ax = axes[i // cols][i % cols]
        models = sorted(agg[mode], key=lambda m: (not str(m).lstrip("-").isdigit(), int(m) if str(m).lstrip("-").isdigit() else 0, str(m)))
        pts = [(m, agg[mode][m][f"{metric}_mean"], agg[mode][m][f"{metric}_sd"]) for m in models
               if agg[mode][m][f"{metric}_mean"] is not None]
        ax.bar([bar_label(mode, m) for m, _, _ in pts], [v for _, v, _ in pts], yerr=[s or 0 for _, _, s in pts],
               capsize=4, color=COLORS[i % len(COLORS)])
        ax.set_title(mode)
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3)
        ax.tick_params(axis="x", rotation=45)
    for j in range(len(modes), rows * cols):
        axes[j // cols][j % cols].axis("off")
    fig.tight_layout()
    return fig
