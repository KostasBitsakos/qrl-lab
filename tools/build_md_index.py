#!/usr/bin/env python3
"""Build docs/INDEX.md: one line per Markdown file (path, title, one-line description, size, date). No LLM.

Agents never read the index whole: they search it, e.g.  grep -i "reward" docs/INDEX.md
Usage:
  python3 tools/build_md_index.py              rebuild now
  python3 tools/build_md_index.py --if-stale   rebuild only if a .md file changed (the dispatcher calls this)
Extra read-only roots (e.g. ~/simulations): one path per line in docs/index_roots.txt.
Also mirrors Claude Code's auto-memory notes for this project into docs/claude-memory/ (copy only, never deletes),
so Codex can read what Claude remembered.
Descriptions: a `description:` line in YAML front matter wins; otherwise the first line of prose.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys

SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", ".lab", "__pycache__", ".mypy_cache", ".pytest_cache",
             ".ipynb_checkpoints", "site-packages", "dist", "build", ".tox", ".cache"}
# .lab subfolders that hold durable knowledge (M-20261028-006); .lab/outbox, tmp, backups stay out
LAB_KEEP = {"tuning", "council", "codex-handoff"}
OUT_MD = os.path.join("docs", "INDEX.md")
OUT_JSON = os.path.join("docs", "index.json")
DESC_LEN = 140


def _strip_md(s):
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[`*_>#]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def describe(path, max_bytes=20000):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(max_bytes)
    except OSError:
        return None, None, 0
    lines = text.splitlines()
    title = desc = None
    i = 0
    if lines and lines[0].strip() == "---":  # YAML front matter
        for j in range(1, min(len(lines), 60)):
            ln = lines[j]
            if ln.strip() == "---":
                i = j + 1
                break
            m = re.match(r"\s*(title|name|description)\s*:\s*(.+)", ln)
            if m:
                val = m.group(2).strip().strip("'\"")
                if m.group(1) == "description":
                    desc = val
                elif not title:
                    title = val
    in_code = in_comment = False
    for ln in lines[i:]:
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if s.startswith("<!--"):
            in_comment = "-->" not in s
            continue
        if in_comment:
            in_comment = "-->" not in s
            continue
        if not s or s.startswith("|") or s == "---":
            continue
        if s.startswith("#"):
            if not title:
                title = _strip_md(s)
            continue
        if not desc:
            desc = _strip_md(re.sub(r"^([-*+]|\d+\.)\s+", "", s))
        if title and desc:
            break
    try:
        with open(path, "rb") as f:
            n_lines = sum(1 for _ in f)
    except OSError:
        n_lines = 0
    if desc and len(desc) > DESC_LEN:
        desc = desc[:DESC_LEN - 1].rstrip() + "…"
    return title, desc, n_lines


def extra_roots(root):
    p = os.path.join(root, "docs", "index_roots.txt")
    out = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    out.append(os.path.abspath(os.path.expanduser(ln)))
    return [r for r in out if os.path.isdir(r)]


def iter_md(base):
    for dirpath, dirnames, filenames in os.walk(base):
        rel = os.path.relpath(dirpath, base)
        if rel == ".lab":  # only curated knowledge folders of .lab (results, councils, handoffs), not drafts
            dirnames[:] = sorted(d for d in dirnames if d in LAB_KEEP)
            continue
        if rel.split(os.sep)[0] == ".lab":
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        else:
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
                                 or d in (".claude", ".agents") or (rel == "." and d == ".lab"))
        for fn in sorted(filenames):
            if fn.lower().endswith(".md"):
                yield os.path.join(dirpath, fn)


def mirror_claude_memory(root):
    slug = os.path.abspath(root).replace(os.sep, "-")
    src = os.path.join(os.path.expanduser("~"), ".claude", "projects", slug, "memory")
    if not os.path.isdir(src):
        return 0
    dst = os.path.join(root, "docs", "claude-memory")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for fn in os.listdir(src):
        if not fn.endswith(".md"):
            continue
        a, b = os.path.join(src, fn), os.path.join(dst, fn)
        try:
            with open(a, "rb") as fa:
                data = fa.read()
            if os.path.exists(b):
                with open(b, "rb") as fb:
                    if fb.read() == data:
                        continue
            shutil.copyfile(a, b)
            n += 1
        except OSError:
            continue
    return n


def collect(root):
    root = os.path.abspath(root)
    entries = []
    skip = {os.path.join(root, OUT_MD)}
    bases = [(root, "")] + [(r, r) for r in extra_roots(root)]
    for base, label in bases:
        for p in iter_md(base):
            if p in skip:
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            rel = os.path.relpath(p, root) if not label else p.replace(os.path.expanduser("~"), "~", 1)
            title, desc, n = describe(p)
            entries.append({"path": rel, "title": title or os.path.basename(p), "description": desc or "",
                            "lines": n, "mtime": st.st_mtime, "external": bool(label)})
    return entries


def render(entries, root):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    by_dir = {}
    for e in entries:
        d = os.path.dirname(e["path"]) or "."
        by_dir.setdefault(d, []).append(e)
    out = ["# INDEX — all Markdown files",
           "",
           f"<!-- Generated by tools/build_md_index.py at {now}. Do not edit by hand. -->",
           f"{len(entries)} files in {len(by_dir)} folders. **Search it, do not read it whole:** "
           "`grep -i \"<topic>\" docs/INDEX.md`. Start every task from `docs/STATE.md`.",
           "",
           "## Recently changed",
           ""]
    for e in sorted(entries, key=lambda e: -e["mtime"])[:20]:
        out.append(f"- `{e['path']}` — {dt.datetime.fromtimestamp(e['mtime']).strftime('%Y-%m-%d %H:%M')}")
    out += ["", "## By folder", ""]
    for d in sorted(by_dir, key=lambda x: (x.startswith("~") or x.startswith("/"), x)):
        files = sorted(by_dir[d], key=lambda e: e["path"])
        out.append(f"### {d}/ ({len(files)})")
        for e in files:
            desc = f" — {e['description']}" if e["description"] else ""
            day = dt.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d")
            out.append(f"- `{e['path']}` — **{e['title']}**{desc} · {e['lines']}l · {day}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def build(root):
    root = os.path.abspath(root)
    mirror_claude_memory(root)
    entries = collect(root)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    tmp = os.path.join(root, OUT_MD + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(entries, root))
    os.replace(tmp, os.path.join(root, OUT_MD))
    with open(os.path.join(root, OUT_JSON), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=0)
    return len(entries)


def is_stale(root):
    root = os.path.abspath(root)
    idx = os.path.join(root, OUT_JSON)
    if not os.path.exists(idx) or not os.path.exists(os.path.join(root, OUT_MD)):
        return True
    t = os.path.getmtime(idx)
    try:
        with open(idx, encoding="utf-8") as f:
            known = len(json.load(f))
    except (OSError, ValueError):
        return True
    n = 0
    for base in [root] + extra_roots(root):
        for p in iter_md(base):
            if p == os.path.join(root, OUT_MD):
                continue
            n += 1
            try:
                if os.path.getmtime(p) > t:
                    return True
            except OSError:
                return True
    return n != known


def build_if_stale(root):
    mirror_claude_memory(root)
    if is_stale(root):
        return build(root)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build docs/INDEX.md")
    ap.add_argument("--root", default=os.environ.get("QRL_LAB_DIR") or os.getcwd())
    ap.add_argument("--if-stale", action="store_true")
    a = ap.parse_args(argv)
    n = build_if_stale(a.root) if a.if_stale else build(a.root)
    print("up to date" if n is None else f"indexed {n} files -> {OUT_MD}")


if __name__ == "__main__":
    sys.exit(main())
