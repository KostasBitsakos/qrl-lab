"""Dashboard panel for the dispatcher: choose the coordinator, failover, pause, and see usage per model.

Used from dashboard/app.py:
    from coord_panel import render_coordinator_panel
    with st.sidebar:
        render_coordinator_panel()
Widgets are outside the auto-refreshing fragment, so a choice is never lost by a refresh.
Costs are client-side estimates from the CLIs (on a subscription they show the equivalent API price, which is a good
relative measure of how much of the limit a task used).
"""
import datetime as dt
import os
import sys
import time

import streamlit as st

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from dispatcher import LABEL, PROVIDERS, DispatchDB, dispatch_db_path, fmt_ts, limits_text  # noqa: E402

LIGHT = {"ok": "🟢", "exhausted": "🔴"}


def _dd():
    return DispatchDB(dispatch_db_path(ROOT))


def _set(key, value):
    try:
        with _dd() as dd:
            dd.set(key, value, actor="researcher")
    except Exception as e:  # shown, never raised into the dashboard
        st.session_state["coord_error"] = str(e)


def _on_coordinator():
    _set("coordinator", st.session_state["coord_choice"])


def _on_toggle(key, state_key, invert=False):
    v = bool(st.session_state[state_key])
    _set(key, "0" if v == invert else "1")


def render_coordinator_panel():
    with _dd() as dd:
        _render(dd)


def _render(dd):
    s = dd.settings()
    st.markdown("#### 🧭 Συντονιστής")
    st.radio("Ποιος συντονίζει", PROVIDERS, index=PROVIDERS.index(s["coordinator"]), key="coord_choice",
             format_func=lambda p: LABEL[p], horizontal=True, on_change=_on_coordinator,
             help="Για ένα μόνο μήνυμα: γράψε στην αρχή του @claude ή @codex.")
    st.toggle("Αυτόματη ανάληψη αν τελειώσει το όριο", value=s["failover"] == "1", key="coord_failover",
              on_change=_on_toggle, args=("failover", "coord_failover"))
    st.toggle("Παύση (δεν ξεκινά καμία εργασία)", value=s["paused"] == "1", key="coord_paused",
              on_change=_on_toggle, args=("paused", "coord_paused"))
    st.toggle("Επιτρέπονται πληρωμένα credits (Claude)", value=s["allow_paid_credits"] == "1", key="coord_paid",
              on_change=_on_toggle, args=("allow_paid_credits", "coord_paid"))
    if st.session_state.get("coord_error"):
        st.error(st.session_state.pop("coord_error"))
    cols = st.columns(2)
    for col, p in zip(cols, PROVIDERS):
        if dd.provider(p)["state"] != "ok" and col.button(f"{LABEL[p]}: διαθέσιμος ξανά", key=f"coord_clear_{p}"):
            dd.clear(p, actor="researcher")
            st.rerun()
    _status_fragment()


@st.fragment(run_every=10)
def _status_fragment():
    with _dd() as dd:
        _status(dd)


def _status(dd):
    lines = []
    for p in PROVIDERS:
        st_p = dd.provider(p)
        extra = f" ως {fmt_ts(st_p['until_ts'])}" if st_p["state"] != "ok" else ""
        lim = limits_text(dd, p)
        lines.append(f"{LIGHT.get(st_p['state'], '⚪')} {LABEL[p]}{extra}" + (f" — {lim}" if lim else ""))
    st.caption("  \n".join(lines))
    hb = os.path.join(ROOT, ".lab", "bridge_heartbeat")
    age = time.time() - os.path.getmtime(hb) if os.path.exists(hb) else None
    if age is None or age > 30:
        st.caption("⚫ dispatcher εκτός λειτουργίας")
    run = dd.running_task()
    if run:
        st.caption(f"⏳ τώρα: {LABEL.get(run['provider'], run['provider'])} · {run['kind']} · από {run['started'][11:16]}")
    since = (dt.datetime.now().astimezone() - dt.timedelta(days=7)).isoformat(timespec="seconds")
    today = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0).isoformat(timespec="seconds")
    with st.expander("Κατανάλωση (εκτίμηση)"):
        for title, t0 in (("Σήμερα", today), ("7 ημέρες", since)):
            rows = dd.totals(t0)
            if not rows:
                st.caption(f"{title}: καμία εργασία")
                continue
            parts = [f"{LABEL.get(r['provider'], r['provider'])}: {r['n']} εργ., ≈${(r['cost'] or 0):.2f}, "
                     f"{(r['inp'] or 0) // 1000}k in / {(r['cached'] or 0) // 1000}k cache / {(r['out'] or 0) // 1000}k out"
                     for r in rows]
            st.caption(f"**{title}** — " + " · ".join(parts))
        for t in dd.recent_tasks(8):
            cost = f"${t['cost_usd']:.2f}" if t["cost_usd"] is not None else "–"
            st.caption(f"#{t['id']} {t['started'][5:16].replace('T', ' ')} {LABEL.get(t['provider'], t['provider'])}"
                       f" · {t['kind']} · {t['status']} · {cost}")
