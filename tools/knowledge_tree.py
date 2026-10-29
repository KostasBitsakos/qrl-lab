"""«Γνώση» tab: self-contained zoomable tree (HTML + vanilla JS + SVG, no CDN, nothing phones home).
Mobile-first (M-20261029-118): pinch / drag / double-tap zoom, tap a theme or folder to open it, tap a file for a
bottom sheet with its summary and a link that opens it in the «📁 Αρχεία» tab (?path=). Search runs in the browser.
Data: tools/knowledge_view.tree_data()."""
import json

_PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1f2933;background:#fff}
#wrap{position:relative;height:__H__px;border:1px solid #e3e7ee;border-radius:14px;overflow:hidden;background:#fbfcfe}
#bar{position:absolute;top:8px;left:8px;right:8px;display:flex;gap:6px;z-index:3}
#q{flex:1;min-width:0;font-size:16px;padding:9px 12px;border:1px solid #cfd6e0;border-radius:10px;background:#fff}
.b{font-size:15px;padding:8px 11px;border:1px solid #cfd6e0;border-radius:10px;background:#fff;cursor:pointer;white-space:nowrap}
.b:active{background:#eef3ff}
#info{position:absolute;top:54px;left:12px;right:12px;font-size:12.5px;color:#5f6b7a;z-index:2;pointer-events:none}
svg{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:grab}
#g.anim{transition:transform .35s ease}
.lnk{fill:none;stroke:#cdd5e0;stroke-width:1.4}
.nd text{font-size:13px;paint-order:stroke;stroke:#fbfcfe;stroke-width:4px;stroke-linejoin:round}
.nd.theme text{font-size:15px;font-weight:600}
.nd.root text{font-size:16px;font-weight:700}
.nd .hitbox{fill:transparent}
.nd.hit text{fill:#c0392b;font-weight:700}
.nd.dim{opacity:.35}
#sheet{position:absolute;left:0;right:0;bottom:0;max-height:62%;overflow:auto;background:#fff;border-top:1px solid #dfe4ea;
 border-radius:16px 16px 0 0;box-shadow:0 -6px 24px rgba(0,0,0,.12);padding:14px 16px 18px;transform:translateY(105%);
 transition:transform .25s ease;z-index:4}
#sheet.open{transform:none}
#sheet h3{margin:0 0 4px;font-size:17px}
#sheet .p{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:#5f6b7a;word-break:break-all}
#sheet .d{margin:10px 0;font-size:15px;line-height:1.45}
#sheet .note{background:#fff6e0;border-left:4px solid #f0ad4e;padding:8px 10px;border-radius:6px;font-size:14px}
#sheet .acts{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
#sheet .acts a,#sheet .acts button{font-size:15px;padding:10px 14px;border-radius:10px;border:1px solid #cfd6e0;
 background:#fff;color:#1f2933;text-decoration:none;cursor:pointer}
#sheet .acts a.pri{background:#2b6de8;border-color:#2b6de8;color:#fff}
#help{position:absolute;bottom:8px;left:12px;right:12px;font-size:12px;color:#8a94a3;z-index:2;pointer-events:none;text-align:center}
</style></head><body><div id="wrap">
<div id="bar"><input id="q" type="search" placeholder="🔎 Αναζήτηση (π.χ. poisson, HPA, κανόνες)" autocomplete="off">
<button class="b" id="fit" title="Όλο το δέντρο">⤢</button><button class="b" id="home" title="Κλείσε όλα">⌂</button></div>
<div id="info"></div>
<svg id="svg"><g id="g"></g></svg>
<div id="help">Πάτα ένα θέμα για να ανοίξει · τσίμπημα ή διπλό πάτημα για zoom · σύρε για μετακίνηση</div>
<div id="sheet"></div>
</div>
<script>
(function(){
var DATA=__DATA__,ROOT=__ROOT__,FILES_TAB=__FTAB__;
var NS="http://www.w3.org/2000/svg",svg=document.getElementById("svg"),g=document.getElementById("g");
var q=document.getElementById("q"),info=document.getElementById("info"),sheet=document.getElementById("sheet");
var ROW=34;
var T={x:16,y:80,k:1},open={};
// parents, theme colour inheritance, search text
(function walk(n,par,color){n.par=par;n.color=n.color||color||"#5b8def";
  n.txt=((n.path||n.name)+" "+(n.title||"")+" "+(n.desc||"")).toLowerCase();
  (n.children||[]).forEach(function(c){walk(c,n,n.kind==="root"?null:n.color);});})(DATA,null,null);
open[DATA.id]=true;
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function short(s,n){return s.length>n?s.slice(0,n-1)+"…":s;}
function label(n){
  if(n.kind==="root")return "📚 "+n.name;
  if(n.kind==="theme")return n.emoji+" "+n.name+"  ("+n.n+")";
  if(n.kind==="folder")return "📁 "+short(n.name,28)+" ("+n.n+")";
  return (n.kind==="index"?"⭐ ":"📄 ")+short(n.name.replace(/\.md$/,""),30);}
var hits=null;
function lw(n){return (n.w||label(n).length*7.6)+22;}  // n.w = measured rendered width once drawn, else estimate
function layout(){var nodes=[],links=[],slot=0,wid=[];
  function kidsOf(n){var k=open[n.id]?(n.children||[]):[];return hits!==null?k.filter(function(c){return c.hitq;}):k;}
  (function lay(n,d){n.d=d;var kids=kidsOf(n);wid[d]=Math.max(wid[d]||0,kids.length?lw(n):0);
    if(!kids.length){n.y=slot++*ROW;}
    else{kids.forEach(function(c){lay(c,d+1);links.push([n,c]);});n.y=(kids[0].y+kids[kids.length-1].y)/2;}
    nodes.push(n);})(DATA,0);
  var xs=[0];for(var i=1;i<wid.length+1;i++)xs[i]=xs[i-1]+Math.max(60,(wid[i-1]||0)+18);  // next column starts after the widest open label
  nodes.forEach(function(n){n.x=xs[n.d];});
  return {nodes:nodes,links:links};}
function draw(again){var grew=false,L=layout();while(g.firstChild)g.removeChild(g.firstChild);
  L.links.forEach(function(l){var p=document.createElementNS(NS,"path"),a=l[0],b=l[1],mx=(a.x+b.x)/2;
    p.setAttribute("class","lnk");p.setAttribute("d","M"+a.x+","+a.y+"C"+mx+","+a.y+" "+mx+","+b.y+" "+b.x+","+b.y);g.appendChild(p);});
  L.nodes.forEach(function(n){var e=document.createElementNS(NS,"g"),leaf=!(n.children&&n.children.length);
    var sr=hits!==null;e.setAttribute("class","nd "+n.kind+(sr&&n.hitq&&leaf?" hit":"")+(sr&&!n.hitq?" dim":""));
    e.setAttribute("transform","translate("+n.x+","+n.y+")");
    var r=n.kind==="root"?9:n.kind==="theme"?8:leaf?5:6.5,c=document.createElementNS(NS,"circle");
    c.setAttribute("r",r);var closed=!leaf&&!open[n.id];
    c.setAttribute("fill",n.kind==="index"?"#f0ad4e":(leaf?"#fff":(closed?n.color:"#fff")));
    c.setAttribute("stroke",n.kind==="root"?"#1f2933":(sr&&n.hitq&&leaf?"#c0392b":n.color));c.setAttribute("stroke-width",2.2);
    var t=document.createElementNS(NS,"text");t.setAttribute("x",r+6);t.setAttribute("dy","0.35em");t.textContent=label(n);
    var hb=document.createElementNS(NS,"rect");hb.setAttribute("class","hitbox");hb.setAttribute("x",-14);hb.setAttribute("y",-ROW/2);
    hb.setAttribute("height",ROW);hb.setAttribute("width",Math.max(40,label(n).length*8+30));
    e.appendChild(hb);e.appendChild(c);e.appendChild(t);e._n=n;g.appendChild(e);
    try{var w=t.getComputedTextLength()+r+6;if(!n.w||w>n.w+1){n.w=w;grew=true;}}catch(err){}});
  if(grew&&!again)return draw(true);  // one re-layout with real text widths so columns never overlap
  return L;}
function apply(anim){g.classList.toggle("anim",!!anim);g.style.transform="translate("+T.x+"px,"+T.y+"px) scale("+T.k+")";}
function bbox(L){var x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;L.nodes.forEach(function(n){x0=Math.min(x0,n.x);y0=Math.min(y0,n.y);
  x1=Math.max(x1,n.x+label(n).length*7.5+20);y1=Math.max(y1,n.y);});return [x0,y0,x1,y1];}
function fit(L){var b=bbox(L||layout()),W=svg.clientWidth,H=svg.clientHeight-110;
  var k=Math.min(1.3,Math.max(0.25,Math.min((W-24)/(b[2]-b[0]+1),H/(b[3]-b[1]+ROW))));
  T.k=k;T.x=12-b[0]*k;T.y=74+(H-(b[3]-b[1])*k)/2-b[1]*k;apply(true);}
function focus(n){var W=svg.clientWidth,H=svg.clientHeight;T.k=Math.max(T.k,0.8);
  T.x=Math.min(16,W*0.28-n.x*T.k);T.y=H/2-n.y*T.k;apply(true);}
function toggle(n){if(!(n.children&&n.children.length))return showSheet(n);
  open[n.id]=!open[n.id];
  if(open[n.id]&&n.kind==="theme"&&hits===null)DATA.children.forEach(function(c){if(c!==n)open[c.id]=false;});
  if(open[n.id]&&n.children.length===1&&n.children[0].children)open[n.children[0].id]=true;  // skip single-folder chains
  draw();n.kind==="root"?fit():focus(n);}
function showSheet(n){
  var href="";try{var u=new URL(window.parent.location.href);u.search="";u.hash="";u.searchParams.set("tab",FILES_TAB);u.searchParams.set("path",ROOT+"/"+n.path);href=u.toString();}catch(e){}
  sheet.innerHTML="<h3>"+(n.kind==="index"?"⭐ ":"📄 ")+esc(n.title||n.name)+"</h3><div class='p'>"+esc(n.path)+" · "+esc(n.lines==null?"?":n.lines)+" γραμμές</div>"+
    (n.desc?"<div class='d'>"+esc(n.desc)+"</div>":"")+(n.note?"<div class='note'>⭐ Ευρετήριο: "+esc(n.note)+"</div>":"")+
    "<div class='acts'>"+(href?"<a class='pri' href='"+esc(href)+"' target='_top'>📂 Άνοιγμα</a>":"")+
    "<button id='cp'>📋 Αντιγραφή διαδρομής</button><button id='cl'>✕ Κλείσιμο</button></div>";
  sheet.classList.add("open");
  document.getElementById("cl").onclick=function(){sheet.classList.remove("open");};
  document.getElementById("cp").onclick=function(ev){try{navigator.clipboard.writeText(n.path);ev.target.textContent="✓ Αντιγράφηκε";}catch(e){}};}
function search(){var s=q.value.trim().toLowerCase();sheet.classList.remove("open");
  if(s.length<2){hits=null;info.textContent="";draw();fit();return;}
  var cnt=0;(function mark(n){var kids=n.children||[],any=false;kids.forEach(function(c){if(mark(c))any=true;});
    var self=!kids.length&&n.txt.indexOf(s)>=0;if(self)cnt++;n.hitq=self||any;if(any)open[n.id]=true;return n.hitq;})(DATA);
  hits=cnt;DATA.hitq=true;info.textContent=cnt?cnt+" αρχεία ταιριάζουν· πάτα ένα για λεπτομέρειες":"Κανένα αποτέλεσμα για «"+q.value+"»";
  var L=draw();fit(L);}
// ---- pointer pan / pinch / tap
var pts={},start=null,moved=false,lastTap=0;
function dist(){var a=Object.values(pts);return a.length<2?0:Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y);}
function mid(){var a=Object.values(pts);return {x:(a[0].x+a[1].x)/2,y:(a[0].y+a[1].y)/2};}
svg.addEventListener("pointerdown",function(ev){svg.setPointerCapture(ev.pointerId);pts[ev.pointerId]={x:ev.clientX,y:ev.clientY};
  start={T:{x:T.x,y:T.y,k:T.k},p:{x:ev.clientX,y:ev.clientY},d:dist(),m:Object.keys(pts).length>1?mid():null,tgt:ev.target};
  if(Object.keys(pts).length===1)moved=false;else moved=true;});
svg.addEventListener("pointermove",function(ev){if(!pts[ev.pointerId]||!start)return;pts[ev.pointerId]={x:ev.clientX,y:ev.clientY};
  var r=svg.getBoundingClientRect();
  if(Object.keys(pts).length>1&&start.d){var m=mid(),k=Math.min(4,Math.max(0.15,start.T.k*dist()/start.d)),
      ox=start.m.x-r.left,oy=start.m.y-r.top;
    T.k=k;T.x=(m.x-r.left)-(ox-start.T.x)*k/start.T.k;T.y=(m.y-r.top)-(oy-start.T.y)*k/start.T.k;moved=true;}
  else{var dx=ev.clientX-start.p.x,dy=ev.clientY-start.p.y;if(Math.abs(dx)+Math.abs(dy)>6)moved=true;
    if(moved){T.x=start.T.x+dx;T.y=start.T.y+dy;}}
  apply(false);});
function up(ev){var wasTap=!moved&&Object.keys(pts).length===1;delete pts[ev.pointerId];
  if(Object.keys(pts).length){var p=Object.values(pts)[0];start={T:{x:T.x,y:T.y,k:T.k},p:p,d:0,m:null};return;}
  if(wasTap&&start){var el=start.tgt;while(el&&el!==svg&&!el._n)el=el.parentNode;
    var now=Date.now();
    if(el&&el._n){toggle(el._n);}
    else if(now-lastTap<320){zoomAt(ev.clientX,ev.clientY,1.8);}
    else sheet.classList.remove("open");
    lastTap=now;}
  start=null;}
function cancel(ev){delete pts[ev.pointerId];moved=true;var rest=Object.values(pts);
  start=rest.length?{T:{x:T.x,y:T.y,k:T.k},p:rest[0],d:0,m:null}:null;}  // rebase on the surviving finger: no jump
svg.addEventListener("pointerup",up);svg.addEventListener("pointercancel",cancel);svg.addEventListener("lostpointercapture",function(ev){if(pts[ev.pointerId])cancel(ev);});
function zoomAt(cx,cy,f){var r=svg.getBoundingClientRect(),x=cx-r.left,y=cy-r.top,k=Math.min(4,Math.max(0.15,T.k*f));
  T.x=x-(x-T.x)*k/T.k;T.y=y-(y-T.y)*k/T.k;T.k=k;apply(true);}
svg.addEventListener("wheel",function(ev){ev.preventDefault();zoomAt(ev.clientX,ev.clientY,Math.exp(-ev.deltaY*0.0015));},{passive:false});
q.addEventListener("input",search);
document.getElementById("fit").onclick=function(){fit();};
document.getElementById("home").onclick=function(){q.value="";hits=null;info.textContent="";open={};open[DATA.id]=true;
  sheet.classList.remove("open");draw();fit();};
draw();fit();window.addEventListener("resize",function(){fit();});
})();
</script></body></html>"""


def _clean(n):
    """Drop fields the browser does not need (keeps the payload small)."""
    out = {k: v for k, v in n.items() if k not in ("hit", "children")}
    if n.get("children"):
        out["children"] = [_clean(c) for c in n["children"]]
    return out


def _js(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def render(tree, root, files_tab, height=640):
    """Full HTML page for components.html. root = absolute lab dir (the Files tab only opens absolute paths);
    files_tab = its label for ?tab=. JSON is embedded with '</' escaped so file text cannot close the script."""
    return (_PAGE.replace("__DATA__", _js(_clean(tree))).replace("__ROOT__", _js(root.rstrip("/")))
            .replace("__FTAB__", _js(files_tab)).replace("__H__", str(int(height))))
