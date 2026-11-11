"""«⚙️ Σύστημα» tab (v0.5.1 B1): view only. Never writes, never calls a model.

Data functions take explicit inputs so tests can run them on fake databases; `render()` is the only Streamlit part.
Databases are opened as sqlite URIs with ?mode=ro. Usage follows the B0 rule (docs/DECISIONS.md, 2026-11-05): the
freshest Claude value from dispatch.db.limits or the statusline, with its time; an expired window is «άγνωστη»,
never 100 %; Codex unknown is shown as unknown.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import time
from contextlib import closing

import dispatcher as D
import governor as G
import usage_limits as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def paths(root=ROOT):
    """dispatch.db honours QRL_DISPATCH_DB like dispatcher/usage_limits, so every section reads the same database."""
    return {"dispatch": os.environ.get("QRL_DISPATCH_DB") or os.path.join(root, ".lab", "dispatch.db"),
            "lab": os.path.join(root, ".lab", "lab.db"), "heartbeat": os.path.join(root, ".lab", "bridge_heartbeat"),
            "claude_status": os.environ.get("QRL_CLAUDE_USAGE_FILE") or os.path.join(root, ".lab", "usage", "claude.json")}


DISPATCH_DB, LAB_DB, HEARTBEAT = (paths()[k] for k in ("dispatch", "lab", "heartbeat"))
UNITS = ("qrl-dispatcher", "qrl-dashboard")
UNKNOWN = "άγνωστη"
try:
    from zoneinfo import ZoneInfo
    ATHENS = ZoneInfo("Europe/Athens")
except ImportError:  # python3.8 outside the venv
    ATHENS = None

# Every dispatcher setting: (group, Greek label, help). tests/test_system_view.py fails if a DEFAULTS key is missing.
SETTINGS_META = {
    "coordinator": ("Πάροχοι", "Κύριος πάροχος", "Ποιος παίρνει πρώτος κάθε δουλειά (claude/codex)."),
    "failover": ("Πάροχοι", "Εναλλαγή σε όριο", "1 = όταν ο ένας πιάσει όριο, η δουλειά πάει στον άλλο."),
    "paused": ("Πάροχοι", "Παύση", "1 = ο dispatcher δεν παίρνει νέα δουλειά."),
    "allow_paid_credits": ("Πάροχοι", "Πληρωμένα credits", "0 = αν το Claude χρεώνει credits, εναλλαγή αντί για συνέχεια."),
    "claude_model": ("Μοντέλα", "Μοντέλο Claude", "Πάρις και workers Claude, όταν το μήνυμα δεν ορίζει μοντέλο."),
    "claude_effort": ("Μοντέλα", "Effort Claude", ""),
    "codex_model": ("Μοντέλα", "Μοντέλο Codex", "Κενό = ό,τι λέει το ~/.codex/config.toml."),
    "codex_effort": ("Μοντέλα", "Effort Codex", ""),
    "events_model": ("Μοντέλα", "Μοντέλο γεγονότων", "Για τέλος παρτίδας και απαντήσεις αδειών· κενό = όπως πάνω."),
    "peer_claude_model": ("Μοντέλα", "Peer: Codex ρωτά Claude", ""),
    "peer_claude_major_model": ("Μοντέλα", "Peer major: Codex ρωτά Claude", ""),
    "peer_codex_model": ("Μοντέλα", "Peer: Claude ρωτά Codex", "Κενό = προεπιλογή του config."),
    "peer_codex_effort": ("Μοντέλα", "Peer effort Codex", ""),
    "peer_codex_major_effort": ("Μοντέλα", "Peer major effort Codex", ""),
    "max_workers": ("Παραλληλία", "Μέγιστοι workers", "Παράλληλες εκτελέσεις· ο Πάρις μετρά χωριστά."),
    "chat_budget_usd": ("Κόστος", "Όριο $ ανά απάντηση Πάρη", "Εκτίμηση του Claude CLI."),
    "max_budget_usd": ("Κόστος", "Όριο $ ανά worker", "Εκτίμηση του Claude CLI."),
    "peer_budget_usd": ("Κόστος", "Όριο $ ανά ερώτηση peer", ""),
    "resume_max_tokens": ("Context", "Μέγιστο context για resume", "Πάνω από αυτό, νέα συνεδρία."),
    "codex_resume_window_s": ("Context", "Παράθυρο resume Codex (s)", ""),
    "thread_messages": ("Context", "Μηνύματα νήματος στο πακέτο", ""),
    "state_max_lines": ("Context", "Μέγιστες γραμμές STATE", ""),
    "state_max_bytes": ("Context", "Μέγιστο μέγεθος STATE (bytes)", "Πάνω από αυτό ο Πάρις ζητά συμπύκνωση (με archive του παλιού κειμένου)."),
    "governor_enabled": ("Governor", "Governor ενεργός", "0 = χωρίς έλεγχο ρυθμού/ορίων (μόνο τα πραγματικά όρια του παρόχου)."),
    "pace_margin_pct": ("Governor", "Περιθώριο ρυθμού (%)", "Προαιρετική δουλειά αν η εβδομαδιαία χρήση ≤ ρυθμός + αυτό."),
    "optional_hard_pct": ("Governor", "Σκληρό όριο προαιρετικών (%)", "Εβδομαδιαία χρήση ≥ αυτό: καμία προαιρετική δουλειά."),
    "five_hour_max_pct": ("Governor", "Όριο 5ωρου (%)", "5ωρη χρήση ≥ αυτό: οι προαιρετικές δουλειές περιμένουν."),
    "chat_hard_pct": ("Governor", "Όριο Πάρη (%)", "Ο Πάρις απαντά μέχρι εδώ, μετά εναλλαγή παρόχου."),
    "usage_stale_h": ("Governor", "Παλιά μέτρηση (ώρες)", "Παλιότερη/άγνωστη χρήση: συντηρητικά, ένα προαιρετικό job τη φορά."),
    "unknown_daily_runs": ("Governor", "Εκτελέσεις/24ω με άγνωστη χρήση", "Παραδοχή, ρυθμίζεται."),
    "peer_hold_max_min": ("Governor", "Μέγιστη αναμονή peer (λεπτά)", "Αίτημα peer που κρατιέται τόσο, αποτυγχάνει με σαφές μήνυμα."),
    "max_retries": ("Governor", "Μέγιστες επαναλήψεις", "Παροδικό σφάλμα: τόσες φορές· άρνηση ασφαλείας: ποτέ."),
    "role_research_claude": ("Ρόλοι", "research · Claude", "Worker με --role research (κώδικας πειραμάτων/μοντέλων, ανάλυση)."),
    "role_work_claude": ("Ρόλοι", "work · Claude", "Υλοποίηση, tools."),
    "role_light_claude": ("Ρόλοι", "light · Claude", "Dashboard, docs."),
    "role_quick_claude": ("Ρόλοι", "quick · Claude", "Μηχανικά κείμενα: σύνοψη, μορφοποίηση, εξαγωγή."),
    "role_research_codex": ("Ρόλοι", "research · Codex", "Κενό = προεπιλογή του ~/.codex/config.toml (δεν μαντεύω ονόματα μοντέλων)."),
    "role_work_codex": ("Ρόλοι", "work · Codex", "Κενό = προεπιλογή του config."),
    "role_light_codex": ("Ρόλοι", "light · Codex", "Κενό = προεπιλογή του config."),
    "role_quick_codex": ("Ρόλοι", "quick · Codex", "Κενό = προεπιλογή του config."),
    "role_research_codex_effort": ("Ρόλοι", "research · effort Codex", ""),
    "role_work_codex_effort": ("Ρόλοι", "work · effort Codex", "Κενό = codex_effort."),
    "role_light_codex_effort": ("Ρόλοι", "light · effort Codex", ""),
    "role_quick_codex_effort": ("Ρόλοι", "quick · effort Codex", ""),
    "role_light_claude_effort": ("Ρόλοι", "light · effort Claude", ""),
    "kb_related": ("Context", "«Σχετικά» από kb.py", "1 = δείκτες από το kb.py query για μηνύματα μεγαλύτερα από το όριο."),
    "kb_related_min_chars": ("Context", "Όριο χαρακτήρων για «Σχετικά»", "Κοντά μηνύματα δεν ψάχνουν στο kb."),
    "kb_refresh_min": ("Context", "Ανανέωση kb μετά από job (λεπτά)", "Το πολύ κάθε τόσα λεπτά, πυρήνες 4–7· 0 = ποτέ."),
    "codex_commit": ("Πάροχοι", "Commit για τον Codex", "1 = ο dispatcher κάνει commit τα claimed αρχεία ενός Codex job (έλεγχος hash)."),
    "task_timeout_min": ("Χρόνοι", "Timeout δουλειάς (λεπτά)", ""),
    "peer_timeout_min": ("Χρόνοι", "Timeout peer (λεπτά)", ""),
    "escalation_debounce_s": ("Χρόνοι", "Αραίωση κλιμακώσεων (s)", "Ο Πάρις ξυπνά για κλιμακώσεις το πολύ μία φορά ανά τόσο."),
}

# What wakes a model today (dispatcher._candidates), in Greek.
KINDS = {
    "message": "μήνυμά σου",
    "job": "δουλειά worker",
    "decision": "απόφασή σου (και έγκριση πειράματος)",
    "escalation": "κλιμάκωση από worker",
    "perm_answer": "απάντηση σε άδεια",
    "run_event": "τέλος παρτίδας πειραμάτων",
}


def connect_ro(path):
    return sqlite3.connect("file:" + os.path.abspath(path) + "?mode=ro", uri=True, timeout=2)


def _rows(path, sql, args=(), strict=False):
    try:
        with closing(connect_ro(path)) as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(sql, args)]
    except sqlite3.Error:
        if strict:
            raise
        return []


# ---------------------------------------------------------------- settings
def settings_rows(db=DISPATCH_DB):
    """One row per DEFAULTS key (plus unknown stored keys): value, default, source, last change."""
    try:
        stored = {r["key"]: r for r in _rows(db, "SELECT key, value, updated_at, updated_by FROM settings", strict=True)}
        unread = False
    except sqlite3.Error:
        stored, unread = {}, True
    out = []
    for key, default in D.DEFAULTS.items():
        group, label, help_ = SETTINGS_META.get(key, ("Άλλες", key, ""))
        r = stored.get(key)
        out.append({"group": group, "key": key, "label": label, "value": r["value"] if r else default,
                    "default": default, "source": "βάση" if r else ("ΒΑΣΗ ΜΗ ΑΝΑΓΝΩΣΙΜΗ" if unread else "προεπιλογή"),
                    "changed": f"{r['updated_at'] or '?'} · {r['updated_by'] or '?'}" if r else "", "help": help_})
    return out


def effective(rows):
    return {r["key"]: r["value"] for r in rows}


def apply_change(path, key, new, expected_old, actor="researcher"):
    """One click = one change (B4). -> (status, message_in_greek); status in applied|noop|conflict|invalid|error.
    Compare-and-set against the value the page showed, so a second click or a stale page changes nothing."""
    try:
        dd = D.DispatchDB(path)
        try:
            res = dd.change(key, new, expected_old=expected_old, actor=actor)
        finally:
            dd.conn.close()
    except D.LabError as e:
        return "invalid", str(e)
    except sqlite3.Error as e:
        return "error", f"βάση: {e}"
    return res, {"applied": f"{key} = {str(new).strip()!r} (πριν {expected_old!r}). Ισχύει από το επόμενο tick.",
                 "noop": f"{key}: ήδη {str(new).strip()!r}, δεν έγινε τίποτα.",
                 "conflict": f"{key}: άλλαξε στο μεταξύ. Φόρτωσε ξανά τη σελίδα και δες την τρέχουσα τιμή."}[res]


def _editor(st, r, path):
    """One row: input + «Εφαρμογή». Choices come from the same rules the dispatcher enforces."""
    key, rule = r["key"], D.SETTING_RULES.get(r["key"])
    c1, c2, c3 = st.columns([3, 2, 1])
    c1.markdown(f"**{r['label']}** `{key}`  \n{r['help']}" if r["help"] else f"**{r['label']}** `{key}`")
    if rule is None:
        c2.text_input("τιμή", value=r["value"], disabled=True, key=f"sv_{key}", label_visibility="collapsed")
        c3.caption("μόνο CLI")
        return
    if rule[0] == "bool":
        new = c2.selectbox("τιμή", ["0", "1"], index=0 if r["value"] != "1" else 1, key=f"sv_{key}",
                           label_visibility="collapsed")
    elif rule[0] == "enum":
        opts = list(rule[1])
        new = c2.selectbox("τιμή", opts, index=opts.index(r["value"]) if r["value"] in opts else 0, key=f"sv_{key}",
                           label_visibility="collapsed")
    else:
        new = c2.text_input("τιμή", value=r["value"], key=f"sv_{key}", label_visibility="collapsed")
    c2.caption(f"προεπιλογή {r['default']!r} · {r['source']}" + (f" · {r['changed']}" if r["changed"] else ""))
    base = st.session_state.setdefault(f"sbase_{key}", r["value"])      # what this page first showed for the key
    if base != r["value"]:
        c3.warning("άλλαξε")
        if c3.button("Ενημέρωση", key=f"sr_{key}"):
            st.session_state[f"sbase_{key}"] = r["value"]
            st.session_state.pop(f"sv_{key}", None)       # the input shows the fresh value again, not the stale choice
            st.rerun()
        c2.caption(f"Η τιμή άλλαξε στο μεταξύ ({base!r} → {r['value']!r}). Πάτα «Ενημέρωση» και δες τη νέα τιμή.")
        return
    if c3.button("Εφαρμογή", key=f"sb_{key}", disabled=str(new).strip() == r["value"]):
        status, msg = apply_change(path, key, new, base)
        st.session_state.pop(f"sbase_{key}", None)
        (st.success if status == "applied" else st.warning if status in ("noop", "conflict") else st.error)(msg)


# ---------------------------------------------------------------- routing
def routing_rows(s):
    """Who answers each event kind with the current settings, and why (no per-message selection)."""
    first = s["coordinator"]
    other = D.OTHER.get(first, "")
    fallback = other if s["failover"] == "1" else "—"
    codex = s["codex_model"] or "config.toml"
    out = []
    for kind, what in KINDS.items():
        cm, why = D.claude_model_for(s, kind)
        out.append({"event": kind, "what": what, "first": first, "fallback": fallback,
                    "claude": f"{cm} · {s['claude_effort']}", "codex": f"{codex} · {s['codex_effort'] or 'config'}",
                    "why": f"coordinator={first}; Claude από `{why}`" +
                           ("; failover=1" if s["failover"] == "1" else "; failover=0")})
    out.append({"event": "peer", "what": "Codex ρωτά Claude / Claude ρωτά Codex", "first": "ο άλλος", "fallback": "—",
                "claude": f"{s['peer_claude_model']} (major: {s['peer_claude_major_model']})",
                "codex": f"{s['peer_codex_model'] or 'config.toml'} · {s['peer_codex_effort']} "
                         f"(major: {s['peer_codex_major_effort']})",
                "why": "ρυθμίσεις peer_*"})
    out.append({"event": "μήνυμα με επιλογή", "what": "dropdown του composer ≠ auto", "first": "όπως η επιλογή",
                "fallback": "—", "claude": "req_model", "codex": "req_model",
                "why": "η επιλογή του μηνύματος κερδίζει τις ρυθμίσεις· «auto» = οι ρυθμίσεις"})
    return out


def recent_tasks(db=DISPATCH_DB, lab_db=LAB_DB, limit=15, s=None):
    """Last tasks with the model that really ran and why (per-message selection or setting)."""
    tasks = _rows(db, "SELECT id, started, kind, refs, provider, model, status, cost_usd FROM tasks"
                      " ORDER BY id DESC LIMIT ?", (limit,))
    out = []
    for t in tasks:
        try:
            refs = json.loads(t["refs"] or "[]")
        except ValueError:
            refs = []
        mids = [r for r in refs if isinstance(r, str) and r.startswith("M-")]
        sel = None
        if mids:
            q = "SELECT id, req_model, body FROM messages WHERE id IN (%s) ORDER BY ts, id" % ",".join("?" * len(mids))
            msgs = _rows(lab_db, q, mids)
            mention = next((m for m in reversed(msgs) if D.MENTION_RE.match(m["body"] or "")), None)
            if mention:
                sel = "@" + D.MENTION_RE.match(mention["body"]).group(1).lower()
            else:
                got = [m["req_model"] for m in msgs if m["req_model"]]
                sel = got[-1] if got else None
        if sel and sel.startswith("@"):
            why = f"(εκτίμηση) {sel} στο μήνυμα"
        elif sel:
            why = f"(εκτίμηση) επιλογή μηνύματος req_model={sel}"
        elif s and t["provider"] == "claude":
            exp, src = D.claude_model_for(s, t["kind"])
            why = f"(εκτίμηση) ρύθμιση `{src}`" + ("" if exp == t["model"] else f" (τώρα: {exp})")
        else:
            why = "ρυθμίσεις"
        out.append({"id": t["id"], "started": t["started"], "kind": t["kind"], "provider": t["provider"],
                    "model": t["model"], "status": t["status"],
                    "usd": round(t["cost_usd"], 2) if t["cost_usd"] is not None else None, "why": why})
    return out


# ---------------------------------------------------------------- usage
def _age(ts, now):
    if not ts:
        return "χρόνος άγνωστος"
    m = int((now - ts) // 60)
    return f"πριν {m} λ" if m < 120 else f"πριν {m // 60} ω"


def _fmt_ts(ts):
    if not ts:
        return "—"
    return dt.datetime.fromtimestamp(ts, ATHENS).strftime("%d/%m %H:%M")


def claude_usage(status, now):
    """Freshest value per window from statusline/limits; expired window -> unknown (never 100 %)."""
    cands = G.claude_candidates(status, now)
    missing = dict(pct=None, reset=None, as_of=None, source="καμία μέτρηση")
    return [_usage_row("claude", key, cands.get(key, missing), now) for key in ("five_hour", "seven_day")]


def codex_usage(entries, now):
    rows = [_usage_row("codex", e.get("slot") or e.get("window"),
                       dict(pct=e.get("used_percent"), reset=e.get("resets_at"), as_of=e.get("as_of"),
                            source="codex rollout"), now) for e in entries or [] if e]
    return rows or [{"provider": "codex", "window": "—", "pct": UNKNOWN, "pace": "—", "reset": "—", "measured": "—",
                     "age": "καμία μέτρηση", "source": "—"}]


def _usage_row(provider, key, c, now):
    expired = c.get("reset") is not None and c["reset"] <= now
    pct = UNKNOWN if expired or c.get("pct") is None else f"{c['pct']:.0f}%"
    label = {"five_hour": "5ω", "seven_day": "7ημ", "primary": "5ω", "secondary": "7ημ"}.get(key, key)
    pace = G.pace_pct(c.get("reset"), now) if key in ("seven_day", "secondary") else None
    return {"provider": provider, "window": label, "pct": pct,
            "pace": "—" if pace is None else f"{pace:.0f}%",
            "reset": _fmt_ts(c.get("reset")) + (" (έληξε)" if expired else ""),
            "measured": _fmt_ts(c.get("as_of")), "age": _age(c.get("as_of"), now), "source": c.get("source")}


def rate_rows(db=DISPATCH_DB, now=None):
    """Runs and ≈$ per provider over the last 1 h and 24 h, from tasks (Codex reports no $)."""
    now = now or time.time()
    out = []
    for hours in (1, 24):
        for r in _rows(db, "SELECT provider, COUNT(*) AS n, ROUND(COALESCE(SUM(cost_usd),0),2) AS usd FROM tasks"
                           " WHERE CAST(strftime('%s', started) AS INTEGER) >= ? AND status!='released' GROUP BY provider",
                       (int(now - hours * 3600),)):
            out.append({"window": f"{hours} ω", "provider": r["provider"], "runs": r["n"],
                        "usd": r["usd"] if r["provider"] == "claude" else None})
    return out


# ---------------------------------------------------------------- services
def _cmd(args, timeout=5):
    """-> (ok, text). ok is False when the command could not run or failed."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout.strip() or p.stderr.strip())
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"σφάλμα: {type(e).__name__}"


def services(now=None, heartbeat=HEARTBEAT, db=DISPATCH_DB):
    now = now or time.time()
    out = [{"name": u, "state": _cmd(["systemctl", "--user", "is-active", u + ".service"])[1] or "άγνωστο"} for u in UNITS]
    try:
        hb = os.path.getmtime(heartbeat)
        out.append({"name": "heartbeat dispatcher", "state": _age(hb, now) if now - hb > 120 else f"πριν {int(now - hb)} s"})
    except OSError:
        out.append({"name": "heartbeat dispatcher", "state": "δεν υπάρχει"})
    paused = _rows(db, "SELECT value FROM settings WHERE key='paused'")
    out.append({"name": "παύση dispatcher", "state": "ναι" if paused and paused[0]["value"] == "1" else "όχι"})
    ok, text = _cmd(["crontab", "-l"])
    if ok or "no crontab" in text:
        cron = [ln for ln in text.splitlines() if ok and ln.strip() and not ln.startswith("#")]
        state = f"{len(cron)} γραμμές" + (": " + "; ".join(c[:80] for c in cron) if cron else "")
    else:
        state = f"μη διαθέσιμο ({text[:80]})"
    out.append({"name": "crontab", "state": state})
    ok, text = _cmd(["systemctl", "--user", "list-timers", "--no-legend", "--all"])
    timers = [ln for ln in text.splitlines() if ln.strip()]
    out.append({"name": "systemd timers (user)", "state": str(len(timers)) if ok else f"μη διαθέσιμο ({text[:80]})"})
    prov = _rows(db, "SELECT name, state, until_ts, note FROM providers")
    for p in prov:
        until = p.get("until_ts")
        if p["state"] != "ok" and until and until <= now:
            state = f"διαθέσιμος (το «{p['state']}» έληξε {_fmt_ts(until)})"
        else:
            state = p["state"] + (f" ως {_fmt_ts(until)}" if until else "")
        out.append({"name": f"πάροχος {p['name']}", "state": state})
    return out


# ---------------------------------------------------------------- render
def render(root=ROOT):
    import pandas as pd
    import streamlit as st

    now = time.time()
    P = paths(root)
    st.caption("Οι ρυθμίσεις αλλάζουν εδώ: έλεγχος τιμής, audit, ένα κλικ = μία αλλαγή (ισχύει στο επόμενο tick). Καμία κλήση μοντέλου από αυτή την καρτέλα.")
    rows = settings_rows(P["dispatch"])
    s = effective(rows)

    st.subheader("Αυτόματη έγκριση c4 sim")
    try:
        from c4_autonomy import policy
        approval = policy(root)
        st.caption("M-20261110-049 · " + ("ΕΝΕΡΓΗ" if approval["active"] else "ΕΛΗΞΕ")
                   + " · μόνο validation μέσω c4_train · λήξη: " + approval["until"])
        st.json(approval)
    except (OSError, ValueError, KeyError, D.LabError) as e:
        st.caption(f"Ανενεργή: {e}")

    st.subheader("Χρήση ανά πάροχο")
    try:
        status = U.load_claude_status(P["claude_status"]) or {}
        status = dict(status, _dispatcher=U.load_dispatcher_usage(P["dispatch"]))
        usage = claude_usage(status, now) + codex_usage(U.latest_codex(now), now)
    except Exception as e:  # never break the dashboard
        usage = [{"provider": "?", "window": "?", "pct": UNKNOWN, "source": f"σφάλμα {type(e).__name__}"}]
    st.dataframe(pd.DataFrame(usage), hide_index=True, width="stretch")
    st.caption("«Ρυθμός» = ποσοστό της εβδομάδας που έχει περάσει: οι προαιρετικές δουλειές ξεκινούν όσο η 7ημ χρήση ≤ ρυθμός + περιθώριο. Τιμή «άγνωστη» = το παράθυρο έληξε ή δεν υπάρχει μέτρηση. Ρυθμός από τον πίνακα tasks (≈$ μόνο Claude):")
    st.dataframe(pd.DataFrame(rate_rows(P["dispatch"], now=now)), hide_index=True, width="stretch")

    st.subheader("Δρομολόγηση: ποιος απαντά σε τι, και γιατί")
    st.dataframe(pd.DataFrame(routing_rows(s)), hide_index=True, width="stretch")
    st.caption("Τελευταίες εκτελέσεις (τι έτρεξε πραγματικά):")
    st.dataframe(pd.DataFrame(recent_tasks(P["dispatch"], P["lab"], s=s)), hide_index=True, width="stretch")

    st.subheader("Υπηρεσίες")
    st.dataframe(pd.DataFrame(services(now, P["heartbeat"], P["dispatch"])), hide_index=True, width="stretch")

    st.subheader("Όλες οι ρυθμίσεις")
    for group in dict.fromkeys(r["group"] for r in rows):
        with st.expander(group, expanded=group in ("Πάροχοι", "Μοντέλα")):
            for r in rows:
                if r["group"] == group:
                    _editor(st, r, P["dispatch"])
