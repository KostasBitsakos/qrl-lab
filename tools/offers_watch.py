#!/usr/bin/env python3
"""10-minute watcher for free limit resets / offers (M-20261021-056). No LLM, stdlib only, GET only.

1. Local signals: a usage window that reset or restarted (used % dropped, resets_at advanced / passed) in the Codex
   rollout logs (usage_limits.latest_codex) or the Claude statusline file (.lab/usage/claude.json) -> event "limit_reset".
2. Official pages/feeds (SOURCES; https on offers_check.ALLOWED_DOMAINS, redirects re-checked, 10 s timeout): NEW items
   whose title/body match KEYWORDS -> .lab/offers_candidates.json (status "unverified") + event "candidate".
   The first successful fetch of a source only seeds the seen-set (no flood). docs/free_offers.json is never touched.
3. Events are appended to .lab/offers_watch_events.jsonl; state lives in .lab/offers_watch_state.json.
No logins, no credentials, no account actions.

Usage: python3 tools/offers_watch.py [--once | --loop 600] [--no-network]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import offers_check  # noqa: E402
import usage_limits  # noqa: E402

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.dirname(HERE)
LAB = os.path.join(ROOT, ".lab")
STATE = os.path.join(LAB, "offers_watch_state.json")
CANDS = os.path.join(LAB, "offers_candidates.json")
EVENTS = os.path.join(LAB, "offers_watch_events.jsonl")
HEARTBEAT = os.path.join(LAB, "offers_watch.heartbeat")
UA = "qrl-lab-offers-watch/1.0 (academic research lab; read-only GET; contact: lab owner)"
TIMEOUT = 10
MAX_BYTES = 6 << 20

# (provider, name, url, kind)  kind: rss | links:<path prefix> | sections
SOURCES = [
    ("claude", "Anthropic news", "https://www.anthropic.com/news", "links:/news/"),
    ("claude", "Claude apps release notes", "https://support.claude.com/en/articles/12138966-release-notes", "sections"),
    ("claude", "Claude usage and length limits",
     "https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work", "sections"),
    ("codex", "OpenAI news (RSS)", "https://openai.com/news/rss.xml", "rss"),
    ("codex", "Codex changelog", "https://developers.openai.com/codex/changelog", "sections"),
]
KEYWORDS = re.compile(r"(?i)\b(free|resets?|bonus(?:es)?|credits?|promo(?:tion|tions)?|offers?|"
                      r"(?:limit|limits) (?:increase|increased|doubled)|(?:increased|higher|double|doubled) (?:usage )?limits?)\b")


def matched_words(text):
    return sorted({m.group(1).lower() for m in KEYWORDS.finditer(text or "")})


# ------------------------------------------------------------------ parsing
class _Page(HTMLParser):
    """Collects <a> links (href, text) and heading sections (h1-h4: id, text, following body text)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.sections = [], []
        self._a, self._h, self._skip = None, None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "a" and a.get("href"):
            self._a = [a["href"], ""]
        elif tag in ("h1", "h2", "h3", "h4"):
            self._h = {"id": a.get("id") or "", "title": "", "body": ""}
            self.sections.append(self._h)
            self._htag = tag

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._a:
            self.links.append((self._a[0], " ".join(self._a[1].split())))
            self._a = None
        elif self._h is not None and tag == getattr(self, "_htag", None):
            self._h["title"] = " ".join(self._h["title"].split())
            self._cur = self._h
            self._h = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._a is not None:
            self._a[1] += data
        if self._h is not None:
            self._h["title"] += data
        elif self.sections and len(self.sections[-1]["body"]) < 500:
            self.sections[-1]["body"] += " " + data


def parse_items(kind, base_url, raw):
    """-> [{id, title, url, text}]; `text` is what the keywords are matched against."""
    out = []
    if kind == "rss":
        root = ET.fromstring(raw)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            gid = (it.findtext("guid") or link or title).strip()
            out.append({"id": gid, "title": title, "url": link or base_url,
                        "text": title + " " + re.sub(r"<[^>]+>", " ", it.findtext("description") or "")})
        return out
    p = _Page()
    p.feed(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
    if kind.startswith("links:"):
        prefix = kind.split(":", 1)[1]
        seen = set()
        for href, text in p.links:
            path = href.split("://", 1)[-1]
            path = path[path.find("/"):] if not href.startswith("/") else href
            if path.startswith(prefix) and len(path) > len(prefix) and href not in seen and text:
                seen.add(href)
                url = href if "://" in href else base_url.split("/", 3)[0] + "//" + base_url.split("/")[2] + href
                out.append({"id": path, "title": text[:200], "url": url, "text": text})
        return out
    for s in p.sections:
        if s["title"]:
            body = " ".join(s["body"].split())[:400]
            url = base_url + ("#" + s["id"] if s["id"] else "")
            out.append({"id": hashlib.sha1((s["id"] + "|" + s["title"]).encode()).hexdigest()[:16],
                        "title": s["title"][:200], "url": url, "text": s["title"] + " " + body})
    return out


# ------------------------------------------------------------------ io helpers
class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not offers_check.official_https(newurl):
            raise urllib.error.HTTPError(newurl, code, "redirect to non-official URL refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    if not offers_check.official_https(url):
        raise ValueError("not an official https URL: " + url)
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA, "Accept": "text/html,application/xml,*/*"})
    with urllib.request.build_opener(_Redirect).open(req, timeout=TIMEOUT) as r:
        return r.read(MAX_BYTES)


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def emit(ev, path=None):
    os.makedirs(os.path.dirname(path or EVENTS), exist_ok=True)
    with open(path or EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ signal 1: local resets
def current_windows(codex_entries, claude_status):
    """{ 'codex:5h': (used%, resets_at), 'claude:5h': ... } from raw readings (no stale-hiding)."""
    cur = {}
    for e in codex_entries or []:
        cur[f"codex:{e['window']}"] = (e["used_percent"], e.get("resets_at"))
    if isinstance(claude_status, dict):
        for key, lab in (("five_hour", "5h"), ("seven_day", "7d")):
            w = claude_status.get(key)
            if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
                cur[f"claude:{lab}"] = (float(w["used_percentage"]), w.get("resets_at"))
    return cur


def detect_resets(prev, cur, now, drop=5.0):
    """prev/cur: {key: (used, resets_at)} -> [event]. Reset = previous resets_at passed and the window moved on
    (resets_at advanced or used dropped), or used % fell by >= `drop` points with resets_at advanced/unchanged-unknown."""
    evs = []
    for key, (used, rs) in cur.items():
        if key not in prev:
            continue
        pu, prs = prev[key]
        advanced = rs is not None and prs is not None and rs > prs + 60
        passed = prs is not None and prs <= now
        dropped = used is not None and pu is not None and used <= pu - drop
        if (advanced and (passed or dropped)) or (dropped and advanced is not False and (rs is None or prs is None)):
            prov, win = key.split(":")
            evs.append({"ts": now, "kind": "limit_reset", "provider": prov, "window": win,
                        "title": f"{prov} {win}: νέο παράθυρο ({pu:.0f}% → {used:.0f}%)",
                        "url": "", "status": "local"})
    return evs


# ------------------------------------------------------------------ one pass
def run_once(now=None, network=True, fetcher=fetch, codex=None, claude=None):
    now = time.time() if now is None else now
    st = _load(STATE, {})
    st.setdefault("windows", {}); st.setdefault("seen", {})
    events = []
    try:
        cx = usage_limits.latest_codex(now) if codex is None else codex
    except Exception:  # noqa: BLE001
        cx = []
    cl = usage_limits.load_claude_status() if claude is None else claude
    cur = current_windows(cx, cl)
    prev = {k: tuple(v) for k, v in st["windows"].items()}
    events += detect_resets(prev, cur, now)
    st["windows"] = {**st["windows"], **{k: list(v) for k, v in cur.items()}}

    cands = _load(CANDS, [])
    known = {c.get("id") for c in cands}
    errors = {}
    for prov, name, url, kind in (SOURCES if network else []):
        try:
            items = parse_items(kind, url, fetcher(url))
        except Exception as e:  # noqa: BLE001 - one broken source must not stop the others
            errors[name] = f"{type(e).__name__}: {e}"[:200]
            continue
        seen = st["seen"].get(url)
        ids = {i["id"] for i in items}
        if seen is None:                       # first success: seed only
            st["seen"][url] = sorted(ids)
            continue
        new = [i for i in items if i["id"] not in set(seen)]
        for it in new:
            words = matched_words(it["text"])
            cid = hashlib.sha1((url + "|" + it["id"]).encode()).hexdigest()[:16]
            if words and cid not in known and offers_check.official_https(it["url"]):
                c = {"id": cid, "provider": prov, "source_name": name, "title": it["title"], "url": it["url"],
                     "as_of": time.strftime("%Y-%m-%d", time.gmtime(now)), "matched": words, "status": "unverified"}
                cands.append(c)
                known.add(cid)
                events.append({"ts": now, "kind": "candidate", "provider": prov, "title": it["title"], "url": it["url"],
                               "matched": words, "status": "unverified"})
        st["seen"][url] = sorted(set(seen) | ids)
    st["errors"], st["last_run"] = errors, now
    _save(CANDS, cands)
    _save(STATE, st)
    for ev in events:
        emit(ev)
    with open(HEARTBEAT, "w") as f:
        f.write(str(now))
    return events, errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="seconds between passes")
    ap.add_argument("--no-network", action="store_true")
    a = ap.parse_args(argv)
    while True:
        try:
            ev, err = run_once(network=not a.no_network)
            print(time.strftime("%F %T"), "events:", len(ev), "errors:", err, flush=True)
        except Exception as e:  # noqa: BLE001
            print(time.strftime("%F %T"), "pass failed:", type(e).__name__, e, flush=True)
        if not a.loop:
            return 0
        time.sleep(a.loop)


if __name__ == "__main__":
    sys.exit(main())
