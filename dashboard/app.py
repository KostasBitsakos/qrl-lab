"""QRL-Lab dashboard: the researcher's single place to talk to the agents, decide, and watch the work.

Run from ~/qrl-lab:  .venv/bin/streamlit run dashboard/app.py
It binds to 127.0.0.1:8501 (see .streamlit/config.toml); reach it from the laptop through an SSH tunnel.

Design rules:
- The dashboard never executes commands typed by the user. It only writes validated rows to .lab/lab.db
  (messages, decisions, stop requests); the coordinator and the launcher act on them.
- Widgets where the researcher types are never inside auto-refreshing fragments, so nothing typed is lost.
"""
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

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ["QRL_LAB_DIR"] = ROOT
sys.path.insert(0, os.path.join(ROOT, "tools"))
from labdb import DECISIONS, LabDB, LabError  # noqa: E402
import k8s_view  # noqa: E402
from uploads import UploadError, body_with_attachments, save_uploads  # noqa: E402

LAB = os.path.join(ROOT, ".lab")
DB_PATH = os.path.join(LAB, "lab.db")
EVENTS = os.path.join(LAB, "events.jsonl")
HEARTBEAT = os.path.join(LAB, "bridge_heartbeat")

# Categorical slots in fixed order (validated reference palette, light mode). Colour follows the agent, never rank.
AGENTS = {
    "coordinator": ("Συντονιστής (Claude Opus)", "#2a78d6", "🧭"),
    "codex": ("Codex (OpenAI)", "#eb6834", "🟠"),
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
             "external": "εξωτερικό", "other": "άλλο"}
REQ_STATE = {"open": ("🟡", "ανοιχτό"), "approved": ("✅", "εγκρίθηκε"), "rejected": ("⛔", "απορρίφθηκε"),
             "changes_requested": ("✏️", "ζητήθηκαν αλλαγές"), "answered": ("💬", "απαντήθηκε"),
             "acknowledged": ("👁️", "το είδες"), "withdrawn": ("↩️", "αποσύρθηκε")}
RUN_STATUS = {"starting": ("🔵", "ξεκινά"), "running": ("🟢", "τρέχει"), "done": ("✅", "ολοκληρώθηκε"),
              "failed": ("❌", "απέτυχε"), "stopped": ("⏹️", "διακόπηκε")}

st.set_page_config(page_title="QRL-Lab", page_icon="🧪", layout="wide")


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
    rows = []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({"ts": dt.datetime.fromtimestamp(e.get("ts", 0)), "agent": agent_key(e.get("agent_type")),
                     "agent_id": e.get("agent_id"), "event": e.get("hook_event_name", ""),
                     "tool": e.get("tool_name", ""), "summary": e.get("summary", "")})
    return pd.DataFrame(rows)


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


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


# ---------------------------------------------------------------- sidebar (auto-refresh)
st.sidebar.markdown("### 🧪 QRL-Lab")
refresh = st.sidebar.select_slider("Ανανέωση κάθε (δευτ.)", options=[3, 5, 10, 30], value=5)


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
        if not notif.empty and "permission" in str(notif.iloc[-1]["summary"]).lower():
            st.warning("Ο συντονιστής περιμένει άδεια στο terminal/app: " + str(notif.iloc[-1]["summary"]),
                       icon="🔐")
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

# ---------------------------------------------------------------- tabs
d0 = db()
n_open = len(d0.requests(state="open"))
d0.close()
tab_chat, tab_dec, tab_agents, tab_runs, tab_council, tab_res, tab_k8s, tab_paper, tab_audit = st.tabs([
    "💬 Συνομιλία", f"✅ Αποφάσεις ({n_open})", "🤖 Πράκτορες", "📈 Πειράματα", "⚖️ Council",
    "🖥️ Πόροι", "☸️ Kubernetes", "📄 Paper & συνέδρια", "🧾 Ιστορικό"])

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
                with st.container(height=260):
                    st.radio("Θέματα", ids, key="thread_sel", format_func=thread_label,
                             label_visibility="collapsed", on_change=_leave_new_topic)
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
        def show_thread(tid):
            dd = db()
            msgs = dd.thread(tid)
            dd.close()
            if not msgs:
                return
            root = msgs[0]
            icon, label = MSG_STATUS.get(root["status"] or "", ("", ""))
            first = (root["title"] or (root["body"] or "").strip().splitlines()[0])[:80] if root["body"] else tid
            st.markdown(f"**Κύρια συζήτηση** · {first} · `{tid}` · {icon} {label}")
            with st.container(height=480):  # oldest first, newest at the bottom
                for m in msgs:
                    name, avatar = author_info(m["author"])
                    with st.chat_message("user" if m["author"] == "researcher" else "assistant", avatar=avatar):
                        extra = ""
                        if m["author"] == "researcher" and m["status"]:
                            si, sl = MSG_STATUS.get(m["status"], ("", m["status"]))
                            extra = f" · {si} {sl}"
                        label = f"{name} · {m['model']}" if m.get("model") else name
                        st.caption(f"**{label}** · {fmt_ts(m['ts'])} · {KIND_LABEL.get(m['kind'], m['kind'])}"
                                   f"{extra} · `{m['id']}`")
                        st.markdown(m["body"])
                st.html("<div id='chat-end'></div>")
            for m in msgs:
                if m["author"] == "researcher" and m["status"] == "delivered" and (since(m["updated_at"]) or 0) > 180:
                    st.info(f"Το {m['id']} παραδόθηκε αλλά ο συντονιστής δεν το έχει αναλάβει ακόμη "
                            "(απασχολημένος, offline ή σε όριο χρήσης).", icon="⏳")
                    break

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
    # Enter sends, Shift+Enter = newline. Not inside any fragment, so typing is never refreshed away.
    sub = st.chat_input("Γράψε εδώ… (Enter = αποστολή, Shift+Enter = νέα γραμμή)", accept_file="multiple",
                        key="composer")
    if sub:
        text = getattr(sub, "text", sub) if not isinstance(sub, str) else sub
        files = list(getattr(sub, "files", None) or [])
        try:
            saved = save_uploads([(f.name, f.getvalue()) for f in files], ROOT) if files else []
            dd = db()
            target = None if new_topic else cur
            reply_to = None
            if target:
                thr = dd.thread(target)
                reply_to = thr[-1]["id"] if thr else None
            mid = dd.researcher_send(body_with_attachments(text, saved), kind=kind or "message",
                                     thread_id=target, reply_to=reply_to)
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
    open_reqs = sorted(d.requests(state="open"), key=lambda r: (-r["blocking"], r["ts"]))
    if not open_reqs:
        st.success("Δεν υπάρχει τίποτα που να περιμένει απόφασή σου.", icon="✅")
    for r in open_reqs:
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
            with st.form(f"decide_{r['id']}"):
                note = st.text_area("Σχόλιο / απάντηση" + (" (υποχρεωτικό)" if r["kind"] == "question" else ""),
                                    key=f"note_{r['id']}", height=80)
                cols = st.columns(len(options))
                labels = {"approve": "✅ Έγκριση", "reject": "⛔ Απόρριψη", "changes": "✏️ Ζητώ αλλαγές",
                          "answer": "💬 Απάντηση", "ack": "👁️ Το είδα"}
                pressed = None
                for col, opt in zip(cols, options):
                    if col.form_submit_button(labels.get(opt, opt), type="primary" if opt == "approve" else "secondary"):
                        pressed = opt
            if pressed:
                try:
                    state = d.decide(r["id"], pressed, note, actor="researcher")
                    st.toast(f"{r['id']}: {REQ_STATE[state][1]}", icon=REQ_STATE[state][0])
                    st.rerun()
                except LabError as e:
                    st.error(str(e))
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
    hours = st.select_slider("Παράθυρο", options=[1, 3, 6, 12, 24, 72], value=6, format_func=lambda h: f"{h} ώρες",
                             key="agent_hours")

    @st.fragment(run_every=refresh)
    def agents_view(hours):
        ev = read_events()
        if ev.empty:
            st.info("Δεν υπάρχει ακόμη δραστηριότητα πρακτόρων. Τα hooks του Claude Code γράφουν στο "
                    "`.lab/events.jsonl` μόλις ξεκινήσει ο συντονιστής.", icon="🤖")
            return
        now_ = dt.datetime.now()
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
            fig.add_trace(go.Scatter(
                x=sub["ts"], y=[name] * len(sub), mode="markers", name=name,
                marker=dict(size=9, color=color, line=dict(width=2, color="#fcfcfb")),
                customdata=list(zip(sub["tool"].fillna(""), sub["summary"].fillna("").str.slice(0, 120))),
                hovertemplate="%{x|%H:%M:%S}<br><b>%{customdata[0]}</b> %{customdata[1]}<extra>" + name + "</extra>"))
        fig.update_layout(height=90 + 46 * len(lanes), margin=dict(l=10, r=10, t=10, b=30), showlegend=False,
                          hovermode="closest", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig.update_xaxes(showgrid=True, gridcolor="rgba(137,135,129,0.25)", gridwidth=1)
        fig.update_yaxes(showgrid=False, categoryorder="array", categoryarray=[AGENTS.get(k, (k,))[0] for k in lanes][::-1])
        st.plotly_chart(fig, theme="streamlit", width="stretch", config={"displayModeBar": False})
        counts = win.groupby("agent").size().reindex(lanes).fillna(0).astype(int)
        st.caption(" · ".join(f"{AGENTS.get(k, (k,))[0]}: {n} ενέργειες" for k, n in counts.items()))
        with st.expander("Πίνακας τελευταίων ενεργειών"):
            tail = ev.tail(40).iloc[::-1]
            st.dataframe(pd.DataFrame({"ώρα": tail["ts"].dt.strftime("%H:%M:%S"),
                                       "πράκτορας": [AGENTS.get(a, (a,))[0] for a in tail["agent"]],
                                       "γεγονός": tail["event"], "εργαλείο": tail["tool"],
                                       "περίληψη": tail["summary"]}), hide_index=True, width="stretch")
    agents_view(hours)

# ================================================================ runs
with tab_runs:
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

# ================================================================ kubernetes (read-only)
BADGE = {"ok": "🟢", "degraded": "🟠", "failing": "🔴"}
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

# ================================================================ paper & venues
with tab_paper:
    dl = read_text(os.path.join(ROOT, "docs", "deadlines.json"))
    if dl:
        try:
            items = json.loads(dl)
            rows = []
            for it in items:
                due = dt.datetime.fromisoformat(it["due"])
                days = (due - dt.datetime.now(dt.timezone.utc)).total_seconds() / 86400
                rows.append({"συνέδριο": it["venue"], "τι": it["what"], "προθεσμία": it["due_label"],
                             "μέρες": round(days, 1), "πηγή": it["source"], "επαληθεύτηκε": it["verified"]})
            st.markdown("##### Προθεσμίες")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={"πηγή": st.column_config.LinkColumn("πηγή")})
        except (ValueError, KeyError) as e:
            st.error(f"docs/deadlines.json: {e}")
    venues = read_text(os.path.join(ROOT, "docs", "VENUES.md"))
    st.markdown("##### Υποψήφια συνέδρια (scholar)")
    st.markdown(venues or "_Δεν υπάρχει ακόμη `docs/VENUES.md`._")
    claims = read_text(os.path.join(ROOT, "paper", "claims.md"))
    st.markdown("##### Ισχυρισμοί → τεκμήρια")
    st.markdown(claims or "_Δεν υπάρχει ακόμη `paper/claims.md`._")
    secs = sorted(glob.glob(os.path.join(ROOT, "paper", "sections", "*.tex")))
    if secs:
        st.markdown("##### Ενότητες paper")
        st.dataframe(pd.DataFrame([{"ενότητα": os.path.basename(p),
                                    "λέξεις (περίπου)": len((read_text(p) or "").split()),
                                    "\\todo": (read_text(p) or "").count("\\todo")} for p in secs]),
                     hide_index=True, width="stretch")

# ================================================================ audit
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
