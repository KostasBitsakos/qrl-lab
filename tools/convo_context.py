#!/usr/bin/env python3
"""Bounded memory for the conversant: facts relevant to a researcher message, from the knowledge tree
(docs/index.json), DECISIONS / researcher_requirements lines, lab requests and earlier researcher messages.

  python3 tools/convo_context.py "text of the message" [--max-chars 1800]

Read-only. Matching is accent-insensitive with 5-letter prefixes (Greek inflections). Output is a short list of
one-line pointers, never file contents; follow a pointer with `labq.py show/request` or by reading the file."""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STOP = set("""και την του των της τον στο στη στην στον που για απο ειναι οτι θελω μου σου εσεις εχετε ειχατε
με να δεν θα ενα μια αυτο αυτα ωστε οπως πως the and for that with from this have been will not are was were you your
our what when where which into about there their them then than also""".split())
SOURCE_FILES = ["docs/DECISIONS.md", "docs/researcher_requirements.md"]


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").casefold()) if unicodedata.category(c) != "Mn")


def keys(text):
    """Set of prefix keys (<=5 chars) of the informative words in `text`."""
    return {w[:5] for w in re.findall(r"[a-zα-ω0-9_\-]{4,}", norm(text)) if w not in STOP}


def _clip(s, n):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1] + "…"


def candidates(root):
    """Yield (group, pointer, text) from every source; a failing source never blocks the others."""
    try:
        with open(os.path.join(root, "docs", "index.json"), encoding="utf-8") as f:
            data = json.load(f)
        for e in (data if isinstance(data, list) else data.get("files", [])):
            yield "tree", e["path"], f"{e['path']} {e.get('title', '')} {e.get('description', '')}"
    except Exception:
        pass
    for rel in SOURCE_FILES:
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if len(line.strip()) > 25:
                        yield rel, f"{rel}:{i}", line
        except Exception:
            pass
    try:
        from labdb import LabDB
        d = LabDB(os.path.join(root, ".lab", "lab.db"))
        for r in d.requests(limit=3000):
            yield "request", f"labq.py request {r['id']}", \
                f"{r['title']} {r.get('decision_text') or ''} {(r.get('body') or '')[:400]}"
        for r in d.conn.execute("SELECT id, title, body FROM messages WHERE author='researcher' "
                                "ORDER BY ts DESC LIMIT 600"):
            yield "message", f"labq.py show {r['id']}", f"{r['title'] or ''} {r['body'] or ''}"
    except Exception:
        pass


def relevant(text, root, max_chars=1800, min_score=2, per_group=3):
    qk = keys(text)
    if not qk:
        return ""
    groups = {}
    for grp, ptr, body in candidates(root):
        sc = len(qk & keys(body))
        if sc >= min_score:
            groups.setdefault(grp, []).append((sc, ptr, body))
    lines = []
    for g in groups.values():
        g.sort(key=lambda t: -t[0])
        lines += [(sc, f"- {ptr} — {_clip(body, 190)}") for sc, ptr, body in g[:per_group]]
    lines.sort(key=lambda t: -t[0])
    out, used = [], 0
    for _, ln in lines:
        if used + len(ln) + 1 > max_chars:
            break
        out.append(ln)
        used += len(ln) + 1
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("text")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--max-chars", type=int, default=1800)
    a = ap.parse_args(argv)
    print(relevant(a.text, a.root, a.max_chars) or "(no relevant memory found)")


if __name__ == "__main__":
    main()
