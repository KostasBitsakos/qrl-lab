"""Purchased extra credits (researcher, 2026-10-23): ESTIMATE of spend since purchase + coordinator awake/asleep helpers.

Config .lab/usage/extra_credits.json: {"claude": {"purchased_usd", "purchased_at" (ISO UTC), "cost_baseline_usd"}} (codex optional).
State .lab/usage/extra_credits_state.json: {"sessions": {session_id: {"baseline": x, "latest": y}}}. The first
session_cost_usd seen after purchased_at is that session's baseline; spend = sum(latest - baseline). This is an ESTIMATE
(API-equivalent cost, may differ from the actual credit charge; spend before the first reading after purchase is not
counted). The exact balance is on claude.ai -> Settings -> Usage. Pure helpers, no network.
"""
import json
import os
import tempfile
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE_DIR = os.path.join(ROOT, ".lab", "usage")
EXPLICIT_OUT = r"(?i)out of extra usage|extra usage (?:is )?(?:exhausted|used up)|credits? (?:exhausted|used up|ran out)|(?:no|out of) (?:extra )?credits?"


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".ec.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def load_config(usage_dir=None):
    d = _read(os.path.join(usage_dir or USAGE_DIR, "extra_credits.json"), {})
    return d if isinstance(d, dict) else {}


def purchased_ts(cfg):
    try:
        return datetime.fromisoformat(str(cfg["purchased_at"]).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except (KeyError, ValueError, TypeError):
        return None


def observe(session_id, cost, now=None, usage_dir=None):
    """Record one statusline reading. No-op before purchase or on bad input."""
    now = time.time() if now is None else now
    if not isinstance(session_id, str) or not session_id or isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return
    cfg = (load_config(usage_dir).get("claude") or {})
    p = purchased_ts(cfg)
    if p is None or now < p:
        return
    path = os.path.join(usage_dir or USAGE_DIR, "extra_credits_state.json")
    st = _read(path, {})
    sess = st.setdefault("sessions", {}) if isinstance(st, dict) else {}
    if not isinstance(sess, dict):
        st, sess = {"sessions": {}}, {}
        st["sessions"] = sess
    e = sess.get(session_id)
    if not isinstance(e, dict) or "baseline" not in e:
        e = {"baseline": float(cost), "latest": float(cost)}
    else:
        e["latest"] = float(cost)
    sess[session_id] = e
    _write(path, st)


def status(provider="claude", usage_dir=None):
    """-> {"active", "purchased_usd", "spent_usd" (estimate), "remaining_usd"} ; active = configured and spend < purchased."""
    ud = usage_dir or USAGE_DIR
    cfg = (load_config(ud).get(provider) or {})
    try:
        total = float(cfg["purchased_usd"])
    except (KeyError, ValueError, TypeError):
        return {"active": False, "purchased_usd": 0.0, "spent_usd": 0.0, "remaining_usd": 0.0}
    st = _read(os.path.join(ud, "extra_credits_state.json"), {})
    sess = st.get("sessions", {}) if isinstance(st, dict) else {}
    spent = sum(max(0.0, float(e["latest"]) - float(e["baseline"])) for e in sess.values()
                if isinstance(e, dict) and "latest" in e and "baseline" in e) if isinstance(sess, dict) else 0.0
    base = cfg.get("cost_baseline_usd")
    if isinstance(base, (int, float)) and not isinstance(base, bool):
        spent += float(base)
    return {"active": total > 0 and spent < total, "purchased_usd": total, "spent_usd": spent,
            "remaining_usd": max(0.0, total - spent)}


def sidebar_text(st):
    """Greek line under the Claude ring (ESTIMATE label)."""
    return (f"Χρησιμοποιεί αγορασμένα credits: ${st['purchased_usd']:.0f} · εκτίμηση κατανάλωσης ${st['spent_usd']:.2f} "
            f"(μένουν ~${st['remaining_usd']:.2f})")


def show_credits(seven_day_pct, state, st):
    return bool(st.get("active")) and ((seven_day_pct is not None and seven_day_pct >= 100) or state == "extra")


def is_explicit_out(line):
    import re
    return bool(re.search(EXPLICIT_OUT, line or ""))


def awake_info(provider, health, now, tz="Europe/Athens"):
    """-> {"name", "awake", "badge", "reset"} ; health = that provider's {"state","detail",...} dict (may be empty)."""
    from zoneinfo import ZoneInfo  # noqa: F401  (validated lazily below)
    state = (health or {}).get("state", "ok")
    asleep = state in ("limit", "down")
    name = "Πάρις (Claude)" if provider == "claude" else "Codex"
    reset = ""
    if asleep:
        reset = str((health or {}).get("detail") or "")
        ra = (health or {}).get("resets_at")
        if isinstance(ra, (int, float)):
            reset = datetime.fromtimestamp(ra, ZoneInfo(tz)).strftime("%d/%m %H:%M")
    return {"name": name, "awake": not asleep, "badge": "💳" if state == "extra" else "", "reset": reset}


AWAKE_CSS = ("<style>.qz{display:inline-block;animation:qzf 2.4s ease-in-out infinite}"
             "@keyframes qzf{0%{transform:translateY(0);opacity:.2}50%{opacity:1}100%{transform:translateY(-8px);opacity:.1}}</style>")


def awake_html(infos):
    cells = []
    for i in infos:
        if i["awake"]:
            icon = "🟢" + (f'<sup title="αγορασμένα credits">{i["badge"]}</sup>' if i["badge"] else "")
            sub = "ξύπνιος"
        else:
            icon = '😴<span class="qz">Z</span><span class="qz" style="animation-delay:.8s">z</span><span class="qz" style="animation-delay:1.6s">z</span>'
            sub = "κοιμάται" + (f" · επαναφορά {i['reset']}" if i["reset"] else "")
        cells.append(f'<span style="margin-right:12px;font-size:.85rem"><b>{i["name"]}</b> {icon}'
                     f'<br><span style="opacity:.65;font-size:.75rem">{sub}</span></span>')
    return AWAKE_CSS + '<div style="margin:2px 0 6px">' + "".join(cells) + "</div>"
