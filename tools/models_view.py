#!/usr/bin/env python3
"""Tab «🧠 Μοντέλα»: loader/validator for docs/models.json, edit helpers (design sandbox), SVG/HTML renderers,
JSON proposals, and the git-plumbing «Εφαρμογή στον κώδικα» (see models_apply section below). No LLM, no network.

The edits never touch training code. Only `apply_commit` writes (a config JSON inside ~/qrl-lab/code, via git)."""
import copy
import datetime as dt
import difflib
import html
import importlib.util
import json
import math
import os
import re
import subprocess

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATUS = ("used", "proposed")
KINDS = ("classical", "quantum")
CLASSICAL_TYPES = ("input", "dense", "lstm", "output")
QUANTUM_TYPES = ("pre", "encoding", "variational", "entangle", "measure", "post")
CONN_KINDS = ("dense", "recurrent", "conv", "sequence", "copy")
ACTIVATIONS = ("relu", "tanh", "sigmoid", "leaky_relu", "gelu", "elu", "selu", "softplus", "linear")
GATES = ("RX", "RY", "RZ")
PATTERNS = ("ring", "chain", "none")
# role -> (fill, Greek name)
ROLES = {
    "input": ("#38bdf8", "Είσοδος"), "recurrent": ("#a78bfa", "Αναδρομικό / LSTM"), "dense": ("#34d399", "Κρυφό dense"),
    "output": ("#fbbf24", "Έξοδος / Q-values"), "online": ("#60a5fa", "Online δίκτυο"), "target": ("#fb7185", "Target δίκτυο"),
    "replay": ("#fb923c", "Replay buffer"), "loss": ("#e879f9", "Loss / στόχος"), "env": ("#94a3b8", "Περιβάλλον"),
    "q_encoding": ("#22d3ee", "Κβαντική κωδικοποίηση"), "q_variational": ("#818cf8", "Παραμετρικά επίπεδα"),
    "q_entangle": ("#f472b6", "Εμπλοκή"), "q_measure": ("#facc15", "Μέτρηση"),
    "classical_pre": ("#94a3b8", "Κλασική προεπεξεργασία"), "classical_post": ("#a3e635", "Κλασική μετεπεξεργασία"),
}
FIXED_FIRST = ("input", "pre")
FIXED_LAST = ("output", "measure", "post")
PROPOSAL_NOTE = "πρόταση — δεν αλλάζει τον κώδικα"
ACTION_LABELS = ["-1 pod", "0", "+1 pod"]   # code/sim_v2/env.py:33 ACTION_DELTA {0:-1, 1:0, 2:+1}


class ModelsError(ValueError):
    pass


# ------------------------------------------------------------------ load / validate
def _resolve(doc):
    by_id = {m["id"]: m for m in doc["models"] if isinstance(m, dict) and "id" in m}
    out = []
    for m in doc["models"]:
        if "extends" in m:
            base = by_id.get(m["extends"])
            if base is None or "extends" in base:
                raise ModelsError(f"{m['id']}: extends unknown/nested base {m['extends']!r}")
            r = copy.deepcopy(base)
            for k, v in m.items():
                if k in ("extends", "extra_sources", "hyperparams_override", "block_overrides"):
                    continue
                r[k] = copy.deepcopy(v)
            r["sources"] = r["sources"] + copy.deepcopy(m.get("extra_sources", []))
            r["hyperparams"].update(copy.deepcopy(m.get("hyperparams_override", {})))
            for b in r["blocks"]:
                b.update(copy.deepcopy(m.get("block_overrides", {}).get(b["id"], {})))
            r["extends"] = m["extends"]
            out.append(r)
        else:
            out.append(copy.deepcopy(m))
    return out


def validate_model(m):
    def need(c, msg):
        if not c:
            raise ModelsError(f"{m.get('id', '?')}: {msg}")
    for k in ("id", "name", "desc_el"):
        need(isinstance(m.get(k), str) and m[k].strip(), f"missing '{k}'")
    need(m.get("status") in STATUS, f"status must be one of {STATUS}")
    need(m.get("kind") in KINDS, f"kind must be one of {KINDS}")
    src = m.get("sources")
    need(isinstance(src, list) and src and all(isinstance(s, dict) and s.get("path") and s.get("lines") for s in src),
         "sources must be a non-empty list of {path, lines}")
    hp = m.get("hyperparams")
    need(isinstance(hp, dict) and hp, "hyperparams must be a non-empty object")
    for k, v in hp.items():
        need(isinstance(v, dict) and "value" in v and v.get("src"), f"hyperparam {k}: needs value and src")
    bl = m.get("blocks")
    need(isinstance(bl, list) and bl, "blocks must be a non-empty list")
    ids = [b.get("id") for b in bl]
    need(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids), "block ids must be unique strings")
    types = CLASSICAL_TYPES if m["kind"] == "classical" else QUANTUM_TYPES
    for b in bl:
        need(b.get("type") in types, f"block {b['id']}: type {b.get('type')!r} not in {types}")
        need(b.get("role") in ROLES, f"block {b['id']}: unknown role {b.get('role')!r}")
        need(isinstance(b.get("label_el"), str) and b.get("desc_el") and b.get("src"), f"block {b['id']}: label_el/desc_el/src required")
        if m["kind"] == "classical":
            need(isinstance(b.get("units"), int) and not isinstance(b["units"], bool) and b["units"] > 0, f"block {b['id']}: units > 0")
            if b["type"] in ("dense", "output", "input"):
                need(b.get("activation") in ACTIVATIONS, f"block {b['id']}: activation must be in {ACTIVATIONS}")
            if b["type"] == "lstm":
                need(isinstance(b.get("num_layers"), int) and 1 <= b["num_layers"] <= 16, f"block {b['id']}: num_layers 1..16")
        else:
            if b["type"] in ("encoding", "variational"):
                need(b.get("gates") and all(g in GATES for g in b["gates"]), f"block {b['id']}: gates ⊂ {GATES}")
            if b["type"] == "entangle":
                need(b.get("pattern") in PATTERNS, f"block {b['id']}: pattern in {PATTERNS}")
            if b["type"] == "measure":
                need(b.get("mode") in ("probs", "expval") and isinstance(b.get("readout"), int) and b["readout"] >= 1, f"block {b['id']}: mode/readout")
    first, last = bl[0]["type"], bl[-1]["type"]
    if m["kind"] == "classical":
        need(first == "input" and last == "output", "first block must be input and last output")
        types_in = [b["type"] for b in bl]
        need(types_in.count("input") == 1 and types_in.count("output") == 1, "exactly one input and one output")
        if "lstm" in types_in:
            need(types_in.count("lstm") == 1, "at most one lstm block")
            need(all(t != "dense" for t in types_in[:types_in.index("lstm")]), "dense layers must come after the LSTM")
    else:
        need(first == "pre" and last == "post", "first block must be pre and last post")
        need(any(b["type"] == "measure" for b in bl), "a measure block is required")
        need(isinstance(hp.get("n_qubits", {}).get("value"), int) and 1 <= hp["n_qubits"]["value"] <= 16, "n_qubits 1..16")
    idset = set(ids)
    cons = m.get("connections")
    need(isinstance(cons, list), "connections must be a list")
    for c in cons:
        need(c.get("from") in idset and c.get("to") in idset and c.get("kind") in CONN_KINDS, f"bad connection {c}")
    return m


def validate(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("models"), list) or not doc["models"]:
        raise ModelsError("models.json needs a non-empty 'models' list")
    models = _resolve(doc)
    ids = [m["id"] for m in models]
    if len(set(ids)) != len(ids):
        raise ModelsError("duplicate model ids")
    for m in models:
        validate_model(m)
    return models


def load(path=None):
    with open(path or os.path.join(ROOT, "docs", "models.json"), encoding="utf-8") as f:
        return validate(json.load(f))


# ------------------------------------------------------------------ stats
def _lstm_params(inp, h, layers):
    n, cur = 0, inp
    for _ in range(layers):
        n += 4 * (h * (cur + h) + 2 * h)
        cur = h
    return n


def classical_params(m):
    total, cur, per = 0, None, {}
    for b in m["blocks"]:
        if b["type"] == "input":
            cur = b["units"]; per[b["id"]] = 0
        elif b["type"] == "lstm":
            per[b["id"]] = _lstm_params(cur, b["units"], b["num_layers"]); cur = b["units"]
        else:
            per[b["id"]] = cur * b["units"] + b["units"]; cur = b["units"]
        total += per[b["id"]]
    return total, per


def n_qubits(m):
    return int(m["hyperparams"]["n_qubits"]["value"])


def stage_gates(b, n):
    """Gate list of one stage: (name, [qubits], trainable)."""
    t = b["type"]
    if t == "encoding":
        return [(g, [q], False) for g in b["gates"] for q in range(n)]
    if t == "variational":
        return [(g, [q], True) for g in b["gates"] for q in range(n)]
    if t == "entangle":
        if n < 2 or b["pattern"] == "none":
            return []
        pairs = [(i, (i + 1) % n) for i in range(n)] if b["pattern"] == "ring" else [(i, i + 1) for i in range(n - 1)]
        return [("CNOT", [c, t_], False) for c, t_ in pairs]
    if t == "measure":
        return [("M", [q], False) for q in range(min(b["readout"], n) if b["mode"] == "expval" else n)]
    return []


def quantum_stats(m):
    n = n_qubits(m)
    separate = bool(m["hyperparams"].get("separate_weights", {}).get("value", True))
    counts, params, front, seq = {}, 0, [0] * n, []
    for b in m["blocks"]:
        if b["type"] not in ("encoding", "variational", "entangle"):
            continue
        rep = int(b.get("repeat", 1))
        gl = stage_gates(b, n)
        for r in range(rep):
            for g, qs, tr in gl:
                seq.append((g, qs))
                counts[g] = counts.get(g, 0) + 1
                if tr and (separate or r == 0):
                    params += 1
    for g, qs in seq:
        t = max(front[q] for q in qs) + 1
        for q in qs:
            front[q] = t
    extra = sum(int(b.get("extra_params", 0)) for b in m["blocks"] if b["type"] in ("pre", "post"))
    return {"qubits": n, "depth": max(front) if front else 0, "gate_counts": counts, "gates_total": sum(counts.values()),
            "circuit_params": params, "extra_params": extra, "params": params + extra}


def stats(m):
    if m["kind"] == "classical":
        total, per = classical_params(m)
        return {"params": total, "per_block": per}
    return quantum_stats(m)


# ------------------------------------------------------------------ edits (pure; return a modified deep copy)
def _find(m, bid):
    for i, b in enumerate(m["blocks"]):
        if b["id"] == bid:
            return i
    raise ModelsError(f"unknown block {bid}")


def relink(m):
    old = {(c["from"], c["to"]): c for c in m["connections"] if c["from"] != c["to"]}
    loops = [c for c in m["connections"] if c["from"] == c["to"] and any(b["id"] == c["from"] for b in m["blocks"])]
    new = []
    bl = m["blocks"]
    for a, b in zip(bl, bl[1:]):
        c = old.get((a["id"], b["id"]))
        if c is None:
            c = {"from": a["id"], "to": b["id"], "kind": "sequence" if (a["type"] == "input" and b["type"] == "lstm") or m["kind"] == "quantum" else "dense",
                 "label_el": "" if m["kind"] == "quantum" else "πλήρως συνδεδεμένο"}
        new.append(dict(c))
    m["connections"] = new + [dict(c) for c in loops]
    return m


def edit_block(m, bid, **fields):
    m = copy.deepcopy(m)
    b = m["blocks"][_find(m, bid)]
    allowed = {"units", "activation", "num_layers", "gates", "pattern", "mode", "readout", "repeat", "window"}
    for k, v in fields.items():
        if k not in allowed:
            raise ModelsError(f"field {k} is not editable")
        b[k] = v
    validate_model(m)
    return m


def edit_hyper(m, name, value):
    m = copy.deepcopy(m)
    if name not in m["hyperparams"]:
        raise ModelsError(f"unknown hyperparameter {name}")
    m["hyperparams"][name]["value"] = value
    validate_model(m)
    return m


def move_block(m, bid, delta):
    m = copy.deepcopy(m)
    i = _find(m, bid)
    b = m["blocks"][i]
    if b["type"] in FIXED_FIRST + FIXED_LAST:
        raise ModelsError("αυτό το επίπεδο δεν μετακινείται")
    j = i + delta
    lo = 1
    hi = len(m["blocks"]) - 1
    while hi > 0 and m["blocks"][hi - 1]["type"] in FIXED_LAST:
        hi -= 1
    if not lo <= j < hi:
        raise ModelsError("εκτός ορίων")
    m["blocks"][i], m["blocks"][j] = m["blocks"][j], m["blocks"][i]
    relink(m)
    validate_model(m)
    return m


def remove_block(m, bid):
    m = copy.deepcopy(m)
    i = _find(m, bid)
    if m["blocks"][i]["type"] in FIXED_FIRST + FIXED_LAST + ("lstm", "encoding"):
        raise ModelsError("αυτό το επίπεδο δεν διαγράφεται")
    del m["blocks"][i]
    relink(m)
    validate_model(m)
    return m


def add_block(m, after_id, btype):
    """Add a dense layer (classical) or a variational / entangle stage (quantum) after `after_id`."""
    m = copy.deepcopy(m)
    i = _find(m, after_id)
    if m["blocks"][i]["type"] in FIXED_LAST:
        raise ModelsError("δεν μπαίνει μετά το τελευταίο επίπεδο")
    n = 1
    ids = {b["id"] for b in m["blocks"]}
    while f"{btype}{n}" in ids:
        n += 1
    nid = f"{btype}{n}"
    if m["kind"] == "classical":
        if btype != "dense":
            raise ModelsError("μόνο dense")
        prev = next(b for b in reversed(m["blocks"][:i + 1]) if "units" in b)
        blk = {"id": nid, "type": "dense", "role": "dense", "label_el": f"Νέο κρυφό {n}", "units": min(prev["units"], 128) or 16,
               "activation": "relu", "desc_el": "Νέο επίπεδο από το sandbox (δεν υπάρχει στον κώδικα).", "src": "sandbox"}
    elif btype == "variational":
        blk = {"id": nid, "type": "variational", "role": "q_variational", "label_el": f"Παραμετρικό {n}", "gates": ["RY", "RZ"],
               "desc_el": "Νέο παραμετρικό επίπεδο από το sandbox.", "src": "sandbox"}
    elif btype == "entangle":
        blk = {"id": nid, "type": "entangle", "role": "q_entangle", "label_el": f"Εμπλοκή {n}", "pattern": "ring",
               "desc_el": "Νέο επίπεδο εμπλοκής από το sandbox.", "src": "sandbox"}
    else:
        raise ModelsError("μόνο variational/entangle")
    m["blocks"].insert(i + 1, blk)
    relink(m)
    validate_model(m)
    return m


# ------------------------------------------------------------------ proposals
def _slug(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", s).strip("-") or "model"


def diff_models(base, new):
    """Human-readable list of differences in blocks and hyperparameters."""
    out = []
    bb, nb = {b["id"]: b for b in base["blocks"]}, {b["id"]: b for b in new["blocks"]}
    for i in nb:
        if i not in bb:
            out.append(f"+ {i}")
    for i in bb:
        if i not in nb:
            out.append(f"- {i}")
        else:
            for k in sorted(set(bb[i]) | set(nb[i])):
                if bb[i].get(k) != nb[i].get(k) and k not in ("desc_el", "src"):
                    out.append(f"{i}.{k}: {bb[i].get(k)} → {nb[i].get(k)}")
    if [b["id"] for b in base["blocks"] if b["id"] in nb] != [b["id"] for b in new["blocks"] if b["id"] in bb]:
        out.append("σειρά επιπέδων: " + " → ".join(b["id"] for b in new["blocks"]))
    for k in new["hyperparams"]:
        if base["hyperparams"].get(k, {}).get("value") != new["hyperparams"][k]["value"]:
            out.append(f"hyperparam {k}: {base['hyperparams'].get(k, {}).get('value')} → {new['hyperparams'][k]['value']}")
    return out


def save_proposal(base, edited, name, outdir=None, now=None):
    """Write docs/model_proposals/<name>-<timestamp>.json. Returns the path. Never touches code."""
    outdir = outdir or os.environ.get("QRL_PROPOSALS_DIR") or os.path.join(ROOT, "docs", "model_proposals")
    os.makedirs(outdir, exist_ok=True)
    now = now or dt.datetime.now()
    ts = now.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(outdir, f"{_slug(name or edited['id'])}-{ts}.json")
    doc = {"proposal": True, "note_el": PROPOSAL_NOTE, "created": now.isoformat(timespec="seconds"), "base_model": base["id"],
           "name": name, "changes": diff_models(base, edited), "stats": stats(edited), "model": edited}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return path


# ------------------------------------------------------------------ rendering
BG = "#0f172a"
INK = "#0b1220"      # text on coloured cards
LIGHT = "#e2e8f0"    # text on the dark canvas
MUTED = "#94a3b8"
FONT = "system-ui,-apple-system,'Segoe UI',Roboto,sans-serif"


def _e(s):
    return html.escape(str(s), quote=True)


def _wrap(text, width):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def _text(x, y, s, size=12, fill=INK, anchor="middle", weight="normal", extra=""):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {extra}>{_e(s)}</text>'


def _lines(x, y, s, width, size=10, fill=LIGHT, anchor="middle", dy=12.5):
    return "".join(_text(x, y + i * dy, ln, size, fill, anchor) for i, ln in enumerate(_wrap(s, width)))


def _g(b, inner, sel, extra_cls=""):
    info = _e(b.get("desc_el", ""))
    return (f'<g class="blk{" sel" if sel else ""} {extra_cls}" tabindex="0" data-t="{_e(b["label_el"])}" data-d="{info}" '
            f'data-s="{_e(b.get("src", ""))}" data-p="{_e(b.get("_info", ""))}"><title>{_e(b["label_el"])}</title>{inner}</g>')


def _arrow(x1, y1, x2, y2, color=MUTED, w=2, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    ang = math.atan2(y2 - y1, x2 - x1)
    hx, hy = x2 - 8 * math.cos(ang), y2 - 8 * math.sin(ang)
    p1 = (hx - 5 * math.sin(ang), hy + 5 * math.cos(ang))
    p2 = (hx + 5 * math.sin(ang), hy - 5 * math.cos(ang))
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" stroke="{color}" stroke-width="{w}"{d}/>'
            f'<polygon points="{x2:.1f},{y2:.1f} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" fill="{color}"/>')


def _neuron_ys(units, top, bottom):
    k = min(units, 7)
    shown = list(range(k))
    ys = [top + (bottom - top) * i / max(k - 1, 1) for i in range(k)] if k > 1 else [(top + bottom) / 2]
    return ys, units > 7


def _flow(m, sel):
    """Left-to-right layer diagram. Returns (svg_body, width, height_used, positions)."""
    bw = {"lstm": 210}
    X0, Y0, H, GAP = 34, 74, 280, 140
    x, pos = X0, {}
    for b in m["blocks"]:
        w = bw.get(b["type"], 150)
        pos[b["id"]] = (x, w)
        x += w + GAP
    width = x - GAP + X0
    out, ports = [], {}
    for b in m["blocks"]:
        x, w = pos[b["id"]]
        fill = ROLES[b["role"]][0]
        t = b["type"]
        issel = sel == b["id"]
        stroke = "#ffffff" if issel else "#0b1220"
        sw = 4 if issel else 1.5
        s = []
        if t == "input" and b.get("window", 1) > 1:
            for k in (2, 1):
                s.append(f'<rect x="{x + 9 * k}" y="{Y0 - 9 * k}" width="{w}" height="{H}" rx="16" fill="{fill}" opacity="{0.35 / k + .1:.2f}"/>')
            s.append(_text(x + w + 6, Y0 - 26, f"T = {b['window']} βήματα", 10, MUTED, "end"))
        dash = ' stroke-dasharray="7 5"' if b.get("frozen") else ""
        s.append(f'<rect x="{x}" y="{Y0}" width="{w}" height="{H}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
        s.append(_text(x + w / 2, Y0 + 24, b["label_el"], 14, INK, weight="bold"))
        sub = {"input": "είσοδος", "dense": "dense (fully connected)", "lstm": "LSTM (recurrent)", "output": "έξοδος"}[t]
        s.append(_text(x + w / 2, Y0 + 40, sub, 10, INK))
        b = dict(b)
        if t == "lstm":
            L = b["num_layers"]; shown = min(L, 4)
            sh, gapv, y = 50, 12, Y0 + 56
            ys_in = []
            for i in range(shown):
                s.append(f'<rect x="{x + 14}" y="{y}" width="{w - 28}" height="{sh}" rx="10" fill="#ffffff" opacity=".78" stroke="{INK}" stroke-width="1"/>')
                s.append(_text(x + w / 2, y + 19, f"LSTM στρώμα {i + 1} · {b['units']} κελιά", 11, INK, weight="bold"))
                for j, (nm, cx) in enumerate((("h", x + w / 2 - 28), ("c", x + w / 2 + 28))):
                    s.append(f'<rect x="{cx - 20}" y="{y + 27}" width="40" height="17" rx="8" fill="{["#7c3aed", "#db2777"][j]}"/>')
                    s.append(_text(cx, y + 39.5, f"{nm}ₜ", 10, "#ffffff", weight="bold"))
                ys_in.append(y + sh / 2)
                if i < shown - 1:
                    s.append(_arrow(x + w / 2, y + sh, x + w / 2, y + sh + gapv, INK, 1.6))
                y += sh + gapv
            if L > shown:
                s.append(_text(x + w / 2, y + 4, f"… +{L - shown} ακόμη στρώματα", 10, INK))
            ports[b["id"]] = (ys_in[:1] + ys_in[-1:] if len(ys_in) > 1 else ys_in, ys_in)
            s.append(_text(x + w / 2, Y0 + H - 34, f"{b['units']} × {L} στρώματα", 12, INK, weight="bold"))
            s.append(_text(x + w / 2, Y0 + H - 18, "πύλες σ · υποψήφιο tanh (σταθερά)", 9.5, INK))
            b["_info"] = f"παράμετροι: {classical_params(m)[1][b['id']]:,}".replace(",", ".")
        else:
            ys, dots = _neuron_ys(b["units"], Y0 + 70, Y0 + H - 70)
            cx = x + 30 if (t == "input" and b.get("features")) or t == "output" else x + w / 2
            for i, y in enumerate(ys):
                if dots and i == 3:
                    s.append(_text(cx, y + 7, "⋮", 20, INK, weight="bold"))
                    continue
                s.append(f'<circle cx="{cx}" cy="{y:.1f}" r="9" fill="#ffffff" opacity=".9" stroke="{INK}" stroke-width="1.2"/>')
                if t == "input" and b.get("features") and i < len(b["features"]) and len(ys) == len(b["features"]):
                    s.append(_text(cx + 15, y + 3.5, b["features"][i], 9.5, INK, "start"))
                if t == "output":
                    lab = ACTION_LABELS[i] if b["units"] == 3 and i < 3 else f"a{i}"
                    s.append(_text(cx + 15, y + 3.5, f"Q({lab})", 10.5, INK, "start", "bold"))
            ports[b["id"]] = (ys, ys)
            act = b.get("activation", "linear")
            s.append(_text(x + w / 2, Y0 + H - 34, f"{b['units']} νευρώνες", 12, INK, weight="bold"))
            s.append(_text(x + w / 2, Y0 + H - 17, "ενεργ.: " + ("linear (καμία)" if act == "linear" else act), 10.5, INK))
            if t != "input":
                b["_info"] = f"παράμετροι: {classical_params(m)[1][b['id']]:,}".replace(",", ".")
        out.append(_g(b, "".join(s), issel))
    # connections
    for c in m["connections"]:
        a, b2 = c["from"], c["to"]
        xa, wa = pos[a]
        xb, wb = pos[b2]
        if a == b2:
            xr, yt = xa + wa - 40, Y0
            out.append(f'<path d="M {xa + wa - 40} {Y0} C {xa + wa - 40} {Y0 - 52}, {xa + 40} {Y0 - 52}, {xa + 40} {Y0 - 2}" fill="none" stroke="{fill_of(m, a)}" stroke-width="3" stroke-dasharray="6 4"/>')
            out.append(_arrow(xa + 40, Y0 - 14, xa + 40, Y0 - 1, fill_of(m, a), 3))
            out.append(_lines(xa + wa / 2, Y0 - 62, c["label_el"], 40, 10, LIGHT))
            continue
        x1, x2 = xa + wa, xb
        col = fill_of(m, a)
        ya, yb = ports[a][1], ports[b2][0]
        if c["kind"] == "sequence":
            for y1, y2 in zip(ya[:3], [Y0 + H / 2 - 30, Y0 + H / 2, Y0 + H / 2 + 30]):
                out.append(_arrow(x1 + 4, y1 + 0, x2 - 4, y2, col, 2))
        else:
            for y1 in ya:
                for y2 in yb:
                    out.append(f'<line x1="{x1 + 2}" y1="{y1:.1f}" x2="{x2 - 2}" y2="{y2:.1f}" stroke="{col}" stroke-width="1" opacity=".28"/>')
        out.append(_lines((x1 + x2) / 2, Y0 + H + 18, c["label_el"], 22, 10, MUTED))
    return "".join(out), width, Y0 + H + 56, pos


def fill_of(m, bid):
    return ROLES[next(b for b in m["blocks"] if b["id"] == bid)["role"]][0]


def _box(x, y, w, h, role, title, sub="", dashed=False, bid=None, desc=""):
    fill = ROLES[role][0]
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{INK}" stroke-width="1.5"{dash}/>'
    s += _text(x + w / 2, y + 22, title, 13, INK, weight="bold")
    for i, ln in enumerate(_wrap(sub, int(w / 6.3))):
        s += _text(x + w / 2, y + 40 + i * 13, ln, 10, INK)
    b = {"label_el": title, "desc_el": desc or sub, "src": ""}
    return _g(b, s, False)


def _train_lane(m, y0, width):
    hp = {k: v["value"] for k, v in m["hyperparams"].items()}
    dbl = bool(hp.get("double_dqn"))
    sync = hp.get("target_sync_every", 1)
    s = [_text(34, y0 - 50, "Εκπαίδευση: " + ("Double DQN" if dbl else "DQN (απλό max στο target)") + " με δύο δίκτυα, online και target",
               15, LIGHT, "start", "bold")]
    s.append(_box(34, y0 + 10, 190, 96, "env", "Περιβάλλον (Sim v2)", "δίνει s, r και παίρνει δράση a ∈ {−1, 0, +1} pod"))
    s.append(_box(300, y0 + 10, 210, 96, "replay", "Replay buffer", f"deque μέγιστο {hp.get('replay_size')} · (s, a, r, s′, done)"))
    s.append(_box(590, y0 + 10, 210, 96, "online", "Online δίκτυο Qθ", f"το δίκτυο που εκπαιδεύεται · lr {hp.get('lr')} · Adam"))
    s.append(_box(590, y0 + 190, 210, 96, "target", "Target δίκτυο Qθ⁻", "παγωμένο αντίγραφο, δεν εκπαιδεύεται", dashed=True))
    s.append(_box(880, y0 + 100, 220, 96, "loss", "Loss · " + str(hp.get("loss", "Huber")), f"στόχος y, γ = {hp.get('gamma')}"))
    s.append(_arrow(224, y0 + 58, 300, y0 + 58, MUTED, 2.2))
    s.append(_text(262, y0 + 48, "remember", 10, MUTED))
    s.append(_arrow(510, y0 + 58, 590, y0 + 58, ROLES["replay"][0], 2.5))
    s.append(_lines(550, y0 + 128, f"δείγμα batch = {hp.get('batch_size')}", 14, 10.5, LIGHT))
    s.append(f'<path d="M 405 {y0 + 106} L 405 {y0 + 238} L 590 {y0 + 238}" fill="none" stroke="{ROLES["replay"][0]}" stroke-width="2.2"/>')
    s.append(_arrow(580, y0 + 238, 590, y0 + 238, ROLES["replay"][0], 2.2))
    s.append(_text(497, y0 + 232, "s′ (επόμενες καταστάσεις)", 10, LIGHT))
    s.append(_arrow(800, y0 + 58, 940, y0 + 100, ROLES["online"][0], 2.2))
    s.append(_text(872, y0 + 64, "Q(s, a)", 10.5, LIGHT))
    s.append(_arrow(800, y0 + 238, 940, y0 + 196, ROLES["target"][0], 2.2))
    s.append(_text(884, y0 + 232, "y (στόχος)", 10.5, LIGHT))
    s.append(_arrow(695, y0 + 106, 695, y0 + 190, MUTED, 2.2, "7 5"))
    s.append(_lines(703, y0 + 140, "sync: αντιγραφή βαρών " + ("μετά από ΚΑΘΕ replay" if sync == 1 else f"κάθε {sync} replay"), 24, 10.5, "#fde68a", "start"))
    s.append(f'<path d="M 695 {y0 + 10} C 695 {y0 - 24}, 130 {y0 - 24}, 130 {y0 + 10}" fill="none" stroke="{ROLES["online"][0]}" stroke-width="2" stroke-dasharray="6 4"/>')
    s.append(_arrow(130, y0 - 6, 130, y0 + 9, ROLES["online"][0], 2))
    s.append(_text(412, y0 - 20, "δράση ε-greedy από το online (" + str(hp.get("epsilon", "")) + ")", 10, MUTED))
    formula = ("y = r + γ · Q_target(s′, argmax_a Q_online(s′, a))" if dbl else "y = r + γ · max_a Q_target(s′, a)")
    s.append(_text(34, y0 + 330, "Στόχος: " + formula + "   (y = r στο τέλος του επεισοδίου)", 12, LIGHT, "start"))
    return "".join(s), y0 + 350


def _lstm_detail(y0, m):
    b = next(b for b in m["blocks"] if b["type"] == "lstm")
    T = next(x for x in m["blocks"] if x["type"] == "input").get("window", 1)
    col = ROLES["recurrent"][0]
    s = [_text(34, y0 - 14, f"Μέσα στο LSTM: ξεδίπλωμα {T} βημάτων και ένα κελί (h = κρυφή κατάσταση, c = κατάσταση κελιού)", 15, LIGHT, "start", "bold")]
    xs = [40, 190, 340, 640] if T > 4 else [40 + 150 * i for i in range(max(T, 1))]
    names = [1, 2, 3, T] if T > 4 else list(range(1, T + 1))
    for i, (x, n) in enumerate(zip(xs, names)):
        s.append(f'<rect x="{x}" y="{y0 + 70}" width="110" height="74" rx="12" fill="{col}" stroke="{INK}" stroke-width="1.5"/>')
        s.append(_text(x + 55, y0 + 100, f"LSTM t={n}", 13, INK, weight="bold"))
        s.append(_text(x + 55, y0 + 120, f"{b['num_layers']} × {b['units']}", 11, INK))
        s.append(_arrow(x + 55, y0 + 210, x + 55, y0 + 146, ROLES["input"][0], 2))
        s.append(_text(x + 55, y0 + 228, f"x_{n} (6)", 11, LIGHT))
        if i < len(xs) - 1:
            dots = (T > 4 and i == 2)
            nx = xs[i + 1]
            s.append(_arrow(x + 110, y0 + 95, nx, y0 + 95, "#7c3aed" if not dots else MUTED, 2.2, "5 4" if dots else None))
            s.append(_arrow(x + 110, y0 + 122, nx, y0 + 122, "#db2777" if not dots else MUTED, 2.2, "5 4" if dots else None))
            mid = (x + 110 + nx) / 2
            s.append(_text(mid, y0 + 88, "h" if not dots else "…", 11, "#c4b5fd"))
            s.append(_text(mid, y0 + 138, "c" if not dots else "", 11, "#f9a8d4"))
    xl = xs[-1]
    s.append(_arrow(xl + 55, y0 + 70, xl + 55, y0 + 18, ROLES["output"][0], 2.4))
    s.append(_text(xl + 62, y0 + 12, "h_T του τελευταίου βήματος → Linear → Q-values", 11, LIGHT, "start"))
    # one cell, schematic
    cx = 800
    s.append(_text(cx + 170, y0 + 50, "ένα κελί LSTM", 11, MUTED))
    s.append(f'<rect x="{cx}" y="{y0 + 30}" width="340" height="200" rx="14" fill="none" stroke="{col}" stroke-width="2"/>')
    s.append(_arrow(cx - 20, y0 + 70, cx + 360, y0 + 70, "#db2777", 3))
    s.append(_text(cx - 20, y0 + 62, "c_{t-1}", 11, "#f9a8d4", "start"))
    s.append(_text(cx + 360, y0 + 62, "c_t", 11, "#f9a8d4", "end"))
    for gx, lab, act in ((cx + 40, "forget", "σ"), (cx + 105, "input", "σ"), (cx + 170, "candidate", "tanh"), (cx + 275, "output", "σ")):
        s.append(f'<rect x="{gx}" y="{y0 + 168}" width="56" height="30" rx="8" fill="{col}" stroke="{INK}"/>')
        s.append(_text(gx + 28, y0 + 187, act, 12, INK, weight="bold"))
        s.append(_text(gx + 28, y0 + 214, lab, 9.5, LIGHT))
    s.append(f'<circle cx="{cx + 68}" cy="{y0 + 70}" r="10" fill="#fff"/>' + _text(cx + 68, y0 + 75, "×", 14, INK, weight="bold"))
    s.append(_arrow(cx + 68, y0 + 168, cx + 68, y0 + 82, col, 2))
    s.append(f'<circle cx="{cx + 180}" cy="{y0 + 70}" r="10" fill="#fff"/>' + _text(cx + 180, y0 + 75, "+", 14, INK, weight="bold"))
    s.append(f'<circle cx="{cx + 160}" cy="{y0 + 120}" r="10" fill="#fff"/>' + _text(cx + 160, y0 + 125, "×", 14, INK, weight="bold"))
    s.append(_arrow(cx + 133, y0 + 168, cx + 150, y0 + 125, col, 2))
    s.append(_arrow(cx + 198, y0 + 168, cx + 170, y0 + 125, col, 2))
    s.append(_arrow(cx + 160, y0 + 110, cx + 176, y0 + 82, col, 2))
    s.append(f'<rect x="{cx + 225}" y="{y0 + 88}" width="46" height="24" rx="8" fill="{col}"/>' + _text(cx + 248, y0 + 104, "tanh", 11, INK))
    s.append(_arrow(cx + 248, y0 + 70, cx + 248, y0 + 88, "#db2777", 1.8))
    s.append(f'<circle cx="{cx + 303}" cy="{y0 + 130}" r="10" fill="#fff"/>' + _text(cx + 303, y0 + 135, "×", 14, INK, weight="bold"))
    s.append(_arrow(cx + 271, y0 + 106, cx + 294, y0 + 125, col, 2))
    s.append(_arrow(cx + 303, y0 + 168, cx + 303, y0 + 142, col, 2))
    s.append(_arrow(cx + 313, y0 + 130, cx + 360, y0 + 130, "#7c3aed", 3))
    s.append(_text(cx + 360, y0 + 122, "h_t", 11, "#c4b5fd", "end"))
    s.append(_arrow(cx - 20, y0 + 240, cx + 40, y0 + 240, "#7c3aed", 2))
    s.append(_text(cx - 20, y0 + 256, "[h_{t-1}, x_t]", 11, LIGHT, "start"))
    s.append(f'<line x1="{cx + 40}" y1="{y0 + 240}" x2="{cx + 331}" y2="{y0 + 240}" stroke="{MUTED}" stroke-width="1.5"/>')
    return "".join(s), y0 + 270


# ---- quantum circuit
def _wrap_box(x, y, w, h, role, title, sub, dashed=False, bid=None, b=None):
    fill = ROLES[role][0]
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{INK}" stroke-width="1.5"{dash}/>'
    s += _lines(x + w / 2, y + 26, title, int(w / 7), 12, INK, dy=15)
    return s


def _circuit(m, sel):
    n = n_qubits(m)
    WS, Y0, PITCH, CX0 = 50, 96, 46, 270
    ys = [Y0 + q * WS for q in range(n)]
    pre = m["blocks"][0]
    post = m["blocks"][-1]
    stages = [b for b in m["blocks"][1:-1]]
    x = CX0
    layout = []
    for b in stages:
        gl = stage_gates(b, n)
        if b["type"] in ("encoding", "variational"):
            cols = [[(g, [q], tr) for q in range(n) for (gg, qq, tr) in [(g, [q], b["type"] == "variational")]] for g in b["gates"]]
        else:
            cols = [[g] for g in gl]
        if b["type"] == "measure":
            cols = [gl]
        w = max(len(cols), 1) * PITCH + 14
        layout.append((b, cols, x, w))
        x += w + 12
    xpost = x + 6
    width = xpost + 170 + 30
    height = ys[-1] + 80 + 40
    out = []
    # wires
    for q in range(n):
        out.append(f'<line x1="150" y1="{ys[q]}" x2="{xpost}" y2="{ys[q]}" stroke="{MUTED}" stroke-width="1.6"/>')
        out.append(_text(40, ys[q] + 4, f"q{q}  |0⟩", 12, LIGHT, "start"))
    pre_b = dict(pre, _info=f"παράμετροι: {pre.get('extra_params', 0)}")
    ph = ys[-1] - ys[0] + 56
    out.append(_g(pre_b, _wrap_box(106, ys[0] - 28, 150 + 0, ph, pre["role"], pre["label_el"], "", pre.get("frozen", False)) +
                  (_text(181, ys[0] + ph - 38, "❄ παγωμένο", 11, INK) if pre.get("frozen") else ""), sel == pre["id"]))
    # groups
    seen = {}
    for b, cols, xx, w in layout:
        if b.get("group"):
            seen.setdefault(b["group"], []).append((xx, w, b.get("repeat", 1)))
    for grp, items in seen.items():
        x1, x2 = items[0][0] - 4, items[-1][0] + items[-1][1] + 4
        out.append(f'<path d="M {x1} 50 L {x1} 40 L {x2} 40 L {x2} 50" fill="none" stroke="#fde68a" stroke-width="2"/>')
        out.append(_text((x1 + x2) / 2, 34, f"× {items[0][2]} βήματα χρόνου (data re-uploading)", 11, "#fde68a"))
    for b, cols, xx, w in layout:
        col = ROLES[b["role"]][0]
        issel = sel == b["id"]
        s = [f'<rect x="{xx}" y="52" width="{w}" height="{ys[-1] - 52 + 38}" rx="10" fill="{col}" opacity=".13" stroke="{col}" stroke-width="{3 if issel else 1}"/>']
        s.append(_lines(xx + w / 2, 66, b["label_el"], max(int(w / 6), 6), 10, col, dy=11))
        for ci, colg in enumerate(cols):
            cx = xx + 7 + PITCH * ci + PITCH / 2
            for g, qs, tr in colg:
                if g == "CNOT":
                    c, t = qs
                    s.append(f'<line x1="{cx}" y1="{ys[c]}" x2="{cx}" y2="{ys[t]}" stroke="{col}" stroke-width="2.4"/>')
                    s.append(f'<circle cx="{cx}" cy="{ys[c]}" r="5" fill="{col}"/>')
                    s.append(f'<circle cx="{cx}" cy="{ys[t]}" r="10" fill="{BG}" stroke="{col}" stroke-width="2.4"/>')
                    s.append(f'<line x1="{cx - 10}" y1="{ys[t]}" x2="{cx + 10}" y2="{ys[t]}" stroke="{col}" stroke-width="2.4"/>')
                    s.append(f'<line x1="{cx}" y1="{ys[t] - 10}" x2="{cx}" y2="{ys[t] + 10}" stroke="{col}" stroke-width="2.4"/>')
                else:
                    q = qs[0]
                    lab = {"encoding": f"{g}(x)", "variational": f"{g}(θ)"}.get(b["type"], "⟨Z⟩" if b.get("mode") == "expval" else "P")
                    s.append(f'<rect x="{cx - 19}" y="{ys[q] - 14}" width="38" height="28" rx="7" fill="{col}" stroke="{INK}"/>')
                    s.append(_text(cx, ys[q] + 4, lab, 10 if len(lab) > 3 else 12, INK, weight="bold"))
        b2 = dict(b, _info=("εκπαιδευόμενες παράμετροι: %d" % sum(1 for g in stage_gates(b, n) if g[2])) if b["type"] == "variational" else "")
        out.append(_g(b2, "".join(s), issel))
    post_b = dict(post, _info=f"εκπαιδευόμενες παράμετροι: {post.get('extra_params', 0)}")
    out.append(_g(post_b, _wrap_box(xpost, ys[0] - 28, 170, ph, post["role"], post["label_el"], "") +
                  _lines(xpost + 85, ys[0] + 30, "→ 3 τιμές Q" if m["id"] != "quantum_sampler" else "→ δράση (δειγματοληψία)", 20, 10.5, INK), sel == post["id"]))
    return "".join(out), width, height


def _legend(roles, width):
    items, x, y = [], 34, 14
    for r in roles:
        label = ROLES[r][1]
        w = 24 + 6.6 * len(label) + 14
        if x + w > max(width, 700):
            x, y = 34, y + 22
        items.append(f'<rect x="{x}" y="{y}" width="14" height="14" rx="4" fill="{ROLES[r][0]}"/>' + _text(x + 20, y + 11.5, label, 11, LIGHT, "start"))
        x += w
    return "".join(items), y + 28


def render_svg(m, selected=None):
    """Complete self-contained SVG of the whole diagram (flow + training lane + LSTM detail, or the circuit)."""
    roles, body, width, h = [], [], 0, 0
    if m["kind"] == "classical":
        flow, width, h, _ = _flow(m, selected)
        body.append(flow)
        roles = [b["role"] for b in m["blocks"]]
        tl, h2 = _train_lane(m, h + 80, width)
        body.append(tl); h = h2
        roles += ["replay", "online", "target", "loss", "env"]
        if any(b["type"] == "lstm" for b in m["blocks"]):
            dl, h = _lstm_detail(h + 50, m)
            body.append(dl)
        width = max(width, 1180)
    else:
        circ, width, h = _circuit(m, selected)
        body.append(circ)
        roles = [b["role"] for b in m["blocks"]]
        width = max(width, 760)
    order = list(ROLES)
    uniq = [r for r in order if r in set(roles)]
    leg, lh = _legend(uniq, width)
    body = f'<g transform="translate(0 {lh})">{"".join(body)}</g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{h + lh:.0f}" viewBox="0 0 {width:.0f} {h + lh:.0f}" '
            f'font-family="{FONT}">{leg}{body}</svg>')


def _stats_line(m):
    st = stats(m)
    if m["kind"] == "classical":
        return f"παράμετροι (εκπαιδεύσιμες): {st['params']:,}".replace(",", ".")
    gc = " · ".join(f"{k}×{v}" for k, v in st["gate_counts"].items())
    return (f"qubits {st['qubits']} · βάθος {st['depth']} · πύλες {st['gates_total']} ({gc}) · "
            f"εκπαιδεύσιμες παράμετροι {st['params']} (κύκλωμα {st['circuit_params']} + κλασικές {st['extra_params']})")


def render_html(m, selected=None):
    """Self-contained HTML for components.html. Returns (html, height). Dark card, horizontal scroll inside the card."""
    svg = render_svg(m, selected)
    height = int(re.search(r'height="(\d+)"', svg).group(1)) + 190
    page = f"""<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;background:transparent;font-family:{FONT}}}
.card{{background:{BG};border-radius:16px;padding:12px;color:{LIGHT}}}
.scroll{{overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch}}
.blk{{cursor:pointer;outline:none}} .blk:hover rect:first-child,.blk:focus rect:first-child{{filter:brightness(1.12)}}
.blk.sel>rect:first-of-type{{stroke:#fff;stroke-width:4}}
#info{{margin-top:8px;padding:10px 12px;border-radius:10px;background:#1e293b;font-size:13px;line-height:1.45;min-height:54px}}
#info b{{color:#fde68a}} #info code{{color:#93c5fd}}
.st{{font-size:12px;color:{MUTED};margin-top:6px}}
</style><div class="card"><div class="scroll">{svg}</div>
<div class="st">{_e(_stats_line(m))}</div>
<div id="info">Πάτα σε ένα επίπεδο του διαγράμματος για περιγραφή και πηγή. Για αλλαγές χρησιμοποίησε τα πεδία κάτω από το διάγραμμα.</div></div>
<script>
const info=document.getElementById('info');
function show(g){{document.querySelectorAll('.blk').forEach(x=>x.classList.remove('sel'));g.classList.add('sel');
info.innerHTML='<b>'+g.dataset.t+'</b><br>'+g.dataset.d+(g.dataset.p?'<br><i>'+g.dataset.p+'</i>':'')+(g.dataset.s?'<br>πηγή: <code>'+g.dataset.s+'</code>':'');}}
document.querySelectorAll('.blk').forEach(g=>{{g.addEventListener('click',()=>show(g));g.addEventListener('keydown',e=>{{if(e.key==='Enter')show(g)}});}});
</script>"""
    return page, height


# ------------------------------------------------------------------ «Εφαρμογή στον κώδικα» (config JSON committed with git plumbing)
CODE_DIR = os.environ.get("QRL_CODE_DIR") or os.path.join(ROOT, "code")
CONFIG_REL = "models/configs/{}.json"
TRAILERS = ("Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
            "Claude-Session: https://claude.ai/code/session_011UVF9t3bWf8yyXfTWqG494")
ZERO = "0" * 40


def _code_dir():
    return os.environ.get("QRL_CODE_DIR") or CODE_DIR


def _arch():
    """code/models/arch.py loaded by path (single source of truth for config validation)."""
    p = os.path.join(_code_dir(), "models", "arch.py")
    spec = importlib.util.spec_from_file_location("qrl_code_arch", p)
    mod = importlib.util.module_from_spec(spec)
    import sys
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True   # no __pycache__ inside the code worktree
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


def _git(repo, *args, env=None, inp=None):
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, input=inp, env=e)
    return r.returncode, (r.stdout if r.returncode == 0 else r.stdout + r.stderr).rstrip("\n")


def arch_config(m):
    """Architecture JSON (code/models/arch.py format) derived from an edited classical model."""
    if m["kind"] != "classical":
        raise ModelsError("μόνο κλασικά μοντέλα έχουν αρχείο αρχιτεκτονικής στον κώδικα")
    bl = m["blocks"]
    inp = bl[0]
    out = bl[-1]
    dense = [{"units": b["units"], "activation": b["activation"]} for b in bl if b["type"] == "dense"]
    cfg = {"model": m.get("config_name") or m["id"], "input_size": inp["units"]}
    lstm = next((b for b in bl if b["type"] == "lstm"), None)
    if lstm:
        cfg.update(kind="lstm", hidden_size=lstm["units"], num_layers=lstm["num_layers"], head=dense)
    else:
        cfg.update(kind="dense", layers=dense)
    cfg.update(output_size=out["units"], output_activation=out["activation"])
    order = ["model", "kind", "input_size", "hidden_size", "num_layers", "layers", "head", "output_size", "output_activation"]
    return {k: cfg[k] for k in order if k in cfg}


def validate_arch(cfg):
    """Returns a list of error strings (empty = valid)."""
    try:
        _arch().validate_config(cfg)
    except Exception as ex:  # ArchError or a missing arch.py
        return [str(ex)]
    return []


def list_branches(repo=None):
    rc, out = _git(repo or _code_dir(), "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return out.split() if rc == 0 and out else []


def worktree_of(repo, branch):
    """Path of the worktree that has `branch` checked out, else None."""
    rc, out = _git(repo, "worktree", "list", "--porcelain")
    path = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[9:]
        elif line.strip() == f"branch refs/heads/{branch}":
            return path
    return None


def running_runs(rows):
    return [r for r in rows if r.get("status") in ("starting", "running")]


def _flat(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _flat(v, f"{p}.{k}" if p else k)
    elif isinstance(x, list):
        yield (f"{p}#len", len(x))
        for i, v in enumerate(x):
            yield from _flat(v, f"{p}[{i}]")
    else:
        yield (p, x)


def summarize_cfg(old, new):
    if not old:
        return "new config"
    a, b = dict(_flat(old)), dict(_flat(new))
    ch = [f"{k} {a.get(k, '∅')}→{b.get(k, '∅')}" for k in b if a.get(k) != b[k] and not k.endswith("#len")]
    ch += [f"{k} removed" for k in a if k not in b and not k.endswith("#len")]
    ch += [f"{k[:-4]} {a.get(k, 0)}→{b[k]}" for k in b if k.endswith("#len") and a.get(k, 0) != b[k]]
    return "; ".join(ch[:4]) + (f" (+{len(ch) - 4} more)" if len(ch) > 4 else "") if ch else "no change"


def plan_apply(edited, branch=None, new_branch=None, base=None, repo=None, running=()):
    """Everything the confirm step shows: diff, summary, commit message, errors (block) and warnings. Writes nothing."""
    repo = repo or _code_dir()
    plan = {"ok": False, "errors": [], "warnings": [], "diff": "", "summary": "", "message": "", "target": None,
            "create": bool(new_branch), "source": None, "rel": None, "new_text": "", "model": edited["id"], "worktree": None}
    err = plan["errors"]
    name = edited.get("config_name")
    if not name:
        err.append("Αυτό το μοντέλο δεν έχει αρχείο αρχιτεκτονικής στον κώδικα (μόνο derp, dinos, dinos_t).")
        return plan
    try:
        cfg = arch_config(edited)
    except ModelsError as ex:
        err.append(str(ex)); return plan
    err += validate_arch(cfg)
    if os.path.realpath(repo) != os.path.realpath(_code_dir()) or not os.path.isdir(repo):
        err.append("Επιτρέπεται μόνο το ~/qrl-lab/code.")
    branches = list_branches(repo)
    if new_branch:
        rc, _ = _git(repo, "check-ref-format", "--branch", new_branch)
        if rc or not new_branch.strip():
            err.append(f"Μη έγκυρο όνομα branch: {new_branch!r}")
        elif new_branch in branches:
            err.append(f"Το branch {new_branch} υπάρχει ήδη.")
        if base not in branches:
            err.append("Διάλεξε branch βάσης για το νέο branch.")
        plan["target"], plan["source"] = new_branch, base
    else:
        if branch not in branches:
            err.append("Διάλεξε υπάρχον branch.")
        plan["target"], plan["source"] = branch, branch
    if err:
        return plan
    rel = CONFIG_REL.format(name)
    plan["rel"] = rel
    rc, old_text = _git(repo, "show", f"{plan['source']}:{rel}")
    old_text = old_text + "\n" if rc == 0 else ""
    new_text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    plan["new_text"] = new_text
    old_cfg = None
    if old_text:
        try:
            old_cfg = json.loads(old_text)
        except ValueError:
            old_cfg = None
    plan["summary"] = summarize_cfg(old_cfg, cfg)
    plan["diff"] = "".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True),
                                                f"a/{rel}", f"b/{rel}"))
    if old_text == new_text:
        err.append("Καμία αλλαγή σε σχέση με το περιεχόμενο του branch.")
    wt = None if new_branch else worktree_of(repo, plan["target"])
    plan["worktree"] = wt
    run_ids = [r.get("run_id", "?") for r in running]
    if wt:
        rc, dirty = _git(wt, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            err.append(f"Το worktree {wt} (branch {plan['target']}) έχει μη committed αλλαγές· δεν γράφω εκεί. "
                       "Φτιάξε νέο branch (δεν αγγίζει το worktree) ή κάνε commit/stash πρώτα.")
        if run_ids:
            err.append(f"Τρέχουν πειράματα ({', '.join(run_ids[:5])}) και το branch {plan['target']} είναι αυτό που έχει checkout στο worktree τους.")
    elif run_ids:
        plan["warnings"].append(f"Τρέχουν πειράματα ({', '.join(run_ids[:5])}). Το commit γίνεται με git plumbing στο branch "
                                f"{plan['target']} και δεν αγγίζει το worktree/αρχεία που χρησιμοποιούν.")
    plan["warnings"].append("Τα εγκεκριμένα/παγωμένα specs καρφώνουν αρχεία και commit (freeze.py): το αρχείο δεν συνδέεται "
                            "ακόμα με τους agents, άρα δεν αλλάζει κανένα τρέχον ή παγωμένο πείραμα.")
    plan["message"] = f"Model edit from dashboard: {edited['id']} {plan['summary']}\n\n{TRAILERS}"
    plan["ok"] = not err
    return plan


def apply_commit(plan, repo=None):
    """Commit `plan` (from plan_apply, after the researcher's confirm click). Returns the new commit sha."""
    import tempfile
    repo = repo or _code_dir()
    if not plan.get("ok"):
        raise ModelsError("το σχέδιο έχει σφάλματα: " + "; ".join(plan.get("errors", [])))
    if os.path.realpath(repo) != os.path.realpath(_code_dir()):
        raise ModelsError("επιτρέπεται μόνο το ~/qrl-lab/code")
    tgt, rel, msg = plan["target"], plan["rel"], plan["message"]
    wt = plan.get("worktree")
    if wt:   # branch checked out in a worktree: it was verified clean; commit only our path
        p = os.path.join(wt, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(plan["new_text"])
        for args in (("add", "--", rel), ("commit", "-q", "-m", msg, "--", rel)):
            rc, out = _git(wt, *args)
            if rc:
                raise ModelsError(f"git {args[0]} απέτυχε: {out}")
        return _git(wt, "rev-parse", "HEAD")[1]
    rc, parent = _git(repo, "rev-parse", f"refs/heads/{plan['source']}")
    if rc:
        raise ModelsError(f"άγνωστο branch {plan['source']}")
    tmp = tempfile.mkdtemp(prefix="qrl-idx-")
    env = {"GIT_INDEX_FILE": os.path.join(tmp, "index")}
    try:
        steps = []
        rc, out = _git(repo, "read-tree", parent, env=env); steps.append(out)
        if rc:
            raise ModelsError(f"read-tree: {out}")
        rc, blob = _git(repo, "hash-object", "-w", "--stdin", inp=plan["new_text"])
        if rc:
            raise ModelsError(f"hash-object: {blob}")
        rc, out = _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{plan['rel']}", env=env)
        if rc:
            raise ModelsError(f"update-index: {out}")
        rc, tree = _git(repo, "write-tree", env=env)
        if rc:
            raise ModelsError(f"write-tree: {tree}")
        rc, commit = _git(repo, "commit-tree", tree, "-p", parent, "-m", msg)
        if rc:
            raise ModelsError(f"commit-tree: {commit}")
        old = ZERO if plan["create"] else parent
        rc, out = _git(repo, "update-ref", "-m", "model edit from dashboard", f"refs/heads/{tgt}", commit, old)
        if rc:
            raise ModelsError(f"update-ref: {out}")
        return commit
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
