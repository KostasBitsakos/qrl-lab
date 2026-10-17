#!/usr/bin/env python3
"""Task labels and the 80s «race view» for the dashboard Agents tab. Pure functions, no Streamlit, no I/O except
`load_events`. The race is one self-contained HTML/CSS/SVG document (rendered with st.components.v1.html);
only the pixel font comes from Google Fonts, with a monospace fallback, and there is no JavaScript at all.
"""
import html
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_log import clean_label, task_word  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Typical duration (seconds) per role, used only to place a car; roles not listed run a looping animation.
# These are rough display defaults, not measurements.
TYPICAL_SECONDS = {"engineer": 600, "scholar": 300, "Explore": 90, "runner": 300, "writer": 420,
                   "codex-quick": 60, "codex-reviewer": 240, "codex-researcher": 300, "codex-architect": 400,
                   "codex-deputy": 120, "codex:codex-rescue": 240}
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


def lanes(events, now=None, roles=None, window=6 * 3600, max_lanes=10):
    """Race lanes: one per subagent run (plus the coordinator when it acted in the last 2 minutes).

    Active runs first, then the most recently finished. Each lane: dict(role, name, model, label, start, end,
    status ("running"|"done"|"failed"), elapsed, progress (0..1 or None for unknown), color).
    """
    now = time.time() if now is None else now
    roles = roles or {}
    ann = annotate(events)
    runs, order = {}, []
    for e, (lab, _) in zip(events, ann):
        aid = e.get("agent_id")
        if not aid:
            continue
        if e.get("hook_event_name") == "SubagentStart":
            runs[aid] = {"role": _atype(e), "model": e.get("model") or "", "label": lab, "start": float(e["ts"]),
                         "end": None, "status": "running"}
            order.append(aid)
        elif e.get("hook_event_name") == "SubagentStop" and aid in runs:
            runs[aid]["end"] = float(e["ts"])
            runs[aid]["status"] = "failed" if e.get("status") == "failed" else "done"
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
    coord = [(e, a) for e, a in zip(events, ann) if not e.get("agent_id") and e.get("hook_event_name") == "PreToolUse"]
    if coord and now - float(coord[-1][0]["ts"]) < 120 and len(out) < max_lanes:
        out.insert(0, {"role": "coordinator", "model": "", "label": coord[-1][1][0],
                       "start": float(coord[-1][0]["ts"]), "end": None, "status": "running", "coord": True})
    for r in out:
        name, color = (roles.get(r["role"]) or (r["role"] or "agent", DEFAULT_COLOR))[:2]
        r["name"], r["color"] = name, color
        end = r["end"] or now
        r["elapsed"] = max(0.0, end - r["start"])
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

CSS = """
*{box-sizing:border-box}html,body{margin:0;background:#0b0221}
body{font-family:'Press Start 2P',ui-monospace,'Courier New',monospace;color:#05d9e8;font-size:10px;line-height:1.5}
.screen{position:relative;padding:10px;border:3px solid #ff2a6d;box-shadow:0 0 12px #ff2a6d,inset 0 0 18px #3a0a5e;
 background:linear-gradient(#0b0221,#1a0a3a);overflow:hidden}
.screen:after{content:"";position:absolute;inset:0;pointer-events:none;
 background:repeating-linear-gradient(0deg,rgba(0,0,0,.28) 0,rgba(0,0,0,.28) 1px,transparent 1px,transparent 3px)}
h1{margin:0 0 8px;font-size:12px;color:#fffb96;text-shadow:0 0 6px #ff2a6d,2px 2px 0 #ff2a6d;letter-spacing:1px}
.sub{color:#d1f7ff;margin-bottom:8px;font-size:9px}
.lane{margin-bottom:8px}.hd{display:flex;justify-content:space-between;gap:6px;flex-wrap:wrap;margin-bottom:2px;font-size:9px}
.role{color:#d1f7ff;overflow-wrap:anywhere}.st{white-space:nowrap}
.track{position:relative;height:30px;background:#14082e;border-top:2px solid #05d9e8;border-bottom:2px solid #05d9e8}
.track:before{content:"";position:absolute;left:0;right:34px;top:13px;height:2px;
 background:repeating-linear-gradient(90deg,#fffb96 0 8px,transparent 8px 16px);opacity:.55}
.finish{position:absolute;right:0;top:0;bottom:0;width:30px;
 background:repeating-conic-gradient(#fff 0 25%,#000 0 50%) 0 0/10px 10px;border-left:2px solid #fff}
.finish span{position:absolute;left:-1px;top:50%;transform:translateY(-50%);font-size:11px;background:#000;padding:0 2px}
.runner{position:absolute;top:2px;display:flex;align-items:center;gap:4px;white-space:nowrap}
.runner .w{color:#fff;text-shadow:0 0 4px currentColor;font-size:9px}
.run{animation:bob .35s steps(2) infinite}
.loop{animation:loop 5s linear infinite,bob .35s steps(2) infinite}
.parked{right:34px}
@keyframes bob{50%{transform:translateY(1px)}}
@keyframes loop{from{left:0}to{left:calc(100% - 200px)}}
.ok{color:#39ff14}.bad{color:#ff3860}.go{color:#fffb96}
@media (max-width:420px){body{font-size:8px}.hd,.sub,.runner .w{font-size:8px}}
@media (prefers-reduced-motion:reduce){.run,.loop{animation:none}}
"""


def _clock(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def render(lane_list, now=None):
    """The complete HTML document for st.components.v1.html. All dynamic text is escaped."""
    esc = html.escape
    active = sum(1 for r in lane_list if r["status"] == "running")
    parts = [f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">'
             f'<style>{CSS}</style></head><body><div class="screen" id="race">'
             f'<h1>🏁 QRL GRAND PRIX</h1><div class="sub">{active} στην πίστα · {len(lane_list) - active} τερμάτισαν</div>']
    if not lane_list:
        parts.append('<div class="sub">Η πίστα είναι άδεια. Κανένας πράκτορας δεν τρέχει.</div>')
    for r in lane_list:
        color = r["color"] if str(r.get("color", "")).startswith("#") and len(r["color"]) in (4, 7) else DEFAULT_COLOR
        who = esc(r["name"] if not r["model"] else f'{r["name"].split(" · ")[0]} · {r["model"]}')
        word = esc(r.get("label") or "")
        if r["status"] == "running":
            st_html = f'<span class="go">▶ {_clock(r["elapsed"])}</span>'
            if r["progress"] is None:
                run = f'<div class="runner loop" style="left:0">{CAR.format(c=color)}<span class="w">{word}</span></div>'
            else:
                run = (f'<div class="runner run" style="left:calc((100% - 200px) * {r["progress"]:.3f})">'
                       f'{CAR.format(c=color)}<span class="w">{word}</span></div>')
        else:
            good = r["status"] == "done"
            mark = '<span class="ok">✓</span>' if good else '<span class="bad">✗</span>'
            st_html = f'{mark} {_clock(r["elapsed"])}'
            run = f'<div class="runner parked">{CAR.format(c=color)}<span class="w">{word} {mark}</span></div>'
        parts.append(f'<div class="lane"><div class="hd"><span class="role" style="color:{color}">{who}</span>'
                     f'<span class="st">{st_html}</span></div><div class="track">{run}'
                     f'<div class="finish"><span>🏁</span></div></div></div>')
    parts.append("</div></body></html>")
    return "".join(parts)


def height_for(n):
    return 90 + 62 * max(1, n)
