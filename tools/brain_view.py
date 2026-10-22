#!/usr/bin/env python3
"""Sidebar «brain» of the dashboard: one neuron per agent role, edges to the coordinator, pulses on real messages.

Pure functions, no Streamlit, no I/O. Inputs are raw event dicts (.lab/events.jsonl, incl. agent_log.py start/end
entries) and labdb message dicts. Nothing is simulated: a neuron glows only if the logs show that role running, and an
edge pulses only when a log line shows a start / stop / post at that moment.

  derive(events, messages, now) -> {"nodes": {role: {"active": bool}}, "pulses": [{"src","dst","age","kind"}]}
  render(state)                 -> self-contained HTML (inline SVG + CSS animation, no JavaScript)

The HTML contains no wall-clock value: with no pulse running and an unchanged active set it is byte-identical between
two renders, so st.components.v1.html (inside a fragment) keeps the same iframe and nothing flickers. A running
pulse is rendered with a negative animation-delay equal to its age, so it continues smoothly after a re-render.
"""
import datetime as dt
import html
import json
import agent_models

COORD = "coordinator"
ACTIVE_TOOL_S = 25     # a tool event this recent keeps a role active even without a start/stop pair
COORD_ACTIVE_S = 40
OPEN_MAX_S = 2 * 3600  # a start without a stop older than this is treated as lost, not running
PULSE_S = 6.0          # an edge stays lit this long; the travelling dot takes TRAVEL_S of it
TRAVEL_S = 3.0

# role -> (label, colour, x, y); x/y are legacy and unused: the real positions are mesh vertices (see NODE_PT).
ROLES = {
    COORD: ("Πάρις", "#1d4ed8", 150, 135),
    "writer": ("writer", "#7c3aed", 105, 45),
    "engineer": ("engineer", "#db2777", 55, 85),
    "runner": ("runner", "#d97706", 40, 140),
    "Explore": ("Explore", "#059669", 60, 195),
    "scholar": ("scholar", "#15803d", 105, 232),
    "codex-quick": ("codex-quick", "#0891b2", 195, 45),
    "codex-reviewer": ("codex-reviewer", "#dc2626", 245, 85),
    "codex-researcher": ("codex-researcher", "#92400e", 258, 140),
    "codex-architect": ("codex-architect", "#4338ca", 240, 195),
    "codex-deputy": ("codex-deputy", "#a21caf", 195, 232),
    "codex-engineer": ("codex-engineer", "#0e7490", 195, 210),
}
WORKERS = [r for r in ROLES if r != COORD]
DEPUTY_MARKERS = ("αναπληρωτ", "deputy")


def _role(agent_type):
    """Known role of an agent_type string, else None (e.g. the bare 'codex:codex-rescue' plugin agent: its role is
    carried by the agent_log start/end entries around the call, so the raw plugin agent is ignored)."""
    return agent_type if agent_type in ROLES and agent_type != COORD else None


def _msg_ts(m):
    try:
        t = dt.datetime.fromisoformat(str(m.get("ts")))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def derive(events, messages=(), now=0.0, health=None):
    identity = agent_models.coordinator_identity(events, health, now)
    nodes = {r: {"active": False} for r in ROLES}
    pulses = []
    open_ = {}   # agent_id -> (role, start ts)
    id_role = {}
    last_tool = {}
    last_codex_role = None

    def pulse(src, dst, ts, kind):
        age = now - ts
        if 0 <= age < PULSE_S:
            pulses.append({"src": src, "dst": dst, "age": round(age, 2), "kind": kind})

    for e in sorted((e for e in events if isinstance(e, dict)), key=lambda e: e.get("ts") or 0):
        ts = e.get("ts") or 0
        if ts > now:
            continue
        name, aid = e.get("hook_event_name"), e.get("agent_id")
        if name == "SubagentStart":
            role = _role(e.get("agent_type"))
            if role:
                id_role[aid] = role
                open_[aid] = (role, ts)
                pulse(COORD, role, ts, "spawn")
                if role.startswith("codex"):
                    last_codex_role = role
        elif name == "SubagentStop":
            role = id_role.get(aid)
            if role:
                open_.pop(aid, None)
                pulse(role, COORD, ts, "report")
        elif name in ("PreToolUse", "PostToolUse"):
            role = _role(e.get("agent_type")) if aid else COORD
            if role is None and aid:
                role = id_role.get(aid)
            if role:
                last_tool[role] = ts
        elif name == "Stop" and not aid:
            last_tool[COORD] = max(last_tool.get(COORD, 0), ts)
    for role, ts in open_.values():
        if now - ts < OPEN_MAX_S:
            nodes[role]["active"] = True
    for role, ts in last_tool.items():
        if now - ts < (COORD_ACTIVE_S if role == COORD else ACTIVE_TOOL_S):
            nodes[role]["active"] = True
    # labdb posts: a Codex post comes from a codex role to the coordinator (deputy when the text says so).
    for m in messages or ():
        ts = _msg_ts(m)
        if ts is None or not 0 <= now - ts < PULSE_S:
            continue
        author = m.get("author") or ""
        if author == COORD:
            nodes[COORD]["active"] = True
        elif author.startswith("codex"):
            text = f"{m.get('title') or ''} {m.get('body') or ''}".lower()[:400]
            role = author if author in ROLES else ("codex-deputy" if any(k in text for k in DEPUTY_MARKERS)
                                                   else last_codex_role)
            if role:
                nodes[role]["active"] = True
                pulse(role, COORD, ts, "post")
    pulses.sort(key=lambda p: p["age"])
    nodes[COORD]["active"] = identity["active"]
    return {"nodes": nodes, "pulses": pulses, "coordinator": identity}


# ---------------------------------------------------------------- rendering
# Original drawing: side-view brain (frontal pole left), a fixed set of mesh vertices, Delaunay triangulation computed
# once at import (pure Python, deterministic), agents = highlighted vertices with a leader line to a label box.
import functools
import heapq
import math

_OUTLINE = [(86, 140), (92, 114), (108, 96), (130, 84), (156, 78), (182, 78), (206, 84), (226, 98), (238, 120),
            (240, 146), (236, 168), (240, 186), (226, 204), (206, 210), (196, 218), (196, 240), (180, 242),
            (178, 214), (160, 204), (138, 198), (118, 186), (100, 168), (88, 156)]
_INNER = [(118, 118), (150, 106), (180, 110), (208, 114), (130, 142), (160, 140), (190, 144), (214, 150),
          (110, 152), (140, 172), (172, 172), (200, 176), (214, 192), (150, 190), (120, 170), (190, 200), (188, 230)]
PTS = _OUTLINE + _INNER
# role -> (vertex, label box centre, short label)
LAYOUT = {
    "writer": ((130, 84), (62, 11), "writer"),
    COORD: ((160, 140), (160, 11), "Πάρις"),
    "scholar": ((206, 84), (250, 11), "scholar"),
    "engineer": ((118, 118), (37, 66), "engineer"),
    "runner": ((110, 152), (37, 116), "runner"),
    "Explore": ((120, 170), (37, 166), "Explore"),
    "codex-quick": ((208, 114), (284, 62), "cdx-quick"),
    "codex-reviewer": ((240, 146), (284, 112), "cdx-review"),
    "codex-researcher": ((214, 192), (284, 162), "cdx-research"),
    "codex-architect": ((150, 190), (95, 259), "cdx-arch"),
    "codex-deputy": ((188, 230), (225, 259), "cdx-deputy"),
    "codex-engineer": ((200, 176), (280, 212), "cdx-engineer"),
}
FULL_DX = 60  # full-name mode widens the frame by 2*FULL_DX and recentres the drawing


def _inside(pt, poly):
    x, y = pt
    c = False
    for i in range(len(poly)):
        x1, y1 = poly[i - 1]
        x2, y2 = poly[i]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _delaunay(pts):
    n = len(pts)
    tris = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                (ax, ay), (bx, by), (cx, cy) = pts[i], pts[j], pts[k]
                d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
                if abs(d) < 1e-9:
                    continue
                ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
                uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
                r2 = (ax - ux) ** 2 + (ay - uy) ** 2
                if all(m in (i, j, k) or (pts[m][0] - ux) ** 2 + (pts[m][1] - uy) ** 2 >= r2 - 1e-9 for m in range(n)):
                    tris.append((i, j, k))
    return tris


@functools.lru_cache(maxsize=1)
def mesh_edges():
    """Fixed mesh: Delaunay edges whose triangle lies inside the silhouette and is not a long sliver."""
    edges = set()
    for i, j, k in _delaunay(PTS):
        cen = tuple(sum(PTS[m][d] for m in (i, j, k)) / 3 for d in (0, 1))
        if not _inside(cen, _OUTLINE):
            continue
        tri = [(i, j), (j, k), (i, k)]
        if any(math.dist(PTS[a], PTS[b]) > 62 for a, b in tri):
            continue
        edges.update((min(a, b), max(a, b)) for a, b in tri)
    return sorted(edges)


def _vertex(role):
    return PTS.index(LAYOUT[role][0])


def mesh_path(src, dst):
    """Shortest vertex path along mesh edges between two agent roles (Dijkstra, deterministic)."""
    adj = {}
    for a, b in mesh_edges():
        w = math.dist(PTS[a], PTS[b])
        adj.setdefault(a, []).append((b, w))
        adj.setdefault(b, []).append((a, w))
    s, t = _vertex(src), _vertex(dst)
    dist, prev, q = {s: 0.0}, {}, [(0.0, s)]
    while q:
        d, u = heapq.heappop(q)
        if u == t:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w in adj.get(u, ()):
            if d + w < dist.get(v, 1e18):
                dist[v], prev[v] = d + w, u
                heapq.heappush(q, (d + w, v))
    if t not in dist:
        return [s, t]
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    return path[::-1]


def _zigzag(points, step=6.0, amp=2.6):
    """Jagged polyline along the vertex path (like a firing fibre); amplitude zero at both ends."""
    out, flip, total = [points[0]], 1, 0.0
    segs = list(zip(points, points[1:]))
    length = sum(math.dist(a, b) for a, b in segs) or 1.0
    for (x1, y1), (x2, y2) in segs:
        L = math.dist((x1, y1), (x2, y2)) or 1.0
        nx, ny = -(y2 - y1) / L, (x2 - x1) / L
        m = max(1, int(L // step))
        for i in range(1, m + 1):
            f = i / m
            total_here = total + f * L
            taper = min(1.0, total_here / 10, (length - total_here) / 10)
            o = amp * flip * max(0.0, taper) if i < m or (x2, y2) != points[-1] else 0.0
            if i == m:
                o = 0.0
            out.append((x1 + (x2 - x1) * f + nx * o, y1 + (y2 - y1) * f + ny * o))
            flip = -flip
        total += L
    return out


def _smooth_closed(pts):
    n = len(pts)
    d = [f"M{pts[0][0]} {pts[0][1]}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]} {p2[1]}")
    return "".join(d) + "Z"


_CSS = (
    "html,body{margin:0;height:100%;background:#030a14;overflow:hidden}svg{display:block;width:100%;height:100%}"
    "text{font-family:ui-monospace,Menlo,Consolas,monospace}"
    ".mesh line{stroke:#bff6ff;stroke-width:.7;opacity:.5}"
    ".nd{fill:#e6fbff}.ag{opacity:.7}.ag.on{opacity:1}"
    ".halo{opacity:0}.on .halo{animation:glow 1.5s ease-in-out infinite;transform-box:fill-box;transform-origin:center}"
    "@keyframes glow{0%,100%{opacity:.25;transform:scale(1)}50%{opacity:.9;transform:scale(1.7)}}"
    ".lead{stroke:#9fd8e6;stroke-width:.7;opacity:.75}.on .lead{opacity:1;stroke:#fff}"
    # ambient layer: deliberately faint and cyan/white; real pulses are thick orange/red
    ".breathe{animation:br 7s ease-in-out infinite}@keyframes br{0%,100%{opacity:.35}50%{opacity:.85}}"
    ".core{animation:br 5s ease-in-out infinite}"
    ".tw{animation:tw 4.5s ease-in-out infinite}@keyframes tw{0%,100%{opacity:1}50%{opacity:.25}}"
    ".scan{animation:scan 6s linear infinite}@keyframes scan{from{transform:translateY(-20px)}to{transform:translateY(0)}}"
    ".fl{animation:fl 11s ease-in-out infinite alternate}@keyframes fl{from{transform:translateY(0)}to{transform:translateY(-9px)}}"
)


def _css():
    """Static rules plus the real-pulse timeline: the fibre is drawn during the first TRAVEL_S, then fades by PULSE_S."""
    pct = round(100 * TRAVEL_S / PULSE_S, 1)
    return (_CSS
            + f".fire{{fill:none;stroke-linejoin:round;stroke-linecap:round;stroke-dasharray:100;opacity:0;"
              f"animation:fire {PULSE_S}s linear both}}"
            + "@keyframes fire{0%{stroke-dashoffset:100;opacity:1}"
            + f"{pct}%{{stroke-dashoffset:0;opacity:1}}100%{{stroke-dashoffset:0;opacity:0}}}}")


_CODE = ("inline alpha_n real = ( 0.01 * ( V_m / mV + 55. ) )", "Act_n' = ( alpha_n * ( 1 - Act_n ) - beta_n * Act_n )",
         "agent.spawn(role) -> report", "def pulse(src, dst): ...", "I_Na = g_Na * Act_m**3 * Act_h")
CX, CY = 163, 160          # rotation centre of the pseudo-3D sway
SWAY_DEG, SWAY_S = 17, 16  # +-17 degrees about the vertical axis, one full left-right-left cycle per 16 s
# decorative far-field network on both sides (like the reference's side graphs); purely ambient
_FAR = [(8, 40), (30, 70), (14, 100), (40, 130), (10, 170), (34, 200), (12, 232), (312, 36), (290, 66), (310, 104),
        (284, 134), (312, 176), (290, 206), (308, 238)]


def depth(i):
    """Deterministic pseudo-random depth of mesh vertex i (outline shallower), in [-38, 38]."""
    amp = 14 if i < len(_OUTLINE) else 38
    return round(amp * math.sin(i * 2.399 + 0.7), 1)


# JS: rotate the vertices about the vertical axis, mild perspective, update the same SVG elements ~30 fps. Labels stay
# unrotated (only their leader lines follow the projected node). Wall-clock phase: a re-render continues the sway.
_JS = """(function(){var D=%s,A=%s*Math.PI/180,T=%s*1000,CX=%s,CY=%s;
var q=function(s){return Array.prototype.slice.call(document.querySelectorAll(s))};
var P=D.P,n=P.length,X=new Array(n),Y=new Array(n),Zr=new Array(n);
var E=q('[data-e]'),V=q('[data-v]'),S=q('[data-sp]'),F=q('[data-path]'),sil=q('[data-sil]');
var rm=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches,last=0;
function proj(th){var c=Math.cos(th),s=Math.sin(th);for(var i=0;i<n;i++){var dx=P[i][0]-CX,z=P[i][2];
var x1=dx*c+z*s,z1=-dx*s+z*c,k=1+(z1-z)/900;X[i]=CX+x1*k;Y[i]=CY+(P[i][1]-CY)*k;Zr[i]=z1}}
function smooth(){var m=D.O,d='M'+X[0].toFixed(1)+' '+Y[0].toFixed(1);for(var i=0;i<m;i++){
var a=(i+m-1)%%m,b=i,c=(i+1)%%m,e=(i+2)%%m;
d+='C'+(X[b]+(X[c]-X[a])/6).toFixed(1)+' '+(Y[b]+(Y[c]-Y[a])/6).toFixed(1)+' '+(X[c]-(X[e]-X[b])/6).toFixed(1)+' '
+(Y[c]-(Y[e]-Y[b])/6).toFixed(1)+' '+X[c].toFixed(1)+' '+Y[c].toFixed(1)}return d+'Z'}
function zig(ids){var pts=[],L=0,i,j;for(i=0;i<ids.length;i++)pts.push([X[ids[i]],Y[ids[i]]]);
for(i=1;i<pts.length;i++)L+=Math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]);L=L||1;
var out=[pts[0]],f=1,run=0;for(i=1;i<pts.length;i++){var a=pts[i-1],b=pts[i],l=Math.hypot(b[0]-a[0],b[1]-a[1])||1,
nx=-(b[1]-a[1])/l,ny=(b[0]-a[0])/l,m=Math.max(1,Math.floor(l/6));
for(j=1;j<=m;j++){var t=j/m,h=run+t*l,o=2.6*f*Math.max(0,Math.min(1,h/10,(L-h)/10));if(j==m&&i==pts.length-1)o=0;
out.push([a[0]+(b[0]-a[0])*t+nx*o,a[1]+(b[1]-a[1])*t+ny*o]);f=-f}run+=l}
return out.map(function(p){return p[0].toFixed(1)+','+p[1].toFixed(1)}).join(' ')}
function draw(now){var th=rm?0:A*Math.sin(2*Math.PI*now/T);proj(th);
E.forEach(function(l){var e=l.dataset.e.split(','),a=+e[0],b=+e[1];l.setAttribute('x1',X[a]);l.setAttribute('y1',Y[a]);
l.setAttribute('x2',X[b]);l.setAttribute('y2',Y[b])});
V.forEach(function(c){var i=+c.dataset.v;if(c.tagName=='line'){c.setAttribute('x1',X[i]+(+c.dataset.dx||0));c.setAttribute('y1',Y[i])}
else{c.setAttribute('cx',X[i]);c.setAttribute('cy',Y[i])}});
S.forEach(function(c){var e=c.dataset.sp.split(','),a=+e[0],b=+e[1],per=+e[2]*1000,ph=((now+ +e[3]*1000)%%per)/per,
v=ph<.22?ph/.22:-1;if(v<0){c.setAttribute('opacity',0)}else{c.setAttribute('opacity',.55*Math.sin(Math.PI*v));
c.setAttribute('cx',X[a]+(X[b]-X[a])*v);c.setAttribute('cy',Y[a]+(Y[b]-Y[a])*v)}});
var d=smooth();sil.forEach(function(p){p.setAttribute('d',d)});
F.forEach(function(p){p.setAttribute('points',zig(p.dataset.path.split(',').map(Number)))})}
function tick(){if(!document.hidden){var now=Date.now();if(now-last>=33){last=now;draw(now)}}if(!rm)requestAnimationFrame(tick)}
draw(Date.now());if(!rm)requestAnimationFrame(tick)})();"""


def render(state, full_names=False):
    """Self-contained HTML (SVG + CSS + a small rAF script for the 3D sway).
    Compact (sidebar): short labels; full_names: wider frame with the real role names."""
    nodes, pulses = state["nodes"], state["pulses"]
    dx = FULL_DX if full_names else 0
    W, H = 320 + 2 * dx, 270
    P3 = [[x, y, depth(i)] for i, (x, y) in enumerate(PTS)]
    edges = mesh_edges()
    o = [f'<!doctype html><html><head><meta charset="utf-8"><style>{_css()}</style></head><body>',
         f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="Εγκέφαλος πρακτόρων">',
         '<defs><radialGradient id="bg" cx=".5" cy=".5" r=".75"><stop offset="0" stop-color="#0b2a3d"/>'
         '<stop offset="1" stop-color="#030a14"/></radialGradient>'
         '<linearGradient id="gr" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7df9ff"/>'
         '<stop offset=".55" stop-color="#1fb6d6"/><stop offset="1" stop-color="#3b6fe0"/></linearGradient>'
         '<radialGradient id="cg"><stop offset="0" stop-color="#e6fdff" stop-opacity=".95"/>'
         '<stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></radialGradient>'
         '<pattern id="sl" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" '
         'fill="#7df9ff" opacity=".07"/></pattern>'
         '<filter id="bl" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6"/></filter></defs>',
         f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
         '<g font-size="5" fill="#5bc8e6" opacity=".14">'
         + "".join(f'<text x="{4 + (i * 53) % 90 + dx // 2}" y="{40 + i * 38}">{html.escape(t)}</text>'
                   for i, t in enumerate(_CODE)) + '</g>',
         f'<g transform="translate({dx} 0)">']
    # far-field decorative network + drifting particles (ambient, static geometry)
    far = _FAR
    o.append('<g class="fl" stroke="#7df9ff" stroke-width=".5" opacity=".28">' + "".join(
        f'<line x1="{far[i][0]}" y1="{far[i][1]}" x2="{far[j][0]}" y2="{far[j][1]}"/>'
        for i, j in ((0, 1), (1, 2), (1, 3), (2, 3), (3, 4), (4, 5), (5, 6), (3, 5), (7, 8), (8, 9), (8, 10), (9, 10),
                     (10, 11), (11, 12), (12, 13), (10, 12))) + "</g>")
    o.append('<g class="nd tw" opacity=".7">' + "".join(
        f'<circle cx="{x}" cy="{y}" r="1.5" style="animation-delay:-{i * 0.9 % 4.5:.1f}s"/>'
        for i, (x, y) in enumerate(far)) + "</g>")
    o.append(f'<circle class="core" cx="{CX}" cy="{CY - 20}" r="70" fill="url(#cg)" opacity=".4"/>')
    o.append('<path class="breathe" data-sil="1" fill="none" stroke="#9ff3ff" stroke-width="7" filter="url(#bl)"/>')
    o.append(f'<path data-sil="1" d="{_smooth_closed(_OUTLINE)}" fill="url(#gr)" fill-opacity=".38" stroke="#c9faff" stroke-width="1.1"/>')
    o.append('<g class="mesh">' + "".join(
        f'<line data-e="{a},{b}" x1="{PTS[a][0]}" y1="{PTS[a][1]}" x2="{PTS[b][0]}" y2="{PTS[b][1]}"/>'
        for a, b in edges) + '</g>')
    agent_v = {_vertex(r) for r in LAYOUT}
    plain = [i for i in range(len(PTS)) if i not in agent_v]
    o.append('<g class="nd">' + "".join(
        f'<circle data-v="{i}" cx="{PTS[i][0]}" cy="{PTS[i][1]}" r="1.7"'
        + (' class="tw" style="animation-delay:-%.1fs"' % (i * 0.7 % 4.5) if i % 3 == 0 else "") + "/>"
        for i in plain) + "</g>")
    # ambient sparks along decorative edges (both ends are plain vertices): faint, sparse, positioned by the script
    deco = [e for e in edges if e[0] in plain and e[1] in plain][::3][:7]
    for n_, (a, b) in enumerate(deco):
        o.append(f'<circle class="sp" data-sp="{a},{b},{6 + n_ * 1.3:.1f},{n_ * 2.1:.1f}" r="1.5" fill="#fff" '
                 f'opacity="0" cx="{PTS[a][0]}" cy="{PTS[a][1]}"/>')
    for p in pulses:
        path = mesh_path(p["src"], p["dst"])
        zz = " ".join(f"{x:.1f},{y:.1f}" for x, y in _zigzag([PTS[v] for v in path]))
        dl = f"animation-delay:-{p['age']}s"
        ids = ",".join(map(str, path))
        o.append(f'<polyline class="fire" data-path="{ids}" pathLength="100" points="{zz}" stroke="#ff2a1a" '
                 f'stroke-width="4.5" style="{dl};opacity:.35"/>')
        o.append(f'<polyline class="fire" data-path="{ids}" pathLength="100" points="{zz}" stroke="#ffa11f" '
                 f'stroke-width="1.8" style="{dl}"/>')
    o.append("</g>")
    for r, (label, colour, _x, _y) in ROLES.items():
        (vx, vy), (bx, by), short = LAYOUT[r]
        identity = state.get("coordinator") or {}
        if r == COORD and identity.get("provider") not in (None, agent_models.UNKNOWN):
            # «Πάρις (Claude) · τώρα» / «Πάρις (Codex αναπληρωτής)» (M-20261022-024); model/effort in the line below
            label = identity["label"] + (" · τώρα" if nodes[r]["active"] else "")
            short = "Πάρις (" + identity["provider"] + ")"
        vi = _vertex(r)
        vx += dx
        bx += dx
        text = label if full_names else short
        on = nodes[r]["active"]
        bw = len(text) * 5.1 + 8
        bx = min(max(bx, bw / 2 + 1), W - bw / 2 - 1)
        vert = abs(by - vy) > abs(bx - vx)
        ey = by + (6.5 if by < vy else -6.5) if vert else by
        ex = bx if vert else (bx + bw / 2 if bx < vx else bx - bw / 2)
        rad = 4.6 if r == COORD else 3.6
        tr = f'transform="translate({dx} 0)"'
        o.append(
            f'<g class="ag{" on" if on else ""}" data-role="{html.escape(r)}">'
            f'<title>{html.escape(label)} · {"ενεργός" if on else "αδρανής"}</title>'
            f'<g {tr}><circle class="halo" data-v="{vi}" cx="{vx - dx}" cy="{vy}" r="{rad + 3}" fill="{colour}"/>'
            f'<circle data-v="{vi}" cx="{vx - dx}" cy="{vy}" r="{rad}" fill="#fff" stroke="{colour}" stroke-width="2"/></g>'
            f'<line class="lead" data-v="{vi}" data-dx="{dx}" x1="{vx}" y1="{vy}" x2="{ex:.1f}" y2="{ey:.1f}" {""}/>'
            f'<rect x="{bx - bw / 2:.1f}" y="{by - 6.5}" width="{bw:.1f}" height="13" rx="4" fill="#fff" '
            f'stroke="{colour}" stroke-width="1.4"/>'
            f'<text x="{bx:.1f}" y="{by + 3.1}" text-anchor="middle" font-size="8.4" font-weight="700" '
            f'fill="#0b1220">{html.escape(text)}</text></g>')
    o.append(f'<rect width="{W}" height="{H}" fill="url(#sl)" class="scan" pointer-events="none"/>')
    o.append("</svg>")
    identity = state.get("coordinator") or {}
    if identity.get("provider") not in (None, agent_models.UNKNOWN):
        details = " · ".join(str(identity.get(k) or agent_models.UNKNOWN) for k in ("provider", "role", "model", "effort"))
        o.append('<div style="font:10px sans-serif;color:#c9faff;text-align:center">'
                 + html.escape(details) + '</div>')
    data = '{"P":%s,"O":%d}' % (json.dumps(P3), len(_OUTLINE))
    o.append("<script>" + _JS % (data, SWAY_DEG, SWAY_S, CX, CY) + "</script></body></html>")
    return "".join(o)
