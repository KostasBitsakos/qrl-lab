#!/usr/bin/env python3
"""Validate and merge candidate free-offer / reset entries into docs/free_offers.json (M-20261021-021).

It does NOT search the web: a scheduled agent finds candidates and calls this helper, which only accepts entries
whose url (and source, if given) is https on an official domain (ALLOWED_DOMAINS or a subdomain), dedupes by
normalised url, stamps added_at (UTC ISO) and writes the file atomically.

Usage: python3 tools/offers_check.py candidates.json [--file docs/free_offers.json] [--dry-run]
       (candidates.json: one object or a list; "-" reads stdin). Prints {"added": [...], "duplicates": [...],
       "rejected": [{"entry", "reason"}]} as JSON; exit 0 unless the input itself cannot be read.
"""
import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFERS = os.path.join(ROOT, "docs", "free_offers.json")
ALLOWED_DOMAINS = ("anthropic.com", "claude.ai", "claude.com", "support.anthropic.com", "openai.com",
                   "help.openai.com", "chatgpt.com")
FIELDS = ("provider", "title", "url", "as_of", "note", "source")
REQUIRED = ("provider", "title", "url", "as_of")


def official_https(url):
    """True only for https://<allowed domain or subdomain>/... without credentials or an explicit port."""
    try:
        u = urlsplit(str(url).strip())
        port = u.port
    except ValueError:
        return False
    host = (u.hostname or "").lower().rstrip(".")
    if u.scheme != "https" or not host or u.username or u.password or port not in (None, 443):
        return False
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def norm_url(url):
    u = urlsplit(str(url).strip())
    path = u.path.rstrip("/") or "/"
    return urlunsplit(("https", (u.hostname or "").lower().rstrip("."), path, u.query, ""))


def validate(entry):
    """-> (clean entry, None) or (None, reason)."""
    if not isinstance(entry, dict):
        return None, "not an object"
    e = {k: (entry.get(k) if entry.get(k) is not None else "") for k in FIELDS}
    for k in FIELDS:
        if not isinstance(e[k], str):
            return None, f"{k} is not a string"
        e[k] = e[k].strip()
    for k in REQUIRED:
        if not e[k]:
            return None, f"missing {k}"
    if not official_https(e["url"]):
        return None, "url is not https on an official domain"
    if e["source"] and not official_https(e["source"]):
        return None, "source is not https on an official domain"
    try:
        dt.date.fromisoformat(e["as_of"][:10])
    except ValueError:
        return None, "as_of is not an ISO date (YYYY-MM-DD)"
    if len(e["title"]) > 200 or len(e["note"]) > 500:
        return None, "title/note too long"
    return e, None


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return []
    if not isinstance(d, list):
        raise ValueError(f"{path} is not a JSON list")
    return d


def write_atomic(data, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".offers.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge(candidates, path=OFFERS, now=None, dry_run=False):
    """Validate candidates, append the new ones to the file. Returns {"added", "duplicates", "rejected"}."""
    if isinstance(candidates, dict):
        candidates = [candidates]
    existing = load(path)
    seen = {norm_url(x["url"]) for x in existing if isinstance(x, dict) and x.get("url")}
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = {"added": [], "duplicates": [], "rejected": []}
    for c in candidates if isinstance(candidates, list) else []:
        e, why = validate(c)
        if why:
            res["rejected"].append({"entry": c, "reason": why})
            continue
        key = norm_url(e["url"])
        if key in seen:
            res["duplicates"].append(e)
            continue
        seen.add(key)
        e["added_at"] = stamp
        res["added"].append(e)
    if res["added"] and not dry_run:
        write_atomic(existing + res["added"], path)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("candidates")
    ap.add_argument("--file", default=OFFERS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        raw = sys.stdin.read() if a.candidates == "-" else open(a.candidates, encoding="utf-8").read()
        cand = json.loads(raw)
    except (OSError, ValueError) as ex:
        print(json.dumps({"error": str(ex)}))
        return 2
    print(json.dumps(merge(cand, a.file, dry_run=a.dry_run), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
