#!/usr/bin/env python3
"""Duplicate check before appending to a shared md file (DECISIONS, STATE, researcher_requirements, rules).

  python3 tools/md_dedupe.py check  <file.md> "new entry text"     exit 1 and print the similar lines if any
  python3 tools/md_dedupe.py append <file.md> "new entry text"     append only when no similar line exists
  python3 tools/md_dedupe.py append <file.md> "text" --replace N   replace line N (update instead of duplicating)

A line is similar when it shares an M-/R-/J-/C- id with the new text, or when the word overlap (accent-insensitive
5-letter prefixes) is >= --threshold of the smaller side (default 0.6). Read the printed lines, then update the
existing entry (--replace) rather than adding a second one."""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convo_context import keys  # noqa: E402

ID_RE = re.compile(r"\b[MRJC]-\d{8}-\d{3}\b|\b[JC]\d{2,4}\b")


def similar(lines, new, threshold=0.6, min_words=4):
    nk, nids = keys(new), set(ID_RE.findall(new))
    hits = []
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        ids = set(ID_RE.findall(line))
        lk = keys(line)
        small = min(len(nk), len(lk))
        ov = len(nk & lk) / small if small >= min_words else 0.0
        shared_id = bool(nids & ids) and len(nk & lk) >= 2
        if ov >= threshold or shared_id:
            hits.append((i, line.rstrip("\n"), round(ov, 2)))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["check", "append"])
    ap.add_argument("file")
    ap.add_argument("text")
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--replace", type=int, help="line number to replace with the new text")
    a = ap.parse_args(argv)
    with open(a.file, encoding="utf-8") as f:
        lines = f.read().split("\n")
    hits = similar(lines, a.text, a.threshold)
    if a.mode == "check" or (hits and a.replace is None):
        for i, line, ov in hits:
            print(f"{a.file}:{i} (overlap {ov}): {line[:200]}")
        if hits:
            print("SIMILAR: update the existing line (append --replace N) instead of duplicating.", file=sys.stderr)
            return 1
        print("OK: no similar line")
        return 0
    if a.replace is not None:
        if not 1 <= a.replace <= len(lines):
            print("bad line number", file=sys.stderr)
            return 2
        lines[a.replace - 1] = a.text
        print(f"replaced {a.file}:{a.replace}")
    else:
        while lines and lines[-1] == "":
            lines.pop()
        lines.append(a.text)
        print(f"appended to {a.file}")
    with open(a.file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
