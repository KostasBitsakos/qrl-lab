"""Read-only coordinator status for the dashboard sidebar (M-20261028-011).

Sources (never written): .lab/dispatch.db (settings, providers, tasks; opened mode=ro), .lab/bridge_heartbeat mtime,
and the systemd user unit state passed in by the caller. Pure `classify` is unit-tested.
"""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import time

try:
    from zoneinfo import ZoneInfo
    ATHENS = ZoneInfo("Europe/Athens")
except Exception:  # noqa: BLE001
    ATHENS = None

STALE_S = 60.0
# mirrors DEFAULTS in tools/dispatcher.py for keys never written to the settings table
DEFAULTS = {"coordinator": "claude", "paused": "0", "claude_model": "opus", "claude_effort": "medium",
            "codex_model": "", "codex_effort": "medium"}


def hhmm(ts):
    """HH:MM Greek time from an ISO string or unix timestamp."""
    try:
        d = dt.datetime.fromtimestamp(ts, ATHENS) if isinstance(ts, (int, float)) else dt.datetime.fromisoformat(str(ts))
        if ATHENS and d.tzinfo is not None:
            d = d.astimezone(ATHENS)
        return d.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return "?"


def read_state(root, ro_db=None):
    """{'settings','providers','running','hb_age'} from the dispatcher files; missing pieces are empty."""
    out = {"settings": dict(DEFAULTS), "providers": {}, "running": None, "hb_age": None}
    hb = os.path.join(root, ".lab", "bridge_heartbeat")
    if os.path.exists(hb):
        out["hb_age"] = max(0.0, time.time() - os.path.getmtime(hb))
    path = ro_db or os.path.join(root, ".lab", "dispatch.db")
    if not os.path.exists(path):
        return out
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        c.row_factory = sqlite3.Row
        out["settings"].update({r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")})
        for r in c.execute("SELECT name, state, until_ts FROM providers"):
            out["providers"][r["name"]] = dict(r)
        r = c.execute("SELECT id, started, provider, model, refs FROM tasks WHERE status='running' "
                      "ORDER BY id DESC LIMIT 1").fetchone()
        out["running"] = dict(r) if r else None
        c.close()
    except sqlite3.Error:
        pass
    return out


def service_active(unit="qrl-dispatcher"):
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() == "active"
    except Exception:  # noqa: BLE001
        return False


def _refs(refs):
    try:
        v = json.loads(refs or "[]")
        return ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    except ValueError:
        return str(refs or "")


def classify(state, active, now=None):
    """-> (kind, icon, headline, explanation); kind in idle|working|paused|limit|down."""
    now = time.time() if now is None else now
    s, run, hb = state["settings"], state["running"], state["hb_age"]
    coord = s.get("coordinator", "claude")
    if not active:
        return ("down", "🔴", "Η υπηρεσία dispatcher είναι σταματημένη",
                "Τα μηνύματά σου μένουν στην ουρά και θα απαντηθούν όταν ξαναξεκινήσει η υπηρεσία.")
    if run:
        return ("working", "🟡", f"Δουλεύει: task #{run['id']} (μηνύματα {_refs(run['refs'])}) από {hhmm(run['started'])} ώρα Ελλάδας",
                "Ο συντονιστής επεξεργάζεται κάτι· νέα μηνύματα μπαίνουν στην ουρά και θα τα πάρει μόλις τελειώσει.")
    if str(s.get("paused")) == "1":
        return ("paused", "⏸️", "Σε παύση", "Ο dispatcher δεν παίρνει νέα μηνύματα· μένουν στην ουρά μέχρι να άρεις την παύση.")
    p = state["providers"].get(coord)
    if p and p.get("state") != "ok" and (p.get("until_ts") or 0) > now:
        return ("limit", "😴", f"Όριο χρήσης ({coord}) μέχρι {hhmm(p['until_ts'])} ώρα Ελλάδας",
                "Τα μηνύματα μένουν στην ουρά" + (" ή περνούν στο άλλο μοντέλο (failover)." if str(s.get("failover", "1")) == "1" else "."))
    if hb is None or hb > STALE_S:
        return ("down", "🔴", "Η υπηρεσία dispatcher είναι σταματημένη",
                "Δεν υπάρχει πρόσφατο σήμα ζωής και καμία δουλειά σε εξέλιξη· τα μηνύματα μένουν στην ουρά.")
    return ("idle", "🟢", "Σε αναμονή — έτοιμος", "Ο συντονιστής περιμένει· τα μηνύματά σου θα παραληφθούν αμέσως.")


def coordinator_now(state):
    """('claude'|'codex', pretty model, effort) from the running task if any, else dispatcher settings."""
    s, run = state["settings"], state["running"]
    prov = (run or {}).get("provider") or s.get("coordinator", "claude")
    if prov not in ("claude", "codex"):
        prov = s.get("coordinator", "claude")
    model = (run or {}).get("model") or s.get(f"{prov}_model") or "default"
    return prov, model, s.get(f"{prov}_effort") or ""


def pretty(prov, model):
    m = str(model)
    if prov == "claude":
        m = m.replace("claude-", "").split("-")[0] if m.startswith("claude-") else m
        return "Claude " + m.capitalize()
    return "Codex " + m
