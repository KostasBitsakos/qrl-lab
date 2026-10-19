#!/usr/bin/env python3
"""Streamlit body of the tab «Αρχιτεκτονική» (kept out of dashboard/app.py). Logic lives in topology_view.py."""
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import topology_view as tv


def show(unlocked, pin_form, who="researcher"):
    inv = tv.inventory()
    st.caption("Ολόκληρο το lab ως «σχολή»: κάθε κόμβος είναι πραγματικό στοιχείο (αρχείο, tmux window, cron, k8s object, "
               "τεκμηριωμένος ρόλος). Hover/tap για περιγραφή. Χρώμα πυρήνα = κατάσταση, παλμός = heartbeat, "
               "σωματίδια = ροή. Το «unknown» σημαίνει ότι καμία πηγή δεν το λέει.")
    components.html(tv.render(inv), height=960)
    st.button("🔄 Ανανέωση", key="arch_refresh")
    with st.expander("Πίνακας κόμβων (χωρίς WebGL)"):
        st.dataframe(pd.DataFrame(tv.node_table(inv)), hide_index=True, width="stretch")
    st.subheader("Μοντέλο και effort ανά πράκτορα")
    st.caption("Γράφει ΜΟΝΟ το `docs/agent_routing.json` (τιμές που ακολουθεί ο συντονιστής) και καταγράφει την αλλαγή· "
               "δεν αγγίζει settings ή δικαιώματα.")
    roles = tv.routable(inv)
    ids = [r[0] for r in roles]
    sel = st.selectbox("Πράκτορας", ids, key="arch_role")
    _, kind, cur_m, cur_e = next(r for r in roles if r[0] == sel)
    models, efforts = tv.allowed(kind)
    c = st.columns(2)
    m = c[0].selectbox("Μοντέλο", models, index=models.index(cur_m) if cur_m in models else 0, key=f"arch_m_{sel}")
    e = c[1].selectbox("Effort", efforts, index=efforts.index(cur_e) if cur_e in efforts else 0, key=f"arch_e_{sel}")
    st.caption(f"Τρέχον: {cur_m} / {cur_e}" + (" (override)" if tv.load_routing().get(sel) else ""))
    if not unlocked:
        pin_form("arch")
        return
    if st.button("Εφαρμογή", key="arch_apply", type="primary"):
        ok, msg = tv.apply_routing(sel, m, e, kind, unlocked, actor=who)
        (st.success if ok else st.error)(msg)
