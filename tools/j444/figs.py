"""J444: figures for reports/2026-11-10-models-report. Reads only stored JSON (batch S summary, eval-only trajectories)."""
import json, glob, os, statistics as st
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
R = "/home/ubuntu/qrl-lab/"; T = R + "code-poisson-c345/tuning/results/cycle3/j444/"; O = R + "reports/2026-11-10-models-report/fig/"
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})
NAME = {"dinos": "Dinos", "v2": "Dinos+Transfer V.2", "lstm_transfer": "LSTM+transfer", "lstm": "LSTM", "derp": "DERP (original)",
        "derp_hist10": "DERP enhanced (hist10)", "rppo": "RPPO / DRe-SCale"}
ORDER = ["dinos", "v2", "lstm_transfer", "lstm", "derp", "derp_hist10", "rppo"]
COL = {"dinos": "#1f77b4", "v2": "#ff7f0e", "lstm_transfer": "#2ca02c", "lstm": "#9467bd", "derp": "#8c564b", "derp_hist10": "#e377c2", "rppo": "#7f7f7f"}
BCOL = {"hpa_orig": "#000000", "hpa_demand": "#d62728", "oracle": "#17becf", "fixed": "#bcbd22"}
BNAME = {"hpa_orig": "HPA original (thr 50)", "hpa_demand": "Tuned HPA (0.9)", "oracle": "Oracle look-ahead (1.1)", "fixed": "Fixed 13 pods"}

def summ(): return json.load(open(R + ".lab/j442/summary.json"))
def p0():
    d = json.load(open(R + "code-poisson-spiky/tuning/results/spiky-stage1/spiky1-P0-reference-off-s16000.json"))
    out = {}
    for k, v in d["selected"].items():
        eps = d["grids"][k][str(v["param"])]["episodes"]; x = [e["ret"] for e in eps]
        out[k] = dict(mean=st.mean(x), sd=st.stdev(x), n=len(x), param=v["param"])
    return out

def fig_rewards():
    s, b = summ(), p0()
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    labs, i = [], 0
    for a in ORDER:
        v = s[a]; xs = list(v["seeds"].values())
        ax.bar(i, v["mean"], yerr=v["sd"], color=COL[a], alpha=.55, capsize=3)
        ax.scatter(np.full(len(xs), i) + np.linspace(-.25, .25, len(xs)), xs, s=9, c="k", zorder=3)
        labs.append(NAME[a]); i += 1
    for k in ["hpa_orig", "hpa_demand", "oracle", "fixed"]:
        ax.bar(i, b[k]["mean"], yerr=b[k]["sd"], color=BCOL[k], alpha=.35, hatch="//", capsize=3); labs.append(BNAME[k]); i += 1
    ax.set_xticks(range(i)); ax.set_xticklabels(labs, rotation=35, ha="right"); ax.set_ylabel("mean return / episode (5000 ticks)")
    ax.set_title("poisson_ms_spiky, val 16000-16019: models = mean ± sample SD over 10 training seeds (dots = seeds);\nbaselines (hatched) = mean ± SD over the 20 val episodes", fontsize=8)
    fig.tight_layout(); fig.savefig(O + "rewards_spiky.png"); plt.close(fig)

def fig_rewards_shift():
    d = json.load(open(R + ".lab/j438/summary.json")); refs = d["references"]
    arms = d["shift_models"]
    fig, ax = plt.subplots(figsize=(7.2, 3.4)); labs = []
    nm = {"dinos": "Dinos", "derp_ddqn": "DERP+DDQN", "mlp_a1h": "MLP", "transfer_mlp_a1h": "MLP+transfer", "derp_hist10": "DERP enh.", "lstm_transfer": "LSTM+transfer",
          "v2": "Dinos+Transfer V.2", "lstm": "LSTM", "derp": "DERP orig"}
    for i, a in enumerate(arms):
        ax.bar(i, a["mean"], yerr=a["sd_training_seeds"], alpha=.6, capsize=3, color="#4c72b0"); labs.append(nm.get(a["arm"], a["arm"]))
    n = len(arms)
    for j, k in enumerate(["hpa_orig", "hpa_demand", "oracle", "fixed"]):
        r = refs[k]; ax.bar(n + j, r["mean"], yerr=r["sd_workloads"], alpha=.35, hatch="//", color=BCOL[k], capsize=3); labs.append(BNAME[k].split(" (")[0])
    ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs, rotation=35, ha="right"); ax.set_ylabel("mean return / episode")
    ax.set_title("poisson_ms_shift val 13500-13509 (F checkpoints, eval-only): models ± SD over 10 training seeds; baselines ± SD over 10 workloads", fontsize=7.5)
    fig.tight_layout(); fig.savefig(O + "rewards_shift.png"); plt.close(fig)

def load_traj():
    out = {}
    for a in ORDER:
        f = T + f"c3S-{a}-s19100.traj.json"
        if not os.path.exists(f): continue
        d = json.load(open(f)); cr = d["checkpoint_results"]; ck = list(cr)[-1]
        out[a] = cr[ck]["val"]["trajectory"]["episodes"]
    return out

def base(tag):
    f = T + f"base_{tag}.json"
    return json.load(open(f)) if os.path.exists(f) else None

def fig_workload(tag, title):
    b = base(tag)
    if not b: return False
    c = b["controllers"]; hd = [k for k in c if k.startswith("hpa_demand")][0]; ep = c[hd][0]
    fx = [k for k in c if k.startswith("fixed")][0]; ho = [k for k in c if k.startswith("hpa_orig")][0]
    fig, ax = plt.subplots(5, 1, figsize=(7.2, 7.6), sharex=True); t = np.arange(len(ep["load"]))
    ax[0].plot(t, ep["load"], c="k", lw=.5); ax[0].set_ylabel("input load\n(req/tick)")
    for k, col in [(hd, "#d62728"), (ho, "k"), (fx, "#bcbd22")]:
        e = c[k][0]
        ax[1].plot(t, e["latency"], lw=.4, c=col, label=k); ax[2].plot(t, e["cpu"], lw=.4, c=col); ax[3].plot(t, e["mem"], lw=.4, c=col); ax[4].plot(t, e["pods"], lw=.6, c=col)
    ax[1].axhline(1.0, ls="--", c="gray", lw=.6); ax[1].set_ylabel("latency p95\n(ticks, proxy;\nSLO=1.0)"); ax[2].set_ylabel("CPU %"); ax[3].set_ylabel("memory %"); ax[4].set_ylabel("active pods"); ax[4].set_xlabel("tick")
    ax[1].legend(fontsize=6, ncol=3, loc="upper right")
    fig.suptitle(title + f" · val episode seed {ep['seed']}\n(latency/CPU/memory/pods depend on the controller: HPA tuned red, HPA original black, fixed olive)", fontsize=8)
    fig.tight_layout(); fig.savefig(O + f"workload_{tag}.png"); plt.close(fig); return True

def fig_adapt():
    tr, b = load_traj(), base("spiky")
    if not tr: return False
    items = [(a, NAME[a], COL[a], tr[a][0]) for a in ORDER if a in tr]
    if b:
        for k, v in b["controllers"].items():
            kk = k.split("_")[0] if not k.startswith("hpa") else "_".join(k.split("_")[:2]); kk = "hpa_orig" if k.startswith("hpa_orig") else "hpa_demand" if k.startswith("hpa_demand") else kk
            items.append((kk, BNAME[kk], BCOL[kk], v[0]))
    n = len(items); cols = 2; rows = (n + 1) // 2
    fig, axs = plt.subplots(rows, cols, figsize=(7.4, 1.7 * rows), sharex=True); axs = axs.ravel()
    for ax, (a, nm, col, e) in zip(axs, items):
        t = np.arange(len(e["load"])); ax.plot(t, e["load"], c="#bbbbbb", lw=.5); ax.set_ylim(0, 230)
        ax2 = ax.twinx(); ax2.plot(t, e["pods"], c=col, lw=.7); ax2.set_ylim(0, 21); ax2.spines["top"].set_visible(False)
        ax.set_title(f"{nm}", fontsize=7, pad=2); ax.tick_params(labelsize=6); ax2.tick_params(labelsize=6)
    for ax in axs[n:]: ax.axis("off")
    axs[0].set_ylabel("load (grey)", fontsize=6)
    fig.suptitle(f"Adaptation: active pods (colour, right axis) vs input load (grey), poisson_ms_spiky val episode seed {items[0][3]['seed']}; training seed 19100", fontsize=8)
    fig.tight_layout(); fig.savefig(O + "adaptation_timeseries.png"); plt.close(fig)
    # pods vs load, binned means, all recorded episodes
    fig, ax = plt.subplots(figsize=(6.4, 3.8)); bins = np.arange(0, 201, 20)
    for a, nm, col, _ in items:
        eps = tr[a] if a in tr else b["controllers"][[k for k in b["controllers"] if k.startswith(a)][0]]
        L = np.concatenate([e["load"] for e in eps]); P = np.concatenate([e["pods"] for e in eps]); idx = np.digitize(L, bins)
        xs = [(bins[i - 1] + bins[i]) / 2 for i in range(1, len(bins)) if (idx == i).sum() > 20]
        ys = [P[idx == i].mean() for i in range(1, len(bins)) if (idx == i).sum() > 20]
        ax.plot(xs, ys, marker="o", ms=2.5, lw=1, c=col, ls="--" if a in BCOL else "-", label=nm)
    ax.set_xlabel("input load (req/tick), bins of 20"); ax.set_ylabel("mean active pods"); ax.legend(fontsize=6, ncol=2)
    ax.set_title("Mean active pods vs input load (3 val episodes 16000-16002, seed 19100)", fontsize=8)
    fig.tight_layout(); fig.savefig(O + "adaptation_pods_vs_load.png"); plt.close(fig); return True

if __name__ == "__main__":
    fig_rewards(); fig_rewards_shift(); print("workload", fig_workload("spiky", "poisson_ms_spiky"), fig_workload("shift", "poisson_ms_shift")); print("adapt", fig_adapt())
