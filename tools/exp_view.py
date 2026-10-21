"""Pure helpers for the dashboard «📈 Πειράματα» tab (M-20261021-008): live files, tuning result browser, run
parameters, closeness to the paper targets, closeness history + forecast, runs left in the tuning loop.

No Streamlit here (tests: tests/test_exp_view.py). Every number shown comes from a file; what cannot be determined is
UNKNOWN («άγνωστο») with the place where it would be.
"""
import datetime as dt
import glob
import importlib.util
import json
import math
import os
import re

UNKNOWN = "άγνωστο"
RESULTS_REL = os.path.join("code-tuning", "tuning", "results")
CLOSENESS_REL = os.path.join("code-tuning", "tuning", "closeness.py")
HISTORY_REL = os.path.join(".lab", "tuning", "closeness_history.json")
LOOP_REQUESTS = ("R-20261019-001", "R-20261020-005", "R-20261021-001")
LOOP_END = "2026-10-21T23:59:00+00:00"
LIVE_MAX_AGE = 120.0
CK_RE = re.compile(r"\.ck\d+\.json$")
# Seed of .lab/tuning/closeness_history.json (coordinator brief M-20261021-008). primary = the cycle's headline value.
SEED_HISTORY = [
    {"cycle": "c8", "variant": "coupled (conditioning)", "closeness": 28, "ratio": 1.06, "primary": True,
     "source": ".lab/tuning/cycles/c8_brief.md:19"},
    {"cycle": "c9b", "variant": "spike300", "closeness": 31, "ratio": 1.23, "primary": True,
     "source": "docs/tuning_experiments.md:19 (c9_codex_verdict.md)"},
    {"cycle": "c10b", "variant": "orig_d5", "closeness": 36, "ratio": 1.51, "primary": False,
     "source": ".lab/tuning/cycles/c10b_brief.md:18"},
    {"cycle": "c10b", "variant": "orig_d10", "closeness": 37, "ratio": 3.78, "primary": True,
     "source": ".lab/tuning/cycles/c10b_brief.md:18"},
    {"cycle": "c12a", "variant": "spike300_d5", "closeness": 36, "ratio": 1.52, "primary": True,
     "source": ".lab/tuning/cycles/c12_brief.md:18"},
    {"cycle": "c13a", "variant": "spike300_d5", "closeness": 36, "ratio": 1.50, "primary": True,
     "source": ".lab/tuning/cycles/c13_brief.md:7"},
]


# ---------------------------------------------------------------- small utils
def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def parse_ts(s):
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def load_closeness(root):
    """code-tuning/tuning/closeness.py as a module (pure; no torch)."""
    p = os.path.join(root, CLOSENESS_REL)
    spec = importlib.util.spec_from_file_location("tuning_closeness", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------- live files
def live_candidates(results_dir, now, max_age=LIVE_MAX_AGE):
    """Fresh live files [(path, age_s)] under <results>/**/live/*.json, newest first (tmp files skipped)."""
    out = []
    for p in glob.glob(os.path.join(results_dir, "**", "live", "*.json"), recursive=True):
        try:
            age = now - os.path.getmtime(p)
        except OSError:
            continue
        if age <= max_age:
            out.append((p, age))
    return sorted(out, key=lambda x: x[1])


def read_live(path):
    """Live JSON -> dict with 'columns' {col: list}, or None if unreadable/malformed."""
    d = read_json(path)
    if not isinstance(d, dict) or not isinstance(d.get("rows"), list) or not isinstance(d.get("cols"), list):
        return None
    cols = d["cols"]
    good = [r for r in d["rows"] if isinstance(r, list) and len(r) == len(cols)]
    d["columns"] = {c: [r[i] for r in good] for i, c in enumerate(cols)}
    return d


# ---------------------------------------------------------------- result browser
def is_main_result(path):
    b = os.path.basename(path)
    return b.endswith(".json") and not CK_RE.search(b) and ".diag" not in b and not b.startswith("baselines") \
        and os.sep + "live" + os.sep not in path and not b.endswith(".tmp")


def list_results(results_dir):
    """[(cycle folder, path)] of main result JSONs, newest first."""
    ps = [p for p in glob.glob(os.path.join(results_dir, "*", "*.json")) if is_main_result(p)]
    ps.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return [(os.path.basename(os.path.dirname(p)), p) for p in ps]


def out_path_of(cmd, cwd):
    """Absolute --out path of a run command (JSON string or list), else None."""
    try:
        c = json.loads(cmd) if isinstance(cmd, str) else list(cmd)
        o = c[c.index("--out") + 1]
    except (ValueError, IndexError, TypeError):
        return None
    return o if os.path.isabs(o) else os.path.normpath(os.path.join(cwd or "", o))


def test_split(res):
    """The reported split: the last non-'val' eval split (else the last split)."""
    sp = [s for s in (res.get("eval_splits") or []) if s != "val"]
    return sp[-1] if sp else ((res.get("eval_splits") or [None])[-1])


def ck_mean(res, ck, split):
    try:
        return float(res["checkpoint_results"][str(ck)][split]["mean_ret"])
    except (KeyError, TypeError, ValueError):
        return None


def checkpoints(res):
    return sorted(int(k) for k in (res.get("checkpoint_results") or {}))


def select_ck(res):
    """Checkpoint with the best 'val' mean return (as the loop selects), else the last one."""
    cks = checkpoints(res)
    if not cks:
        return None
    vals = [(ck_mean(res, c, "val"), c) for c in cks]
    vals = [v for v in vals if v[0] is not None]
    return max(vals)[1] if vals else cks[-1]


def variant_of(res):
    return res.get("orig_variant") or res.get("target_variant") or res.get("env") or UNKNOWN


def run_label(res):
    return f"{res.get('arm', res.get('agent', '?'))} · {variant_of(res)} · seed {res.get('seed', '?')}"


# ---------------------------------------------------------------- parameters
def _fmt(v):
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, (list, tuple)):
        return ", ".join(_fmt(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}={_fmt(x)}" for k, x in v.items())
    return str(v)


def _seeds_txt(seeds):
    out = []
    for sp, ss in (seeds or {}).items():
        out.append(f"{sp}: {ss[0]}-{ss[-1]} ({len(ss)})" if ss else f"{sp}: -")
    return "; ".join(out)


def param_rows(res, intro=None, path=""):
    """[{ομάδα, παράμετρος, τιμή, πηγή}] for one result JSON; intro = tools/agent_introspect.py output or None."""
    src = f"result JSON ({os.path.basename(path)})" if path else "result JSON"
    rows = []

    def add(group, name, value, source=src, missing_where=None):
        if value is None or value == "":
            rows.append({"ομάδα": group, "παράμετρος": name, "τιμή": UNKNOWN,
                         "πηγή": missing_where or "δεν καταγράφηκε στο result JSON"})
        else:
            rows.append({"ομάδα": group, "παράμετρος": name, "τιμή": _fmt(value), "πηγή": source})

    def key(group, name, k, missing_where=None):
        add(group, name, res.get(k), f"{src} · {k}", missing_where)
    ih = (intro or {}).get("hyper") or {}

    def hi(group, name, k):
        h = ih.get(k)
        if h:
            add(group, name, h.get("value"), h.get("source") or "agent_introspect")
        else:
            add(group, name, None, missing_where="tools/agent_introspect.py (δεν εκτελέστηκε/απέτυχε)")
    key("Agent", "agent", "agent")
    key("Agent", "arm", "arm")
    add("Agent", "agent_variant", res.get("agent_variant") or ("verbatim" if res.get("agent") == "derp" else None),
        f"{src} · agent_variant (derp: verbatim)")
    if intro:
        add("Agent", "κλάση agent", intro.get("class"), "tools/agent_introspect.py")
    add("Agent", "n_params (trainable)", res.get("n_params") if res.get("n_params") is not None else (intro or {}).get("n_params"),
        f"{src} · n_params" if res.get("n_params") is not None else "tools/agent_introspect.py")
    key("Εξερεύνηση", "epsilon start", "epsilon_start")
    key("Εξερεύνηση", "epsilon min", "epsilon_min")
    key("Εξερεύνηση", "epsilon decay (ανά replay)", "epsilon_decay")
    key("Εξερεύνηση", "epsilon schedule", "eps_schedule")
    if res.get("eps_linear_ticks") is not None:
        key("Εξερεύνηση", "linear ticks", "eps_linear_ticks")
    if res.get("finetune_eps") is not None:
        key("Εξερεύνηση", "fine-tune epsilon", "finetune_eps")
    hi("Μάθηση", "gamma", "gamma")
    key("Μάθηση", "learning rate", "learning_rate")
    hi("Μάθηση", "batch size", "batch_size")
    hi("Μάθηση", "replay memory", "memory (replay capacity)")
    if res.get("target_sync_replays") is not None:
        key("Μάθηση", "target sync (replays)", "target_sync_replays")
    else:
        hi("Μάθηση", "target sync", "target_sync")
    if res.get("double_dqn_target") is not None:
        key("Μάθηση", "Double DQN target", "double_dqn_target")
    hi("Μάθηση", "κανόνας target", "target rule")
    hi("Μάθηση", "optimizer", "optimizer")
    hi("Μάθηση", "loss", "loss")
    if intro and intro.get("layers"):
        for i, L in enumerate(intro["layers"]):
            parts = [L.get("type")]
            if L.get("in") is not None:
                parts.append(f"in {L['in']}")
            if L.get("units") is not None:
                parts.append(f"units {L['units']}")
            if L.get("num_layers"):
                parts.append(f"{L['num_layers']} layers")
            parts.append(f"activation: {L.get('activation') or UNKNOWN}")
            if L.get("connection"):
                parts.append(L["connection"])
            add("Δίκτυο", f"{i + 1}. {L.get('name')}", " · ".join(parts), intro.get("network_source") or "agent_introspect")
    else:
        add("Δίκτυο", "layers", None, missing_where="tools/agent_introspect.py (δεν εκτελέστηκε/απέτυχε)")
    # reward
    fam = res.get("env_family")
    rl = ((intro or {}).get("reward_lines") or {}).get("orig" if fam == "orig" else "lstm_transfer") or []
    if fam == "orig" and rl:
        add("Reward", "τύπος (env)", rl[0]["line"], rl[0]["source"])
        if res.get("startup_delay") and len(rl) > 1:
            add("Reward", "τύπος (startup delay > 0)", rl[1]["line"] + "   (p = pending pods)", rl[1]["source"])
    elif rl:
        add("Reward", "τύπος (env)", rl[0]["line"], rl[0]["source"])
    else:
        add("Reward", "τύπος", None, missing_where="tuning/legacy/env_orig.py / env_transfer.py")
    key("Reward", "reward_div (στόχοι μάθησης r/D)", "reward_div")
    key("Reward", "συνιστώσες", "reward_components")
    # state
    feats = res.get("obs_features")
    if feats:
        key("State", "features", "obs_features")
    elif fam == "orig" and intro and intro.get("features"):
        f = intro["features"]["orig"]
        add("State", "features", f["value"], f["source"])
    else:
        add("State", "features", None, missing_where="tuning/legacy/c5_protocol.py OBS_FEATURES")
    key("State", "obs scaling", "obs_scale")
    if res.get("obs_scale_divisors"):
        key("State", "διαιρέτες", "obs_scale_divisors")
    key("State", "state size", "state_size", "6 αν λείπει (cycle 9: όχι delay) — δεν καταγράφηκε")
    if res.get("input_size") is not None:
        key("State", "input size", "input_size")
    if res.get("derp_history") is not None:
        key("State", "derp history", "derp_history")
    # env
    key("Env", "env family", "env_family")
    add("Env", "variant", variant_of(res) if variant_of(res) != UNKNOWN else None, f"{src} · orig_variant/target_variant")
    key("Env", "target env", "target_env")
    add("Env", "startup delay (ticks)", res.get("startup_delay") if res.get("startup_delay") is not None
        else (0 if fam == "orig" else None), f"{src} · startup_delay (cycle 9 χωρίς delay = 0)")
    if res.get("pretrain_env_family"):
        key("Env", "pretrain family", "pretrain_env_family")
        key("Env", "pretrain variant", "pretrain_variant")
        key("Env", "source env", "source_env")
    if res.get("init"):
        key("Env", "αρχικοποίηση", "init")
    # seeds
    key("Seeds", "training seed", "seed")
    key("Seeds", "target stream", "target_stream_seed")
    if res.get("source_stream_seed"):
        key("Seeds", "source stream", "source_stream_seed")
    add("Seeds", "eval splits / seeds", _seeds_txt(res.get("eval_seeds")), f"{src} · eval_seeds")
    # ticks
    key("Ticks", "pretrain ticks", "pretrain_ticks")
    key("Ticks", "target (train) ticks", "target_ticks")
    key("Ticks", "σύνολο", "total_ticks")
    key("Ticks", "checkpoints", "checkpoints")
    key("Ticks", "ticks ανά eval επεισόδιο", "eval_episode_ticks")
    # cpu
    key("CPU", "CPU (s)", "cpu_s")
    key("CPU", "wall (s)", "wall_s")
    key("CPU", "train CPU s / 1k ticks", "train_cpu_s_per_1k_ticks")
    key("CPU", "eval CPU (s)", "eval_cpu_s")
    key("CPU", "torch threads", "torch_threads")
    return rows


def intro_key(res):
    """(agent, agent_variant, state_size, derp_history, transfer) for tools/agent_introspect.py."""
    agent = res.get("agent")
    var = res.get("agent_variant") or "verbatim"
    ss = int(res.get("state_size") or 6)
    return (agent, var, ss, int(res.get("derp_history") or 1), agent == "dinos_t" and not res.get("pretrain_env_family"))


def intro_args(k):
    agent, var, ss, h, tr = k
    a = ["--agent", agent, "--agent-variant", var, "--state-size", str(ss), "--derp-history", str(h)]
    return a + (["--transfer"] if tr else [])


# ---------------------------------------------------------------- closeness
def arm_target(res):
    """'dinos' for DInos+transfer runs, 'derp' for the original DERP, else None (no paper target)."""
    if res.get("agent") == "dinos_t":
        return "dinos"
    if res.get("arm") == "derp":
        return "derp"
    return None


def run_closeness(C, res, ck=None, split=None):
    """One run's part of closeness.score: x = 5 x mean episode return (the paper sums 5 episodes) vs its target."""
    ck = ck if ck is not None else select_ck(res)
    split = split or test_split(res)
    m = ck_mean(res, ck, split)
    kind = arm_target(res)
    out = {"checkpoint": ck, "split": split, "mean_ret": m, "x": None if m is None else 5.0 * m, "kind": kind}
    if kind and m is not None:
        t = C.DINOS_T if kind == "dinos" else C.DERP_T
        out.update(target=t, part=C.part(5.0 * m, t))
    return out


def folder_arm_means(results):
    """results: [res] of one folder -> {(variant, arm): {ck, split, mean, n_seeds}} with the checkpoint chosen by the
    mean 'val' return over seeds (as the cycle summaries do) and the mean over seeds of the test-split mean."""
    groups = {}
    for r in results:
        if r.get("protocol") != "c5":
            continue
        groups.setdefault((variant_of(r), r.get("arm")), []).append(r)
    out = {}
    for k, rs in groups.items():
        cks = sorted(set.intersection(*[set(checkpoints(r)) for r in rs])) if rs else []
        if not cks:
            continue
        sp = test_split(rs[0])

        def mean_at(c, s):
            v = [ck_mean(r, c, s) for r in rs]
            v = [x for x in v if x is not None]
            return sum(v) / len(v) if v else None
        vals = [(mean_at(c, "val"), c) for c in cks]
        vals = [v for v in vals if v[0] is not None]
        ck = max(vals)[1] if vals else cks[-1]
        m = mean_at(ck, sp)
        if m is not None:
            out[k] = {"ck": ck, "split": sp, "mean": m, "n_seeds": len(rs), "agent": rs[0].get("agent")}
    return out


def folder_scores(C, arm_means):
    """{variant: {derp, dinos, ratio_part, total (closeness.score parts), ratio (raw DInos/DERP), means...}} for variants
    that have both 'derp' and a transfer arm (best transfer mean, as closeness.best)."""
    out = {}
    for v in sorted({k[0] for k in arm_means}):
        de = arm_means.get((v, "derp"))
        tr = [(m["mean"], a) for (vv, a), m in arm_means.items() if vv == v and m["agent"] == "dinos_t"]
        if de and tr:
            mt, arm = max(tr)
            s = C.score(5.0 * mt, 5.0 * de["mean"])
            out[v] = dict(derp=s["derp"], dinos=s["dinos"], ratio_part=s["ratio"], total=s["total"], derp_mean=de["mean"], dinos_mean=mt, dinos_arm=arm, ratio=mt / de["mean"] if de["mean"] else None,
                          split=de["split"], n_seeds=(de["n_seeds"], arm_means[(v, arm)]["n_seeds"]))
    return out


# ---------------------------------------------------------------- history + forecast
def load_history(path):
    d = read_json(path)
    return d if isinstance(d, list) and d else None


def ensure_history(path):
    """Create the history file from SEED_HISTORY if absent; return its entries."""
    h = load_history(path)
    if h is None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(SEED_HISTORY, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
        h = list(SEED_HISTORY)
    return h


def primary_series(hist):
    """One value per cycle, in file order: the entry marked primary (else the last entry of that cycle)."""
    by, order = {}, []
    for e in hist:
        c = e.get("cycle")
        if c not in by:
            order.append(c)
        if e.get("primary") or c not in by or not by[c].get("primary"):
            by[c] = e
    return [by[c] for c in order]


def forecast(values, steps=1, k=4, min_band=2.0):
    """Least-squares line over the last k values (x = cycle index), extrapolated `steps` cycles ahead.
    band = max(min_band, 2 x residual sd) (sd with n - 2 dof; 0 when n <= 2). Everything capped to 0..100.
    -> dict(pred, lo, hi, slope, n) or None with < 2 values."""
    y = [float(v) for v in values][-k:]
    n = len(y)
    if n < 2:
        return None
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(y) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (v - my) for x, v in zip(xs, y)) / sxx
    a = my - b * mx
    res = [v - (a + b * x) for x, v in zip(xs, y)]
    sd = math.sqrt(sum(r * r for r in res) / (n - 2)) if n > 2 else 0.0
    band = max(min_band, 2.0 * sd)
    p = a + b * (n - 1 + steps)

    def cap(v):
        return max(0.0, min(100.0, v))
    return {"pred": cap(p), "lo": cap(p - band), "hi": cap(p + band), "slope": b, "n": n, "band": band}


# ---------------------------------------------------------------- runs left in the loop
def driver_files(cmdlines):
    """Entries files driven by a running drive_chunks.py, from process command lines (lists of args)."""
    out = set()
    for c in cmdlines:
        if any(os.path.basename(x) == "drive_chunks.py" for x in c):
            i = next(i for i, x in enumerate(c) if os.path.basename(x) == "drive_chunks.py")
            if i + 1 < len(c):
                out.add(os.path.basename(c[i + 1]))
    return out


def proc_cmdlines():
    out = []
    for p in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(p, "rb") as f:
                out.append([x.decode(errors="replace") for x in f.read().split(b"\0") if x])
        except OSError:
            pass
    return out


def remaining_runs(tuning_dir, code_dir, running=0, drivers=()):
    """Runs still to launch in the tuning loop.
    queued = distinct entry names past the .launched counter of the *_entries.json files that HAVE a counter
             [driver protocol], minus names launched through any other file (re-queued entries count once);
    orphan = entries of files WITHOUT a counter whose name is in no counted file and whose --out result is missing
             (prepared but not handed to a driver; may never run).
    -> dict(queued, orphan, running, total = queued + running, files=[...])."""
    files, counted_names, launched_names, no_counter = [], set(), set(), []
    for f in sorted(glob.glob(os.path.join(tuning_dir, "*_entries.json"))):
        ents = read_json(f)
        if not isinstance(ents, list):
            continue
        cnt_path = f + ".launched"
        try:
            with open(cnt_path) as fh:
                n = int(fh.read().strip() or 0)
        except (OSError, ValueError):
            n = None
        b = os.path.basename(f)
        if n is None:
            no_counter.append((b, ents))
            continue
        n = min(n, len(ents))
        counted_names |= {e.get("name") for e in ents}
        launched_names |= {e.get("name") for e in ents[:n]}
        files.append({"file": b, "entries": len(ents), "launched": n, "names": [e.get("name") for e in ents[n:]],
                      "driver": b in drivers})
    orphan = 0
    seen = set()
    for b, ents in no_counter:
        for e in ents:
            nm = e.get("name")
            if nm in counted_names or nm in seen:
                continue
            seen.add(nm)
            out = out_path_of(e.get("cmd") or [], code_dir)
            if out and not os.path.exists(out):
                orphan += 1
    pending = set()
    for x in files:         # an entry re-queued in a later file (e.g. c14_rest) counts once, as launched if launched anywhere
        names = [nm for nm in x.pop("names") if nm not in launched_names]
        x["remaining"] = len([nm for nm in names if nm not in pending])
        pending |= set(names)
    queued = len(pending)
    return {"queued": queued, "orphan": orphan, "running": int(running), "total": queued + int(running),
            "files": [x for x in files if x["remaining"] or x["driver"]]}


def hours_left(now, end=LOOP_END):
    return (parse_ts(end) - now).total_seconds() / 3600.0
