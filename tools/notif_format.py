"""Human-readable limit/offer notifications for the sidebar (M-20261022-063). Pure helpers, no streamlit.

Source: .lab/offers_watch_events.jsonl (audit log, never modified). Dismissals live in
.lab/notifications_dismissed.json (list of ids ts|kind|provider)."""
import json
import os
import re
import time
from zoneinfo import ZoneInfo

ATHENS = ZoneInfo("Europe/Athens")
BRAND = {"claude": ("Claude", "#d97757"), "codex": ("Codex", "#10a37f")}
WINDOW_GR = {"5h": "5ωρο", "7d": "εβδομαδιαίο", "1d": "ημερήσιο"}
WINDOW_GEN = {"5h": "5ωρου", "7d": "εβδομαδιαίου", "1d": "ημερήσιου"}
DAYS_GR = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
MAX_AGE_S = 86400
_PCT = re.compile(r"\((\d+(?:\.\d+)?)%\s*→\s*(\d+(?:\.\d+)?)%\)")


def event_id(e):
    return f"{e.get('ts', 0)}|{e.get('kind', '')}|{e.get('provider', '')}"


def rel_time(ts, now):
    """«πριν 2 ώρες» / «πριν 5 λεπτά» / «μόλις τώρα»; future -> «σε ...»."""
    d = now - ts
    fut = d < 0
    s = abs(d)
    if s < 60:
        return "μόλις τώρα"
    if s < 3600:
        n, u = int(s // 60), ("λεπτό", "λεπτά")
    elif s < 86400:
        n, u = int(s // 3600), ("ώρα", "ώρες")
    else:
        n, u = int(s // 86400), ("ημέρα", "ημέρες")
    txt = f"{n} {u[0] if n == 1 else u[1]}"
    return f"σε {txt}" if fut else f"πριν {txt}"


def athens_time(ts, now=None):
    """Local Greek time: «HH:MM» today, «Δευτέρα 06:00» within a week, else «dd/mm HH:MM»."""
    t = __import__("datetime").datetime.fromtimestamp(ts, ATHENS)
    hm = t.strftime("%H:%M")
    if now is None:
        return t.strftime("%d/%m ") + hm
    n = __import__("datetime").datetime.fromtimestamp(now, ATHENS)
    if t.date() == n.date():
        return f"σήμερα {hm}"
    if 0 < (t.date() - n.date()).days < 7:
        return f"{DAYS_GR[t.weekday()]} {hm}"
    return t.strftime("%d/%m ") + hm


def _pcts(e):
    m = _PCT.search(e.get("title", "") or "")
    old = e.get("old_percent", float(m.group(1)) if m else None)
    new = e.get("used_percent", float(m.group(2)) if m else None)
    return old, new


def format_event(e, now):
    """-> dict(icon, color, severity, provider_label, brand, text, url, when, ts, id). severity: ok|warn|crit|info."""
    kind, prov = e.get("kind", ""), e.get("provider", "")
    label, brand = BRAND.get(prov, (prov.capitalize() or "?", "#888"))
    win = e.get("window", "")
    wname = WINDOW_GR.get(win, win)
    wgen = WINDOW_GEN.get(win, win)
    old, new = _pcts(e)
    reset = f" — επαναφορά {athens_time(e['resets_at'], now)} (ώρα Ελλάδας)" if e.get("resets_at") else ""
    if kind == "limit_reset":
        sev, icon = "ok", "✅"
        was = f" (ήταν {old:.0f}% χρησιμοποιημένο)" if old is not None else ""
        text = f"{label}: ανανεώθηκε το {wname} όριο — διαθέσιμο ξανά{was}"
    elif kind in ("limit_hit", "limit_reached"):
        sev, icon = "crit", "⛔"
        text = f"{label}: εξαντλήθηκε το {wname} όριο{reset}"
    elif kind in ("limit_warn", "limit_approaching", "approaching"):
        sev, icon = "warn", "⚠️"
        p = f"{new:.0f}%" if new is not None else "υψηλό ποσοστό"
        text = f"{label}: έφτασε το {p} του {wgen} ορίου{reset}"
    elif kind == "candidate":
        sev, icon = "info", "🎁"
        text = f"{label}: πιθανή προσφορά (ανεπιβεβαίωτη) — {e.get('title', '')}"
    else:
        sev, icon = "info", "ℹ️"
        text = f"{label}: {e.get('title', '') or kind}"
    colors = {"ok": "#2e9e5b", "warn": "#e0a800", "crit": "#d64545", "info": "#4a7fd1"}
    ts = float(e.get("ts", 0) or 0)
    return {"icon": icon, "color": colors[sev], "severity": sev, "provider": prov, "provider_label": label,
            "brand": brand, "text": text, "url": e.get("url", "") or "", "ts": ts, "id": event_id(e),
            "when": rel_time(ts, now), "at": athens_time(ts, now)}


def load_dismissed(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return set(map(str, d)) if isinstance(d, list) else set()
    except (OSError, ValueError):
        return set()


def save_dismissed(path, ids, keep=500):
    ids = sorted(set(ids))[-keep:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ids, f)
    os.replace(tmp, path)


def dismiss(path, new_ids):
    save_dismissed(path, load_dismissed(path) | set(new_ids))


def visible(events, dismissed, now, max_age=MAX_AGE_S):
    """Events from the last `max_age` seconds that are not dismissed (order kept)."""
    return [e for e in events if now - float(e.get("ts", 0) or 0) <= max_age and event_id(e) not in dismissed]


def group_by_provider(formatted):
    out = {}
    for f in formatted:
        out.setdefault(f["provider"], []).append(f)
    return out
