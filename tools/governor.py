#!/usr/bin/env python3
"""Usage governor (v0.5.1 B2, plan §5): pace-based admission of model runs. Pure decisions, no model calls, no writes.

Pace (weekly) = share of the 7-day window that has already passed. A new optional run (worker, peer, review, council)
on provider P starts only if weekly use <= pace + pace_margin_pct and < optional_hard_pct, and the 5 h window is
< five_hour_max_pct. The chat coordinator runs until chat_hard_pct. A missing, stale (> usage_stale_h) or expired
measurement is «unknown»: conservative mode (one optional run at a time per provider; Codex also a daily run cap).

Windows are dicts {pct (0-100|None), reset (epoch|None), as_of (epoch|None), source}."""
import os
import sqlite3
import sys
import time
from contextlib import closing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_limits as U  # noqa: E402

WEEK_S = 7 * 86400
FIVE_S = 5 * 3600
KEYS = ("five_hour", "seven_day")
CODEX_SLOT = {"primary": "five_hour", "secondary": "seven_day"}
CODEX_GLOB = None          # tests may point this at fake rollouts; None = usage_limits.CODEX_GLOB (~/.codex/sessions)
CODEX_TTL_S = 15.0         # the rollout scan reads files: do it at most this often (Claude's sources are cheap sqlite/json)
_codex_memo = {}


def pace_pct(reset, now, window_s=WEEK_S):
    """Percent of the window that has passed, or None when the reset time is unknown/expired."""
    if reset is None or reset <= now:
        return None
    return max(0.0, min(100.0, (1 - (reset - now) / window_s) * 100))


def claude_candidates(status, now=None):
    """Freshest Claude value per window from the statusline snapshot and dispatch.db.limits (`status['_dispatcher']`)."""
    status = status if isinstance(status, dict) else {}
    events = status.get("_dispatcher") or {}
    cands = {}
    obs = U._measurement_time(status.get("as_of"))
    for key in KEYS:
        w = status.get(key)
        if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
            cands[key] = dict(pct=float(w["used_percentage"]), reset=U._measurement_time(w.get("resets_at")),
                              as_of=obs, source="statusline")
    for row in events.get("limits") or []:
        key = row.get("window")
        if key not in KEYS:
            continue
        ts = U._measurement_time(row.get("updated_at"))
        prev = cands.get(key)
        if prev and (prev["as_of"] or 0) >= (ts or 0):
            continue
        util = row.get("utilization")
        cands[key] = dict(pct=float(util) * 100 if isinstance(util, (int, float)) else None,
                          reset=U._measurement_time(row.get("resets_at")), as_of=ts, source="dispatch.db.limits")
    return cands


def codex_candidates(entries):
    out = {}
    for e in entries or []:
        key = CODEX_SLOT.get(e.get("slot"))
        if key:
            out[key] = dict(pct=e.get("used_percent"), reset=e.get("resets_at"), as_of=e.get("as_of"),
                            source="codex rollout")
    return out


def windows(provider, dispatch_db=None, claude_status=None, now=None, ttl=None):
    """-> {'five_hour': w, 'seven_day': w} for the provider; missing windows are absent (= unknown).
    Codex usage comes from its rollout logs (the newest token_count record), so it is as fresh as the last Codex run."""
    now = time.time() if now is None else now
    try:
        if provider == "claude":
            status = U.load_claude_status(claude_status) or {}
            status = dict(status, _dispatcher=U.load_dispatcher_usage(dispatch_db))
            return claude_candidates(status, now)
        ttl = CODEX_TTL_S if ttl is None else ttl
        hit = _codex_memo.get("v")
        if hit and ttl > 0 and time.time() - hit[0] < ttl and hit[1] == CODEX_GLOB:
            return hit[2]
        out = codex_candidates(U.latest_codex(now, CODEX_GLOB or U.CODEX_GLOB))
        _codex_memo["v"] = (time.time(), CODEX_GLOB, out)
        return out
    except Exception:  # usage is advisory: a failing source means «unknown», never a crash
        return {}


def _known(w, now, stale_s):
    """True if the window carries a usable measurement (present, not expired, not stale)."""
    if not w or w.get("pct") is None or w.get("as_of") is None:
        return False
    if w.get("reset") is not None and w["reset"] <= now:
        return False
    return now - w["as_of"] <= stale_s


def decide(role, wins, now, s, running_optional=0, runs_today=None):
    """-> (verdict, reason). verdict: 'go' | 'wait'. role: 'chat' | 'optional'. `s` = settings (strings ok)."""
    stale_s = float(s["usage_stale_h"]) * 3600
    five, week = wins.get("five_hour"), wins.get("seven_day")
    k5, k7 = _known(five, now, stale_s), _known(week, now, stale_s)
    if role == "chat":
        hard = float(s["chat_hard_pct"])
        for name, w, k in (("5ω", five, k5), ("7ημ", week, k7)):
            if k and w["pct"] >= hard:
                return "wait", f"{name} {w['pct']:.0f}% ≥ chat_hard_pct {hard:.0f}%"
        return "go", "ok"
    if k5 and five["pct"] >= float(s["five_hour_max_pct"]):
        return "wait", f"5ω {five['pct']:.0f}% ≥ {float(s['five_hour_max_pct']):.0f}%"
    if k7:
        pace = pace_pct(week.get("reset"), now)
        if week["pct"] >= float(s["optional_hard_pct"]):
            return "wait", f"7ημ {week['pct']:.0f}% ≥ optional_hard_pct {float(s['optional_hard_pct']):.0f}%"
        if pace is not None and week["pct"] > pace + float(s["pace_margin_pct"]):
            return "wait", (f"7ημ {week['pct']:.0f}% > ρυθμός {pace:.0f}% + {float(s['pace_margin_pct']):.0f}%")
    if not (k5 and k7):
        if running_optional >= 1:
            return "wait", "άγνωστη/παλιά χρήση: ένα προαιρετικό job τη φορά"
        cap = int(s["unknown_daily_runs"])
        if runs_today is not None and runs_today >= cap:
            return "wait", f"άγνωστη χρήση: {runs_today} εκτελέσεις σήμερα ≥ όριο {cap}"
    return "go", "ok"


def counts(dispatch_db, provider, now=None):
    """-> (running optional runs, runs started in the last 24 h) for the provider, from dispatch.db.tasks (read-only)."""
    import datetime as dt
    now = time.time() if now is None else now
    since = dt.datetime.fromtimestamp(now - 86400, dt.timezone.utc).isoformat()
    try:
        with closing(sqlite3.connect("file:" + os.path.abspath(dispatch_db) + "?mode=ro", uri=True, timeout=1)) as db:
            running = db.execute("SELECT COUNT(*) FROM tasks WHERE provider=? AND status='running' AND kind IN"
                                 " ('job','peer','run_event')", (provider,)).fetchone()[0]
            today = db.execute("SELECT COUNT(*) FROM tasks WHERE provider=? AND started>=?", (provider, since)).fetchone()[0]
            return running, today
    except sqlite3.Error:
        return 0, None
