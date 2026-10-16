"""Read-only file browser logic for the dashboard (pure functions, no Streamlit).

Security model:
- every path is resolved with realpath and must lie inside an allowed root (symlinks that escape are refused);
- a deny list blocks credentials and key material even inside the roots (checked on the given path AND the real path);
- nothing here writes, renames, deletes or executes anything.
"""
import collections
import csv
import fnmatch
import hashlib
import os
import re
import urllib.parse

HOME = os.path.expanduser("~")
ROOTS = [os.path.join(HOME, d) for d in ("qrl-lab", "simulations", "redis", "k8s", "prometheus-grafana")]

DENY_DIRS = {".ssh", ".kube", ".codex", ".aws", ".gnupg"}
DENY_SEQ = [(".config", "gh")]  # directory pairs, e.g. ~/.config/gh
DENY_NAMES = [".env*", "*credentials*", "*secret*", "*token*", "auth.json", "id_rsa*", "*.pem", "*.key", "kubeconfig"]
DENIED_MSG = "Μη επιτρεπτό αρχείο"

TEXT_EXT = {".py", ".sh", ".yaml", ".yml", ".json", ".jsonl", ".md", ".txt", ".log", ".toml", ".cfg", ".ini", ".tex",
            ".bib", ".js", ".ts", ".html", ".css", ".sql", ".ipynb", ".out", ".err", ".conf", ".env.example", ".dockerfile"}
LANG = {".py": "python", ".sh": "bash", ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".jsonl": "json",
        ".md": "markdown", ".toml": "toml", ".tex": "latex", ".js": "javascript", ".ts": "typescript",
        ".html": "html", ".css": "css", ".sql": "sql", ".ini": "ini", ".cfg": "ini"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".gif"}
MAX_LINES, TAIL_LINES, CSV_ROWS = 2000, 500, 500
PDF_EMBED_MAX, DOWNLOAD_MAX = 20 * 2**20, 200 * 2**20


class FileViewError(Exception):
    pass


def expand(p):
    p = (p or "").strip()
    if p == "~" or p.startswith("~/"):
        p = HOME + p[1:]
    return p


def _under(real, roots):
    for r in roots:
        rr = os.path.realpath(r)
        if real == rr or real.startswith(rr + os.sep):
            return True
    return False


def is_denied(path):
    """True if any component or the file name matches the deny list. Case-insensitive."""
    parts = [x for x in path.replace("\\", "/").split("/") if x]
    low = [x.lower() for x in parts]
    if any(x in DENY_DIRS for x in low):
        return True
    for a, b in DENY_SEQ:
        if any(low[i] == a and low[i + 1] == b for i in range(len(low) - 1)):
            return True
    if not low:
        return False
    for comp in low:
        if any(fnmatch.fnmatch(comp, pat) for pat in DENY_NAMES):
            return True
    return False


def resolve(path, roots=None):
    """Return the real path, or raise FileViewError('outside'|'denied'|'missing')."""
    roots = roots or ROOTS
    p = expand(path)
    if not p or "\x00" in p:
        raise FileViewError("outside")
    if not os.path.isabs(p):
        raise FileViewError("outside")
    given = os.path.normpath(p)
    real = os.path.realpath(p)
    if not _under(real, roots):
        raise FileViewError("outside")
    if is_denied(given) or is_denied(real):
        raise FileViewError("denied")
    if not os.path.exists(real):
        raise FileViewError("missing")
    return real


def breadcrumbs(real, roots=None):
    """[(label, abs path)] from the allowed root down to real."""
    roots = [os.path.realpath(r) for r in (roots or ROOTS)]
    root = next((r for r in roots if real == r or real.startswith(r + os.sep)), None)
    if root is None:
        return []
    out = [(os.path.basename(root) or root, root)]
    cur = root
    rel = os.path.relpath(real, root)
    if rel != ".":
        for part in rel.split(os.sep):
            cur = os.path.join(cur, part)
            out.append((part, cur))
    return out


def list_dir(real, show_hidden=False, roots=None, newest_first=True):
    """Entries of a directory: dicts name, path, is_dir, size, mtime (ISO). Denied and escaping entries are omitted."""
    import datetime as dt
    roots = roots or ROOTS
    rows = []
    with os.scandir(real) as it:
        for e in it:
            if e.name.startswith(".") and not show_hidden:
                continue
            if is_denied(e.name):
                continue
            try:
                rp = os.path.realpath(e.path)
                if not _under(rp, roots) or is_denied(rp):
                    continue
                st = os.stat(rp)
            except OSError:
                continue
            isdir = os.path.isdir(rp)
            rows.append({"name": e.name, "path": os.path.join(real, e.name), "is_dir": isdir,
                         "size": None if isdir else st.st_size,
                         "mtime": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                         "icon": icon_for(e.name, isdir)})
    rows.sort(key=lambda r: r["mtime"], reverse=newest_first)
    return rows


def icon_for(name, is_dir):
    if is_dir:
        return "📁"
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXT:
        return "🖼️"
    if ext == ".pdf":
        return "📕"
    if ext == ".csv":
        return "📊"
    if ext in TEXT_EXT:
        return "📄"
    return "📦"


def kind_of(real):
    ext = os.path.splitext(real)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext == ".csv":
        return "csv"
    if ext in TEXT_EXT:
        return "text"
    try:
        with open(real, "rb") as f:
            chunk = f.read(4096)
    except OSError:
        return "binary"
    return "binary" if b"\x00" in chunk else "text"


def read_text(real, tail=False, max_lines=MAX_LINES, tail_lines=TAIL_LINES):
    """(lines, total_or_None, truncated). Head mode: first max_lines. Tail mode: last tail_lines (reads the last 8 MB)."""
    if tail:
        size = os.path.getsize(real)
        with open(real, "rb") as f:
            f.seek(max(0, size - 8 * 2**20))
            data = f.read().decode("utf-8", "replace").splitlines()
        return data[-tail_lines:], None, True
    out = []
    truncated = False
    with open(real, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                truncated = True
                break
            out.append(line.rstrip("\n"))
    return out, (None if truncated else len(out)), truncated


def read_csv(real, max_rows=CSV_ROWS):
    """(header, rows, truncated): header is the first row, rows at most max_rows data rows (strings)."""
    with open(real, "r", encoding="utf-8", errors="replace", newline="") as f:
        rd = csv.reader(f)
        header = next(rd, [])
        rows, truncated = [], False
        for row in rd:
            if len(rows) >= max_rows:
                truncated = True
                break
            rows.append(row)
    return header, rows, truncated


def sha256(real):
    h = hashlib.sha256()
    with open(real, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- chat paths -> deep links
_PATH_RE = re.compile(r"(?<![\w/~.:=-])(`?)((?:~|/)[^\s`<>\[\]()\"']*)(`?)")
_TRAIL = ".,;:!?)]}'\""


def split_ref(token):
    """'~/a/b.py:5.' -> ('~/a/b.py', 5). Strips trailing punctuation and a :line (or :line:col) suffix."""
    t = token.rstrip(_TRAIL)
    line = None
    m = re.search(r":(\d+)(?::\d+)?$", t)
    if m:
        line = int(m.group(1))
        t = t[:m.start()]
    return t.rstrip(_TRAIL), line


def deep_link(path, line=None):
    q = "?path=" + urllib.parse.quote(path, safe="/")
    if line:
        q += f"&line={line}"
    return q


def linkify(text, roots=None):
    """Render-time transform: wrap paths under the allowed roots as markdown links to ?path=. Stored text is unchanged.
    Fenced code blocks are left alone."""
    roots = roots or ROOTS

    def repl(m):
        tok = m.group(2)
        if len(tok) < 2:
            return m.group(0)
        path, line = split_ref(tok)
        full = os.path.normpath(expand(path))
        if not os.path.isabs(full) or not _under(os.path.realpath(full), roots) or is_denied(full):
            return m.group(0)
        label_end = tok.rstrip(_TRAIL)
        label = label_end
        tail = tok[len(label_end):]
        if m.group(1) and m.group(3):
            tail = tail.rstrip("`")
        return f"[{label}]({deep_link(full, line)}){tail}"

    parts = re.split(r"(```.*?```)", text, flags=re.S)
    return "".join(p if p.startswith("```") else _PATH_RE.sub(repl, p) for p in parts)
