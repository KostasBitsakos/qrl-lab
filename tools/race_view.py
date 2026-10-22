#!/usr/bin/env python3
"""Task labels and the 80s «race view» for the dashboard Agents tab. Pure functions, no Streamlit, no I/O except
`load_events`. The race is one self-contained HTML/CSS/SVG document (rendered with st.components.v1.html);
only the pixel font comes from Google Fonts, with a monospace fallback, and there is no JavaScript at all
(swerving and obstacle dodging are pure CSS keyframes; activity and trouble are derived in Python from the logs).
"""
import html
import re
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_log import PREFIX as PREFIX_RE, STOPWORDS, clean_label, task_word  # noqa: E402
import agent_models  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Typical duration (seconds) per role, used only to place a car; roles not listed run a looping animation.
# These are rough display defaults, not measurements.
TYPICAL_SECONDS = {"engineer": 600, "scholar": 300, "Explore": 90, "runner": 300, "writer": 420,
                   "codex-quick": 60, "codex-reviewer": 240, "codex-researcher": 300, "codex-architect": 400,
                   "codex-deputy": 120, "codex-engineer": 600, "codex:codex-rescue": 240}
GAP_SECONDS = 300  # coordinator actions further apart than this belong to different tasks
LOOKBACK = 120     # the coordinator's Agent-tool call precedes the SubagentStart by at most this long
DEFAULT_COLOR = "#898781"


def load_events(path, max_lines=6000):
    """Raw event dicts from events.jsonl (tail only); bad lines skipped."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 3_000_000))
            lines = f.read().decode("utf-8", "ignore").splitlines()[-max_lines:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def _atype(e):
    return e.get("agent_type") or ""


def annotate(events):
    """-> list of (label, group) parallel to `events`.

    Subagent events get the label of their SubagentStart: explicit `label`, else the first meaningful word of
    `task`/`summary`, else of the coordinator's matching Agent-tool call just before the start (type: description),
    else the role. Coordinator actions are grouped by time gaps; the group's label is the first meaningful word
    of its summaries. Dots with the same group share one label.
    """
    n = len(events)
    res = [("", "")] * n
    start_label = {}
    used = set()
    for i, e in enumerate(events):
        if e.get("hook_event_name") != "SubagentStart" or not e.get("agent_id"):
            continue
        lab = clean_label(e.get("label")) or task_word(e.get("task") or e.get("summary"))
        if not lab:
            ts, at = float(e.get("ts", 0)), _atype(e)
            for j in range(i - 1, -1, -1):
                f = events[j]
                if ts - float(f.get("ts", 0)) > LOOKBACK:
                    break
                s = str(f.get("summary") or "")
                if (j not in used and f.get("hook_event_name") == "PreToolUse" and not f.get("agent_id")
                        and at and s.startswith(at + ":")):
                    lab = task_word(s)
                    used.add(j)
                    break
        start_label[e["agent_id"]] = lab or task_word(_atype(e).split(":")[-1])[:LABEL_FALLBACK]
    prev_ts, gid, glabel = None, 0, {}
    for i, e in enumerate(events):
        aid = e.get("agent_id")
        if aid:
            res[i] = (start_label.get(aid, ""), aid)
        elif e.get("hook_event_name") in ("PreToolUse", "PostToolUse"):
            ts = float(e.get("ts", 0))
            if prev_ts is None or ts - prev_ts > GAP_SECONDS:
                gid += 1
            prev_ts = ts
            if not glabel.get(gid) and e.get("hook_event_name") == "PreToolUse" and e.get("tool_name") not in ("Agent", "Task"):
                glabel[gid] = task_word(e.get("summary"))  # delegations are labelled on the subagent's own dots
            res[i] = (glabel.get(gid, ""), f"coord-{gid}")
    # a coordinator group may learn its label after its first dot: fill in
    for i, (lab, g) in enumerate(res):
        if g.startswith("coord-") and not lab:
            res[i] = (glabel.get(int(g[6:]), ""), g)
    return res


LABEL_FALLBACK = 14


RECENT = 120          # seconds: tool events newer than this count as "recent activity"
SLOW_FACTOR = 2.0     # a task this much longer than its role's median finished duration counts as slow
SLOW_MIN_SAMPLES = 3
RETRY_WINDOW = 1800   # seconds
HEALTH_GREEK = {"limit": "όριο χρήσης", "down": "ο συντονιστής δεν τρέχει", "permission": "περιμένει άδεια",
                "api_error": "σφάλμα API"}


def load_health(path):
    """health.json -> {"claude": state dict, "codex": state dict}; missing/bad file -> {}."""
    try:
        with open(path, encoding="utf-8") as f:
            h = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(h, dict):
        return {}
    cx = h.get("codex")
    return {"claude": {k: h.get(k) for k in ("state", "detail")}, "codex": cx if isinstance(cx, dict) else {}}


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return 0.0 if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def derive(runs, events, now, health=None):
    """Activity (0..1) and trouble for every run in `runs` (aid -> run dict with role/label/start/end/status).

    Adds to each run: activity, reasons (short Greek phrases), obstacles (0..3), final (True when failed).
    Activity uses only real data: tool events of the agent in the last RECENT seconds, how many runs of the same role
    are active at once, and (for roles without tool events, i.e. the Codex log) the fact that it is running.
    Trouble: status failed, repeated start of the same role+label before it, much longer than the role's median,
    and the usage-limit / health state of Claude or Codex in `health`.
    """
    health = health or {}
    recent = {}
    for e in events:
        aid = e.get("agent_id")
        if aid in runs and e.get("hook_event_name") in ("PreToolUse", "PostToolUse") and now - float(e.get("ts", 0)) <= RECENT:
            recent[aid] = recent.get(aid, 0) + 1
    active_by_role = {}
    for r in runs.values():
        if r["end"] is None:
            active_by_role[r["role"]] = active_by_role.get(r["role"], 0) + 1
    durs = {}
    for r in runs.values():
        if r["end"] is not None and r["status"] == "done":
            durs.setdefault(r["role"], []).append(r["end"] - r["start"])
    seen = {}
    for aid, r in sorted(runs.items(), key=lambda kv: kv[1]["start"]):
        # a retry = same role re-started with the same task text, or the same label right after a failed run
        # with that label, within RETRY_WINDOW; distinct tasks that merely share a role are not retries
        prev = seen.get(r["role"], [])
        n = 0
        for p in reversed(prev):
            if r["start"] - p["start"] > RETRY_WINDOW:
                break
            same_task = bool(r.get("task")) and r.get("task") == p.get("task")
            same_fail = bool(r.get("label")) and r.get("label") == p.get("label") and p["status"] == "failed"
            if same_task or same_fail:
                n = p["_retry"] + 1
                break
        r["_retry"] = n
        seen.setdefault(r["role"], []).append(r)
    for aid, r in runs.items():
        running = r["end"] is None
        reasons = []
        if running:
            act = 0.25 + min(0.5, recent.get(aid, 0) / 20.0) + min(0.25, 0.125 * (active_by_role.get(r["role"], 1) - 1))
            r["activity"] = round(min(1.0, act), 3)
        else:
            r["activity"] = 0.0
        if r["status"] == "failed":
            reasons.append("απέτυχε")
        if r["_retry"]:
            reasons.append(f"επανάληψη ×{r['_retry']}")
        d = durs.get(r["role"], [])
        if running and len(d) >= SLOW_MIN_SAMPLES and (now - r["start"]) > SLOW_FACTOR * max(_median(d), 1.0):
            reasons.append("πολύ πιο αργός από το κανονικό")
        if running:
            side = "codex" if str(r["role"]).startswith("codex") else "claude"
            st = (health.get(side) or {}).get("state")
            if st and st != "ok":
                reasons.append(("Codex: " if side == "codex" else "Claude: ") + HEALTH_GREEK.get(st, str(st)))
        r["reasons"] = reasons
        r["final"] = r["status"] == "failed"
        r["obstacles"] = min(3, len(reasons)) if reasons else 0
        r.pop("_retry", None)


DESC_MAX = 24


def two_words(label, task="", role=""):
    """Short two-word description (verb + object): the explicit label if it has two words, else the first two
    meaningful words of the task text, else label + role."""
    lab = " ".join(str(label or "").split())
    if len(lab.split()) >= 2:
        return lab[:DESC_MAX]
    t = PREFIX_RE.sub("", str(task or ""), count=1)
    ws = [w for w in re.findall(r"[^\W\d_][\w\-]*", t) if len(w) > 1 and w.lower() not in STOPWORDS]
    if lab:
        ws = [w for w in ws if w.lower() != lab.lower()]
        ws = [lab] + ws[:1]
    words = ws[:2]
    if len(words) < 2:
        r = str(role or "").split(":")[-1].split("-")[-1]
        words = words + ([r] if r and r.lower() not in [w.lower() for w in words] else [])
    return " ".join(words)[:DESC_MAX]


def lanes(events, now=None, roles=None, window=6 * 3600, max_lanes=16, health=None, models=None, coord_model=None):
    """Race lanes: one per subagent run (plus the coordinator when it acted in the last 2 minutes).

    Active runs first, then the most recently finished. Each lane: dict(role, name, model, label, start, end,
    status ("running"|"done"|"failed"), elapsed, progress (0..1 or None for unknown), color).
    models: {agent_id: display text} (tools/agent_models.py) overrides the record's model; coord_model: the
    coordinator lane's model text.
    """
    now = time.time() if now is None else now
    identity = agent_models.coordinator_identity(events, health, now)
    roles = roles or {}
    ann = annotate(events)
    runs, order = {}, []
    for e, (lab, _) in zip(events, ann):
        aid = e.get("agent_id")
        if not aid:
            continue
        if e.get("hook_event_name") == "SubagentStart":
            runs[aid] = {"role": _atype(e), "model": (models or {}).get(aid) or e.get("model") or "", "label": lab,
                         "effort": e.get("effort") or "",
                         "start": float(e["ts"]),
                         "end": None, "status": "running",
                         "task": str(e.get("task") or e.get("summary") or "").strip()}
            order.append(aid)
        elif e.get("hook_event_name") == "SubagentStop" and aid in runs:
            runs[aid]["end"] = float(e["ts"])
            runs[aid]["status"] = "failed" if e.get("status") == "failed" else "done"
    derive(runs, events, now, health)
    out = []
    for aid in order:
        r = runs[aid]
        if r["end"] is None and now - r["start"] > 3 * 3600:  # lost stop event: do not keep a ghost car forever
            continue
        if now - (r["end"] or now) > window:
            continue
        out.append(dict(r))
    out.sort(key=lambda r: (r["status"] != "running", -(r["end"] or r["start"])))
    out = out[:max_lanes]
    coord = [(e, a) for e, a in zip(events, ann) if not e.get("agent_id") and e.get("hook_event_name") in ("PreToolUse", "PostToolUse")]
    n_rec = sum(1 for e, _ in coord if now - float(e["ts"]) <= RECENT)
    last = float(coord[-1][0]["ts"]) if coord else now
    busy = n_rec > 0
    side = "codex" if identity["provider"] == "Codex" else "claude"
    cstate = ((health or {}).get(side) or {}).get("state")
    # live two-word description from the coordinator's latest action summary (e.g. "Launch W0", "Fix toggle")
    ctask = next((str(e.get("summary") or "") for e, _ in reversed(coord)
                  if e.get("hook_event_name") == "PreToolUse" and e.get("tool_name") not in ("Agent", "Task")
                  and e.get("summary")), "")
    if identity["role"] == "codex-deputy":
        # The deputy occupies the coordinator lane, rather than appearing twice as a worker and a coordinator.
        out = [r for r in out if not (r["role"] == "codex-deputy" and r["start"] == identity["ts"])]
        busy, last, ctask = identity["active"], identity["ts"], identity["task"]
        n_rec = 1 if busy else 0
    elif not identity["active"]:
        busy = False
    out.insert(0, {"role": "coordinator", "coordinator_role": identity["role"], "provider": identity["provider"],
                   "model": identity["model"] or (coord_model if identity["provider"] == "Claude" else "") or "",
                   "effort": identity["effort"], "label": "", "task": ctask, "start": last,
                   "end": None if busy else last, "status": "running" if busy else "idle", "coord": True,
                   "activity": min(1.0, 0.25 + 0.75 * min(1.0, n_rec / 20.0)) if busy else 0.0,
                   "reasons": [identity["provider"] + ": " + HEALTH_GREEK[cstate]] if busy and cstate in HEALTH_GREEK else [], "final": False})
    out[0]["obstacles"] = len(out[0]["reasons"])
    for r in out:
        name, color = (roles.get(r["role"]) or (r["role"] or "agent", DEFAULT_COLOR))[:2]
        if r.get("coord"):
            card = identity["card"]
            if not identity["model"] and identity["provider"] == "Claude" and coord_model:
                card = f"🧭 Πάρις (Claude) · μοντέλο {coord_model}"
            name, color = card, (roles.get("coordinator") or ("", "#ff2a6d"))[1]
        r["name"], r["color"] = name, color
        r["desc"] = two_words(r.get("label"), r.get("task"), "" if r.get("coord") else r["role"])
        end = r["end"] or now
        r["elapsed"] = max(0.0, end - r["start"]) if not (r.get("coord") and r["status"] == "idle") else 0.0
        typ = TYPICAL_SECONDS.get(r["role"])
        r["progress"] = None if (typ is None or r.get("coord")) else (
            1.0 if r["end"] else min(0.9, r["elapsed"] / typ))
    return out


CAR = ('<svg class="car" viewBox="0 0 24 12" width="48" height="24" shape-rendering="crispEdges" aria-hidden="true">'
       '<rect x="2" y="4" width="20" height="5" fill="{c}"/><rect x="6" y="1" width="10" height="3" fill="{c}"/>'
       '<rect x="8" y="2" width="3" height="2" fill="#9ff"/><rect x="12" y="2" width="3" height="2" fill="#9ff"/>'
       '<rect x="2" y="7" width="20" height="1" fill="#000" opacity=".25"/>'
       '<rect x="4" y="9" width="4" height="3" fill="#111"/><rect x="16" y="9" width="4" height="3" fill="#111"/>'
       '<rect x="21" y="5" width="2" height="2" fill="#ff0"/><rect x="1" y="5" width="1" height="2" fill="#f33"/></svg>')

CONE = ('<svg class="obs" viewBox="0 0 12 12" width="18" height="18" shape-rendering="crispEdges" aria-hidden="true">'
        '<rect x="5" y="1" width="2" height="2" fill="#ff7a00"/><rect x="4" y="3" width="4" height="2" fill="#ff7a00"/>'
        '<rect x="4" y="4" width="4" height="1" fill="#fff"/><rect x="3" y="5" width="6" height="3" fill="#ff7a00"/>'
        '<rect x="3" y="6" width="6" height="1" fill="#fff"/><rect x="1" y="8" width="10" height="2" fill="#333"/></svg>')
ROCK = ('<svg class="obs" viewBox="0 0 12 12" width="18" height="18" shape-rendering="crispEdges" aria-hidden="true">'
        '<rect x="4" y="2" width="4" height="1" fill="#9a9a9a"/><rect x="2" y="3" width="8" height="2" fill="#8a8a8a"/>'
        '<rect x="1" y="5" width="10" height="4" fill="#6f6f6f"/><rect x="3" y="4" width="2" height="1" fill="#c8c8c8"/>'
        '<rect x="1" y="9" width="10" height="1" fill="#333"/></svg>')

CSS = """
*{box-sizing:border-box}html,body{margin:0;background:#0b0221}
body{font-family:'Press Start 2P',ui-monospace,'Courier New',monospace;color:#05d9e8;font-size:9px;line-height:1.5}
.screen{position:relative;padding:10px;border:3px solid #ff2a6d;box-shadow:0 0 12px #ff2a6d,inset 0 0 18px #3a0a5e;
 background:linear-gradient(#0b0221,#1a0a3a);overflow:hidden}
.screen:after{content:"";position:absolute;inset:0;pointer-events:none;
 background:repeating-linear-gradient(0deg,rgba(0,0,0,.28) 0,rgba(0,0,0,.28) 1px,transparent 1px,transparent 3px)}
h1{margin:0 0 8px;font-size:12px;color:#fffb96;text-shadow:0 0 6px #ff2a6d,2px 2px 0 #ff2a6d;letter-spacing:1px}
.sub{color:#d1f7ff;margin-bottom:8px;font-size:9px}
.road{display:flex;width:100%;overflow-x:auto;border:2px solid #05d9e8;background:#14082e}
.lane{container-type:inline-size;overflow:hidden;flex:1 1 0;min-width:56px;border-right:2px dashed #fffb96aa;display:flex;flex-direction:column}
.lane:last-child{border-right:0}
.hd{padding:4px 3px;text-align:center;min-height:46px;font-size:8px;overflow-wrap:anywhere}
.why{display:block;color:#ffb347;font-size:7px;margin-top:2px;line-height:1.3}
.role{display:block;color:#d1f7ff}.st{display:block;white-space:nowrap;margin-top:2px}
.track{position:relative;height:var(--h,300px);margin:0 auto;width:100%;overflow:hidden}
.dim{opacity:.5;filter:grayscale(.6)}
.track.moving{background:repeating-linear-gradient(180deg,transparent 0,transparent 24px,#fffb9655 24px,#fffb9655 40px) 50% 0/4px 40px repeat-y;
 animation:scroll var(--sp,1.2s) linear infinite}
@keyframes scroll{from{background-position:50% 0}to{background-position:50% 40px}}
.finish{position:absolute;left:0;right:0;top:0;height:18px;
 background:repeating-conic-gradient(#fff 0 25%,#000 0 50%) 0 0/10px 10px;border-bottom:2px solid #fff}
.runner{position:absolute;left:0;right:0;display:flex;flex-direction:column;align-items:center;gap:2px}
.runner .w{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden;
 width:100%;max-width:100%;padding:1px 2px;text-align:center;color:#fff;background:rgba(11,2,33,.78);
 border-radius:2px;font-size:clamp(5px,12cqw,8px);line-height:1.25;overflow-wrap:anywhere;word-break:break-word;
 text-overflow:ellipsis}
.car{transform:rotate(-90deg);margin:12px 0}
.run{animation:bob .35s steps(2) infinite}
.loop{animation:loop var(--lp,5s) linear infinite,bob .35s steps(2) infinite}
.parked{top:22px}.crash{top:48px}
.sw,.dg{display:flex;flex-direction:column;align-items:center;gap:2px;width:100%}
.swerve{animation:sway var(--d,2s) steps(8) infinite alternate}
.dodgeL{animation:dodgeL 3.2s steps(10) infinite}.dodgeR{animation:dodgeR 3.2s steps(10) infinite}
.ob{position:absolute;left:50%;margin-left:-9px;width:18px;height:18px;animation:pass 3.2s steps(16) infinite}
.stuck{animation:none;position:absolute;left:50%;margin-left:-9px;bottom:100%}
.boom{position:absolute;right:4px;top:-4px;font-size:14px}
@keyframes sway{from{transform:translateX(calc(var(--a,0) * -1%))}to{transform:translateX(calc(var(--a,0) * 1%))}}
@keyframes dodgeL{0%,8%{transform:none}22%,58%{transform:translateX(-26%)}72%,100%{transform:none}}
@keyframes dodgeR{0%,8%{transform:none}22%,58%{transform:translateX(26%)}72%,100%{transform:none}}
@keyframes pass{from{transform:translateY(0)}to{transform:translateY(105px)}}
@keyframes bob{50%{margin-left:1px}}
@keyframes loop{from{bottom:0}to{bottom:calc(100% - 100px)}}
.ok{color:#39ff14}.bad{color:#ff3860}.go{color:#fffb96}
@media (prefers-reduced-motion:reduce){.run,.loop,.swerve,.track.moving,.dodgeL,.dodgeR,.ob{animation:none}}
"""


def _clock(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def render(lane_list, now=None):
    """The complete HTML document for st.components.v1.html. All dynamic text is escaped.

    A vertical road: one lane (column) per agent side by side, cars drive upward to the finish line.
    The road is as wide as the iframe; every lane keeps at least 56px (horizontal scroll beyond that).
    """
    esc = html.escape
    active = sum(1 for r in lane_list if r["status"] == "running")
    cap = "" if active else '<div class="sub">Κανένας πράκτορας δεν δουλεύει αυτή τη στιγμή</div>'
    parts = [f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">'
             f'<style>{CSS}</style></head><body><div class="screen" id="race">'
             f'<h1>🏁 QRL GRAND PRIX</h1><div class="sub">{active} στην πίστα · {len(lane_list) - active} τερμάτισαν</div>{cap}']
    if not lane_list:
        parts.append('<div class="sub">Η πίστα είναι άδεια. Κανένας πράκτορας δεν τρέχει.</div>')
    else:
        parts.append(f'<div class="road" style="--h:{TRACK_H}px">')
    for idx, r in enumerate(lane_list):
        color = r["color"] if str(r.get("color", "")).startswith("#") and len(r["color"]) in (4, 7) else DEFAULT_COLOR
        display_name = r["name"] if r.get("coord") else r["name"].split(" · ")[0]
        who = esc(display_name if (not r["model"] or r.get("coord")) else f'{display_name} · {r["model"]}'
                  + (f" · {r['effort']}" if r.get("effort") else ""))
        word = esc(r.get("desc") or r.get("label") or "")
        reasons = r.get("reasons") or []
        why = esc(" · ".join(reasons))
        n_ob = int(r.get("obstacles") or 0)
        act = float(r.get("activity") or 0.0)
        road_cls, road_sty, dim = "", "", ""
        if r["status"] == "running":
            st_html = f'<span class="go">▶ {_clock(r["elapsed"])}</span>'
            inner = f'{CAR.format(c=color)}<span class="w">{word}</span>'
            dg = f'<div class="dg {"dodgeL" if idx % 2 == 0 else "dodgeR"}">{inner}</div>' if n_ob else f'<div class="dg">{inner}</div>'
            sw = f'<div class="sw swerve" style="--a:{3 + 25 * act:.1f};--d:{2.6 - 1.8 * act:.2f}s">{dg}</div>'
            road_cls = " moving"
            road_sty = f' style="--sp:{1.6 - 1.1 * act:.2f}s"'
            obs = "".join(f'<div class="ob" style="bottom:calc(100% + {14 * i}px)">{ROCK if (idx + i) % 2 else CONE}</div>'
                          for i in range(n_ob))
            if r["progress"] is None:
                lp = 5 + 5 * (1 - act)
                run = f'<div class="runner loop" style="bottom:0;--lp:{lp:.1f}s">{obs}{sw}</div>'
            else:
                run = (f'<div class="runner run" style="bottom:calc((100% - 100px) * {r["progress"]:.3f})">'
                       f'{obs}{sw}</div>')
        elif r["status"] == "idle":
            dim = " dim"
            st_html = '<span>zzz</span>'
            run = f'<div class="runner parked">{CAR.format(c=color)}<span class="w">{word}</span></div>'
        else:
            dim = " dim"
            good = r["status"] == "done"
            mark = '<span class="ok">✓</span>' if good else '<span class="bad">✗</span>'
            st_html = f'{mark} {_clock(r["elapsed"])}'
            if r.get("final"):  # final failure: stopped at an obstacle
                run = (f'<div class="runner crash"><div class="stuck">{ROCK if idx % 2 else CONE}</div>'
                       f'{CAR.format(c=color)}<span class="boom">💥</span><span class="w">{word} {mark}</span></div>')
            else:
                run = f'<div class="runner parked">{CAR.format(c=color)}<span class="w">{word} {mark}</span></div>'
        why_html = f'<span class="why">⚠ {why}</span>' if why else ""
        parts.append(f'<div class="lane{dim}" title="{why}"><div class="hd"><span class="role" style="color:{color}">{who}</span>'
                     f'<span class="st">{st_html}</span>{why_html}</div><div class="track{road_cls}"{road_sty}>'
                     f'<div class="finish"></div>{run}</div></div>')
    if lane_list:
        parts.append('</div>')
    parts.append("</div></body></html>")
    return "".join(parts)


TRACK_H = 300


def height_for(n):
    return 110 + TRACK_H + 20
