#!/usr/bin/env python3
"""Usage-limit state of Claude and Codex from LOCAL logs only (sidebar rings, M-20261021-016). Never estimates.

Sources (read-only; credential files are never opened):
  claude  PRIMARY (M-20261021-021): .lab/usage/claude.json, written by tools/claude_statusline.py from the official
          statusLine stdin (rate_limits.five_hour / seven_day: used_percentage, resets_at). Fallback below.
  codex   ~/.codex/sessions/**/rollout-*.jsonl, records {"type": "event_msg", "payload": {"type": "token_count",
          "rate_limits": {"primary"|"secondary": {used_percent, window_minutes, resets_at}, "plan_type"}}} written by
          the Codex CLI after each turn. The latest record gives used % per window AS OF its timestamp.
  claude  ~/.claude/projects/**/*.jsonl transcripts. Claude Code records only REJECTIONS there:
          {"apiError": "usage_limit_reached", "apiErrorParams": {"rate_limit_info": {"status": "rejected",
          "resetsAt", "rateLimitType"}}}. A rejection whose resetsAt is still in the future means 100 % used until
          then; otherwise there is no local percentage for Claude (shown as «—»).
Entry: {provider, window, used_percent, window_minutes, resets_at, source, as_of}. A window whose resets_at is
already past is reported as reset (value no longer known), not as 0 %.
"""
import datetime as dt
import glob
import json
import math
import os
import time

HOME = os.path.expanduser("~")
CODEX_GLOB = os.path.join(HOME, ".codex", "sessions", "**", "rollout-*.jsonl")
CLAUDE_GLOB = os.path.join(HOME, ".claude", "projects", "**", "*.jsonl")
NO_SOURCE = "δεν υπάρχει τοπική πηγή για το όριο"
MAX_AGE_S = 8 * 24 * 3600      # longest window (7 days) + margin
CODEX_TAIL = 4 << 20


def _ts(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _utc(t):
    return dt.datetime.fromtimestamp(float(t), dt.timezone.utc).strftime("%d/%m %H:%M UTC")


def window_name(minutes):
    m = int(minutes or 0)
    return {300: "5h", 10080: "7d"}.get(m, f"{m // 60}h" if m % 60 == 0 and m else f"{m}m")


def parse_codex(obj, source=""):
    """One Codex rollout record -> [entries] (empty if it carries no rate limits)."""
    p = obj.get("payload") if isinstance(obj, dict) else None
    rl = p.get("rate_limits") if isinstance(p, dict) and p.get("type") == "token_count" else None
    if not isinstance(rl, dict):
        return []
    out = []
    for key in ("primary", "secondary"):
        w = rl.get(key)
        if isinstance(w, dict) and w.get("used_percent") is not None:
            out.append({"provider": "codex", "window": window_name(w.get("window_minutes")), "slot": key,
                        "used_percent": float(w["used_percent"]), "window_minutes": w.get("window_minutes"),
                        "resets_at": float(w["resets_at"]) if w.get("resets_at") is not None else None,
                        "plan": rl.get("plan_type"), "source": source, "as_of": _ts(obj.get("timestamp"))})
    return out


def parse_claude(obj, source=""):
    """One Claude Code transcript record -> [entry] for a usage-limit rejection, else []."""
    if not isinstance(obj, dict) or obj.get("apiError") != "usage_limit_reached":
        return []
    info = (obj.get("apiErrorParams") or {}).get("rate_limit_info") or obj.get("quotaLimits") or {}
    if info.get("status") != "rejected" or info.get("resetsAt") is None:
        return []
    return [{"provider": "claude", "window": {"five_hour": "5h", "seven_day": "7d"}.get(info.get("rateLimitType"),
                                                                                      str(info.get("rateLimitType"))),
             "slot": info.get("rateLimitType"), "used_percent": 100.0, "window_minutes": None,
             "resets_at": float(info["resetsAt"]), "plan": None, "source": source, "as_of": _ts(obj.get("timestamp"))}]


def _recent(pattern, now, max_age=MAX_AGE_S):
    out = []
    for p in glob.glob(pattern, recursive=True):
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if now - m <= max_age:
            out.append((m, p))
    return [p for _, p in sorted(out, reverse=True)]


def _lines(path, tail=None):
    try:
        with open(path, "rb") as f:
            if tail:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - tail))
            data = f.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()


def latest_codex(now=None, pattern=CODEX_GLOB, max_files=6):
    """Entries of the newest token_count record with rate limits across the newest session files."""
    now = time.time() if now is None else now
    best = []
    for p in _recent(pattern, now)[:max_files]:
        for ln in reversed(_lines(p, CODEX_TAIL)):
            if '"rate_limits"' not in ln:
                continue
            try:
                e = parse_codex(json.loads(ln), p)
            except ValueError:
                continue
            if e:
                if not best or (e[0]["as_of"] or 0) > (best[0]["as_of"] or 0):
                    best = e
                break
    return best


class ClaudeScanner:
    """Incremental scan of the transcripts for rejection records (only bytes appended since the last scan)."""

    def __init__(self, pattern=CLAUDE_GLOB):
        self.pattern, self.off, self.found = pattern, {}, []

    def scan(self, now=None):
        now = time.time() if now is None else now
        for p in _recent(self.pattern, now):
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            start = self.off.get(p, 0)
            if size < start:
                start = 0
            if size == start:
                continue
            try:
                with open(p, "rb") as f:
                    f.seek(start)
                    data = f.read()
            except OSError:
                continue
            end = data.rfind(b"\n") + 1
            for ln in data[:end].split(b"\n"):
                if b"usage_limit_reached" in ln:
                    try:
                        self.found += parse_claude(json.loads(ln.decode("utf-8", "replace")), p)
                    except ValueError:
                        pass
            self.off[p] = start + end
        return latest_claude(self.found, now)


def latest_claude(entries, now):
    """The rejection with the latest resets_at among the given entries (None if there is none)."""
    if not entries:
        return None
    return max(entries, key=lambda e: (e["resets_at"] or 0, e["as_of"] or 0))


def ring(entry, now):
    """-> (percent or None, hover text) for one provider's headline window."""
    if not entry:
        return None, NO_SOURCE
    when = _utc(entry["resets_at"]) if entry.get("resets_at") else "άγνωστο"
    asof = _utc(entry["as_of"]) if entry.get("as_of") else "άγνωστο"
    if entry.get("resets_at") is not None and entry["resets_at"] <= now:
        return None, (f"το παράθυρο {entry['window']} ανανεώθηκε στις {when} μετά την τελευταία μέτρηση ({asof}); "
                      "νέα τιμή με την επόμενη κλήση")
    left = entry["resets_at"] - now if entry.get("resets_at") else None
    lt = (f"{int(left // 3600)} ώ {int(left % 3600 // 60)} λ" if left is not None else "άγνωστο")
    return entry["used_percent"], f"{entry['used_percent']:.0f}% του ορίου {entry['window']} · reset σε {lt} ({when}) · μέτρηση {asof}"


def provider_ring(provider, entries, now):
    """Headline ring for a provider: (percent or None, window shown or None, hover text listing every window).
    codex: the first still-valid window (5h, else 7d); claude: an active rejection (100 %) or None with NO_SOURCE."""
    entries = [e for e in (entries or []) if e]
    if provider == "claude":
        e = entries[0] if entries else None
        if e and e.get("resets_at") and e["resets_at"] > now:
            pct, tip = ring(e, now)
            return pct, e["window"], tip + " (Claude Code κατέγραψε απόρριψη λόγω ορίου)"
        last = ""
        if e and e.get("resets_at"):
            last = f" · τελευταίο όριο {e['window']} έληξε {_utc(e['resets_at'])}"
        return None, None, NO_SOURCE + " (το Claude Code γράφει μόνο απορρίψεις)" + last
    if not entries:
        return None, None, NO_SOURCE
    tips = [ring(e, now)[1] for e in entries]
    for e in entries:
        pct, _ = ring(e, now)
        if pct is not None:
            return pct, e["window"], " | ".join(tips)
    return None, None, " | ".join(tips)


RESET_TIP = "έγινε reset, αναμονή νέας μέτρησης"
LABELS = {"5h": "5ω", "7d": "7ημ", "five_hour": "5ω", "seven_day": "7ημ"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_STATUS = os.path.join(ROOT, ".lab", "usage", "claude.json")   # written by tools/claude_statusline.py
AMBER, RED = "#f59e0b", "#dc2626"


def load_claude_status(path=None):
    """Official Claude source (statusLine stdin, saved by tools/claude_statusline.py); None if missing/malformed."""
    path = path or os.environ.get("QRL_CLAUDE_USAGE_FILE") or CLAUDE_STATUS
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _win(label, pct, resets_at, now, source=""):
    """One window for the popover: pct None (shown «—») when its resets_at has passed (value no longer known)."""
    stale = resets_at is not None and resets_at <= now
    return {"label": label, "pct": None if stale else pct, "resets_at": resets_at, "stale": stale, "source": source}


def claude_windows(status, rejection, now):
    """Claude windows: statusLine file first (five_hour, seven_day); else an active log rejection (100 %); else []."""
    out = []
    if isinstance(status, dict):
        for key in ("five_hour", "seven_day"):
            w = status.get(key)
            if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
                r = w.get("resets_at")
                out.append(_win(LABELS[key], float(w["used_percentage"]),
                                float(r) if isinstance(r, (int, float)) else None, now, "statusline"))
    if out:
        return out
    if rejection and rejection.get("resets_at") and rejection["resets_at"] > now:
        return [_win(LABELS.get(rejection["window"], rejection["window"]), 100.0, rejection["resets_at"], now, "log")]
    return []


def codex_windows(entries, now):
    """Codex windows from the latest rollout record (5ω, 7ημ); a window whose resets_at passed -> «—»."""
    return [_win(LABELS.get(e["window"], e["window"]), e["used_percent"], e.get("resets_at"), now, "log")
            for e in (entries or []) if e]


def left_text(resets_at, now, step=None):
    """«Hω Mλ» until resets_at. step (seconds): round UP to that step and prefix «≤», so the text (and the HTML that
    contains it) only changes at step boundaries — an auto-refresh then leaves an open popover alone (M-20261021-023)."""
    if resets_at is None:
        return "άγνωστο"
    left = max(0.0, resets_at - now)
    pre = ""
    if step:
        left, pre = math.ceil(left / step) * step, "≤"
    return f"{pre}{int(left // 3600)}ω {int(left % 3600 // 60)}λ"


def win_line(w, now, step=None):
    """Popover text of one window: «<P>% χρησιμοποιημένο · reset σε <Hω Mλ>», or «—» + RESET_TIP after a reset.
    With step: «reset σε ≤Hω Mλ (dd/mm HH:MM UTC)» (countdown rounded up to step seconds, plus the exact reset time)."""
    if w["pct"] is None:
        return "— · " + RESET_TIP
    line = f"{w['pct']:.0f}% χρησιμοποιημένο · reset σε {left_text(w['resets_at'], now, step)}"
    if step and w.get("resets_at") is not None:
        line += f" ({_utc(w['resets_at'])})"
    return line


def headline(wins):
    """Ring value = the most-used window still valid (the binding limit); None if none is valid."""
    vals = [w["pct"] for w in wins if w["pct"] is not None]
    return max(vals) if vals else None


def ring_color(pct, base):
    if pct is None:
        return base
    return RED if pct >= 90 else AMBER if pct >= 75 else base


RING_CSS = ("<style>.qrl-ring{position:relative;display:inline-block}"
            ".qrl-ring>summary{list-style:none;cursor:pointer;display:inline-flex;align-items:center;gap:3px;"
            "outline:none;-webkit-tap-highlight-color:transparent}"
            ".qrl-ring>summary::-webkit-details-marker{display:none}.qrl-ring>summary::marker{content:''}"
            ".qrl-ring>summary:focus-visible svg{outline:2px solid #888;border-radius:50%}"
            ".qrl-pop{position:absolute;top:calc(100% + 4px);right:0;z-index:1000;min-width:190px;max-width:260px;"
            "padding:6px 8px;border-radius:8px;font-size:.72rem;line-height:1.35;background:var(--background-color,#fff);"
            "color:inherit;border:1px solid rgba(137,135,129,.45);box-shadow:0 4px 14px rgba(0,0,0,.18)}"
            ".qrl-pop b{display:block;font-size:.7rem;opacity:.75;margin-bottom:2px}"
            ".qrl-pop div{white-space:nowrap}</style>")


def ring_html(name, wins, color, now, empty_tip=NO_SOURCE, step=None):
    """Small usage ring (SVG stroke-dasharray arc over a grey track, provider colour, amber >=75 %, red >=90 %).
    Tap/click opens a <details> popover with one «P% χρησιμοποιημένο · reset σε Hω Mλ» line per window. No JS."""
    import html
    pct = headline(wins)
    col = ring_color(pct, color)
    r = 11.0
    c = 2 * math.pi * r
    frac = 0.0 if pct is None else max(0.0, min(100.0, float(pct))) / 100.0
    val = "—" if pct is None else f"{pct:.0f}"
    arc = (f'<circle cx="14" cy="14" r="{r}" fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round" '
           f'stroke-dasharray="{c * frac:.2f} {c:.2f}" transform="rotate(-90 14 14)"/>') if pct else ""
    if wins:
        lines = "".join(f'<div title="{html.escape(RESET_TIP) if w["pct"] is None else ""}">'
                        f'{html.escape(w["label"])}: {html.escape(win_line(w, now, step))}</div>' for w in wins)
        tip = " | ".join(f'{w["label"]}: {win_line(w, now, step)}' for w in wins)
    else:
        lines, tip = f"<div>— · {html.escape(empty_tip)}</div>", empty_tip
    return (f'<details class="qrl-ring"><summary title="{html.escape(tip)}" '
            f'aria-label="{html.escape(name)} {val}%">'
            f'<svg width="28" height="28" viewBox="0 0 28 28">'
            f'<circle cx="14" cy="14" r="{r}" fill="none" stroke="rgba(137,135,129,.3)" stroke-width="3"/>{arc}'
            f'<text x="14" y="17.3" text-anchor="middle" font-size="{8.5 if pct is not None else 10}" '
            f'font-family="sans-serif" fill="currentColor">{val}</text></svg>'
            f'<span style="font-size:.68rem;opacity:.8">{html.escape(name)}</span></summary>'
            f'<div class="qrl-pop"><b>{html.escape(name)}</b>{lines}</div></details>')


def load_offers(path):
    """docs/free_offers.json entries (provider, title, url, as_of, note, source, added_at); [] if missing/malformed."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    keys = ("provider", "title", "url", "as_of", "note", "source", "added_at")
    return [{k: str(x.get(k, "") or "") for k in keys} for x in d if isinstance(x, dict) and x.get("title")] \
        if isinstance(d, list) else []


def offer_is_new(offer, seen_ts):
    """True if the entry was merged (added_at, else as_of) after seen_ts (epoch s). Unparseable dates -> False."""
    t = _ts(offer.get("added_at") or offer.get("as_of") or "")
    if t is None and offer.get("as_of"):
        t = _ts(offer["as_of"] + "T00:00:00+00:00")
    return t is not None and seen_ts is not None and t > seen_ts


if __name__ == "__main__":
    n = time.time()
    print(json.dumps({"codex": latest_codex(n), "claude": ClaudeScanner().scan(n)}, indent=1, default=str))
