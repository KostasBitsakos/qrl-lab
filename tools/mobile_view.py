"""Phone layout and home-screen (standalone web-app) mode for the dashboard (researcher, M-20261029-126).

inject() adds, once per rerun, inside the sidebar (no space in the main page):
- CSS that applies only at <=480px (desktop unchanged): compact padding, one-row swipeable tab bar, 44px touch
  targets, 16px inputs (iOS does not zoom on focus), stacked columns, scrollable tables, sticky chat input;
- a same-origin component script that writes the home-screen tags into the parent page's <head>
  (apple-mobile-web-app-*, theme-color, apple-touch-icon, manifest) and, on narrow screens only, a floating
  "☰" button that opens a grouped list of all tabs (tapping an entry clicks the real Streamlit tab).
Icon and manifest are served from dashboard/static/ via server.enableStaticServing (/app/static/...)."""
import json

import streamlit as st
import streamlit.components.v1 as components

STATIC = "/app/static"
TITLE = "QRL-Lab"
THEME = "#2a78d6"
# Tutorials are grouped under Έρευνα (M-20261029-159).
# Grouping for the phone tab menu: keyword in the tab label -> group. Unknown labels go to "Άλλα".
GROUPS = [
    ("Κύρια", ["Συνομιλία", "Αποφάσεις", "Πράκτορες", "Πειράματα", "Council"]),
    ("Έρευνα", ["Paper", "Συνέδρια", "Γνώση", "Tutorials", "Αρχεία", "Μοντέλα", "Αρχιτεκτονική"]),
    ("Υποδομή", ["Πόροι", "Kubernetes", "Prometheus", "Grafana", "Terminal"]),
    ("Διαχείριση", ["Ιστορικό αλλαγών", "Ιστορικό", "Sudo", "Επεκτάσεις", "Διακοπές"]),
]

HEAD = [
    ("meta", {"name": "apple-mobile-web-app-capable", "content": "yes"}),
    ("meta", {"name": "mobile-web-app-capable", "content": "yes"}),
    ("meta", {"name": "apple-mobile-web-app-title", "content": TITLE}),
    ("meta", {"name": "application-name", "content": TITLE}),
    ("meta", {"name": "apple-mobile-web-app-status-bar-style", "content": "default"}),
    ("meta", {"name": "theme-color", "content": THEME}),
    ("link", {"rel": "apple-touch-icon", "href": f"{STATIC}/apple-touch-icon.png"}),
    ("link", {"rel": "manifest", "href": f"{STATIC}/manifest.json"}),
]

# Selectors doubled ([x][x]) to outrank the global tab-wrap rule in app.py regardless of DOM order.
CSS = """<style>
@media (max-width:480px){
.block-container{padding:3rem .5rem 4.5rem .5rem!important}
h1{font-size:1.45rem!important}h2{font-size:1.25rem!important}h3{font-size:1.1rem!important}
[data-testid=stTabs] [role=tablist][role=tablist]{flex-wrap:nowrap!important;overflow-x:auto!important;
 -webkit-overflow-scrolling:touch;scrollbar-width:none;column-gap:4px!important;scroll-snap-type:x proximity}
[data-testid=stTabs] [role=tablist]::-webkit-scrollbar{display:none}
[data-testid=stTab][data-testid=stTab]{white-space:nowrap;min-height:44px;padding:0 8px;scroll-snap-align:start;
 font-size:.9rem}
.stButton button,.stFormSubmitButton button,.stDownloadButton button,.stLinkButton a{min-height:44px;
 padding:.4rem .9rem}
[data-testid=stExpander] summary{min-height:44px;align-items:center}
[data-testid=stCheckbox] label,[data-testid=stRadio] label,[data-testid=stToggle] label{min-height:36px;
 align-items:center}
input,textarea,select,[data-baseweb=select] div{font-size:16px!important}
[data-testid=stHorizontalBlock][data-testid=stHorizontalBlock]>[data-testid=stColumn]{min-width:100%!important;
 flex:1 1 100%!important}
[data-testid=stDataFrame],[data-testid=stTable],.stMarkdown table,pre{max-width:100%!important;overflow-x:auto!important}
.stMarkdown table{display:block}
[data-testid=stMarkdownContainer]{overflow-wrap:anywhere}
iframe,img,svg{max-width:100%}
[data-testid=stChatInput]{position:sticky;bottom:0;z-index:5;padding-bottom:env(safe-area-inset-bottom)}
[data-testid=stSidebar][aria-expanded=true]{width:88vw!important;min-width:88vw!important}
}
</style>"""

_SCRIPT = """<script>(function(){
var w=window.parent,doc;try{doc=w.document;}catch(e){return;}
var HEAD=%(head)s,GROUPS=%(groups)s;
HEAD.forEach(function(h){var t=h[0],a=h[1],sel=t+(a.name?'[name="'+a.name+'"]':'[rel="'+a.rel+'"]');
  if(doc.head.querySelector(sel))return;var el=doc.createElement(t);
  Object.keys(a).forEach(function(k){el.setAttribute(k,a[k]);});doc.head.appendChild(el);});
if(!w.__qrlFb){w.__qrlFb=1;(function(){
  /* J228 (M-20261030-063): instant feedback for every tap + top progress bar while the script runs. A tapped button is dimmed
     and ignores a second tap until the app has finished its run (the 2nd/3rd press used to queue duplicate reruns). */
  var fst=doc.createElement('style');fst.textContent='.qrl-pend{opacity:.55!important;pointer-events:none!important}'+
   '#qrl-bar{position:fixed;left:0;top:0;height:3px;width:0;background:%(theme)s;z-index:999999;opacity:0;'+
   'transition:width 6s cubic-bezier(.1,.7,.2,1),opacity .2s}#qrl-bar.on{width:92%%;opacity:1}';
  doc.head.appendChild(fst);var bar=doc.createElement('div');bar.id='qrl-bar';doc.body.appendChild(bar);
  var pend=[],tmo=null;
  function app(){return doc.querySelector('[data-testid="stApp"]');}
  function running(){var a=app();return !!a&&a.getAttribute('data-test-script-state')==='running';}
  function clear(){pend.forEach(function(b){b.classList.remove('qrl-pend');});pend=[];}
  function sync(){if(running()){bar.classList.add('on');}else{bar.classList.remove('on');bar.style.transition='none';
    bar.offsetWidth;bar.style.transition='';clear();}}
  doc.addEventListener('click',function(e){var b=e.target&&e.target.closest?e.target.closest('button'):null;
    if(!b||b.closest('#qrl-menu')||b.id==='qrl-menu-btn')return;
    var wrap=b.closest('[data-testid="stButton"],[data-testid="stFormSubmitButton"],[data-testid="stChatInput"]');
    if(!wrap)return;b.classList.add('qrl-pend');pend.push(b);bar.classList.add('on');
    clearTimeout(tmo);tmo=setTimeout(function(){if(!running()){clear();bar.classList.remove('on');}},2500);},true);
  var t=setInterval(function(){var a=app();if(!a)return;clearInterval(t);
    new MutationObserver(sync).observe(a,{attributes:true,attributeFilter:['data-test-script-state']});},300);
})();}
if(doc.getElementById('qrl-menu-btn'))return;
var mq=w.matchMedia('(max-width:480px)');
var st=doc.createElement('style');st.textContent='@media (max-width:480px){'+
 '#qrl-menu-btn{position:fixed;right:14px;bottom:calc(16px + env(safe-area-inset-bottom));z-index:999990;width:52px;'+
 'height:52px;border-radius:26px;border:0;background:%(theme)s;color:#fff;font-size:24px;box-shadow:0 2px 8px #0004}'+
 '#qrl-menu{position:fixed;inset:0;z-index:999991;background:#0006}'+
 '#qrl-menu .sheet{position:absolute;left:0;right:0;bottom:0;max-height:80vh;overflow-y:auto;background:#fff;'+
 'border-radius:14px 14px 0 0;padding:10px 12px calc(14px + env(safe-area-inset-bottom))}'+
 '#qrl-menu h4{margin:10px 4px 4px;font:600 13px sans-serif;color:#666;text-transform:uppercase}'+
 '#qrl-menu .grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}'+
 '#qrl-menu button.it{min-height:46px;border:1px solid #ddd;border-radius:10px;background:#f7f8fa;text-align:left;'+
 'padding:6px 10px;font:15px sans-serif;color:#222}#qrl-menu button.it.on{border-color:%(theme)s;background:#e8f1fc}}';
doc.head.appendChild(st);
var btn=doc.createElement('button');btn.id='qrl-menu-btn';btn.textContent='\\u2630';btn.title='Καρτέλες';
btn.setAttribute('aria-label','Καρτέλες');
var ov=doc.createElement('div');ov.id='qrl-menu';ov.style.display='none';ov.innerHTML='<div class="sheet"></div>';
doc.body.appendChild(ov);doc.body.appendChild(btn);
function root(){var all=doc.querySelectorAll('[data-testid="stTabs"]');for(var i=0;i<all.length;i++){
  if(!all[i].parentElement.closest('[data-testid="stTabs"]'))return all[i];}return null;}
function label(t){return (t.innerText||t.textContent||'').trim();}
function tabs(){var r=root();if(!r)return [];return Array.prototype.filter.call(
  r.querySelectorAll('[data-testid="stTab"],[role="tab"]'),function(t){return t.closest('[data-testid="stTabs"]')===r;});}
function group(l){for(var i=0;i<GROUPS.length;i++){for(var j=0;j<GROUPS[i][1].length;j++){
  if(l.indexOf(GROUPS[i][1][j])>=0)return GROUPS[i][0];}}return 'Άλλα';}
function go(l){ov.style.display='none';var t=tabs().filter(function(x){return label(x)===l;})[0];if(!t)return;
  t.click();try{t.scrollIntoView({inline:'center',block:'nearest'});}catch(e){}w.scrollTo(0,0);}
function open(){var sheet=ov.firstChild;sheet.innerHTML='';var by={},order=GROUPS.map(function(g){return g[0];}).concat(['Άλλα']);
  tabs().forEach(function(t){var l=label(t);if(!l)return;var g=group(l);
    (by[g]=by[g]||[]).push([l,t.getAttribute('aria-selected')==='true']);});
  order.forEach(function(g){if(!by[g])return;var h=doc.createElement('h4');h.textContent=g;sheet.appendChild(h);
    var grid=doc.createElement('div');grid.className='grid';sheet.appendChild(grid);
    by[g].forEach(function(p){var b=doc.createElement('button');b.className='it'+(p[1]?' on':'');b.textContent=p[0];
      b.onclick=function(){go(p[0]);};grid.appendChild(b);});});
  ov.style.display='block';}
btn.onclick=open;ov.onclick=function(e){if(e.target===ov)ov.style.display='none';};
function sync(){btn.style.display=mq.matches?'block':'none';if(!mq.matches)ov.style.display='none';}
sync();if(mq.addEventListener)mq.addEventListener('change',sync);else mq.addListener(sync);
})();</script>"""


def script():
    return _SCRIPT % {"head": json.dumps(HEAD, ensure_ascii=False), "groups": json.dumps(GROUPS, ensure_ascii=False),
                      "theme": THEME}


def manifest():
    icons = [{"src": f"{STATIC}/icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"} for n in (192, 512)]
    return {"name": TITLE, "short_name": TITLE, "start_url": "/", "scope": "/", "display": "standalone",
            "background_color": "#ffffff", "theme_color": THEME, "icons": icons}


def inject():
    """Call once per rerun, after st.set_page_config. Renders in the sidebar so the main page gets no extra gap."""
    with st.sidebar:
        st.html(CSS)
        components.html(script(), height=0)
