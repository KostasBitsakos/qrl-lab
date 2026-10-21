"""QRL-Lab dashboard: the researcher's single place to talk to the agents, decide, and watch the work.

Run from ~/qrl-lab:  .venv/bin/streamlit run dashboard/app.py
It binds to 127.0.0.1:8501 (see .streamlit/config.toml); reach it from the laptop through an SSH tunnel.

Design rules:
- The dashboard never executes commands typed by the user. It only writes validated rows to .lab/lab.db
  (messages, decisions, stop requests); the coordinator and the launcher act on them.
- Widgets where the researcher types are never inside auto-refreshing fragments, so nothing typed is lost.
"""
import copy
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ["QRL_LAB_DIR"] = ROOT
sys.path.insert(0, os.path.join(ROOT, "tools"))
import modreload  # noqa: E402
import importlib  # noqa: E402
_LOCAL_MODS = ["labdb", "file_view", "replytext", "k8s_view", "prom_view", "web_terminal", "sudo_ui", "race_view", "brain_view",
               "perm_store", "ext_catalog", "summarize_runs", "paper_plots", "paper_build", "uploads", "installed_view", "access", "outage", "models_view", "banners", "sandbox_view", "topology_view", "topology_ui", "exp_view", "exp_figs"]
for _n in _LOCAL_MODS:  # first import so they are in sys.modules, then reload those whose file changed
    importlib.import_module(_n)
modreload.reload_changed(_LOCAL_MODS)
from labdb import DECISIONS, PAPER_REVIEWERS, PAPER_THREAD_TITLE, PAPER_WRITERS, VENUES_TAG, VENUES_THREAD_TITLE, LabDB, LabError, map_choice, paper_requests  # noqa: E402
import file_view  # noqa: E402
import replytext  # noqa: E402
import k8s_view  # noqa: E402
import prom_view  # noqa: E402
import web_terminal  # noqa: E402
import sudo_ui  # noqa: E402
import race_view  # noqa: E402
import brain_view  # noqa: E402
import perm_store  # noqa: E402
import ext_catalog  # noqa: E402
import installed_view  # noqa: E402
import access  # noqa: E402
import outage  # noqa: E402
import term_prompt  # noqa: E402
import banners  # noqa: E402
import sandbox_view  # noqa: E402
import res_view  # noqa: E402
import token_savings  # noqa: E402
import topology_ui  # noqa: E402
import changes_view  # noqa: E402
import models_view  # noqa: E402
import summarize_runs  # noqa: E402
import paper_plots  # noqa: E402
import paper_build  # noqa: E402
import exp_view  # noqa: E402
import exp_figs  # noqa: E402
from uploads import UploadError, attachment_paths  # noqa: E402

LAB = os.path.join(ROOT, ".lab")
DB_PATH = os.path.join(LAB, "lab.db")
EVENTS = os.path.join(LAB, "events.jsonl")
HEARTBEAT = os.path.join(LAB, "bridge_heartbeat")
HEALTH = os.path.join(LAB, "health.json")

# Categorical slots in fixed order (validated reference palette, light mode). Colour follows the agent, never rank.
AGENTS = {
    "coordinator": ("Συντονιστής (Claude Opus)", "#2a78d6", "🧭"),
    "codex": ("Codex (OpenAI)", "#eb6834", "🟠"),
    "codex-quick": ("codex-quick · gpt-6-luna · low", "#f2a07b", "🟠"),
    "codex-reviewer": ("codex-reviewer · gpt-6.1-sol · medium", "#d9480f", "🟠"),
    "codex-researcher": ("codex-researcher · gpt-6.1-sol · medium", "#a8561f", "🟠"),
    "codex-architect": ("codex-architect · gpt-6-astra · high", "#7a2e0e", "🟠"),
    "codex-deputy": ("codex-deputy · gpt-6.1-sol/luna", "#b58900", "🟠"),
    "Explore": ("Explore (Claude Haiku)", "#1baf7a", "🔎"),
    "runner": ("runner (Claude Haiku)", "#eda100", "🏃"),
    "engineer": ("engineer (Claude Sonnet)", "#e87ba4", "🛠️"),
    "scholar": ("scholar (Claude Sonnet)", "#008300", "📚"),
    "writer": ("writer (Claude Sonnet)", "#6250d6", "✍️"),
}
OTHER_COLOR = "#898781"
RESEARCHER = ("Εσύ", "🧑‍🔬")

MSG_STATUS = {
    "new": ("🆕", "νέο — δεν έχει παραδοθεί"),
    "delivered": ("📨", "παραδόθηκε"),
    "acknowledged": ("👀", "το ανέλαβε"),
    "in_progress": ("⏳", "σε εξέλιξη"),
    "waiting_approval": ("✋", "περιμένει έγκρισή σου"),
    "done": ("✅", "ολοκληρώθηκε"),
    "failed": ("❌", "απέτυχε"),
}
KIND_LABEL = {"message": "Μήνυμα", "proposal": "Πρόταση ιδέας", "code_question": "Ερώτηση για τον κώδικα",
              "reply": "απάντηση", "contribution": "συνεισφορά", "status": "ενημέρωση"}
REQ_KIND = {"approval": "Έγκριση", "question": "Ερώτηση", "proposal": "Πρόταση", "info": "Ενημέρωση"}
REQ_SCOPE = {"sim": "προσομοίωση", "real": "πραγματικό cluster", "qpu": "IBM Quantum", "research": "έρευνα",
             "external": "εξωτερικό", "sudo": "sudo", "other": "άλλο"}
REQ_STATE = {"open": ("🟡", "ανοιχτό"), "approved": ("✅", "εγκρίθηκε"), "rejected": ("⛔", "απορρίφθηκε"),
             "changes_requested": ("✏️", "ζητήθηκαν αλλαγές"), "answered": ("💬", "απαντήθηκε"),
             "acknowledged": ("👁️", "το είδες"), "withdrawn": ("↩️", "αποσύρθηκε")}
MODEL_CHOICES = {None: "Αυτόματα", "haiku": "Γρήγορο · Haiku", "sonnet": "Κανονικό · Sonnet", "opus": "Βαθύ · Opus",
                 "codex": "Codex"}
RUN_STATUS = {"starting": ("🔵", "ξεκινά"), "running": ("🟢", "τρέχει"), "done": ("✅", "ολοκληρώθηκε"),
              "failed": ("❌", "απέτυχε"), "stopped": ("⏹️", "διακόπηκε")}

st.set_page_config(page_title="QRL-Lab", page_icon="🧪", layout="wide")

# ---------------------------------------------------------------- access control over Tailscale Serve (tools/access.py)
try:
    _hdrs = st.context.headers
    _req_host = _hdrs.get("Host", "")
except Exception:  # noqa: BLE001 - no request context (tests)
    _hdrs, _req_host = {}, ""
_on_tailnet = bool(web_terminal.tailnet_host(_req_host))
if _on_tailnet:
    _cinfo = access.client_info(_hdrs)
    _allowed, _why = access.check_login(_cinfo)
    if not _allowed:
        access.alert(_cinfo, _why)
        st.error("Δεν επιτρέπεται η πρόσβαση.", icon="🚫")
        st.stop()
if _on_tailnet and st.session_state.get("pin_until", 0) <= time.time():
    try:  # unlock survives F5 / new session: server-side token store keyed by Tailscale login + per-browser cookie
        _exp = access.check_unlock(_cinfo["login"], st.context.cookies.get(access.COOKIE))
    except Exception:  # noqa: BLE001
        _exp = 0
    if _exp:
        st.session_state["pin_until"] = _exp
_unlocked = (not _on_tailnet) or st.session_state.get("pin_until", 0) > time.time()
if st.session_state.get("_set_cookie"):  # one-shot after a successful PIN: store the token in this browser
    _tok = st.session_state.pop("_set_cookie")
    components.html(f"<script>try{{window.parent.document.cookie='{access.COOKIE}={_tok}; max-age={access.UNLOCK_SECONDS}; "
                    f"path=/; SameSite=Strict; Secure';}}catch(e){{}}</script>", height=0)


def pin_form(name):
    """PIN prompt for the dangerous tabs (Terminal, Sudo/permission approvals) over the tailnet."""
    st.warning("Η καρτέλα απαιτεί PIN όταν μπαίνεις από το tailnet.", icon="🔒")
    left = access.locked()
    if left:
        st.error(f"Κλειδωμένο για ακόμη {left // 60 + 1} λεπτά μετά από λάθος PIN.")
        return
    with st.form(f"pin_{name}"):
        pin = st.text_input("PIN", type="password")
        if st.form_submit_button("Ξεκλείδωμα"):
            ok_, msg = access.try_pin(pin, _cinfo)
            if ok_:
                tok_, exp_ = access.issue_unlock(_cinfo["login"])
                st.session_state["pin_until"] = exp_
                st.session_state["_set_cookie"] = tok_
                st.rerun()
            st.error(msg)


# ---------------------------------------------------------------- helpers
def db():
    return LabDB(DB_PATH)


def parse_ts(s):
    try:
        return dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def fmt_ts(s):
    t = parse_ts(s) if isinstance(s, str) else s
    return t.astimezone().strftime("%d/%m %H:%M") if t else "—"


def ago(seconds):
    if seconds is None:
        return "ποτέ"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} δευτ."
    if seconds < 3600:
        return f"{seconds // 60} λεπτά"
    if seconds < 86400:
        return f"{seconds // 3600} ώρες"
    return f"{seconds // 86400} μέρες"


def since(s):
    t = parse_ts(s)
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() if t else None


def author_info(author):
    if author == "researcher":
        return RESEARCHER[0], RESEARCHER[1]
    if author in AGENTS:
        return AGENTS[author][0], AGENTS[author][2]
    if author.startswith("agent:"):
        key = author.split(":", 1)[1]
        if key in AGENTS:
            return AGENTS[key][0], AGENTS[key][2]
        return f"{key} (Claude)", "🛠️"
    return author, "🤖"


def agent_key(agent_type):
    if not agent_type:
        return "coordinator"
    a = str(agent_type)
    if a in AGENTS:
        return a
    if "codex" in a.lower():
        return "codex"
    return a if a in AGENTS else a


def bridge_age():
    try:
        with open(HEARTBEAT) as f:
            return time.time() - float(f.read().strip() or 0)
    except (OSError, ValueError):
        return None


def read_events(max_lines=6000):
    if not os.path.exists(EVENTS):
        return pd.DataFrame(columns=["ts", "agent", "event", "tool", "summary"])
    with open(EVENTS, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 3_000_000))
        lines = f.read().decode("utf-8", "ignore").splitlines()[-max_lines:]
    rows, raw = [], []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw.append(e)
        rows.append({"ts": dt.datetime.fromtimestamp(e.get("ts", 0)), "agent": agent_key(e.get("agent_type")),
                     "agent_id": e.get("agent_id"), "event": e.get("hook_event_name", ""),
                     "tool": e.get("tool_name", ""), "summary": e.get("summary", ""),
                     "model": e.get("model", ""), "effort": e.get("effort", ""), "status": e.get("status", "")})
    df = pd.DataFrame(rows)
    ann = race_view.annotate(raw)  # (one-word task label, task group) per event
    df["label"] = [a[0] for a in ann]
    df["group"] = [a[1] for a in ann]
    return df


def agent_spans(ev):
    """One row per subagent run (SubagentStart paired with its SubagentStop by agent_id): role, model, task, duration, status."""
    rows, open_ = [], {}
    if ev.empty:
        return pd.DataFrame(columns=["start", "agent", "model", "effort", "task", "seconds", "status"])
    for _, e in ev[ev["event"].isin(["SubagentStart", "SubagentStop"]) & ev["agent_id"].notna()].iterrows():
        if e["event"] == "SubagentStart":
            row = {"start": e["ts"], "agent": e["agent"], "model": e["model"], "effort": e["effort"],
                   "task": e["summary"], "seconds": None, "status": "running"}
            open_[e["agent_id"]] = row
            rows.append(row)
        elif e["agent_id"] in open_:
            row = open_.pop(e["agent_id"])
            row["seconds"] = (e["ts"] - row["start"]).total_seconds()
            row["status"] = e["status"] or "done"
    return pd.DataFrame(rows, columns=["start", "agent", "model", "effort", "task", "seconds", "status"])


def active_agent_keys(ev):
    """Agents with a SubagentStart not yet matched by a SubagentStop; the coordinator is always first."""
    active_ids = {}
    for _, e in ev[ev["event"].isin(["SubagentStart", "SubagentStop"])].iterrows() if not ev.empty else []:
        if e["agent_id"]:
            if e["event"] == "SubagentStart":
                active_ids[e["agent_id"]] = e
            else:
                active_ids.pop(e["agent_id"], None)
    return ["coordinator"] + sorted({e["agent"] for e in active_ids.values()} - {"coordinator"})


def read_health(max_age=90):
    """health.json written by tools/health_watch.py; None when missing or stale (the watcher is not running)."""
    try:
        with open(HEALTH, encoding="utf-8") as f:
            h = json.load(f)
        return h if time.time() - float(h.get("checked", 0)) <= max_age else None
    except (OSError, ValueError):
        return None


def health_banner_text(h, now=None):
    """Exact Greek message for a health state, or None when everything is fine."""
    if not h or h.get("state") in (None, "ok"):
        return None
    when = (h.get("detail") or "").strip()
    st_ = h["state"]
    if st_ == "limit":
        tz = "" if "(" in when else " (ώρα VM)"
        msg = ("⛔ Ο συντονιστής σταμάτησε: όριο χρήσης Claude"
               + (f" — ξαναρχίζει {when}{tz}" if when else " — δεν βρέθηκε ώρα επαναφοράς, δες το terminal"))
    elif st_ == "permission":
        msg = "🔐 Περιμένει άδεια στο terminal: tmux attach -t lab"
    elif st_ == "down":
        msg = "📴 Ο συντονιστής δεν τρέχει"
    elif st_ == "api_error":
        msg = "⚠️ Σφάλμα API / υπερφόρτωση στον συντονιστή" + (f": «{h['line'][:150]}»" if h.get("line") else "")
    else:
        return None
    sec = (now if now is not None else time.time()) - float(h.get("since", 0) or 0)
    return f"{msg} · εδώ και {ago(max(0, int(sec)))}"


def codex_banner_text(h, now=None):
    """Exact Greek message for the Codex state (health.json key `codex`), or None when Codex is fine/unknown."""
    c = (h or {}).get("codex") or {}
    if c.get("state") != "limit":
        return None
    when = (c.get("detail") or "").strip()
    tz = "" if "(" in when else " (ώρα VM)"
    msg = ("⛔ Codex: όριο χρήσης"
           + (f" — ξαναρχίζει {when}{tz}" if when else " — δεν βρέθηκε ώρα επαναφοράς")
           + " · οι ρόλοι Codex περνούν σε πράκτορες Claude")
    sec = (now if now is not None else time.time()) - float(c.get("since", 0) or 0)
    return f"{msg} · εδώ και {ago(max(0, int(sec)))}"


def deadlines_table_html(rows):
    """Wrapping HTML table (fixed layout, no overflow at phone width). All values are escaped."""
    import html as _h
    cols = list(rows[0]) if rows else []
    css = ("<style>.dl{width:100%;table-layout:fixed;border-collapse:collapse;font-size:.85rem}"
           ".dl th,.dl td{border-bottom:1px solid rgba(128,128,128,.3);padding:4px 6px;text-align:left;vertical-align:top;"
           "overflow-wrap:anywhere;word-break:break-word}.dl th{opacity:.7}</style>")
    head = "".join(f"<th>{_h.escape(c)}</th>" for c in cols)
    body = ""
    for r in rows:
        cells = ""
        for c in cols:
            v = _h.escape(str(r[c]))
            if c == "πηγή" and str(r[c]).startswith(("http://", "https://")):
                v = f'<a href="{_h.escape(str(r[c]), quote=True)}" target="_blank" rel="noopener">{v}</a>'
            cells += f"<td>{v}</td>"
        body += f"<tr>{cells}</tr>"
    return f'{css}<div style="overflow-x:auto"><table class="dl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


# ---------------------------------------------------------------- sidebar (auto-refresh)
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 170" width="100%" role="img" aria-label="Πάρις">'
    '<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b3a7a"/>'
    '<stop offset=".55" stop-color="#e8708a"/><stop offset="1" stop-color="#ffd27a"/></linearGradient>'
    '<linearGradient id="sea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1fa3c4"/>'
    '<stop offset="1" stop-color="#0b3f73"/></linearGradient>'
    '<linearGradient id="sand" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f4d58b"/>'
    '<stop offset="1" stop-color="#c99a4b"/></linearGradient>'
    '<linearGradient id="ttl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff6d6"/>'
    '<stop offset="1" stop-color="#ffc24a"/></linearGradient></defs>'
    '<rect width="260" height="170" rx="14" fill="url(#sky)"/>'
    '<circle cx="206" cy="58" r="22" fill="#fff1b0" opacity=".95"/><circle cx="206" cy="58" r="30" fill="#fff1b0" opacity=".25"/>'
    '<g fill="#fff" opacity=".7"><ellipse cx="60" cy="26" rx="22" ry="5"/><ellipse cx="78" cy="22" rx="14" ry="4"/>'
    '<ellipse cx="170" cy="20" rx="18" ry="4"/></g>'
    '<rect y="92" width="260" height="78" fill="url(#sea)"/>'
    '<g stroke="#bff0ff" stroke-width="1.6" fill="none" opacity=".7" stroke-linecap="round">'
    '<path d="M20 104 q8 -4 16 0 t16 0"/><path d="M170 112 q8 -4 16 0 t16 0"/><path d="M110 100 q8 -4 16 0 t16 0"/></g>'
    '<path d="M28 100 Q70 76 130 84 Q172 88 196 100 Q120 112 28 100Z" fill="url(#sand)"/>'
    '<path d="M60 96 Q64 56 92 30" stroke="#6b3f17" stroke-width="5" fill="none" stroke-linecap="round"/>'
    '<path d="M92 30 Q70 14 44 28 Q66 22 90 34Z M92 30 Q82 6 60 4 Q82 14 90 32Z M92 30 Q110 6 134 12 Q108 14 94 34Z'
    ' M92 30 Q122 24 140 44 Q112 32 94 36Z M92 30 Q100 12 96 -2 Q92 18 90 32Z" fill="#1f9d55"/>'
    '<circle cx="90" cy="38" r="3.4" fill="#6b3f17"/><circle cx="96" cy="39" r="3.4" fill="#5a3412"/>'
    '<g fill="#8a5a22" opacity=".9"><ellipse cx="150" cy="92" rx="4" ry="6.5" transform="rotate(-18 150 92)"/>'
    '<circle cx="143" cy="83" r="1.8"/><circle cx="148" cy="81.5" r="1.8"/><circle cx="153" cy="82" r="1.8"/>'
    '<circle cx="157.5" cy="84" r="1.8"/>'
    '<ellipse cx="170" cy="98" rx="4" ry="6.5" transform="rotate(18 170 98)"/>'
    '<circle cx="163" cy="89" r="1.8"/><circle cx="168" cy="87.5" r="1.8"/><circle cx="173" cy="88" r="1.8"/>'
    '<circle cx="177.5" cy="90" r="1.8"/></g>'
    '<text x="130" y="152" text-anchor="middle" font-family="Georgia,\'Palatino Linotype\',serif" font-size="46" '
    'font-weight="bold" font-style="italic" letter-spacing="2" fill="#0b2a52" opacity=".55" transform="translate(2 3)">Πάρις</text>'
    '<text x="130" y="152" text-anchor="middle" font-family="Georgia,\'Palatino Linotype\',serif" font-size="46" '
    'font-weight="bold" font-style="italic" letter-spacing="2" fill="url(#ttl)" stroke="#7a3d00" stroke-width=".8">Πάρις</text>'
    '</svg>')


def _tab_live(t):
    """Hidden tabs skip their body (tab.open is False); None = state untracked. QRL_EAGER_TABS=1 renders all (tests)."""
    return bool(os.environ.get("QRL_EAGER_TABS")) or t.open is not False


HOME_TAB = "💬 Συνομιλία"


# Logo = plain anchor to "./" (resolves to the app root, so ?tab=/?path= are dropped and the chat tab opens). A full
# page load is deliberate: it is the one mechanism that works for every client (phone, tailnet) and clears all params.
st.sidebar.markdown(f'<a href="./" target="_self" title="Αρχική" style="display:block;width:100%;max-width:250px;'
                    f'margin:0 auto 6px;cursor:pointer">{LOGO_SVG}</a>', unsafe_allow_html=True)
st.sidebar.markdown("### 🧪 QRL-Lab")
_recent_denied = access.recent(1, max_age=3600)
if _recent_denied:
    st.sidebar.error(f"🛡️ Απορρίφθηκε πρόσβαση ({_recent_denied[0].get('reason')}) · login: "
                     f"{_recent_denied[0].get('login') or '(κανένα)'} · δες Sudo → Πρόσβαση", icon="🚨")
# No page-level refresh timer and no slider: only small @st.fragment(run_every=...) blocks update themselves, so the
# page never reruns as a whole (no grey-out). Heavy loads live in tabs that render only while open (tab.open).
refresh = 5
st.html("<style>@media (min-width:769px){[data-testid=stSidebar][aria-expanded=true]{min-width:350px!important;"
        "width:350px!important}}</style>")
# Tabs wrap onto extra rows instead of scrolling sideways on narrow screens (researcher, M-20261020-009). The sliding
# Streamlit 1.66 tabs are react-aria: [data-testid=stTabs] [role=tablist] > [data-testid=stTab].
st.html("<style>[data-testid=stTabs] [role=tablist]{flex-wrap:wrap!important;overflow-x:visible!important;"
        "row-gap:2px;column-gap:14px}"
        "@media (max-width:768px){.block-container{padding-left:.6rem!important;padding-right:.6rem!important}"
        "[data-testid=stTabs] [role=tablist]{column-gap:8px}[data-testid=stTab]{font-size:.85rem}"
        "[data-testid=stHorizontalBlock]{flex-wrap:wrap!important}"
        "[data-testid=stHorizontalBlock]>[data-testid=stColumn]{min-width:calc(50% - 1rem)!important}"
        "[data-testid=stDataFrame],[data-testid=stTable],iframe{max-width:100%!important}"
        ".stMarkdown table{display:block;overflow-x:auto}}</style>")


@st.fragment(run_every=refresh)
def sidebar_status():
    d = db()
    age = bridge_age()
    online = age is not None and age < 20
    if online:
        st.success("Συντονιστής online", icon="🟢")
    else:
        st.error(f"Συντονιστής offline (τελευταίο σήμα: {ago(age)} πριν). Τα μηνύματα μένουν στην ουρά "
                 "και παραδίδονται όταν ξαναξεκινήσει.", icon="🔴")
    open_reqs = d.requests(state="open")
    blocking = sum(1 for r in open_reqs if r["blocking"])
    waiting_msgs = d.researcher_open()
    c1, c2 = st.columns(2)
    c1.metric("Αποφάσεις", len(open_reqs), help="Ανοιχτά αιτήματα προς εσένα")
    c2.metric("Σε εξέλιξη", len(waiting_msgs), help="Δικά σου μηνύματα χωρίς τελική απάντηση")
    if blocking:
        st.warning(f"{blocking} αίτημα(τα) μπλοκάρουν τη δουλειά — καρτέλα «Αποφάσεις».", icon="✋")
    ev = read_events(400)
    if not ev.empty:
        recent = ev[ev["ts"] > dt.datetime.now() - dt.timedelta(minutes=10)]
        notif = recent[recent["event"] == "Notification"]
        if read_health() is None and not notif.empty and "permission" in str(notif.iloc[-1]["summary"]).lower():
            st.warning("Ο συντονιστής περιμένει άδεια στο terminal/app: " + str(notif.iloc[-1]["summary"]),
                       icon="🔐")
        ev = ev[ev["event"] != "HealthState"]
        if not ev.empty:
            last = ev.iloc[-1]
            st.caption(f"Τελευταία δραστηριότητα: {AGENTS.get(last['agent'], (last['agent'],))[0]} · "
                       f"{ago((dt.datetime.now() - last['ts']).total_seconds())} πριν")
    # toasts for new items since the last refresh of this browser session
    n_agent_msgs = d.conn.execute("SELECT COUNT(*) FROM messages WHERE author!='researcher'").fetchone()[0]
    prev = st.session_state.get("_seen", None)
    if prev is not None:
        if n_agent_msgs > prev[0]:
            st.toast("Νέα απάντηση από τους πράκτορες", icon="💬")
        if len(open_reqs) > prev[1]:
            st.toast("Νέο αίτημα για απόφαση", icon="✋")
    st.session_state["_seen"] = (n_agent_msgs, len(open_reqs))
    st.caption(f"Βάση: `{os.path.relpath(DB_PATH, ROOT)}` · {dt.datetime.now().strftime('%H:%M:%S')}")
    d.close()


with st.sidebar:
    sidebar_status()


def _brain_state():
    """Brain state from real logs only (events.jsonl incl. agent_log entries, labdb messages)."""
    try:
        dd = db()
        rows = dd.conn.execute("SELECT ts, author, title, body FROM messages WHERE author!='researcher' "
                               "ORDER BY ts DESC LIMIT 20").fetchall()
        dd.close()
        msgs = [{"ts": r[0], "author": r[1], "title": r[2], "body": r[3]} for r in rows]
    except Exception:  # noqa: BLE001 - display only
        msgs = []
    return brain_view.derive(race_view.load_events(EVENTS, max_lines=1500), msgs, time.time())


@st.fragment(run_every=3)
def sidebar_brain():
    """Identical HTML when idle and no pulse is running, so the iframe is not reloaded (no flicker)."""
    components.html(brain_view.render(_brain_state()), height=255)


with st.sidebar:
    sidebar_brain()

# ---------------------------------------------------------------- system banners (every tab), each with a server-side «✕»
def dismissible(bid, key, text, kind="error"):
    """Show `text` with a ✕ button; the dismissal is stored in .lab/dismissed_banners.json (keyed by banner id + event key)."""
    if key is None or banners.is_dismissed(bid, key):
        return False
    c = st.columns([30, 1])
    getattr(c[0], kind)(text)
    if c[1].button("✕", key=f"dismiss_{bid}", help="Απόκρυψη (ξαναεμφανίζεται μόνο για νέο συμβάν)"):
        banners.dismiss(bid, key)
        st.rerun(scope="fragment")
    return True


@st.fragment(run_every=refresh)
def health_banner():
    h = read_health()
    txt = health_banner_text(h)
    if txt:
        shown = dismissible("health", f"{h.get('state')}:{h.get('since')}", txt)
        if shown and h.get("state") == "permission":
            try:
                n = len(perm_store.pending())
            except Exception:
                n = 0
            st.caption(f"Αίτημα Sudo στο perm_store: {'ναι (' + str(n) + ')' if n else 'όχι — πιθανό ψευδής συναγερμός ή άδεια του terminal'}")
            if h.get("prompt_text"):
                with st.expander("Κείμενο που εντοπίστηκε"):
                    st.code(h["prompt_text"], language=None)
    ctxt = codex_banner_text(h)
    if ctxt:
        dismissible("codex", f"limit:{((h or {}).get('codex') or {}).get('since')}", ctxt)


health_banner()


@st.fragment(run_every=refresh)
def recovery_banner():
    txt = outage.banner_text()
    if txt:
        dismissible("reboot", banners.reboot_key(), txt, kind="warning")


recovery_banner()

# ---------------------------------------------------------------- shared decision widget (Decisions + Paper tabs)
def decision_panel(d, select=lambda reqs: reqs, pre="", label="Αίτημα",
                   empty_msg="Δεν υπάρχει τίποτα που να περιμένει απόφασή σου."):
    """One open request at a time with options/proposals and approve/reject/changes + note. Same code path (d.decide,
    actor='researcher') for every tab; `pre` only prefixes widget keys so two tabs never clash."""
    _sel0 = select

    def select(reqs):  # sudo-scope approvals need the PIN over the tailnet
        r_ = _sel0(reqs)
        return r_ if _unlocked else [x for x in r_ if x["scope"] != "sudo"]
    # Live check, outside the form: only compares the set of open request ids with the one rendered; it never touches
    # the form widgets, so unsaved typing is never lost. A full rerun (button) keeps widget state by key.
    @st.fragment(run_every=5)
    def new_request_badge(shown_ids):
        dd = db()
        now_ids = sorted(r["id"] for r in select(dd.requests(state="open")))
        dd.close()
        if now_ids != sorted(shown_ids):
            fresh = len(set(now_ids) - set(shown_ids))
            c = st.columns([3, 2])
            c[0].warning(f"🔔 νέο αίτημα ({fresh} νέα · {len(now_ids)} ανοιχτά συνολικά)", icon=None)
            if c[1].button("Φόρτωση", key=f"{pre}dec_reload"):
                st.rerun()
    # oldest blocking request first, then the oldest overall; one at a time
    open_reqs = sorted(select(d.requests(state="open")), key=lambda r: (-r["blocking"], r["ts"]))
    new_request_badge([r["id"] for r in open_reqs])
    if not open_reqs:
        st.success(empty_msg, icon="✅")
    else:
        N = len(open_reqs)
        idx = min(max(int(st.session_state.get(f"{pre}dec_idx", 0)), 0), N - 1)
        st.session_state[f"{pre}dec_idx"] = idx
        nav = st.columns([1, 2, 1, 4])
        if nav[0].button("◀ Προηγούμενο", key=f"{pre}dec_prev", disabled=idx == 0):
            st.session_state[f"{pre}dec_idx"] = idx - 1
            st.rerun()
        nav[1].markdown(f"**{label} {idx + 1} από {N}**")
        if nav[2].button("Επόμενο ▶", key=f"{pre}dec_next", disabled=idx >= N - 1):
            st.session_state[f"{pre}dec_idx"] = idx + 1
            st.rerun()
        r = open_reqs[idx]
        with st.container(border=True):
            badges = f"**{REQ_KIND[r['kind']]}** · {REQ_SCOPE.get(r['scope'], r['scope'])}"
            if r["blocking"]:
                badges += " · ✋ **μπλοκάρει τη δουλειά**"
            st.markdown(f"#### {r['title']}")
            st.caption(f"{badges} · `{r['id']}` · {fmt_ts(r['ts'])} · από {author_info(r['author'])[0]}"
                       + (f" · κόστος: {r['cost']}" if r["cost"] else ""))
            st.markdown(r["body"])
            links = json.loads(r["links"] or "[]")
            for link in links:
                p = os.path.join(ROOT, link)
                txt = read_text(p) if os.path.isfile(p) else None
                with st.expander(f"📎 {link}"):
                    st.markdown(txt if txt is not None else "_(δεν βρέθηκε το αρχείο)_")
            if r["spec_path"]:
                with st.expander("🧾 Run spec που θα εγκρίνεις (κλειδωμένο)"):
                    st.code(read_text(r["spec_path"]) or "(missing)", language="json")
                    st.caption(f"sha256: `{r['spec_hash']}` — αν αλλάξει το spec, η έγκριση ακυρώνεται.")
            options = json.loads(r["options"])
            props = json.loads(r.get("proposals") or "[]")
            with st.form(f"{pre}decide_{r['id']}"):
                if options == ["ack"]:
                    choice = "ack"
                    note = st.text_area("Σχόλιο (προαιρετικό)", key=f"{pre}note_{r['id']}", height=80)
                    pressed = "ack" if st.form_submit_button("👁️ Το είδα") else None
                else:
                    choices, names = [], {}
                    for i, ptxt in enumerate(props, 1):
                        star = " ⭐ (προτείνεται)" if r.get("recommended") == i else ""
                        choices.append(f"p{i}"); names[f"p{i}"] = f"Πρόταση {i}: {ptxt}{star}"
                    if "approve" in options:
                        choices.append("yes"); names["yes"] = "Ναι / έγκριση"
                    if "reject" in options:
                        choices.append("no"); names["no"] = "Όχι / απόρριψη"
                    if "changes" in options or "answer" in options:
                        choices.append("own"); names["own"] = "Δική μου πρόταση"
                    choice = st.radio("Η απόφασή σου", choices, index=None, format_func=names.get,
                                      key=f"{pre}choice_{r['id']}")
                    note = st.text_area("Σχόλιο — ή η δική σου πρόταση (υποχρεωτικό αν διάλεξες «Δική μου πρόταση»)",
                                        key=f"{pre}note_{r['id']}", height=100)
                    sent = st.form_submit_button("Υποβολή απόφασης", type="primary")
                    pressed = choice if sent else None
                    if sent and not choice:
                        st.error("Διάλεξε μία επιλογή.")
                        pressed = None
            if pressed:
                try:
                    if pressed == "ack":
                        dec, text = "ack", note
                    else:
                        dec, text = map_choice(r, pressed, note)
                    state = d.decide(r["id"], dec, text, actor="researcher")
                    st.toast(f"{r['id']}: {REQ_STATE[state][1]}", icon=REQ_STATE[state][0])
                    st.rerun()
                except LabError as e:
                    st.error(str(e))

# ---------------------------------------------------------------- shared chat rendering
def render_message(m, key="chat"):
    """The ONLY place a chat message is rendered (author, body, ✏️ inline edit, attachments)."""
    name, avatar = author_info(m["author"])
    with st.chat_message("user" if m["author"] == "researcher" else "assistant", avatar=avatar):
        extra = ""
        if m["author"] == "researcher" and m["status"]:
            si, sl = MSG_STATUS.get(m["status"], ("", m["status"]))
            extra = f" · {si} {sl}"
            if m.get("req_model") or m.get("req_effort") not in (None, "med"):
                extra += f" · 🎛️ {m.get('req_model') or 'auto'}/{m.get('req_effort') or 'med'}"
        label = f"{name} · {m['model']}" if m.get("model") else name
        st.caption(f"**{label}** · {fmt_ts(m['ts'])} · {KIND_LABEL.get(m['kind'], m['kind'])}"
                   f"{extra} · `{m['id']}`")
        ekey = f"editing_{key}_{m['id']}"
        if m["author"] == "researcher" and st.session_state.get(ekey):
            # editing in place: keyed widgets keep their text across the fragment's auto-refresh
            new_txt = st.text_area("Νέο κείμενο", value=m["body"], key=f"edit_txt_{key}_{m['id']}",
                                   height=140, label_visibility="collapsed")
            if m["body"].find("docs/uploads/") >= 0:
                st.caption("Κράτα τις γραμμές με τις διαδρομές των συνημμένων στο κείμενο.")
            b1, b2, _b3 = st.columns([1, 1, 6])
            if b1.button("Αποθήκευση", key=f"edit_save_{key}_{m['id']}", type="primary"):
                try:
                    de = db()
                    changed = de.edit_message(m["id"], new_txt)
                    de.close()
                    st.session_state[ekey] = False
                    st.toast("Αποθηκεύτηκε· ο συντονιστής ειδοποιείται" if changed else "Καμία αλλαγή",
                             icon="✏️")
                    st.rerun()
                except LabError as e:
                    st.error(str(e))
            if b2.button("Άκυρο", key=f"edit_cancel_{key}_{m['id']}"):
                st.session_state[ekey] = False
                st.session_state.pop(f"edit_txt_{key}_{m['id']}", None)
                st.rerun()
        else:
            shown = (replytext.readable(m["body"])[0] if m["author"] != "researcher"
                     else ext_catalog.strip_instruction(m["body"]))
            st.markdown(file_view.linkify(shown))  # render-time only; stored text unchanged
            if m["author"] == "researcher" and st.button("✏️", key=f"edit_btn_{key}_{m['id']}",
                                                         help="Επεξεργασία του μηνύματος"):
                st.session_state[ekey] = True
                st.rerun()
        if m.get("edit_count"):
            st.caption(f"(επεξεργάστηκε) · {fmt_ts(m['edited_at'])}")
        for ap in attachment_paths(m["body"]):
            full = os.path.realpath(os.path.join(ROOT, ap))
            up_root = os.path.realpath(os.path.join(ROOT, "docs", "uploads"))
            if full.startswith(up_root + os.sep) and os.path.isfile(full):
                ac1, ac2 = st.columns([1, 1])
                ac1.download_button(f"⬇️ {os.path.basename(full)}", lambda p=full: open(p, "rb").read(),
                                    file_name=os.path.basename(full), key=f"dl_{key}_{m['id']}_{ap}")
                ac2.markdown(f"[📁 Αρχεία]({file_view.deep_link(full)})")


def rename_widget(tid, current, key):
    """✏️ -> inline text input + Save/Cancel; researcher-only (no labq command)."""
    ek = f"renaming_{key}_{tid}"
    if st.session_state.get(ek):
        nt = st.text_input("Νέος τίτλος", value=current, key=f"rn_txt_{key}_{tid}", label_visibility="collapsed")
        b1, b2, _ = st.columns([1, 1, 6])
        if b1.button("Αποθήκευση", key=f"rn_save_{key}_{tid}", type="primary"):
            try:
                dr = db()
                dr.rename_thread(tid, nt)
                dr.close()
                st.session_state[ek] = False
                st.rerun()
            except LabError as e:
                st.error(str(e))
        if b2.button("Άκυρο", key=f"rn_cancel_{key}_{tid}"):
            st.session_state[ek] = False
            st.session_state.pop(f"rn_txt_{key}_{tid}", None)
            st.rerun()
        return True
    return False


@st.fragment(run_every=refresh)
def show_thread(tid, key="chat", title=None):
    dd = db()
    msgs = dd.thread(tid)
    dd.close()
    if not msgs:
        return
    root = msgs[0]
    icon, label = MSG_STATUS.get(root["status"] or "", ("", ""))
    first = (root["title"] or (root["body"] or "").strip().splitlines()[0])[:80] if root["body"] else tid
    hc1, hc2 = st.columns([12, 1])
    hc1.markdown(f"**{title or 'Κύρια συζήτηση'}** · {first} · `{tid}` · {icon} {label}")
    if not st.session_state.get(f"renaming_{key}_{tid}") and hc2.button(
            "✏️", key=f"rn_btn_{key}_{tid}", help="Μετονομασία θέματος"):
        st.session_state[f"renaming_{key}_{tid}"] = True
        st.rerun()
    rename_widget(tid, root["title"] or first, key)
    with st.container(height=480):  # oldest first, newest at the bottom
        for m in msgs:
            render_message(m, key)
        st.html("<div id='chat-end'></div>")
    for m in msgs:
        if m["author"] == "researcher" and m["status"] == "delivered" and (since(m["updated_at"]) or 0) > 180:
            st.info(f"Το {m['id']} παραδόθηκε αλλά ο συντονιστής δεν το έχει αναλάβει ακόμη "
                    "(απασχολημένος, offline ή σε όριο χρήσης).", icon="⏳")
            break


# ---------------------------------------------------------------- global banner: pending terminal permission requests
SUDO_TAB = "🔐 Sudo"


def _go_sudo():
    st.session_state["tab"] = SUDO_TAB


def term_prompt_panel(where, unlocked):
    """Answer the coordinator's terminal permission dialog (tools/term_prompt.py, R-20261019-002)."""
    h = read_health() or {}
    if h.get("state") != "permission" or not h.get("prompt_text") or perm_store.pending():
        return
    txt = h["prompt_text"]
    ph = term_prompt.prompt_hash(txt)
    with st.container(border=True):
        st.warning("Το terminal του συντονιστή περιμένει απάντηση (δεν υπάρχει αίτημα στο Sudo):", icon="⌨️")
        st.code(txt, language=None)
        if not unlocked:
            pin_form(f"term_{where}")
            return
        c = st.columns(2)
        who = _cinfo.get("login", "?") if _on_tailnet else "local"
        if c[0].button("Έγκριση", key=f"term_ok_{where}", type="primary"):
            st.session_state["_term_msg"] = term_prompt.answer("approve", ph, who, True)[1]
            st.rerun()
        if c[1].button("Απόρριψη", key=f"term_no_{where}"):
            st.session_state["_term_msg"] = term_prompt.answer("deny", ph, who, True)[1]
            st.rerun()
    if st.session_state.get("_term_msg"):
        st.info(st.session_state.pop("_term_msg"))


@st.fragment(run_every=3)
def perm_banner():
    pend = perm_store.pending()
    if not pend:
        term_prompt_panel("banner", (not _on_tailnet) or st.session_state.get("pin_until", 0) > time.time())
        return
    unlocked = (not _on_tailnet) or st.session_state.get("pin_until", 0) > time.time()
    with st.container(border=True):
        for pr in pend:
            left = max(0, int(90 - (time.time() - pr["ts"])))
            st.error(f"🔐 Ο συντονιστής ζητά άδεια: {pr['description']} — απομένουν ~{left} δευτ.", icon="🔐")
            if unlocked:
                st.code(pr["detail"] or "(κενό)", language="bash" if pr["tool"] == "Bash" else "text")
                c = st.columns(3)
                if c[0].button("Έγκριση", key=f"banner_ok_{pr['id']}", type="primary"):
                    perm_store.decide(pr["id"], True)
                    st.rerun()
                if c[1].button("Απόρριψη", key=f"banner_no_{pr['id']}"):
                    perm_store.decide(pr["id"], False, "Απορρίφθηκε από τον ερευνητή στο dashboard.")
                    st.rerun()
                c[2].button("Άνοιγμα καρτέλας Sudo", key=f"banner_go_{pr['id']}", on_click=_go_sudo)
        if not unlocked:
            pin_form("banner")


perm_banner()
# ---------------------------------------------------------------- tabs
d0 = db()
n_open = len(d0.requests(state="open"))
d0.close()
FILES_TAB = "📁 Αρχεία"
# Constant label: a changing label (e.g. a request count) makes Streamlit treat it as a new tab and jump to the first.
DEC_TAB = "✅ Αποφάσεις"
# Deep link ?path=...: on the first run of a session with that parameter the Αρχεία tab opens first.
_open_files = "path" in st.query_params and not st.session_state.get("fb_tab_done")
st.session_state["fb_tab_done"] = True
TAB_NAMES = [HOME_TAB, DEC_TAB, "🤖 Πράκτορες", "📈 Πειράματα", "⚖️ Council",
             "🖥️ Πόροι", "☸️ Kubernetes", "📡 Prometheus", "📊 Grafana", FILES_TAB, "📝 Paper", "🎓 Συνέδρια", "🧾 Ιστορικό", "🔐 Sudo", "🧩 Επεκτάσεις", "🔌 Διακοπές", "🧭 Ιστορικό αλλαγών", "🧠 Μοντέλα", "🏛️ Αρχιτεκτονική", "⌨️ Terminal"]
# Tab persistence (F5 / shared link): st.tabs(key="tab", bind="query-params") in Streamlit 1.66 keeps the active
# label in ?tab=... and restores it on load; ?path=... (file deep link) only picks the default when ?tab is absent.
# The default is part of the tabs widget identity: it must stay the same on every rerun of the session, otherwise the first
# widget interaction after a deep link changes the identity and Streamlit resets the active tab to the first one.
if "tab_default" not in st.session_state:
    st.session_state["tab_default"] = FILES_TAB if (_open_files and "tab" not in st.query_params) else None
_tab_default = st.session_state["tab_default"]
_term_url = web_terminal.iframe_url(_req_host) if (web_terminal.running() and _unlocked) else ""
_side = bool(_term_url) and st.sidebar.toggle("Terminal στα δεξιά", key="term_side")
if _side:  # tabs in the left column, the terminal in a right-hand column
    _left, _right = st.columns([3, 2])
    with _right:
        st.iframe(_term_url, height=700)
    with _left:
        (tab_chat, tab_dec, tab_agents, tab_runs, tab_council, tab_res, tab_k8s, tab_prom, tab_grafana, tab_files, tab_paper, tab_venues,
         tab_audit, tab_sudo, tab_ext, tab_outage, tab_changes, tab_models, tab_arch, tab_term) = st.tabs(TAB_NAMES, default=_tab_default, key="tab", bind="query-params")
else:
    (tab_chat, tab_dec, tab_agents, tab_runs, tab_council, tab_res, tab_k8s, tab_prom, tab_grafana, tab_files, tab_paper, tab_venues,
     tab_audit, tab_sudo, tab_ext, tab_outage, tab_changes, tab_models, tab_arch, tab_term) = st.tabs(TAB_NAMES, default=_tab_default, key="tab", bind="query-params")

# ================================================================ conversation
with tab_chat:
    d = db()
    threads = d.threads(limit=100)
    d.close()
    ids = [t["thread_id"] for t in threads]
    by_id = {t["thread_id"]: t for t in threads}
    # Default rule: the thread whose latest message is newest (threads() is ordered by that); none yet -> the first
    # message sent creates «Κύρια συζήτηση».
    if "pending_thread" in st.session_state:
        st.session_state["thread_sel"] = st.session_state.pop("pending_thread")
    if st.session_state.get("thread_sel") not in ids:
        st.session_state["thread_sel"] = ids[0] if ids else None
    cur = st.session_state["thread_sel"]

    def thread_label(tid):
        t = by_id[tid]
        icon = MSG_STATUS.get(t["root_status"] or "", ("💬", ""))[0]
        fb = (t["first_body"] or "").strip()
        first = (t["title"] or (fb.splitlines()[0] if fb else ""))[:60]
        return f"{icon} {first}  ·  {fmt_ts(t['last'])}"

    def _leave_new_topic():
        st.session_state["new_topic"] = False

    top_l, top_r = st.columns([5, 1])
    with top_l:
        with st.expander(f"📚 Θέματα ({len(ids)})"):
            if ids:
                st.html("<style>.st-key-thread_list button{justify-content:flex-start;text-align:left;"
                        "min-height:0;padding:1px 8px;line-height:1.2}"
                        ".st-key-thread_list button div,.st-key-thread_list button p{justify-content:flex-start;"
                        "text-align:left;width:100%;font-size:0.85rem;margin:0}"
                        ".st-key-thread_list [data-testid=stVerticalBlock]{gap:2px}</style>")
                _q = st.text_input("🔎 Αναζήτηση θέματος (τίτλος ή περιεχόμενο)", key="thread_search",
                                   placeholder="π.χ. preflight, logo, Tailscale")
                _shown = ids
                if _q.strip():
                    _d = db()
                    _hits = _d.search_threads(_q)
                    _d.close()
                    _shown = [t for t in ids if t in _hits or _q.strip().lower() in thread_label(t).lower()]
                    st.caption(f"{len(_shown)} από {len(ids)} θέματα")
                with st.container(height=260, key="thread_list"):
                    for tid_ in _shown:
                        if rename_widget(tid_, by_id[tid_]["title"] or thread_label(tid_), "list"):
                            continue
                        lc1, lc2 = st.columns([12, 1])
                        if lc1.button(thread_label(tid_), key=f"th_sel_{tid_}", width="stretch",
                                      type="primary" if tid_ == cur else "secondary"):
                            st.session_state["thread_sel"] = tid_
                            _leave_new_topic()
                            st.rerun()
                        if lc2.button("✏️", key=f"th_rn_{tid_}", help="Μετονομασία θέματος"):
                            st.session_state[f"renaming_list_{tid_}"] = True
                            st.rerun()
            else:
                st.caption("Δεν υπάρχουν ακόμη θέματα.")
    with top_r:
        if st.button("➕ Νέο θέμα", width="stretch", help="Το επόμενο μήνυμα ανοίγει νέο θέμα"):
            st.session_state["new_topic"] = True
            st.rerun()
    new_topic = bool(st.session_state.get("new_topic")) or cur is None

    if new_topic:
        st.markdown("**Νέο θέμα** — γράψε ερώτηση, ιδέα για δοκιμή, ή ερώτηση για τον υπάρχοντα κώδικα. "
                    "Ο συντονιστής θα συνεννοηθεί με τον Codex όπου χρειάζεται και θα απαντήσει εδώ.")
        if ids and st.button("↩️ Επιστροφή στη «Κύρια συζήτηση»"):
            st.session_state["new_topic"] = False
            st.rerun()
    else:
        @st.fragment(run_every=refresh)
        def working_indicator(tid):
            # isolated from the input: only this small block refreshes
            dd = db()
            msgs = dd.thread(tid)
            dd.close()
            mine = [m for m in msgs if m["author"] == "researcher"]
            if not mine or mine[-1]["status"] not in ("acknowledged", "in_progress"):
                return
            names = [AGENTS.get(k, (k,))[0] for k in active_agent_keys(read_events(400)) if k != "coordinator"]
            st.info("⏳ ο συντονιστής δουλεύει…" + (" · ενεργοί τώρα: " + ", ".join(names) if names else ""))

        show_thread(cur)
        working_indicator(cur)

    kind = st.segmented_control("Τύπος μηνύματος", ["message", "proposal", "code_question"],
                                format_func=lambda k: KIND_LABEL[k], default="message", key="composer_kind")
    sel_l, sel_r, _sp = st.columns([2, 2, 4])
    req_model = sel_l.selectbox("Μοντέλο", list(MODEL_CHOICES), format_func=MODEL_CHOICES.get, key="req_model_sel",
                                help="Ποιο μοντέλο απαντά σε αυτό το μήνυμα. Αυτόματα = αποφασίζει ο συντονιστής.")
    req_effort = sel_r.selectbox("Ένταση", ["low", "med", "high"], index=1, key="req_effort_sel",
                                 help="Πόση προσπάθεια/σκέψη θα καταναλώσει η απάντηση.")
    # Voice input (local faster-whisper). Outside any fragment, so a recording is never refreshed away.
    rec = st.audio_input("🎙️ Φωνητικό μήνυμα", key=f"voice_rec_{st.session_state.get('voice_n', 0)}")
    voice_wav = None
    if rec is not None:
        wav = rec.getvalue()
        sig = (len(wav), hash(wav))
        if st.session_state.get("voice_sig") != sig:  # new recording -> transcribe once
            try:
                import voice
                with st.spinner("Μεταγραφή…"):
                    st.session_state["voice_text"] = voice.transcribe(wav)[0]
            except Exception as e:
                st.session_state["voice_text"] = ""
                st.error(f"Η μεταγραφή απέτυχε: {type(e).__name__}: {e}")
            st.session_state["voice_sig"] = sig
            st.session_state["voice_edit"] = st.session_state["voice_text"]
        voice_wav = wav
        st.text_area("Μεταγραφή (διόρθωσέ την πριν την αποστολή)", key="voice_edit", height=120)
        if st.button("Αποστολή", key="voice_send", type="primary"):
            try:
                dd = db()
                target = None if new_topic else cur
                reply_to = None
                if target:
                    thr = dd.thread(target)
                    reply_to = thr[-1]["id"] if thr else None
                mid = dd.researcher_send(st.session_state.get("voice_edit", ""), kind=kind or "message",
                                         thread_id=target, reply_to=reply_to,
                                         req_model=req_model or None, req_effort=req_effort,
                                         attachments=[("voice.wav", voice_wav)], root=ROOT)
                dd.close()
                st.session_state["pending_thread"] = target or mid
                st.session_state["new_topic"] = False
                st.session_state["voice_n"] = st.session_state.get("voice_n", 0) + 1  # fresh recorder widget
                st.session_state["voice_sig"] = None
                st.session_state["voice_edit"] = ""
                st.toast(f"Στάλθηκε ({mid})", icon="📨")
                st.rerun()
            except (LabError, UploadError) as e:
                st.error(str(e))
    # Enter sends, Shift+Enter = newline. Not inside any fragment, so typing is never refreshed away.
    sub = st.chat_input("Γράψε εδώ… (Enter = αποστολή, Shift+Enter = νέα γραμμή)", accept_file="multiple",
                        key="composer")
    if sub:
        text = getattr(sub, "text", sub) if not isinstance(sub, str) else sub
        files = list(getattr(sub, "files", None) or [])
        try:
            dd = db()
            target = None if new_topic else cur
            reply_to = None
            if target:
                thr = dd.thread(target)
                reply_to = thr[-1]["id"] if thr else None
            mid = dd.researcher_send(text, kind=kind or "message",
                                     thread_id=target, reply_to=reply_to,
                                     req_model=req_model or None, req_effort=req_effort,
                                     attachments=[(f.name, f.getvalue()) for f in files] or None, root=ROOT)
            dd.close()
            st.session_state["pending_thread"] = target or mid
            st.session_state["new_topic"] = False
            st.toast(f"Στάλθηκε ({mid})", icon="📨")
            st.rerun()
        except (LabError, UploadError) as e:
            st.error(str(e))

# ================================================================ decisions
with tab_dec:
    top = st.columns([4, 1])
    top[0].markdown("Αιτήματα των πρακτόρων προς εσένα. Τίποτα δεν εκτελείται χωρίς τη δική σου απόφαση εδώ.")
    if top[1].button("🔄 Ανανέωση", key="refresh_dec"):
        st.rerun()
    d = db()
    decision_panel(d)
    closed = [r for r in d.requests() if r["state"] != "open"]
    d.close()
    if closed:
        st.markdown("##### Ιστορικό αποφάσεων")
        st.dataframe(pd.DataFrame([{
            "id": r["id"], "τίτλος": r["title"], "τύπος": REQ_KIND[r["kind"]],
            "πεδίο": REQ_SCOPE.get(r["scope"], r["scope"]),
            "απόφαση": " ".join(REQ_STATE.get(r["state"], ("", r["state"]))), "σχόλιο": r["decision_text"] or "",
            "πότε": fmt_ts(r["decided_at"])} for r in closed]), hide_index=True, width="stretch")

# ================================================================ agents
with tab_agents:
    @st.fragment(run_every=3)
    def agents_brain():
        components.html(brain_view.render(_brain_state(), full_names=True), height=380)

    with st.expander("🧠 Εγκέφαλος πρακτόρων (ζωντανά, από τα logs)", expanded=True):
        agents_brain()
    hours = st.select_slider("Παράθυρο", options=[1, 3, 6, 12, 24, 72], value=6, format_func=lambda h: f"{h} ώρες",
                             key="agent_hours")

    race_on = st.toggle("🏁 Race view", key="race_view")

    @st.fragment(run_every=refresh)
    def agents_view(hours, race_on=False):
        ev = read_events()
        if ev.empty:
            st.info("Δεν υπάρχει ακόμη δραστηριότητα πρακτόρων. Τα hooks του Claude Code γράφουν στο "
                    "`.lab/events.jsonl` μόλις ξεκινήσει ο συντονιστής.", icon="🤖")
            return
        now_ = dt.datetime.now()
        if race_on:
            ln = race_view.lanes(race_view.load_events(EVENTS), roles={k: (v[0], v[1]) for k, v in AGENTS.items()},
                            health=race_view.load_health(HEALTH))
            page, hgt = race_view.render(ln), race_view.height_for(len(ln))
            try:  # st.components.v1.html is deprecated in newer Streamlit; st.iframe takes the same HTML string
                components.html(page, height=hgt, scrolling=True)
            except AttributeError:
                st.iframe(page, height=hgt)
        # who is working now
        st.markdown("##### Τώρα")
        keys = active_agent_keys(ev)
        cols = st.columns(min(4, max(1, len(keys))))
        for i, k in enumerate(keys):
            sub = ev[(ev["agent"] == k) & (ev["event"].isin(["PreToolUse", "PostToolUse", "SubagentStart"]))]
            name, color, icon = AGENTS.get(k, (k, OTHER_COLOR, "🛠️"))
            with cols[i % len(cols)].container(border=True):
                st.markdown(f"{icon} **{name}**")
                if sub.empty:
                    st.caption("καμία ενέργεια ακόμη")
                    continue
                last = sub.iloc[-1]
                busy = (now_ - last["ts"]).total_seconds() < 120
                st.caption(("🟢 εργάζεται" if busy else "⚪ σε αναμονή") + f" · {ago((now_ - last['ts']).total_seconds())} πριν")
                st.markdown(f"`{last['tool'] or last['event']}` {str(last['summary'])[:120]}")
        # timeline
        win = ev[(ev["ts"] > now_ - dt.timedelta(hours=hours)) & (ev["event"].isin(["PreToolUse", "SubagentStart"]))]
        st.markdown(f"##### Χρονογραμμή ({hours} ώρες) — κάθε σημείο είναι μία ενέργεια")
        if win.empty:
            st.caption("Καμία ενέργεια στο παράθυρο.")
            return
        lanes = [k for k in AGENTS if k in set(win["agent"])] + sorted(set(win["agent"]) - set(AGENTS))
        fig = go.Figure()
        for k in lanes:
            sub = win[win["agent"] == k]
            name, color, _ = AGENTS.get(k, (k, OTHER_COLOR, ""))
            # one label per task: written next to the last dot of each task group
            last_of = sub.groupby("group").tail(1).index if "group" in sub else []
            texts = [(sub.at[i, "label"] if i in last_of else "") for i in sub.index]
            fig.add_trace(go.Scatter(
                x=sub["ts"], y=[name] * len(sub), mode="markers+text", name=name,
                text=texts, textposition="middle right", textfont=dict(size=11, color=color),
                cliponaxis=False,
                marker=dict(size=9, color=color, line=dict(width=2, color="#fcfcfb")),
                customdata=list(zip(sub["tool"].fillna(""), sub["summary"].fillna("").str.slice(0, 120))),
                hovertemplate="%{x|%H:%M:%S}<br><b>%{customdata[0]}</b> %{customdata[1]}<extra>" + name + "</extra>"))
        fig.update_layout(height=90 + 46 * len(lanes), margin=dict(l=10, r=90, t=10, b=30), showlegend=False,
                          hovermode="closest", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig.update_xaxes(showgrid=True, gridcolor="rgba(137,135,129,0.25)", gridwidth=1)
        fig.update_yaxes(showgrid=False, categoryorder="array", categoryarray=[AGENTS.get(k, (k,))[0] for k in lanes][::-1])
        st.plotly_chart(fig, theme="streamlit", width="stretch", config={"displayModeBar": False})
        counts = win.groupby("agent").size().reindex(lanes).fillna(0).astype(int)
        st.caption(" · ".join(f"{AGENTS.get(k, (k,))[0]}: {n} ενέργειες" for k, n in counts.items()))
        spans = agent_spans(ev)
        spans = spans[spans["start"] > now_ - dt.timedelta(hours=hours)] if not spans.empty else spans
        if not spans.empty:
            st.markdown("##### Ρόλοι ανά εργασία")
            per = spans.groupby("agent").size()
            st.caption(" · ".join(f"{AGENTS.get(k, (k,))[0]}: {n} εργασίες" for k, n in per.items()))
            st.dataframe(pd.DataFrame({
                "ώρα": spans["start"].dt.strftime("%H:%M:%S"),
                "ρόλος": [AGENTS.get(a, (a,))[0].split(" · ")[0] for a in spans["agent"]],
                "μοντέλο": [m or (AGENTS.get(a, ("",))[0].split(" · ") + ["", ""])[1] for a, m in zip(spans["agent"], spans["model"])],
                "εργασία": spans["task"], "διάρκεια": [ago(x) if x == x and x is not None else "…" for x in spans["seconds"]],
                "κατάσταση": spans["status"]}).iloc[::-1], hide_index=True, width="stretch")
        with st.expander("Πίνακας τελευταίων ενεργειών"):
            tail = ev.tail(40).iloc[::-1]
            st.dataframe(pd.DataFrame({"ώρα": tail["ts"].dt.strftime("%H:%M:%S"),
                                       "πράκτορας": [AGENTS.get(a, (a,))[0] for a in tail["agent"]],
                                       "γεγονός": tail["event"], "εργαλείο": tail["tool"],
                                       "περίληψη": tail["summary"]}), hide_index=True, width="stretch")
    agents_view(hours, race_on)


# ---------------------------------------------------------------- experiments tab helpers (M-20261021-008)
EXP_RESULTS = os.path.join(ROOT, exp_view.RESULTS_REL)
EXP_HISTORY = os.path.join(ROOT, exp_view.HISTORY_REL)
INTRO_CACHE = os.path.join(LAB, "tuning", "agent_introspect_cache.json")
_PAPER_NOTE = "δείκτης προόδου, όχι αποτέλεσμα paper"
_NO_TRAJ = "δεν υπάρχει καταγραφή για αυτό το run (ενεργοποιείται από τον επόμενο κύκλο)"


@st.cache_resource(show_spinner=False, max_entries=3000)
def _res_load(path, mtime):  # noqa: ARG001 - mtime is part of the cache key (reload when the file changes); read-only
    return exp_view.read_json(path)


def _res_folder(cycle):
    out = []
    for p in sorted(glob.glob(os.path.join(EXP_RESULTS, cycle, "*.json"))):
        if exp_view.is_main_result(p):
            try:
                r = _res_load(p, os.path.getmtime(p))
            except OSError:
                continue
            if isinstance(r, dict):
                out.append((p, r))
    return out


def _res_folders():
    ds = [d for d in glob.glob(os.path.join(EXP_RESULTS, "*")) if os.path.isdir(d)]
    return [os.path.basename(d) for d in sorted(ds, key=os.path.getmtime, reverse=True)]


@st.cache_data(ttl=30, show_spinner=False)
def _out_to_run():
    dd = db()
    try:
        rs = dd.runs(limit=100000)
    finally:
        dd.close()
    out = {}
    for r in rs:
        o = exp_view.out_path_of(r.get("cmd"), r.get("cwd"))
        if o and o not in out:
            out[o] = (r["run_id"], r["status"])
    return out


def _introspect(key):
    """tools/agent_introspect.py on CPUs 0-7 (builds the agent, no training), cached per key + legacy-code mtime."""
    mt = max((os.path.getmtime(f) for f in glob.glob(os.path.join(ROOT, "code-tuning", "tuning", "legacy", "*.py"))), default=0)
    k = "|".join(map(str, key)) + f"|{mt:.0f}"
    cache = exp_view.read_json(INTRO_CACHE) or {}
    if k in cache:
        return cache[k]
    cmd = ["taskset", "-c", "0-7", os.path.join(ROOT, ".venv", "bin", "python"),
           os.path.join(ROOT, "tools", "agent_introspect.py")] + exp_view.intro_args(key)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1"))
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    cache[k] = d
    try:
        tmp = INTRO_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, INTRO_CACHE)
    except OSError:
        pass
    return d


def _arm_ck_means(items, variant, arm, split):
    """{checkpoint: mean over seeds of the split mean return} for one arm/variant of a folder."""
    acc = {}
    for _, r in items:
        if r.get("arm") == arm and exp_view.variant_of(r) == variant:
            for c in exp_view.checkpoints(r):
                m = exp_view.ck_mean(r, c, split)
                if m is not None:
                    acc.setdefault(c, []).append(m)
    return {c: sum(v) / len(v) for c, v in acc.items()}


def _baselines(cycle, variant, split):
    b = exp_view.read_json(os.path.join(EXP_RESULTS, cycle, f"baselines-{variant}.json"))
    sp = (b or {}).get(split)
    return {k: v for k, v in sp.items() if isinstance(v, dict) and "mean_ret" in v} if isinstance(sp, dict) else {}


def _paper_figures(path, res, items, cycle):
    """Figures analogous to the DInos paper (Fig.5-8), drawn now from this run's JSON and its folder."""
    split = exp_view.test_split(res)
    variant, arm = exp_view.variant_of(res), res.get("arm")
    ck_sel = exp_view.select_ck(res)
    st.caption(f"Όλα από `{os.path.relpath(path, ROOT)}` και τον φάκελο `{cycle}` · split **{split}** · "
               "«Total Accumulated Reward» = 5 × μέσο reward επεισοδίου (το paper αθροίζει 5 επεισόδια των 5000 ticks).")
    # Fig.5: checkpoints
    st.markdown("**Σαν Fig.5 — συνολικό reward ανά checkpoint εκπαίδευσης**")
    mine = [(f"{arm} trained for {c // 1000}k steps", None if exp_view.ck_mean(res, c, split) is None
             else 5 * exp_view.ck_mean(res, c, split)) for c in exp_view.checkpoints(res)]
    other = "derp"
    if arm == "derp":
        tr_arms = sorted({r.get("arm") for _, r in items if r.get("agent") == "dinos_t" and exp_view.variant_of(r) == variant})
        other = tr_arms[0] if tr_arms else None
    panels = [(f"{arm} (αυτό το run, seed {res.get('seed')})", mine, exp_figs.GREEN if arm == "derp" else exp_figs.PURPLE)]
    om = _arm_ck_means(items, variant, other, split) if other else {}
    if om:
        panels.append((f"{other} (μ.ό. seeds του φακέλου)", [(f"{other} trained for {c // 1000}k steps", 5 * v)
                                                              for c, v in sorted(om.items())],
                       exp_figs.GREEN if other == "derp" else exp_figs.PURPLE))
    st.plotly_chart(exp_figs.checkpoint_bars(panels), width="stretch", config={"displayModeBar": False}, key="xf5")
    # Fig.6 / Fig.7 right: per-tick behaviour
    def _traj(c):
        return (((res.get("checkpoint_results") or {}).get(str(c)) or {}).get(split) or {}).get("trajectory")
    ck_t = ck_sel if _traj(ck_sel) else next((c for c in reversed(exp_view.checkpoints(res)) if _traj(c)), ck_sel)
    st.markdown(f"**Σαν Fig.6 / Fig.7 (δεξιά) — load, μνήμη, CPU, latency και pods στο χρόνο** (checkpoint {ck_t}"
                + ("" if ck_t == ck_sel else f"· το επιλεγμένο {ck_sel} δεν έχει καταγραφή") + ")")
    traj = _traj(ck_t)
    if traj and traj.get("episodes"):
        eps = traj["episodes"]
        i = st.selectbox("Επεισόδιο (eval seed)", range(len(eps)), format_func=lambda j: f"seed {eps[j].get('seed')}",
                         key="xf_ep")
        st.plotly_chart(exp_figs.metrics_over_time(eps[i]), width="stretch", config={"displayModeBar": False}, key="xf6")
        st.markdown("**Σαν Fig.7 (αριστερά, ως καμπύλη) — σωρευτικό reward**")
        st.plotly_chart(exp_figs.cumulative_reward([(f"seed {e.get('seed')}", e.get("reward", []), None) for e in eps]),
                        width="stretch", config={"displayModeBar": False}, key="xf7c")
    else:
        st.info(_NO_TRAJ, icon="🕳️")
    # Fig.7 left / Fig.8: totals of every method of this variant (folder means + baselines)
    st.markdown(f"**Σαν Fig.7 (αριστερά) / Fig.8 — συνολικό reward ανά μέθοδο** ({variant}, {split})")
    am = exp_view.folder_arm_means([r for _, r in items])
    rows, bars = [], []
    for (v, a), m in sorted(am.items(), key=lambda kv: -kv[1]["mean"]):
        if v != variant:
            continue
        lat = [e.get("mean_latency") for _, r in items if r.get("arm") == a and exp_view.variant_of(r) == v
               for e in (((r.get("checkpoint_results") or {}).get(str(m["ck"])) or {}).get(m["split"]) or {}).get("episodes", [])]
        lat = [x for x in lat if x is not None]
        rows.append({"μέθοδος": a, "περιβάλλον": f"sim {v}", "accumulated reward (5×μ.ό.)": round(5 * m["mean"]),
                     "μ.ό. pods": round(sum(((((r.get("checkpoint_results") or {}).get(str(m["ck"])) or {}).get(m["split"]) or {})
                                            .get("mean_pods", 0) for _, r in items if r.get("arm") == a
                                            and exp_view.variant_of(r) == v)) / m["n_seeds"], 3),
                     "μ.ό. latency": f"{sum(lat) / len(lat):.3f}" if lat else exp_view.UNKNOWN,
                     "μ.ό. CPU / μνήμη": "—", "seeds": str(m["n_seeds"]), "checkpoint": str(m["ck"])})
        bars.append((a, 5 * m["mean"], exp_figs.PURPLE if a == arm else None))
    for name, b in _baselines(cycle, variant, split).items():
        rows.append({"μέθοδος": f"baseline {name}", "περιβάλλον": f"sim {variant}",
                     "accumulated reward (5×μ.ό.)": round(5 * b["mean_ret"]), "μ.ό. pods": round(b.get("mean_pods", 0), 3),
                     "μ.ό. latency": exp_view.UNKNOWN, "μ.ό. CPU / μνήμη": "—", "seeds": "-", "checkpoint": "-"})
        bars.append((f"baseline {name}", 5 * b["mean_ret"], exp_figs.GREY))
    if traj and traj.get("episodes"):
        cpu = [x for e in traj["episodes"] for x in e.get("cpu", [])]
        mem = [x for e in traj["episodes"] for x in e.get("mem", [])]
        for rw in rows:
            if rw["μέθοδος"] == arm and cpu:
                rw["μ.ό. CPU / μνήμη"] = f"{sum(cpu) / len(cpu):.1f} / {sum(mem) / len(mem):.1f} (μόνο αυτό το run, {len(traj['episodes'])} επεισόδια)"
    if bars:
        st.plotly_chart(exp_figs.total_bars(sorted(bars, key=lambda b: b[1])), width="stretch",
                        config={"displayModeBar": False}, key="xf7")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("CPU/μνήμη: μόνο από καταγεγραμμένη τροχιά (--record-traj)· «—» = " + _NO_TRAJ + ". "
                   "Latency baselines: δεν αποθηκεύεται μέσος όρος στο baselines JSON (μόνο p95).")


def _exp_overview():
    """Gauge: latest cycle closeness, forecast, runs left in the loop (reads files; launcher status read-only)."""
    hist = exp_view.load_history(EXP_HISTORY) or exp_view.SEED_HISTORY
    ser = exp_view.primary_series(hist)
    vals = [float(e["closeness"]) for e in ser]
    running, run_err = 0, []
    dd = db()
    try:
        import launch_run
        for rid in exp_view.LOOP_REQUESTS:
            try:
                v = launch_run.sandbox_status(dd, rid)["running"]
                running += len(v) if isinstance(v, (list, tuple)) else int(v)
            except Exception as e:  # noqa: BLE001 - read-only view
                run_err.append(f"{rid}: {type(e).__name__}")
    finally:
        dd.close()
    rem = exp_view.remaining_runs(os.path.join(LAB, "tuning"), os.path.join(ROOT, "code-tuning"), running,
                                  exp_view.driver_files(exp_view.proc_cmdlines()))
    fc = exp_view.forecast(vals, steps=1)
    hl = exp_view.hours_left(dt.datetime.now(dt.timezone.utc))
    c1, c2, c3 = st.columns(3)
    with c1:
        last = ser[-1]
        st.plotly_chart(exp_figs.gauge(last["closeness"], "Πόσο κοντά είμαστε στους στόχους",
                                       ref=vals[-2] if len(vals) > 1 else None),
                        width="stretch", config={"displayModeBar": False}, key="xg_gauge")
        st.caption(f"Τελευταίος κύκλος **{last['cycle']}** ({last['variant']}), λόγος DInos+T/DERP {last.get('ratio')}× "
                   f"(στόχος 17.3×) · πηγή `{last['source']}` · {_PAPER_NOTE}.")
    with c2:
        if fc:
            st.metric(f"Εκτίμηση μετά τα {rem['total']} υπόλοιπα runs", f"{fc['pred']:.0f}%",
                      f"{fc['lo']:.0f}–{fc['hi']:.0f}%", delta_color="off")
            st.caption(f"**εκτίμηση**: ευθεία ελαχίστων τετραγώνων στους τελευταίους {fc['n']} κύκλους "
                       f"(κλίση {fc['slope']:+.1f} μονάδες/κύκλο), προέκταση κατά 1 κύκλο (τα υπόλοιπα runs ≈ ένας "
                       f"ακόμη κύκλος)· ζώνη ±{fc['band']:.1f} = max(2, 2×τυπική απόκλιση υπολοίπων)· όρια 0–100. "
                       "Δεν είναι πρόβλεψη αποτελέσματος.")
    with c3:
        st.metric("Runs μέχρι το τέλος του loop", rem["total"], f"{rem['running']} τρέχουν · {rem['queued']} στην ουρά",
                  delta_color="off")
        st.metric("Χρόνος μέχρι 21/10 23:59 UTC", f"{max(hl, 0):.1f} ώρες" if hl > 0 else "έληξε")
        st.caption("Ουρά = εγγραφές `.lab/tuning/*_entries.json` μετά τον μετρητή `.launched` (μοναδικά ονόματα)· "
                   f"τρέχουν = sandbox-status {', '.join(exp_view.LOOP_REQUESTS)}."
                   + (f" Επιπλέον {rem['orphan']} έτοιμες εγγραφές χωρίς driver/αποτέλεσμα (ίσως δεν τρέξουν)." if rem["orphan"] else "")
                   + (f" Σφάλμα ανάγνωσης: {'; '.join(run_err)}" if run_err else ""))
    with st.expander("Ιστορικό closeness ανά κύκλο"):
        st.plotly_chart(exp_figs.history_line([e["cycle"] for e in ser], vals, fc), width="stretch",
                        config={"displayModeBar": False}, key="xg_hist")
        st.dataframe(pd.DataFrame(hist), hide_index=True, width="stretch")
        st.caption(f"Αρχείο `{os.path.relpath(EXP_HISTORY, ROOT)}` · closeness = code-tuning/tuning/closeness.py "
                   "score(5×μ.ό. DInos+T, 5×μ.ό. DERP), μέσος όρος τριών μερών (DERP, DInos, λόγος) · " + _PAPER_NOTE + ".")
        if rem["files"]:
            st.dataframe(pd.DataFrame(rem["files"]), hide_index=True, width="stretch")


# ================================================================ runs
if _tab_live(tab_runs):  # lazy: hidden tabs do no work
    with tab_runs:
        st.fragment(run_every=30)(_exp_overview)()
        @st.fragment(run_every=refresh)
        def runs_view():
            dd = db()
            runs = dd.runs()
            dd.close()
            if not runs:
                st.info("Δεν υπάρχουν ακόμη runs. Κάθε πείραμα ξεκινά μόνο μέσω `tools/launch_run.py` και μόνο αφού "
                        "εγκρίνεις το run spec του στην καρτέλα «Αποφάσεις».", icon="📈")
                return
            rows = []
            for r in runs:
                prog = None
                pj = read_text(os.path.join(r["run_dir"], "progress.json"))
                if pj:
                    try:
                        p = json.loads(pj)
                        prog = min(1.0, float(p["step"]) / float(p["total"])) if p.get("total") else None
                    except (ValueError, KeyError, TypeError, ZeroDivisionError):
                        prog = None
                started, ended = parse_ts(r["started"]), parse_ts(r["ended"])
                dur = ((ended or dt.datetime.now(dt.timezone.utc)) - started).total_seconds() if started else None
                icon, label = RUN_STATUS.get(r["status"], ("", r["status"]))
                rows.append({"run": r["run_id"], "όνομα": r["name"], "κατάσταση": f"{icon} {label}",
                             "πρόοδος": prog, "πεδίο": REQ_SCOPE.get(r["scope"], r["scope"]), "έγκριση": r["request_id"],
                             "διάρκεια": ago(dur) if dur is not None else "—", "exit": "" if r["exit_code"] is None else r["exit_code"],
                             "κώδικας": (r["code_sha"] or "")[:12]})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={"πρόοδος": st.column_config.ProgressColumn("πρόοδος", min_value=0, max_value=1,
                                                                                   format="percent")})
            # metrics
            ids = [r["run_id"] for r in runs]
            chosen = st.multiselect("Σύγκριση runs (μέχρι 8)", ids, default=ids[:2], max_selections=8, key="runs_sel")
            series = {}
            keys = set()
            for rid in chosen:
                run = next(r for r in runs if r["run_id"] == rid)
                path = os.path.join(run["run_dir"], "metrics.jsonl")
                if os.path.exists(path):
                    recs = []
                    with open(path, encoding="utf-8") as f:
                        for line in f:
                            try:
                                recs.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                    if recs:
                        df = pd.DataFrame(recs)
                        series[rid] = df
                        keys |= {c for c in df.columns if c not in ("step", "ts") and pd.api.types.is_numeric_dtype(df[c])}
            if not series:
                st.caption("Τα επιλεγμένα runs δεν έχουν ακόμη `metrics.jsonl`.")
                return
            mlist = sorted(keys)
            metric = st.selectbox("Μετρική", mlist, index=mlist.index("reward") if "reward" in mlist else 0,
                                  key="runs_metric")
            palette = [v[1] for v in AGENTS.values()]
            fig = go.Figure()
            for rid in chosen:  # colour by position in the run list (stable), never by rank of the value
                if rid in series and metric in series[rid]:
                    df = series[rid]
                    x = df["step"] if "step" in df else df.index
                    fig.add_trace(go.Scatter(x=x, y=df[metric], mode="lines", name=rid,
                                             line=dict(width=2, color=palette[ids.index(rid) % len(palette)])))
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=30), hovermode="x unified",
                              legend=dict(orientation="h", y=-0.2), plot_bgcolor="rgba(0,0,0,0)",
                              paper_bgcolor="rgba(0,0,0,0)", xaxis_title="step", yaxis_title=metric)
            fig.update_xaxes(gridcolor="rgba(137,135,129,0.25)")
            fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)")
            st.plotly_chart(fig, theme="streamlit", width="stretch", config={"displayModeBar": False})
        runs_view()

        st.markdown("##### 📡 Live: φορτίο και pods του run που τρέχει τώρα")

        @st.fragment(run_every=3)
        def exp_live():
            cands = exp_view.live_candidates(EXP_RESULTS, time.time())
            if not cands:
                st.info("Κανένα run με live καταγραφή αυτή τη στιγμή — ενεργοποιείται από τον επόμενο κύκλο. "
                        "Μέχρι τότε δες τον πίνακα και το γράφημα μετρικών ακριβώς από πάνω.", icon="📡")
                return
            paths = [p for p, _ in cands]
            ages = dict(cands)
            pick = st.selectbox("Live run", paths, key="live_pick",
                                format_func=lambda p: f"{os.path.relpath(p, EXP_RESULTS)} · ενημέρωση πριν {ages.get(p, 0):.0f} s")
            d = exp_view.read_live(pick)
            if not d or not d["columns"].get("t"):
                st.caption("Το live αρχείο δεν διαβάζεται αυτή τη στιγμή (γράφεται)· ξαναδοκιμάζω σε 3 s.")
                return
            ph = {"pretrain": "προεκπαίδευση (source)", "train": "εκπαίδευση", "eval": "αξιολόγηση (greedy)"}
            st.markdown(f"**{d.get('arm')}** · {d.get('variant')} · seed {d.get('seed')} · φάση "
                        f"**{ph.get(d.get('phase'), d.get('phase'))}** {d.get('label') or ''} · tick {d.get('t'):,} "
                        f"(εκπαίδευση {d.get('total_ticks', '?'):,} + αξιολογήσεις)" + (" · ✅ τελείωσε" if d.get("done") else ""))
            st.plotly_chart(exp_figs.live_figure(d["columns"]), width="stretch", config={"displayModeBar": False},
                            key="live_chart")
            st.caption("Μπλε: load (είσοδος) · κόκκινο: pods · πορτοκαλί: pods σε εκκίνηση (startup delay) · "
                       "γκρι φόντο: επεισόδια αξιολόγησης. Τελευταία ~600 ticks, ανανέωση κάθε 3 s.")
        exp_live()

        st.markdown("##### 🔎 Λεπτομέρειες run (παράμετροι, απόσταση από στόχους, γραφήματα σε στυλ paper)")
        _ss = st.session_state
        _folders = _res_folders()
        if not _folders:
            st.caption(f"Δεν υπάρχουν αποτελέσματα στο `{os.path.relpath(EXP_RESULTS, ROOT)}`.")
        else:
            _c1, _c2 = st.columns(2)
            _cyc = _c1.selectbox("Κύκλος (φάκελος αποτελεσμάτων)", _folders, key="xd_cycle")
            _items = _res_folder(_cyc)
            _arms = sorted({str(r.get("arm")) for _, r in _items})
            _armf = _c2.multiselect("Arm", _arms, key="xd_arm")
            _C = exp_view.load_closeness(ROOT)
            _o2r = _out_to_run()
            _shown = [(p, r) for p, r in _items if not _armf or str(r.get("arm")) in _armf]
            _rows = []
            for _p, _r in _shown:
                _ck = exp_view.select_ck(_r)
                _sp = exp_view.test_split(_r)
                _m = exp_view.ck_mean(_r, _ck, _sp)
                _cl = exp_view.run_closeness(_C, _r, _ck, _sp)
                _rows.append({"run": (_o2r.get(os.path.normpath(_p)) or ("—",))[0], "arm": _r.get("arm"),
                              "variant": exp_view.variant_of(_r), "seed": _r.get("seed"), "checkpoint": _ck,
                              "split": _sp, "μ.ό. reward": None if _m is None else round(_m),
                              "μέρος closeness": None if _cl.get("part") is None else f"{100 * _cl['part']:.0f}%",
                              "CPU (s)": None if _r.get("cpu_s") is None else round(_r["cpu_s"]),
                              "τροχιά": "ναι" if _r.get("record_traj") else "όχι"})
            if _rows:
                _ss["xd_paths"] = [p for p, _ in _shown]

                def _xd_pick():
                    sel = _ss["xd_table"].selection.rows
                    if sel:
                        _ss["xd_sel"] = _ss["xd_paths"][sel[0]]
                st.dataframe(pd.DataFrame(_rows), hide_index=True, width="stretch", on_select=_xd_pick,
                             selection_mode="single-row", key="xd_table")
                st.caption("Πάτησε μια γραμμή για όλες τις παραμέτρους. checkpoint = το καλύτερο στο validation "
                           "(όπως επιλέγει το loop), split = το τελικό test split του run.")
            _sel = _ss.get("xd_sel")
            if _sel and _sel in [p for p, _ in _items]:
                _res = dict(_items)[_sel]
                _run = _o2r.get(os.path.normpath(_sel))
                st.markdown(f"**{exp_view.run_label(_res)}** · `{os.path.relpath(_sel, ROOT)}`"
                            + (f" · run `{_run[0]}` ({_run[1]})" if _run else ""))
                # closeness
                _cl = exp_view.run_closeness(_C, _res)
                _am = exp_view.folder_arm_means([r for _, r in _items])
                _fs = exp_view.folder_scores(_C, _am).get(exp_view.variant_of(_res))
                _t1, _t2 = st.columns(2)
                with _t1:
                    if _cl.get("part") is not None:
                        st.metric(f"Μέρος «{_cl['kind']}» του closeness", f"{100 * _cl['part']:.0f}%")
                        st.caption(f"x = 5 × {_cl['mean_ret']:,.0f} = {_cl['x']:,.0f} (checkpoint {_cl['checkpoint']}, "
                                   f"{_cl['split']}) έναντι στόχου {_cl['target']:,.0f} · μέρος = 1 − |log10(x / στόχος)| "
                                   f"(closeness.part) · {_PAPER_NOTE}.")
                    else:
                        st.caption(f"Το arm `{_res.get('arm')}` δεν έχει στόχο στο paper (στόχοι μόνο για DERP 2.2e5 και "
                                   f"DInos+T 3.8e6)· 5 × μ.ό. = {(_cl['x'] or 0):,.0f}.")
                with _t2:
                    if _fs:
                        st.metric(f"Closeness κύκλου {_cyc} · {exp_view.variant_of(_res)}", f"{100 * _fs['total']:.0f}%")
                        st.caption(f"score(5×{_fs['dinos_mean']:,.0f} DInos+T, 5×{_fs['derp_mean']:,.0f} DERP), όπως το loop "
                                   f"(μ.ό. seeds {_fs['n_seeds']}, split {_fs['split']}): μέσος όρος των μερών DERP "
                                   f"{100 * _fs['derp']:.0f}%, DInos {100 * _fs['dinos']:.0f}%, λόγος {100 * _fs['ratio_part']:.0f}% "
                                   f"(λόγος {_fs['ratio']:.2f}×, στόχος 17.3×) · "
                                   f"{_PAPER_NOTE}.")
                with st.spinner("Παράμετροι agent (κατασκευή μοντέλου χωρίς εκπαίδευση, CPU 0-7)…"):
                    _intro = _introspect(exp_view.intro_key(_res)) if _res.get("agent") in ("derp", "lstm_scratch", "dinos_t") else None
                if _intro is None:
                    st.caption("Η ενδοσκόπηση του agent δεν ήταν διαθέσιμη· ό,τι δεν είναι στο JSON φαίνεται «άγνωστο».")
                st.dataframe(pd.DataFrame(exp_view.param_rows(_res, _intro, _sel)), hide_index=True, width="stretch",
                             height=420)
                if st.button("📊 Γραφήματα σε στυλ paper (Fig.5–8) για αυτό το run", key="xd_figs"):
                    _ss["xd_figs_for"] = _sel
                if _ss.get("xd_figs_for") == _sel:
                    _paper_figures(_sel, _res, _items, _cyc)

        st.markdown("##### Εικόνες αποτελεσμάτων run")
        _d = db()
        _all_runs = _d.runs()
        _d.close()
        if _all_runs:
            _rid = st.selectbox("Run", [r["run_id"] for r in _all_runs], key="img_run")
            _rd = next(r["run_dir"] for r in _all_runs if r["run_id"] == _rid)
            _imgs = paper_plots.find_result_images(_rd)
            if not _imgs:
                st.caption("Το run δεν έχει εικόνες στο `results/`.")
            for _grp in dict.fromkeys(g for g, _, _ in _imgs):
                with st.expander(f"results/{_grp}" if _grp != "(results)" else "results/", expanded=_grp == "(results)"):
                    for _g, _cap, _p in _imgs:
                        if _g == _grp:
                            st.image(_p, caption=f"{_rid}: {_cap}")

        st.markdown("##### Σύγκριση σε στυλ paper")
        _reqs = summarize_runs.request_ids(os.path.join(ROOT, ".lab"))
        if _reqs:
            _req = st.selectbox("Αίτημα (request id)", _reqs, index=len(_reqs) - 1, key="cmp_req")
            _rows = summarize_runs.collect(_req, os.path.join(ROOT, ".lab"))
            _agg = summarize_runs.aggregate_by_seed(_rows)
            if _agg:
                for _metric, _title in (("reward", "Total accumulated reward"), ("vms", "Mean VMs")):
                    st.markdown(f"**{_title}**")
                    _fig = paper_plots.comparison_figure(_agg, _metric)
                    st.pyplot(_fig)
                    _fig.clf()
                st.caption("Οι τιμές είναι μέσοι όροι επί των επεισοδίων και των seeds από τα runs: "
                           + ", ".join(r[0] for r in _rows) + ". Οι μπάρες σφάλματος είναι η τυπική απόκλιση μεταξύ "
                           "seeds (0 όταν υπάρχει ένα seed). Το `model` είναι το προεκπαιδευμένο μοντέλο (k βήματα).")
            else:
                st.caption("Τα runs του αιτήματος δεν έχουν ακόμη επεισόδια με `model` και `reward`.")
        else:
            st.caption("Δεν υπάρχουν runs αιτήματος για σύγκριση.")

        st.markdown("##### Sandbox")

        @st.fragment(run_every=refresh)
        def sandbox_section():
            paths = sandbox_view.ledger_paths(os.path.join(ROOT, ".lab", "sandbox"))
            if not paths:
                st.caption("Δεν υπάρχουν sandbox ledgers.")
                return
            dd = db()
            try:
                by_id = {r["run_id"]: dict(r) for r in dd.runs(limit=100000)}
                for pth in paths:
                    rid = os.path.basename(pth).split(".ledger.")[0]
                    try:
                        import launch_run
                        s = launch_run.sandbox_status(dd, rid)
                        st.markdown(f"**{rid}** · branch `{s['branch']}` · CPU-h {s['cpu_hours_used']}/{s['budget']} "
                                    f"(απομένουν {s['cpu_hours_left']}) · τρέχουν {s['running']}/{s['max_parallel']} · "
                                    + (":red[έληξε]" if s["expired"] else f"λήγει σε {s['hours_to_expiry']} ώρες ({s['expires']})"))
                    except Exception as e:  # noqa: BLE001 - read-only view; show what is known
                        st.markdown(f"**{rid}** · η σύνοψη δεν είναι διαθέσιμη ({type(e).__name__})")
                    v = sandbox_view.summarize(sandbox_view.read_ledger(pth), by_id)
                    if v["running"]:
                        st.dataframe(pd.DataFrame([{"run_id": x["run_id"], "batch": x["batch"], "πυρήνες": ",".join(map(str, x["cores"])),
                                                    "ξεκίνησε": fmt_ts(x["started"]), "διάρκεια": ago(x["elapsed_s"]) if x["elapsed_s"] is not None else "—"}
                                                   for x in v["running"]]), hide_index=True, width="stretch")
                    else:
                        st.caption("Κανένα sandbox run δεν τρέχει.")
                    if v["finished"]:
                        with st.expander(f"Τελευταία {len(v['finished'])} ολοκληρωμένα"):
                            st.dataframe(pd.DataFrame([{"run_id": x["run_id"], "όνομα": x["name"], "wall (s)": x["wall_s"],
                                                        "CPU (s)": x["cpu_seconds"], "κατάσταση": x["status"]}
                                                       for x in v["finished"]]), hide_index=True, width="stretch")
            finally:
                dd.close()
        sandbox_section()

        st.markdown("##### Διακοπή run")
        d = db()
        running = [r["run_id"] for r in d.runs() if r["status"] in ("starting", "running")]
        d.close()
        if running:
            with st.form("stop_run"):
                target = st.selectbox("Run", running)
                sure = st.checkbox("Ναι, θέλω να σταματήσει")
                go_stop = st.form_submit_button("⏹️ Ζήτησε διακοπή")
            if go_stop:
                if not sure:
                    st.warning("Τσέκαρε την επιβεβαίωση.")
                else:
                    try:
                        dd = db()
                        dd.request_stop(target)
                        dd.close()
                        st.toast(f"Ζητήθηκε διακοπή του {target}. Ο supervisor θα το σταματήσει σε ~5 δευτ.", icon="⏹️")
                    except LabError as e:
                        st.error(str(e))
        else:
            st.caption("Κανένα run δεν τρέχει.")

# ================================================================ council
if _tab_live(tab_council):  # lazy: hidden tabs do no work
    with tab_council:
        folders = sorted(glob.glob(os.path.join(LAB, "council", "C-*")), reverse=True)
        if not folders:
            st.info("Δεν υπάρχει ακόμη council. Όταν μια απόφαση αλλάζει την έρευνα, Claude και Codex γράφουν εδώ "
                    "ανεξάρτητες προτάσεις, κριτική και μια κάρτα απόφασης.", icon="⚖️")
        else:
            pick = st.selectbox("Council", folders, format_func=os.path.basename)
            card = read_text(os.path.join(pick, "card.md"))
            brief = read_text(os.path.join(pick, "brief.md"))
            if brief:
                with st.expander("Ερώτημα (brief)", expanded=not card):
                    st.markdown(brief)
            if card:
                with st.container(border=True):
                    st.markdown("**Κάρτα απόφασης**")
                    st.markdown(card)
            cl, cx = st.columns(2)
            with cl:
                st.markdown(f"**{AGENTS['coordinator'][2]} Claude**")
                for fn, lab in (("claude.md", "Πρόταση"), ("claude-r2.md", "Κριτική & αναθεώρηση")):
                    t = read_text(os.path.join(pick, fn))
                    if t:
                        with st.expander(lab, expanded=True):
                            st.markdown(t)
            with cx:
                st.markdown(f"**{AGENTS['codex'][2]} Codex**")
                for fn, lab in (("codex.md", "Πρόταση"), ("codex-r2.md", "Κριτική & αναθεώρηση")):
                    t = read_text(os.path.join(pick, fn))
                    if t:
                        with st.expander(lab, expanded=True):
                            st.markdown(t)

# ================================================================ resources
if _tab_live(tab_res):  # lazy: hidden tabs do no work
    with tab_res:
        @st.fragment(run_every=max(10, refresh))
        def resources():
            try:
                import psutil
            except ImportError:
                st.warning("Λείπει το psutil στο .venv.")
                return
            c = st.columns(4)
            cpu = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory()
            disk = shutil.disk_usage(ROOT)
            load1 = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
            c[0].metric("CPU", f"{cpu:.0f}%", help=f"{psutil.cpu_count()} πυρήνες")
            c[0].progress(min(1.0, cpu / 100))
            c[1].metric("RAM", f"{mem.used / 2**30:.1f} / {mem.total / 2**30:.0f} GiB")
            c[1].progress(mem.percent / 100)
            c[2].metric("Δίσκος", f"{disk.used / 2**30:.0f} / {disk.total / 2**30:.0f} GiB")
            c[2].progress(disk.used / disk.total)
            c[3].metric("Load (1 λεπτό)", f"{load1:.1f}" if load1 is not None else "—")
            if shutil.which("nvidia-smi"):
                out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                                      "--format=csv,noheader"], capture_output=True, text=True, timeout=5).stdout.strip()
                st.caption("GPU: " + (out or "—"))
            else:
                st.caption("GPU: δεν υπάρχει NVIDIA GPU στο VM.")
        resources()
        st.caption("Kubernetes: δες την καρτέλα ☸️ Kubernetes.")
        st.divider()
        st.subheader("Ποιος χρησιμοποιεί το μηχάνημα")

        @st.cache_data(ttl=20, show_spinner="μέτρηση…")
        def _usage_snapshot():
            dd = db()
            runs = dd.runs(limit=300)
            return res_view.collect(ROOT, [r for r in runs if r.get("status") == "running"])

        try:
            snap = _usage_snapshot()
        except Exception as e:  # noqa: BLE001 - read-only view
            snap = None
            st.warning(f"Η ανάλυση δεν είναι διαθέσιμη ({type(e).__name__}).")
        if snap:
            its, tot = snap["items"], snap["totals"]
            df = pd.DataFrame([{"όνομα": i["name"], "κατηγορία": i["category"],
                                "CPU %": None if i.get("unavailable") else round(i["cpu"], 1),
                                "μνήμη MiB": None if i.get("unavailable") else round(i["mem"] / 2**20, 1),
                                "δίσκος MiB": round(i["disk"] / 2**20, 1), "λεπτομέρεια": i.get("detail", "")} for i in its])
            pc = st.columns(3)
            for col, (ttl, key, total, unit) in zip(pc, (("CPU", "cpu", tot["cpu"], 1), ("Μνήμη", "mem", tot["mem"], 2**30),
                                                         ("Δίσκος", "disk", tot["disk"], 2**30))):
                sh = {k: v for k, v in res_view.shares(its, key).items() if v > 0}
                meas = sum(sh.values())
                if key == "disk":   # 'other' = used - measured; free from the filesystem
                    sh["other"] = sh.get("other", 0) + max(0, tot["disk_used"] - meas)
                    sh["free"] = max(0, tot["disk"] - tot["disk_used"])
                else:
                    sh["free"] = max(0, total - meas)
                fig = go.Figure(go.Pie(labels=list(sh), values=[v / unit for v in sh.values()], hole=0.35, sort=False))
                fig.update_layout(title=ttl, height=300, margin=dict(l=0, r=0, t=40, b=0))
                col.plotly_chart(fig, width="stretch")
            st.dataframe(df.sort_values(["κατηγορία", "CPU %"], ascending=[True, False]), hide_index=True, width="stretch")
            for n_ in snap["notes"]:
                st.caption(n_)
            st.caption("Τα args των εντολών κρύβονται αν μοιάζουν με token/key/password. Cache ~20 s.")

# ================================================================ files (read-only; NOT in a fragment)
with tab_files:
    import base64
    ss = st.session_state
    qp_path = st.query_params.get("path")
    if qp_path and ss.get("fb_qp_seen") != (qp_path, st.query_params.get("line")):
        ss["fb_qp_seen"] = (qp_path, st.query_params.get("line"))
        ss["fb_path_in"] = qp_path
        try:
            ss["fb_line"] = int(st.query_params.get("line", 0)) or None
        except ValueError:
            ss["fb_line"] = None
    ss.setdefault("fb_path_in", file_view.ROOTS[0])
    fc1, fc2 = st.columns([5, 1])
    fc1.text_input("Διαδρομή (απόλυτη ή ~/…)", key="fb_path_in")
    hidden = fc2.toggle("Κρυφά αρχεία", value=False, key="fb_hidden")
    glob_hits = None
    try:
        if "*" in ss["fb_path_in"] or "?" in ss["fb_path_in"]:
            glob_hits = file_view.glob_entries(ss["fb_path_in"], show_hidden=hidden)
            real = None
        else:
            real = file_view.resolve(ss["fb_path_in"])
    except file_view.FileViewError as e:
        real = None
        if str(e) == "denied":
            st.error(file_view.DENIED_MSG, icon="🚫")
        elif str(e) == "missing":
            st.warning("Δεν υπάρχει αυτή η διαδρομή.")
        else:
            st.error("Εκτός επιτρεπτών φακέλων: " + ", ".join(file_view.ROOTS))

    def _goto(p):
        ss["fb_path_in"] = p
        ss["fb_line"] = None

    if glob_hits is not None:
        st.caption(f"Μοτίβο `{ss['fb_path_in']}` · {len(glob_hits)} αποτελέσματα")
        for i, r in enumerate(glob_hits[:200]):
            st.button(f"{r['icon']} {r['path']}" + ("/" if r["is_dir"] else ""), key=f"fb_glob_{i}", on_click=_goto, args=(r["path"],))
    if real:
        crumbs = file_view.breadcrumbs(real)
        cols = st.columns(min(len(crumbs), 8) or 1)
        for i, (lbl, p) in enumerate(crumbs[-8:]):
            cols[i].button(lbl or "/", key=f"fb_crumb_{i}_{p}", on_click=_goto, args=(p,), width="stretch")
        if os.path.isdir(real):
            rows = file_view.list_dir(real, show_hidden=hidden)
            st.caption(f"`{real}` · {len(rows)} στοιχεία · πρώτα τα νεότερα· κλικ σε γραμμή για άνοιγμα")
            if rows:
                df = pd.DataFrame({"": [r["icon"] for r in rows], "Όνομα": [r["name"] + ("/" if r["is_dir"] else "") for r in rows],
                                   "Μέγεθος (B)": [r["size"] for r in rows], "Τροποποίηση": [r["mtime"] for r in rows]})
                dkey = f"fb_df_{real}_{hidden}"
                ss["fb_rows"] = (dkey, [r["path"] for r in rows])

                def _pick():
                    k, paths = ss["fb_rows"]
                    sel = ss[k].selection.rows
                    if sel:
                        _goto(paths[sel[0]])

                st.dataframe(df, hide_index=True, width="stretch", on_select=_pick, selection_mode="single-row", key=dkey)
        else:
            size = os.path.getsize(real)
            kind = file_view.kind_of(real)
            st.markdown(f"**{os.path.basename(real)}** · {size:,} B · {kind}")
            st.button("⬆️ Φάκελος", key="fb_up", on_click=_goto, args=(os.path.dirname(real),))
            ext = os.path.splitext(real)[1].lower()
            if kind == "text":
                tail = st.toggle("Τέλος αρχείου (τελευταίες 500 γραμμές)", value=False, key="fb_tail")
                lines, total, trunc = file_view.read_text(real, tail=tail)
                start = ss.get("fb_line")
                if start and not tail:
                    st.caption(f"Γραμμή {start} (ανοίχτηκε από σύνδεσμο)")
                    lo = max(1, start - 5)
                    shown = lines[lo - 1:lo - 1 + 60]
                    st.code("\n".join(f"{lo + i:>5}  {l}" for i, l in enumerate(shown)), language=None)
                    st.caption("Πλήρες αρχείο παρακάτω")
                if trunc:
                    st.caption("Εμφανίζονται οι τελευταίες 500 γραμμές." if tail else "Εμφανίζονται οι πρώτες 2.000 γραμμές.")
                st.code("\n".join(lines), language=file_view.LANG.get(ext), line_numbers=True)
            elif kind == "csv":
                header, crow, trunc = file_view.read_csv(real)
                width = max([len(header)] + [len(r) for r in crow]) if crow or header else 0
                cols_ = (header + [f"col{i}" for i in range(len(header), width)])
                cols_ = [c or f"col{i}" for i, c in enumerate(cols_)]
                st.dataframe(pd.DataFrame([r + [""] * (width - len(r)) for r in crow], columns=cols_), width="stretch")
                if trunc:
                    st.caption("Εμφανίζονται οι πρώτες 500 γραμμές δεδομένων.")
            elif kind == "image":
                if size <= file_view.DOWNLOAD_MAX:
                    st.image(real)
            elif kind == "pdf":
                if size < file_view.PDF_EMBED_MAX:
                    b64 = base64.b64encode(open(real, "rb").read()).decode()
                    st.html(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="700"></iframe>')
                else:
                    st.info("PDF πάνω από 20 MB: μόνο λήψη.")
            else:
                st.info("Δυαδικό αρχείο: μόνο μέγεθος και sha256.")
                st.code(f"size   {size:,} B\nsha256 {file_view.sha256(real)}", language=None)
            if size <= file_view.DOWNLOAD_MAX:
                with open(real, "rb") as fh:
                    st.download_button("⬇️ Λήψη", fh.read(), file_name=os.path.basename(real), key="fb_dl")
            else:
                st.caption("Αρχείο πάνω από 200 MB: χωρίς λήψη.")

# ================================================================ kubernetes (read-only)
BADGE = {"ok": "🟢", "degraded": "🟠", "failing": "🔴"}
if _tab_live(tab_k8s):  # lazy: hidden tabs do no work
    with tab_k8s:
        kc1, kc2, kc3 = st.columns([2, 1, 1])
        snap0 = k8s_view.fetch()
        nss = k8s_view.namespaces(snap0["data"]) if snap0["up"] else []
        ns_sel = kc1.selectbox("Namespace", ["(όλα)"] + nss, key="k8s_ns")
        auto = kc3.toggle("Αυτόματη ανανέωση (30 δ.)", value=False, key="k8s_auto")
        if kc2.button("Ανανέωση", key="k8s_refresh"):
            k8s_view.clear_cache()

        @st.fragment(run_every=30 if auto else None)
        def k8s_panel(ns):
            snap = k8s_view.fetch()
            st.caption(f"context: `{snap['context'] or '—'}` · read-only (`kubectl get`)")
            if not snap["up"]:
                st.error("Το cluster δεν είναι διαθέσιμο (API server δεν απαντά)\n\n`" + (snap["error"] or "—") + "`")
                return
            v = k8s_view.parse_snapshot(snap["data"], None if ns == "(όλα)" else ns)
            k = k8s_view.kpis(v)
            c = st.columns(4)
            c[0].metric("Nodes ready", f"{k['nodes_ready']}/{k['nodes_total']}")
            c[1].metric("Pods Running", k["pods_running"])
            c[2].metric("Pods Pending / Failed", f"{k['pods_pending']} / {k['pods_failed']}")
            c[3].metric("Deployments υγιή", f"{k['deploys_ok']}/{k['deploys_total']}")
            bad = k8s_view.failing_items(v)
            if bad:
                st.markdown("##### Προβλήματα")
                st.dataframe(pd.DataFrame([{"": BADGE[h], "Είδος": kd, "Όνομα": nm, "Αιτία": r} for kd, nm, h, r in bad]),
                             hide_index=True, use_container_width=True)
            else:
                st.success("Όλα υγιή.")
            ph = k8s_view.pods_by_phase(v)
            if ph:
                fig = go.Figure()
                colors = {"Running": "#2e9e5b", "Pending": "#e0a100", "Failed": "#d64545", "Succeeded": "#5b8bd6"}
                for phase in ("Running", "Pending", "Failed", "Succeeded", "Unknown"):
                    fig.add_bar(name=phase, x=list(ph), y=[ph[n].get(phase, 0) for n in ph],
                                marker_color=colors.get(phase, "#888"))
                fig.update_layout(barmode="stack", height=240, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="pods")
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("##### Pods")
            st.dataframe(pd.DataFrame([{"": BADGE[p["health"]], "Όνομα": p["name"], "Namespace": p["namespace"],
                                        "Phase": p["phase"], "Ready": p["ready"], "Restarts": p["restarts"],
                                        "Age": p["age"], "Node": p["node"]} for p in v["pods"]]),
                         hide_index=True, use_container_width=True)
            st.markdown("##### Deployments")
            st.dataframe(pd.DataFrame([{"": BADGE[d["health"]], "Όνομα": d["name"], "Namespace": d["namespace"],
                                        "Ready": d["ready"], "Up-to-date": d["up_to_date"], "Available": d["available"]}
                                       for d in v["deployments"]]), hide_index=True, use_container_width=True)
            st.markdown("##### Services")
            st.dataframe(pd.DataFrame(v["services"]), hide_index=True, use_container_width=True)
            st.markdown("##### Nodes")
            st.dataframe(pd.DataFrame([{"": BADGE[n["health"]], "Όνομα": n["name"], "Ready": "Ναι" if n["ready"] else "ΟΧΙ",
                                        "CPU": n["cpu"], "Μνήμη": n["memory"]} for n in v["nodes"]]),
                         hide_index=True, use_container_width=True)
            if v["hpas"]:
                st.markdown("##### HPAs")
                st.dataframe(pd.DataFrame(v["hpas"]), hide_index=True, use_container_width=True)
        k8s_panel(ns_sel)

# ================================================================ prometheus (read-only, live)
@st.cache_data(ttl=300, show_spinner=False)
def _prom_avail():
    return prom_view.availability()


@st.cache_data(ttl=600, show_spinner=False)
def _prom_names():
    return prom_view.metric_names()


if _tab_live(tab_prom):  # lazy: hidden tabs do no work
    with tab_prom:
        st.caption(f"Prometheus `{prom_view.BASE_URL}` · μόνο GET (`query`, `query_range`, `label/__name__/values`). "
                   "Δεν υπάρχει node-exporter: τα «Node» βγαίνουν από το cAdvisor (root cgroup).")
        if web_terminal.tailnet_host(_req_host):
            st.markdown(f"[Prometheus UI (tailnet)]({web_terminal.service_url(_req_host, 'prometheus', prom_view.BASE_URL)})")
        try:
            _avail = _prom_avail()
        except Exception:  # noqa: BLE001
            _avail = {}
        _defaults = [k for k, v in prom_view.CATALOGUE.items() if v["default"]]

        def _plabel(k):
            v = prom_view.CATALOGUE[k]
            return v["title"] + ("" if _avail.get(k, True) else "  ⚠ χωρίς δεδομένα")

        pr1, pr2 = st.columns([1, 3])
        p_range = pr1.radio("Εύρος", list(prom_view.RANGES), index=1, horizontal=True, key="prom_range")
        p_auto = pr1.toggle("Αυτόματη ανανέωση (15 δ.)", value=True, key="prom_auto")
        p_sel = []
        with pr2:
            for cat in prom_view.CATEGORIES:
                keys = [k for k, v in prom_view.CATALOGUE.items() if v["category"] == cat]
                p_sel += st.multiselect(cat, keys, default=[k for k in keys if k in _defaults], format_func=_plabel,
                                        key=f"prom_cat_{cat}")
        p_names = []
        try:
            p_names = _prom_names()
        except prom_view.PromError as e:
            st.warning(f"Δεν φορτώθηκε η λίστα μετρικών: {e}")
        pa1, pa2 = st.columns([2, 1])
        p_adv = pa1.multiselect("Advanced — οποιαδήποτε μετρική (αναζήτηση)", p_names, key="prom_adv",
                                help="Counters (…_total/_count/_sum/_bucket) εμφανίζονται ως rate(…[5m]).")
        p_custom = {n: prom_view.default_expr_for_metric(n) for n in p_adv}

        @st.fragment(run_every=15 if p_auto else None)
        def prom_panel(sel, custom, rng):
            minutes = prom_view.RANGES[rng]
            items = [(prom_view.CATALOGUE[k]["title"], prom_view.CATALOGUE[k]["expr"], prom_view.CATALOGUE[k]["unit"])
                     for k in sel] + [(n, e, "") for n, e in custom.items()]
            if not items:
                st.info("Διάλεξε τουλάχιστον μία μετρική.")
                return
            cols = st.columns(2)
            for i, (title, expr, unit) in enumerate(items):
                with cols[i % 2]:
                    try:
                        series = prom_view.query_range(expr, minutes)
                    except prom_view.PromError as e:
                        st.error(f"{title}: {e}")
                        continue
                    fig = go.Figure()
                    for lbl, pts in series[:30]:
                        fig.add_scatter(x=[dt.datetime.fromtimestamp(t) for t, _ in pts], y=[v for _, v in pts],
                                        mode="lines", name=lbl)
                    fig.update_layout(title=dict(text=title, font=dict(size=13)), height=260,
                                      margin=dict(l=0, r=0, t=36, b=0), yaxis_title=unit or None,
                                      showlegend=len(series) > 1, legend=dict(font=dict(size=9)))
                    if not series:
                        st.warning(f"{title}: καμία τιμή στο εύρος.")
                    else:
                        st.plotly_chart(fig, use_container_width=True)
                    with st.expander("PromQL", expanded=False):
                        st.code(expr, language="promql")
            st.caption(f"Ανανεώθηκε {dt.datetime.now().strftime('%H:%M:%S')}")
        prom_panel(p_sel, p_custom, p_range)

# ================================================================ grafana (iframe + quick links; no credentials here)
GRAFANA_URL = web_terminal.service_url(_req_host, "grafana", os.environ.get("QRL_GRAFANA_URL", "http://localhost:32000"))
if _tab_live(tab_grafana):  # lazy: hidden tabs do no work
    with tab_grafana:
        st.info("VS Code → Ports → Forward 32000, μετά κάνε login στο Grafana μία φορά μέσα σε αυτό το frame.", icon="🔌")
        st.markdown(f"[Άνοιγμα σε νέα καρτέλα]({GRAFANA_URL})")
        st.markdown("##### Γρήγοροι σύνδεσμοι (Explore, με το προεπιλεγμένο datasource)")
        gl = st.columns(2)
        for i, (title, url) in enumerate(prom_view.grafana_links(GRAFANA_URL)):
            gl[i % 2].markdown(f"- [{title}]({url})")
        st.caption("Αν δεν υπάρχουν dashboards, ένα Redis/K8s dashboard μπορεί να εισαχθεί αργότερα (χρειάζεται το login "
                   "του ερευνητή· δεν γίνεται αυτόματα). Αν το frame μένει κενό, το Grafana μπορεί να μην επιτρέπει "
                   "embedding (`allow_embedding`) ή να λείπει το port forward.")
        st.iframe(GRAFANA_URL, height=800)

# ================================================================ paper & venues
with tab_paper:
    st.markdown("##### 💬 Chat με τον συγγραφέα — «Paper — συγγραφή»")
    _d = db()
    paper_tid = _d.ensure_thread(PAPER_THREAD_TITLE, "Νήμα για τη συγγραφή και το review του paper.")
    _d.close()
    _pd = db()
    st.markdown("##### 🗳️ Ερωτήσεις του συντονιστή για το paper")
    decision_panel(_pd, select=lambda rs: paper_requests(rs, paper_tid), pre="paper_", label="Ερώτηση",
                   empty_msg="Δεν υπάρχουν ανοιχτές ερωτήσεις για το paper.")
    _pd.close()
    show_thread(paper_tid, key="paper", title="Συζήτηση paper")
    pw_col, pr_col = st.columns(2)
    p_writers = pw_col.multiselect("Συγγραφή", list(PAPER_WRITERS), default=["writer-sonnet"],
                                   format_func=PAPER_WRITERS.get, key="paper_writers", placeholder="✍️ Συγγραφή: ποιος γράφει",
                                   label_visibility="collapsed",
                                   help="Ποιοι συντάσσουν το κείμενο σε αυτό το μήνυμα.")
    p_reviewers = pr_col.multiselect("Review", list(PAPER_REVIEWERS), default=["codex-reviewer"],
                                     format_func=PAPER_REVIEWERS.get, key="paper_reviewers", placeholder="🔍 Review: ποιος ελέγχει",
                                     label_visibility="collapsed",
                                     help="Ποιοι κάνουν review μετά τη σύνταξη.")
    # Not inside a fragment, so typing is never refreshed away.
    psub = st.chat_input("Γράψε στον συγγραφέα… (Enter = αποστολή)", accept_file="multiple", key="paper_composer")
    if psub:
        ptext_in = getattr(psub, "text", psub) if not isinstance(psub, str) else psub
        pfiles_in = list(getattr(psub, "files", None) or [])
        try:
            dd = db()
            thr = dd.thread(paper_tid)
            dd.researcher_send(ptext_in, thread_id=paper_tid, reply_to=thr[-1]["id"] if thr else None,
                               req_writers=p_writers, req_reviewers=p_reviewers,
                               attachments=[(f.name, f.getvalue()) for f in pfiles_in] or None, root=ROOT)
            dd.close()
            st.toast("Στάλθηκε στον συγγραφέα", icon="📨")
            st.rerun()
        except (LabError, UploadError) as e:
            st.error(str(e))
    st.divider()
    # ---- manuscript: build, PDF, source (NOT in a fragment, so typing is never refreshed away)
    st.markdown("##### 📝 Paper")
    pss = st.session_state
    pc1, pc2 = st.columns([1, 2])
    pvenue = pc1.selectbox("Venue", paper_build.VENUES, format_func=str.upper, key="paper_venue")
    if pc2.button("Μεταγλώττιση", key="paper_compile", type="primary"):
        with st.spinner("latexmk…"):
            pss["paper_result"] = {"venue": pvenue, **paper_build.compile(ROOT, pvenue, timeout=120)}
    pres = pss.get("paper_result")
    if pres:
        if pres["ok"]:
            st.success(f"{pres['venue'].upper()}: επιτυχία ({pres['seconds']} s)")
        else:
            st.error(f"{pres['venue'].upper()}: αποτυχία (rc={pres['returncode']})")
            if pres["hint"]:
                st.warning(pres["hint"])
            st.code(pres["log_tail"], language=None)
    pdfp = paper_build.pdf_path(ROOT, pvenue)
    if os.path.exists(pdfp):
        st.caption(f"Τελευταία μεταγλώττιση {pvenue.upper()}: {paper_build.build_time(ROOT, pvenue)}")
        with open(pdfp, "rb") as _f:
            pdf_bytes = _f.read()
        st.download_button("⬇️ PDF", pdf_bytes, file_name=os.path.basename(pdfp), mime="application/pdf",
                           key="paper_dl")
        if len(pdf_bytes) < file_view.PDF_EMBED_MAX:
            try:
                st.pdf(pdf_bytes, height=600)
            except Exception:  # noqa: BLE001 - fall back to a base64 iframe
                import base64
                st.markdown(f'<iframe src="data:application/pdf;base64,{base64.b64encode(pdf_bytes).decode()}" '
                            'width="100%" height="600"></iframe>', unsafe_allow_html=True)
    else:
        st.info(f"Δεν υπάρχει PDF για {pvenue.upper()}· πάτα «Μεταγλώττιση».")

    st.markdown("##### Πηγή LaTeX")
    pfiles = paper_build.list_files(ROOT)
    if pfiles:
        psel = st.selectbox("Αρχείο", pfiles, key="paper_file")
        try:
            ptext = paper_build.read_file(ROOT, psel)
        except paper_build.PaperError as e:
            ptext = None
            st.error(str(e))
        if ptext is not None:
            if st.toggle("Επεξεργασία", key="paper_edit"):
                newtext = st.text_area("Περιεχόμενο", ptext, height=420, key=f"paper_ta_{psel}")
                if st.button("Αποθήκευση", key="paper_save"):
                    try:
                        h = paper_build.save_file(ROOT, psel, newtext)
                        st.success(f"Αποθηκεύτηκε και έγινε commit ({h})" if h else "Αποθηκεύτηκε (καμία αλλαγή για commit)")
                    except (paper_build.PaperError, subprocess.CalledProcessError) as e:
                        st.error(str(e))
            else:
                st.code(ptext, language={".tex": "latex", ".bib": "bibtex", ".md": "markdown"}.get(
                    os.path.splitext(psel)[1].lower()), line_numbers=True)

    st.markdown("##### Κατάσταση")
    trows = paper_build.todo_counts(ROOT)
    if trows:
        st.dataframe(pd.DataFrame([{"ενότητα": r["section"], "λέξεις (περίπου)": r["words"], "\\todo": r["todo"]}
                                   for r in trows]), hide_index=True, width="stretch")
    tbd = paper_build.tbd_count(ROOT)
    st.metric("[TBD] στο generated/results.tex", "—" if tbd is None else tbd)
    crows = paper_build.claims_rows(ROOT)
    st.markdown(f"Γραμμές claims.md: **{len(crows)}**")

# ================================================================ venues
if _tab_live(tab_venues):  # lazy: hidden tabs do no work
    with tab_venues:
        dl = read_text(os.path.join(ROOT, "docs", "deadlines.json"))
        if dl:
            try:
                items = json.loads(dl)
                rows = []
                for it in items:
                    due = dt.datetime.fromisoformat(it["due"])
                    days = (due - dt.datetime.now(dt.timezone.utc)).total_seconds() / 86400
                    rows.append({"συνέδριο": it["venue"], "τι": it["what"], "προθεσμία": it["due_label"],
                                 "μέρες": round(days, 1),
                                 "Πότε / Πού": f"{it.get('event_dates') or '—'} · {it.get('location') or '—'}",
                                 "Tier": it.get("tier") or "—",
                                 "Acceptance (3 έτη)": it.get("acceptance") or "—",
                                 "πηγή": it["source"], "επαληθεύτηκε": it["verified"]})
                st.markdown("##### Προθεσμίες")
                st.html(deadlines_table_html(rows))
            except (ValueError, KeyError) as e:
                st.error(f"docs/deadlines.json: {e}")
        venues = read_text(os.path.join(ROOT, "docs", "VENUES.md"))
        st.markdown("##### Υποψήφια συνέδρια (scholar)")
        st.markdown(venues or "_Δεν υπάρχει ακόμη `docs/VENUES.md`._")
        claims = read_text(os.path.join(ROOT, "paper", "claims.md"))
        st.markdown("##### Ισχυρισμοί → τεκμήρια")
        st.markdown(claims or "_Δεν υπάρχει ακόμη `paper/claims.md`._")
        st.divider()
        st.subheader("Συζήτηση συνεδρίων")
        _dv = db()
        ven_tid = _dv.ensure_thread(VENUES_THREAD_TITLE, "Συζήτηση για συνέδρια/περιοδικά και προθεσμίες (scholar).")
        _dv.close()
        show_thread(ven_tid, key="venues_chat", title="Συζήτηση συνεδρίων")
        ven_in = st.chat_input("Ρώτα για συνέδρια, προθεσμίες, καταλληλότητα… (Enter = αποστολή)", key="venues_composer")
        if ven_in:
            try:
                dd = db()
                thr = dd.thread(ven_tid)
                body = ven_in if ven_in.lstrip().startswith(VENUES_TAG) else f"{VENUES_TAG} {ven_in}"
                dd.researcher_send(body, thread_id=ven_tid, reply_to=thr[-1]["id"] if thr else None)
                dd.close()
                st.toast("Στάλθηκε στον συντονιστή (scholar)", icon="📨")
                st.rerun()
            except (LabError, ValueError) as ex:
                st.error(str(ex))

# ================================================================ audit
if _tab_live(tab_audit):  # lazy: hidden tabs do no work
    with tab_audit:
        d = db()
        rows = d.audit(limit=300)
        d.close()
        if rows:
            st.dataframe(pd.DataFrame([{"πότε": fmt_ts(r["ts"]), "ποιος": r["actor"], "ενέργεια": r["action"],
                                        "στόχος": r["target"], "λεπτομέρεια": r["detail"]} for r in rows]),
                         hide_index=True, width="stretch")
        else:
            st.caption("Κενό ιστορικό.")

# ================================================================ sudo grants (researcher approves here)
with tab_sudo:
    if not _unlocked:
        pin_form("sudo")
    else:
        st.markdown("Αιτήματα με scope `sudo`. Η έγκριση ανοίγει χρονικά περιορισμένο grant μόνο για τα προγράμματα που "
                    "προκύπτουν από τις εντολές του αιτήματος (`tools/sudo_grant.py`, ίδια όρια: έως "
                    f"{sudo_ui.MAX_MINUTES} λεπτά, χωρίς shells/editors).")
        st.warning("Το dashboard και οι πράκτορες τρέχουν με τον ίδιο χρήστη Unix. Το grant ελέγχεται από το hook "
                   "`sudo_gate.py` και το αρχείο ανήκει στον root, αλλά αυτό δεν είναι απομόνωση ασφαλείας (PLAN §7).", icon="⚠️")
        st.subheader("Αιτήματα άδειας από το terminal")

        @st.fragment(run_every=refresh)
        def perm_requests():
            pend = perm_store.pending()
            term_prompt_panel("sudo", True)
            if not pend:
                st.caption("Κανένα αίτημα άδειας από το terminal αυτή τη στιγμή. Όταν ο συντονιστής ζητήσει άδεια, "
                           "εμφανίζεται εδώ για ~90 δευτερόλεπτα· αν δεν απαντήσεις, ρωτάει κανονικά το terminal.")
            for pr in pend:
                with st.container(border=True):
                    left = max(0, int(90 - (time.time() - pr["ts"])))
                    st.markdown(f"**{pr['tool']}** · {pr['description']} · απομένουν ~{left} δευτ.")
                    st.code(pr["detail"] or "(κενό)", language="bash" if pr["tool"] == "Bash" else "text")
                    st.caption(f"φάκελος: `{pr['cwd']}` · {dt.datetime.fromtimestamp(pr['ts']).strftime('%H:%M:%S')}")
                    pc = st.columns(2)
                    if pc[0].button("Έγκριση", key=f"perm_ok_{pr['id']}", type="primary"):
                        perm_store.decide(pr["id"], True)
                        st.rerun()
                    if pc[1].button("Απόρριψη", key=f"perm_no_{pr['id']}"):
                        perm_store.decide(pr["id"], False, "Απορρίφθηκε από τον ερευνητή στο dashboard.")
                        st.rerun()
            rec = perm_store.recent(limit=5)
            if rec:
                lab = {"approved": "εγκρίθηκε", "denied": "απορρίφθηκε", "timeout": "έληξε (ρώτησε το terminal)"}
                st.caption("Πρόσφατα: " + " · ".join(
                    f"{dt.datetime.fromtimestamp(r['ts']).strftime('%H:%M')} {r['tool']} {lab.get(r['state'], r['state'])}"
                    for r in rec))

        perm_requests()
        _can_sudo = sudo_ui.sudo_available()
        d = db()
        sreqs = [r for r in d.requests(state="open") if r["scope"] == "sudo"]
        st.subheader(f"Ανοιχτά αιτήματα ({len(sreqs)})")
        if not sreqs:
            st.success("Κανένα ανοιχτό αίτημα sudo.", icon="✅")
        for r in sreqs:
            info = sudo_ui.parse_request(r["body"])
            with st.container(border=True):
                st.markdown(f"**{r['id']}** · {r['title']}")
                if r["body"]:
                    st.caption(r["body"][:600])
                if info["commands"]:
                    st.markdown("Εντολές που ζητούνται:")
                    st.code("\n".join(info["commands"]), language="bash")
                st.markdown("Προγράμματα: " + (", ".join(f"`{x}`" for x in info["programs"]) or "—"))
                problems = []
                if not info["commands"]:
                    problems.append("το αίτημα δεν περιέχει γραμμές `sudo …`")
                if info["unparsed"]:
                    problems.append("εντολές που δεν αναλύονται με ασφάλεια: " + "; ".join(info["unparsed"]))
                if info["refused"]:
                    problems.append("απαγορευμένα προγράμματα (θα επέτρεπαν τα πάντα): " + ", ".join(info["refused"]))
                if "approve" not in json.loads(r["options"]):
                    problems.append("το αίτημα δεν έχει επιλογή έγκρισης")
                for pmsg in problems:
                    st.error(pmsg)
                mins = st.number_input("Λεπτά", min_value=1, max_value=sudo_ui.MAX_MINUTES, value=sudo_ui.DEFAULT_MINUTES,
                                       step=5, key=f"sudo_min_{r['id']}")
                cmd = sudo_ui.open_command(r["id"], info["programs"], mins)
                cols = st.columns(2)
                if _can_sudo:
                    if cols[0].button("Έγκριση και άνοιγμα grant", key=f"sudo_ok_{r['id']}", type="primary",
                                      disabled=bool(problems)):
                        ok_, msg = sudo_ui.open_grant(r["id"], info["programs"], mins)
                        if ok_:
                            d.decide(r["id"], "approve", msg)
                            st.rerun()
                        else:
                            st.error(f"Δεν άνοιξε: {msg}")
                else:
                    st.info("Το `sudo -n` δεν είναι διαθέσιμο από το dashboard. Τρέξε στην καρτέλα ⌨️ Terminal:", icon="ℹ️")
                    st.code(" ".join(cmd), language="bash")
                    if cols[0].button("Το έτρεξα — σήμανση ως εγκεκριμένο", key=f"sudo_ok_{r['id']}", type="primary",
                                      disabled=bool(problems)):
                        d.decide(r["id"], "approve", f"grant ανοίχτηκε χειροκίνητα: {' '.join(cmd)}")
                        st.rerun()
                if cols[1].button("Απόρριψη", key=f"sudo_no_{r['id']}"):
                    d.decide(r["id"], "reject", "")
                    st.rerun()
        d.close()
        st.subheader("Τρέχον grant")
        st.code(sudo_ui.status(), language="text")
        gcols = st.columns([1, 4])
        if _can_sudo:
            if gcols[0].button("Κλείσιμο", key="sudo_close"):
                ok_, msg = sudo_ui.close_grant()
                (st.success if ok_ else st.error)(msg)
        else:
            st.caption("Κλείσιμο από το ⌨️ Terminal: `python3 tools/sudo_grant.py close`")
        st.subheader("🛡️ Πρόσβαση")
        _acc = access.recent(50)
        if _acc:
            st.dataframe(pd.DataFrame([{"ώρα": dt.datetime.fromtimestamp(a["ts"]).strftime("%m-%d %H:%M:%S"),
                                        "login": a.get("login") or "(κανένα)", "λόγος": a.get("reason"),
                                        "ip": a.get("ip") or ""} for a in _acc]), hide_index=True, width="stretch")
        else:
            st.caption("Καμία απορριφθείσα πρόσβαση (`.lab/access_log.jsonl`).")
        st.subheader("Audit log (τελευταίες 50 χρήσεις)")
        aud = sudo_ui.audit_tail(50)
        if aud:
            st.dataframe(pd.DataFrame([{"ώρα": dt.datetime.fromtimestamp(a.get("ts", 0)).strftime("%m-%d %H:%M:%S"),
                                        "task": a.get("task"), "προγράμματα": ", ".join(a.get("programs") or []),
                                        "agent": a.get("agent_type") or "", "εντολή": (a.get("command") or "")[:200]}
                                       for a in aud]), hide_index=True, width="stretch")
        else:
            st.caption("Καμία χρήση ακόμη (`.lab/sudo_audit.jsonl`).")

# ================================================================ VM outages (.lab/outages.jsonl, written by tools/boot_recover.sh)
if _tab_live(tab_outage):  # lazy: hidden tabs do no work
    with tab_outage:
        _orows = outage.load()
        _osum = outage.summary(_orows)
        _c1, _c2, _c3 = st.columns(3)
        _c1.metric("Διακοπές συνολικά", _osum["count"])
        _c2.metric("Τελευταία", outage.fmt_ts(_osum["last"]["boot_at"]) if _osum["last"] else "—")
        _c3.metric("Συνολικός χρόνος διακοπής", outage.fmt_dur(_osum["total_downtime_s"]) if _orows else "—")
        _boot = outage.boot_time()
        _hb = outage.read_epoch(os.path.join(LAB, "heartbeat"))
        st.caption(f"Uptime τώρα: {outage.fmt_dur(time.time() - _boot) if _boot else 'άγνωστο'} · "
                   f"ηλικία heartbeat: {outage.fmt_dur(time.time() - _hb) if _hb else 'δεν υπάρχει (cron watchdog)'}")
        if _orows:
            st.dataframe(pd.DataFrame([{"Έπεσε": outage.fmt_ts(r.get("down_at")), "Ανέβηκε": outage.fmt_ts(r.get("boot_at")),
                                        "Αποκατάσταση": outage.fmt_ts(r.get("recovered_at")),
                                        "Διάρκεια": outage.fmt_dur(r.get("downtime_s")), "Είδος": r.get("kind", "unknown")}
                                       for r in reversed(_orows)]), hide_index=True, width="stretch")
        else:
            st.info("Καμία καταγεγραμμένη διακοπή. Η καταγραφή γίνεται από το `tools/boot_recover.sh` (cron @reboot).")
        st.caption("Ο χρόνος «Έπεσε» είναι το τελευταίο heartbeat (ανά λεπτό), άρα ±1 λεπτό. Το είδος προκύπτει από το `last -x` "
                   "(καθαρή επανεκκίνηση ή κατάρρευση/ρεύμα· «unknown» αν δεν είναι σαφές).")

# ================================================================ research change history (docs/changes.json, curated)
if _tab_live(tab_changes):  # lazy: hidden tabs do no work
    with tab_changes:
        try:
            _chg = changes_view.load()
        except (OSError, ValueError) as ex:
            _chg = []
            st.error(f"Δεν φορτώθηκε το docs/changes.json: {ex}")
        st.caption("Οι σημαντικές αλλαγές της έρευνας, από την πιο πρόσφατη. Πάτα σε μια γραμμή για την αναλυτική εξήγηση. "
                   "Τύποι: " + " · ".join(f"{changes_view.BADGE[t]} {t}" for t in changes_view.TYPES))
        for _it in _chg:
            with st.expander(changes_view.label(_it)):
                st.markdown(f"**{_it['summary_el']}**")
                st.markdown(_it["details_el"])
                st.caption("Αποδείξεις: " + " · ".join(f"`{r}`" for r in _it["refs"]))

# ================================================================ models (docs/models.json -> diagrams; design sandbox + apply to code/ via git)
def _mdl_apply(mid, fn, *args, **kw):
    """Callback: apply an edit function to the sandbox copy of model `mid`; errors are shown, never raised."""
    try:
        st.session_state["mdl_ed"][mid] = fn(st.session_state["mdl_ed"][mid], *args, **kw)
        st.session_state.pop("mdl_err", None)
    except models_view.ModelsError as ex:
        st.session_state["mdl_err"] = f"{mid}: {ex}"


def _mdl_field(mid, bid, field, key):
    _mdl_apply(mid, models_view.edit_block, bid, **{field: st.session_state[key]})


def _mdl_group_repeat(mid, bid, key):
    cur = st.session_state["mdl_ed"][mid]
    grp = next(b for b in cur["blocks"] if b["id"] == bid).get("group")
    m = cur
    try:
        for b in cur["blocks"]:
            if b.get("group") == grp:
                m = models_view.edit_block(m, b["id"], repeat=st.session_state[key])
        st.session_state["mdl_ed"][mid] = m
    except models_view.ModelsError as ex:
        st.session_state["mdl_err"] = f"{mid}: {ex}"


def _mdl_select(mid, bid):
    st.session_state[f"mdl_sel_{mid}"] = bid


def _models_tab():
    base_models = models_view.load()
    st.session_state.setdefault("mdl_ed", {})
    st.session_state.setdefault("mdl_gen", 0)
    st.info(f"Διάγραμμα, hyper-parameters και πηγές κάθε μοντέλου, από τον πραγματικό κώδικα (docs/models.json). Οι αλλαγές εδώ είναι "
            f"**sandbox σχεδιασμού**: «{models_view.PROPOSAL_NOTE}». Μόνο το κουμπί «Εφαρμογή στον κώδικα» γράφει (ένα config JSON, "
            "με commit σε branch της επιλογής σου).")
    ids = [m["id"] for m in base_models]
    names = {m["id"]: m["name"] for m in base_models}
    c1, c2 = st.columns([4, 1])
    show = c1.multiselect("Μοντέλα που εμφανίζονται", ids, default=ids, format_func=lambda i: names[i], key="mdl_show")
    if c2.button("↺ Επαναφορά όλων", key="mdl_reset_all", width="stretch"):
        st.session_state["mdl_ed"] = {}
        st.session_state["mdl_gen"] += 1
        st.rerun()
    if st.session_state.get("mdl_err"):
        st.error(st.session_state["mdl_err"])
    gen = st.session_state["mdl_gen"]
    for base in base_models:
        if base["id"] not in show:
            continue
        mid = base["id"]
        cur = st.session_state["mdl_ed"].setdefault(mid, copy.deepcopy(base))
        with st.container(border=True):
            badge = "✅ σε χρήση" if base["status"] == "used" else "💡 προτεινόμενο — δεν έχει υλοποιηθεί"
            st.markdown(f"## {base['name']}")
            st.markdown(f"**{badge}** · {'κβαντικό κύκλωμα' if base['kind'] == 'quantum' else 'κλασικό νευρωνικό'}")
            st.write(base["desc_el"])
            st.caption("Πηγές: " + " · ".join(f"`{s['path']}:{s['lines']}`" + (f" ({s['note']})" if s.get("note") else "") for s in base["sources"]))
            slot = st.container()
            hp = base["hyperparams"]
            with st.expander("Hyper-parameters και πηγές τους", expanded=False):
                st.dataframe(pd.DataFrame([{"παράμετρος": k, "τιμή": str(cur["hyperparams"][k]["value"]), "πηγή": v["src"],
                                            "σχόλιο": v.get("note", "")} for k, v in hp.items()]), hide_index=True, width="stretch")
            st.markdown("##### ✏️ Επεξεργασία (sandbox)")
            bids = [b["id"] for b in cur["blocks"]]
            skey = f"mdl_sel_{mid}"
            if st.session_state.get(skey) not in bids:
                st.session_state[skey] = bids[0]
            sel = st.radio("Επίλεξε επίπεδο", bids, key=skey, horizontal=True,
                           format_func=lambda i, cur=cur: next(b["label_el"] for b in cur["blocks"] if b["id"] == i))
            blk = next(b for b in cur["blocks"] if b["id"] == sel)
            k0 = f"mdl_{gen}_{mid}_{sel}"
            cols = st.columns(4)
            if base["kind"] == "classical":
                if blk["type"] == "input":
                    cols[0].number_input("Χαρακτηριστικά (είσοδος)", 1, 512, blk["units"], key=k0 + "_u", on_change=_mdl_field, args=(mid, sel, "units", k0 + "_u"))
                    cols[1].number_input("Παράθυρο T", 1, 100, blk["window"], key=k0 + "_w", on_change=_mdl_field, args=(mid, sel, "window", k0 + "_w"))
                else:
                    cols[0].number_input("Νευρώνες / κρυφές μονάδες", 1, 4096, blk["units"], key=k0 + "_u", on_change=_mdl_field, args=(mid, sel, "units", k0 + "_u"))
                if blk["type"] == "lstm":
                    cols[1].number_input("Στρώματα LSTM", 1, 16, blk["num_layers"], key=k0 + "_l", on_change=_mdl_field, args=(mid, sel, "num_layers", k0 + "_l"))
                    cols[2].caption("Ενεργοποίηση: σ/tanh (σταθερή στις πύλες LSTM)")
                elif blk["type"] in ("dense", "output"):
                    cols[2].selectbox("Συνάρτηση ενεργοποίησης", models_view.ACTIVATIONS, index=models_view.ACTIVATIONS.index(blk["activation"]),
                                      key=k0 + "_a", on_change=_mdl_field, args=(mid, sel, "activation", k0 + "_a"))
            else:
                cols[0].number_input("Qubits (όλο το κύκλωμα)", 1, 16, models_view.n_qubits(cur), key=f"mdl_{gen}_{mid}_nq",
                                     on_change=lambda mid=mid, k=f"mdl_{gen}_{mid}_nq": _mdl_apply(mid, models_view.edit_hyper, "n_qubits", st.session_state[k]))
                if blk["type"] in ("encoding", "variational"):
                    cols[1].multiselect("Πύλες", models_view.GATES, default=blk["gates"], key=k0 + "_g", on_change=_mdl_field, args=(mid, sel, "gates", k0 + "_g"))
                if blk["type"] == "entangle":
                    cols[1].selectbox("Εμπλοκή", models_view.PATTERNS, index=models_view.PATTERNS.index(blk["pattern"]), key=k0 + "_p",
                                      on_change=_mdl_field, args=(mid, sel, "pattern", k0 + "_p"))
                if blk["type"] == "measure":
                    cols[1].selectbox("Μέτρηση", ("probs", "expval"), index=("probs", "expval").index(blk["mode"]), key=k0 + "_m",
                                      on_change=_mdl_field, args=(mid, sel, "mode", k0 + "_m"))
                    cols[2].number_input("Qubits ανάγνωσης", 1, 16, blk["readout"], key=k0 + "_r", on_change=_mdl_field, args=(mid, sel, "readout", k0 + "_r"))
                if blk.get("group"):
                    cols[2].number_input("Επαναλήψεις re-uploading", 1, 100, blk["repeat"], key=k0 + "_rep", on_change=_mdl_group_repeat, args=(mid, sel, k0 + "_rep"))
            movable = blk["type"] not in models_view.FIXED_FIRST + models_view.FIXED_LAST
            b1, b2, b3, b4 = st.columns(4)
            b1.button("⬆ Πάνω / αριστερά", key=f"mdl_up_{gen}_{mid}", disabled=not movable, width="stretch", on_click=_mdl_apply, args=(mid, models_view.move_block, sel, -1))
            b2.button("⬇ Κάτω / δεξιά", key=f"mdl_dn_{gen}_{mid}", disabled=not movable, width="stretch", on_click=_mdl_apply, args=(mid, models_view.move_block, sel, 1))
            if base["kind"] == "classical":
                b3.button("➕ Νέο dense μετά", key=f"mdl_add_{gen}_{mid}", disabled=blk["type"] == "output", width="stretch", on_click=_mdl_apply, args=(mid, models_view.add_block, sel, "dense"))
            else:
                b3.button("➕ Παραμετρικό μετά", key=f"mdl_addv_{gen}_{mid}", disabled=blk["type"] in models_view.FIXED_LAST, width="stretch", on_click=_mdl_apply, args=(mid, models_view.add_block, sel, "variational"))
            b4.button("🗑 Διαγραφή επιπέδου", key=f"mdl_del_{gen}_{mid}", disabled=blk["type"] in models_view.FIXED_FIRST + models_view.FIXED_LAST + ("lstm", "encoding"), width="stretch", on_click=_mdl_apply, args=(mid, models_view.remove_block, sel))
            if base["kind"] == "classical":
                st.markdown("**Hyper-parameters εκπαίδευσης**")
                hc = st.columns(5)
                for col, (name, label, kw) in zip(hc, (("batch_size", "Batch size", dict(min_value=1, max_value=4096, step=1)),
                                                      ("gamma", "γ (discount)", dict(min_value=0.0, max_value=1.0, step=0.01, format="%.3f")),
                                                      ("replay_size", "Replay buffer", dict(min_value=1, max_value=10**7, step=100)),
                                                      ("target_sync_every", "Sync target (replays)", dict(min_value=1, max_value=10**6, step=1)),
                                                      ("lr", "Learning rate", dict(min_value=1e-7, max_value=1.0, step=1e-5, format="%.6f")))):
                    kk = f"mdl_{gen}_{mid}_hp_{name}"
                    col.number_input(label, value=type(base["hyperparams"][name]["value"])(cur["hyperparams"][name]["value"]), key=kk,
                                     on_change=lambda mid=mid, name=name, kk=kk: _mdl_apply(mid, models_view.edit_hyper, name, st.session_state[kk]), **kw)
                st.caption("Αλλαγές σε hyper-parameters αποθηκεύονται μόνο στην πρόταση JSON· ο κώδικας (agents) τα ορίζει ο ίδιος.")
            diff = models_view.diff_models(base, cur)
            stt = models_view.stats(cur)
            st.caption(("Αλλαγές από το πραγματικό: " + "; ".join(diff)) if diff else "Καμία αλλαγή από το πραγματικό μοντέλο.")
            with slot:
                page, hgt = models_view.render_html(cur, sel)
                components.html(page, height=hgt, scrolling=False)
            sc1, sc2, sc3 = st.columns([3, 1, 1])
            pname = sc1.text_input("Όνομα πρότασης", value=mid, key=f"mdl_{gen}_{mid}_pname")
            if sc2.button("💾 Αποθήκευση πρότασης", key=f"mdl_save_{gen}_{mid}", width="stretch"):
                path = models_view.save_proposal(base, cur, pname)
                st.success(f"Αποθηκεύτηκε: `{os.path.relpath(path, ROOT)}` — {models_view.PROPOSAL_NOTE}")
            if sc3.button("↺ Επαναφορά", key=f"mdl_reset_{gen}_{mid}", width="stretch"):
                st.session_state["mdl_ed"][mid] = copy.deepcopy(base)
                st.session_state["mdl_gen"] += 1
                st.rerun()
            st.caption(f"💡 {models_view.PROPOSAL_NOTE}")
            if base["kind"] == "classical" and base.get("config_name"):
                with st.expander("⚙️ Εφαρμογή στον κώδικα (~/qrl-lab/code)", expanded=False):
                    st.caption("Γράφει το `models/configs/" + base["config_name"] + ".json` και κάνει commit στο branch που θα διαλέξεις, χωρίς να αλλάξει "
                               "το checkout του code/ (git plumbing). Δεν συνδέεται ακόμα με τους agents (παγωμένα αρχεία), άρα δεν επηρεάζει τρέχοντα ή εγκεκριμένα πειράματα.")
                    branches = models_view.list_branches()
                    mode = st.radio("Προορισμός", ("Υπάρχον branch", "Νέο branch"), horizontal=True, key=f"mdl_{gen}_{mid}_mode")
                    if mode == "Υπάρχον branch":
                        tgt = st.selectbox("Branch", branches, key=f"mdl_{gen}_{mid}_br")
                        nb, bb = None, None
                    else:
                        nb = st.text_input("Όνομα νέου branch", key=f"mdl_{gen}_{mid}_nb", placeholder="π.χ. model-edit-derp-64")
                        bb = st.selectbox("Βασισμένο στο branch", branches, key=f"mdl_{gen}_{mid}_bb")
                        tgt = None
                    pk = f"mdl_plan_{mid}"
                    if st.button("Εφαρμογή στον κώδικα", key=f"mdl_apply_{gen}_{mid}", type="primary"):
                        _d = db()
                        _rows = models_view.running_runs(_d.runs())
                        _d.close()
                        st.session_state[pk] = models_view.plan_apply(cur, branch=tgt, new_branch=(nb or "").strip() or None, base=bb, running=_rows) \
                            if mode == "Υπάρχον branch" or (nb or "").strip() else {"errors": ["Γράψε όνομα νέου branch."], "warnings": [], "ok": False, "diff": ""}
                    plan = st.session_state.get(pk)
                    if plan:
                        for e_ in plan["errors"]:
                            st.error(e_)
                        for w_ in plan["warnings"]:
                            st.warning(w_)
                        if plan.get("diff"):
                            st.markdown(f"**Προεπισκόπηση αλλαγής** → branch `{plan['target']}`" + (" (νέο)" if plan.get("create") else ""))
                            st.code(plan["diff"], language="diff")
                            st.caption("Commit message: " + plan["message"].splitlines()[0])
                        if plan.get("ok") and st.button("✅ Επιβεβαίωση και commit", key=f"mdl_confirm_{gen}_{mid}"):
                            try:
                                _d = db()
                                _rows = models_view.running_runs(_d.runs())
                                _d.close()
                                fresh = models_view.plan_apply(cur, branch=plan["target"] if not plan["create"] else None,
                                                               new_branch=plan["target"] if plan["create"] else None,
                                                               base=plan["source"], running=_rows)
                                sha = models_view.apply_commit(fresh if fresh["ok"] else plan)
                                st.success(f"Commit `{sha[:10]}` στο branch `{plan['target']}`: {plan['rel']}")
                                st.session_state.pop(pk, None)
                            except models_view.ModelsError as ex:
                                st.error(str(ex))
            elif base["kind"] == "quantum":
                st.caption("Τα κβαντικά κυκλώματα δεν έχουν αρχείο αρχιτεκτονικής στον κώδικα: μόνο πρόταση JSON.")


if _tab_live(tab_models):  # lazy: hidden tabs do no work
    with tab_models:
        try:
            _models_tab()
        except (OSError, ValueError) as ex:
            st.error(f"Δεν φορτώθηκε το docs/models.json: {ex}")

# ================================================================ architecture (3D topology of the whole lab)
if _tab_live(tab_arch):  # lazy: hidden tabs do no work
    with tab_arch:
        topology_ui.show(_unlocked, pin_form, _cinfo.get("login", "?") if _on_tailnet else "researcher")

# ================================================================ extensions (catalog only from .lab/extensions_catalog.json)
if _tab_live(tab_ext):  # lazy: hidden tabs do no work
    with tab_ext:
        st.subheader("Εγκατεστημένα")
        st.caption("Ανιχνεύονται τώρα, μόνο για ανάγνωση (ονόματα και περιγραφές).")
        _inst = installed_view.detect(ROOT)
        for _i in range(0, len(_inst), 3):
            for _col, _it in zip(st.columns(3), _inst[_i:_i + 3]):
                _col.markdown(installed_view.card_html(_it), unsafe_allow_html=True)
        st.divider()
        st.subheader("Εξοικονόμηση tokens (τελευταίες 6 ώρες) — εκτίμηση")
        st.caption("ΕΚΤΙΜΗΣΗ, όχι μέτρηση. Πραγματικά δεδομένα: πλήθος γεγονότων στο `.lab/events.jsonl` και στα sandbox ledgers. "
                   "Τα tokens ανά γεγονός είναι **παραδοχές** (πίνακας από κάτω, αποθηκεύονται στο `dashboard/token_savings.json`). "
                   "Μοντέλο: εξοικονόμηση = Σ γεγονότα × (χωρίς σύστημα − με σύστημα).")
        _tsp = os.path.join(ROOT, "dashboard", "token_savings.json")
        _ass = token_savings.load_assumptions(_tsp)
        _cnt = token_savings.count_events(os.path.join(ROOT, ".lab", "events.jsonl"),
                                          sandbox_view.ledger_paths(os.path.join(ROOT, ".lab", "sandbox")), time.time() - 6 * 3600)
        _ts = token_savings.compute(_cnt, _ass)
        _m = st.columns(3)
        _m[0].metric("Με το σύστημα (εκτίμηση)", f"{_ts['with']:,}")
        _m[1].metric("Χωρίς (εκτίμηση)", f"{_ts['without']:,}")
        _m[2].metric("Εξοικονόμηση (εκτίμηση)", f"{_ts['saved']:,}", f"≈{_ts['pct']:.0f}%")
        st.dataframe(pd.DataFrame([{"κατηγορία": r["label"], "γεγονότα 6ω": r["n"], "χωρίς (εκτ.)": r["without"],
                                    "με (εκτ.)": r["with"], "εξοικ. (εκτ.)": r["saved"]} for r in _ts["rows"]]),
                     hide_index=True, width="stretch")
        with st.expander("Παραδοχές (tokens ανά γεγονός) — επεξεργάσιμες"):
            _ed = st.data_editor(pd.DataFrame([{"key": k, "κατηγορία": a["label"], "χωρίς": a["without"], "με": a["with"], "αιτιολόγηση": a["why"]}
                                               for k, a in _ass.items()]), hide_index=True, width="stretch",
                                 disabled=["key", "κατηγορία", "αιτιολόγηση"], key="tok_assump")
            if st.button("Αποθήκευση παραδοχών", key="tok_save"):
                json.dump({r["key"]: {"without": int(r["χωρίς"]), "with": int(r["με"]), "why": r["αιτιολόγηση"]}
                           for r in _ed.to_dict("records")}, open(_tsp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
                st.rerun()
        st.caption("Κλήσεις Codex μέσω wrapper (`codex:codex-rescue`) δεν προσμετρώνται διπλά.")
        st.divider()
        st.markdown("Προτάσεις skills/plugins/MCP **μόνο** από το αρχείο `.lab/extensions_catalog.json`, που το γεμίζει "
                    "ο συντονιστής μετά από αναζήτηση. Τίποτα δεν εγκαθίσταται από εδώ· το «Πρόσθεσε» στέλνει αίτημα έγκρισης.")
        cat = ext_catalog.load(ROOT)
        shown = [c for c in ext_catalog.CATEGORIES if c in cat] + [c for c in cat if c not in ext_catalog.CATEGORIES]
        if not shown:
            st.info("δεν υπάρχει ακόμα κατάλογος", icon="🧩")
        for ci, c in enumerate(shown):
            st.subheader(c)
            for ei, e in enumerate(cat[c]):
                with st.container(border=True):
                    st.markdown(f"**{e['name']}** · {e['kind']} · {e['provider']}")
                    st.write(e["description"])
                    st.caption(f"Κόστος: {e['cost']} · [πηγή]({e['url']})")
                    if st.button("Πρόσθεσε", key=f"ext_add_{ci}_{ei}"):
                        try:
                            dd = db()
                            t_, b_ = ext_catalog.add_request(e)
                            rid_ = dd.ask("approval", t_, b_, author="researcher", scope="external", options=["approve", "reject"])
                            dd.close()
                            st.success(f"Στάλθηκε αίτημα έγκρισης {rid_} (καρτέλα Αποφάσεις).")
                        except LabError as ex:
                            st.error(str(ex))
        st.divider()
        st.subheader("Ζήτα ένα skill")
        _dx = db()
        ext_tid = _dx.ensure_thread(ext_catalog.EXT_THREAD_TITLE, "Αιτήματα αναζήτησης επεκτάσεων και οι απαντήσεις τους.")
        _dx.close()
        show_thread(ext_tid, key="ext_chat")
        ext_in = st.chat_input("Περίγραψε ποιο skill/επέκταση θέλεις… (Enter = αποστολή)", key="ext_composer")
        if ext_in:
            try:
                dd = db()
                thr = dd.thread(ext_tid)
                dd.researcher_send(ext_catalog.search_message(ext_in), thread_id=ext_tid,
                                   reply_to=thr[-1]["id"] if thr else None)
                dd.close()
                st.toast("Στάλθηκε στον συντονιστή", icon="📨")
                st.rerun()
            except (LabError, ValueError) as ex:
                st.error(str(ex))

# ================================================================ terminal (on demand, localhost only)
with tab_term:
    if not _unlocked:
        pin_form("term")
    else:
        st.warning("Πλήρες shell της VM για όποιον έχει το SSH tunnel. Ανοίγει μόνο όταν το ζητήσεις, μόνο στο "
                   "127.0.0.1:8502, με τυχαίο token, και κλείνει μόνο του μετά από 30 λεπτά αδράνειας.", icon="⚠️")
        if web_terminal.running():
            if st.button("Κλείσιμο", key="term_close"):
                web_terminal.stop()
                st.rerun()
            url = web_terminal.iframe_url(_req_host)
            if url and not _side:
                st.iframe(url, height=600)
            elif _side:
                st.caption("Το terminal εμφανίζεται στη δεξιά στήλη.")
            st.caption("Αν δεν φορτώνει: στο VS Code → Ports → Forward 8502")
        elif st.button("Άνοιγμα terminal", key="term_open"):
            ok_, msg = web_terminal.start()
            if ok_:
                st.rerun()
            else:
                st.error(f"Δεν άνοιξε: {msg}")
