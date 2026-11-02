"""Γνώση tab graph (J322, M-20261102-026 item 7): the graphify code graph in .lab/kb/ drawn as a force-directed GRAPH.
Nodes = source files (colour = corpus, size = symbols in the file), edges = calls/imports/uses/inherits between files
(width = number of symbol-level edges). Built from graph.json only (AST edges, no LLM); self-contained canvas JS, no CDN."""
import collections
import json
from pathlib import Path

CROSS_FILE = ("calls", "imports", "imports_from", "indirect_call", "uses", "inherits", "references")
GRAPH_REL = Path(".lab/kb/graphify-out/graph.json")
DB_REL = Path(".lab/kb/kb.db")


def file_graph(graph, max_nodes=400):
    """graph = parsed graph.json -> {"nodes": [{id,corp,sym,deg}], "edges": [[a,b,weight,rel]], "total_files", "total_symbols"}.
    Only files with a cross-file edge are drawn (the rest would be isolated dots); capped at the max_nodes most connected."""
    nf = {n["id"]: n.get("source_file") for n in graph.get("nodes", [])}
    sym = collections.Counter(f for f in nf.values() if f)
    agg, rels = collections.Counter(), collections.defaultdict(collections.Counter)
    for e in graph.get("edges", []):
        rel = e.get("relation")
        if rel not in CROSS_FILE:
            continue
        a, b = nf.get(e.get("source")), nf.get(e.get("target"))
        if a and b and a != b:
            agg[(a, b)] += 1
            rels[(a, b)][rel] += 1
    deg = collections.Counter()
    for (a, b), w in agg.items():
        deg[a] += w
        deg[b] += w
    keep = {f for f, _ in deg.most_common(max_nodes)}
    nodes = [{"id": f, "corp": f.split("/")[0] if "/" in f else "?", "sym": sym[f], "deg": deg[f]} for f in sorted(keep)]
    edges = [[a, b, w, rels[(a, b)].most_common(1)[0][0]] for (a, b), w in agg.items() if a in keep and b in keep]
    return {"nodes": nodes, "edges": edges, "total_files": len(sym), "total_symbols": sum(sym.values())}


def load(root):
    """(data, error): data None when graph.json is missing/unreadable (the tab then says to run kb.py refresh)."""
    p = Path(root) / GRAPH_REL
    try:
        return file_graph(json.loads(p.read_text(encoding="utf-8"))), None
    except (OSError, ValueError) as e:
        return None, f"{p}: {type(e).__name__}"


def index_stats(root):
    """Chunk counts per kind and the build time from kb.db (read-only); {} if unavailable."""
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{Path(root) / DB_REL}?mode=ro", uri=True)
        kinds = dict(con.execute("SELECT kind, count(*) FROM chunks GROUP BY kind"))
        built = (con.execute("SELECT v FROM meta WHERE k='built'").fetchone() or [""])[0]
        con.close()
        return {"chunks": kinds, "built": built}
    except sqlite3.Error:
        return {}


def _js(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


_PAGE = """<div style="font:13px sans-serif;color:#ddd"><input id="q" placeholder="αναζήτηση αρχείου (π.χ. dispatcher)" style="width:260px;padding:4px">
<span id="info" style="margin-left:10px;opacity:.8">πάτα έναν κόμβο: γείτονες· σύρε: μετακίνηση</span></div>
<canvas id="c" width="1100" height="__H__" style="width:100%;background:#12151c;border-radius:8px;cursor:grab"></canvas>
<div id="leg" style="font:12px sans-serif;color:#bbb"></div>
<script>
const D=__DATA__, H=__H__, cv=document.getElementById('c'), cx=cv.getContext('2d'), W=cv.width;
const COL={qrl:'#4ea1ff',tuning:'#f5a742',spiky:'#e86a92',simulations:'#6fd08c',redis:'#c58af9',promgraf:'#f2d94e',k8s:'#5ad1d1','?':'#999'};
const N=D.nodes.map((n,i)=>({...n,i,x:W/2+(Math.random()-.5)*W*.6,y:H/2+(Math.random()-.5)*H*.6,vx:0,vy:0}));
const idx=Object.fromEntries(N.map(n=>[n.id,n]));
const E=D.edges.map(e=>({a:idx[e[0]],b:idx[e[1]],w:e[2],rel:e[3]})).filter(e=>e.a&&e.b);
const adj=new Map(N.map(n=>[n,[]]));E.forEach(e=>{adj.get(e.a).push(e);adj.get(e.b).push(e)});
let sel=null,hit=new Set(),tx=0,ty=0,k=1,alpha=1;
const r=n=>3+Math.min(9,Math.sqrt(n.sym)*0.9);
function tick(){
  for(let i=0;i<N.length;i++){const a=N[i];for(let j=i+1;j<N.length;j++){const b=N[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.01;
    if(d2<90000){const f=900/d2,d=Math.sqrt(d2);a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f}}}
  E.forEach(e=>{const dx=e.b.x-e.a.x,dy=e.b.y-e.a.y,d=Math.sqrt(dx*dx+dy*dy)+.01,f=(d-70)*0.01*Math.min(3,1+Math.log(e.w));
    e.a.vx+=dx/d*f;e.a.vy+=dy/d*f;e.b.vx-=dx/d*f;e.b.vy-=dy/d*f});
  N.forEach(n=>{n.vx+=(W/2-n.x)*0.002;n.vy+=(H/2-n.y)*0.002;n.x+=n.vx*alpha;n.y+=n.vy*alpha;n.vx*=.6;n.vy*=.6});
  alpha=Math.max(.03,alpha*.985);
}
function draw(){
  cx.setTransform(1,0,0,1,0,0);cx.clearRect(0,0,W,H);cx.setTransform(k,0,0,k,tx,ty);
  const dim=hit.size>0;
  E.forEach(e=>{const on=!dim||(hit.has(e.a)&&hit.has(e.b)&&(e.a===sel||e.b===sel||!sel));
    cx.strokeStyle=on?'rgba(180,190,210,.55)':'rgba(120,130,150,.08)';cx.lineWidth=Math.min(4,.5+Math.log(1+e.w));
    cx.beginPath();cx.moveTo(e.a.x,e.a.y);cx.lineTo(e.b.x,e.b.y);cx.stroke()});
  N.forEach(n=>{const on=!dim||hit.has(n);cx.globalAlpha=on?1:.15;cx.fillStyle=COL[n.corp]||COL['?'];
    cx.beginPath();cx.arc(n.x,n.y,r(n),0,7);cx.fill();
    if((dim&&on)||n.deg>60){cx.fillStyle='#eee';cx.font='10px sans-serif';cx.fillText(n.id.split('/').pop(),n.x+r(n)+2,n.y+3)}});
  cx.globalAlpha=1;
}
function loop(){tick();draw();requestAnimationFrame(loop)}
function pick(ev){const b=cv.getBoundingClientRect(),s=W/b.width,x=((ev.clientX-b.left)*s-tx)/k,y=((ev.clientY-b.top)*s-ty)/k;
  return N.find(n=>(n.x-x)**2+(n.y-y)**2<(r(n)+3)**2)}
let drag=null;
cv.onmousedown=ev=>{const n=pick(ev);drag={n,x:ev.clientX,y:ev.clientY,moved:false}};
window.onmousemove=ev=>{if(!drag)return;const b=cv.getBoundingClientRect(),s=W/b.width;
  if(Math.abs(ev.clientX-drag.x)+Math.abs(ev.clientY-drag.y)>3)drag.moved=true;
  if(drag.moved&&!drag.n){tx+=(ev.clientX-drag.x)*s;ty+=(ev.clientY-drag.y)*s;drag.x=ev.clientX;drag.y=ev.clientY}};
window.onmouseup=ev=>{if(drag&&!drag.moved)select(drag.n);drag=null};
cv.onwheel=ev=>{ev.preventDefault();const f=ev.deltaY<0?1.1:.9;k=Math.max(.3,Math.min(5,k*f))};
function select(n){sel=n;hit=new Set();const info=document.getElementById('info');
  if(!n){info.textContent='';return}
  hit.add(n);const rel=[];adj.get(n).forEach(e=>{const o=e.a===n?e.b:e.a;hit.add(o);rel.push((e.a===n?'→ ':'← ')+o.id.split('/').pop()+' ('+e.rel+'×'+e.w+')')});
  info.textContent=n.id+' · '+n.sym+' σύμβολα · '+rel.slice(0,8).join(', ')+(rel.length>8?' …':'');alpha=Math.max(alpha,.2)}
document.getElementById('q').oninput=ev=>{const q=ev.target.value.toLowerCase();sel=null;hit=new Set();
  if(q)N.forEach(n=>{if(n.id.toLowerCase().includes(q))hit.add(n)});
  document.getElementById('info').textContent=q?hit.size+' αρχεία':''};
document.getElementById('leg').innerHTML=Object.keys(COL).filter(c=>N.some(n=>n.corp===c)).map(c=>'<span style="color:'+COL[c]+'">● '+c+'</span>').join(' &nbsp; ');
loop();
</script>"""


def render(data, height=620):
    """Self-contained HTML for components.html."""
    return _PAGE.replace("__DATA__", _js(data)).replace("__H__", str(int(height)))
